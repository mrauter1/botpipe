"""Thin generic workflow runner for the filesystem runtime."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Literal

from pydantic import BaseModel, ValidationError

from botlane.policy import PolicyInput
from botlane.core.artifacts import resolve_artifact_template
from botlane.core.compiler import CompiledArtifact, CompiledWorkflow, compile_workflow
from botlane.core.context import ChildWorkflowResult, _DEFAULT_MESSAGE
from botlane.core.engine import Engine, RunResult, StepFinalizationRecord
from botlane.core.errors import WorkflowExecutionError
from botlane.core.mappings import normalize_mapping
from botlane.core.primitives import AWAIT_INPUT, FINISH
from botlane.core.providers.models import RuntimeInteractionPolicy
from botlane.core.providers.protocols import LLMProvider
from botlane.core.schema_registry import RUN_METADATA_SCHEMA, WORKFLOW_TOPOLOGY_SCHEMA, migrate_schemaless_payload, validate_persisted_schema
from botlane.core.statuses import terminal_to_run_status
from botlane.extensions.session_paths import extract_session_path_strategy
from .config import (
    ConfigError,
    DEFAULT_MAX_STEPS,
    ProviderConfig,
    ProviderPolicyRuntimeConfig,
    RuntimeConfig,
)
from .events import EventLogger
from .git_tracking import RuntimeGitTracker
from .loader import (
    WorkflowReference,
    coerce_workflow_parameter_mapping,
    inspect_workflow_reference,
    materialize_workflow_params,
    resolve_workflow_reference,
)
from .observability import BoundRuntimeObservability
from .prompts import FilesystemPromptRegistry
from .provider_policy_resolver import create_provider_policy_resolver
from .stores.filesystem import FilesystemCheckpointStore, FilesystemSessionStore
from .static_graph import (
    ARTIFACT_CONTRACTS_FILENAME,
    COMPILE_REPORT_FILENAME,
    PROMPT_REFS_FILENAME,
    ROUTE_TABLE_FILENAME,
    SESSION_CONTRACTS_FILENAME,
    STATE_CONTRACTS_FILENAME,
    STATIC_GRAPH_FILENAME,
    TOPOLOGY_FILENAME,
    TOPOLOGY_MERMAID_FILENAME,
    workflow_static_step_graph_payload,
)
from .tracing import RuntimeTraceWriter
from .workspace import (
    RunWorkspace,
    TaskWorkspace,
    WorkflowWorkspace,
    append_child_run_record,
    append_run_warning,
    create_run_id,
    create_run,
    ensure_workspace,
    ensure_workflow_workspace,
    latest_run_id,
    next_observability_sequence,
    resolve_run_workspace,
    write_parent_run_metadata,
    update_run_metadata,
    open_existing_run,
    legacy_state_root,
    resolve_task_workspace,
    resolve_workflow_workspace,
    resolve_run_workflow_input,
    resolve_run_workflow_params,
    resolve_resume_state_root,
    task_request_text,
)


@dataclass(frozen=True, slots=True)
class RunnerOptions:
    root: Path
    task_id: str
    run_id: str | None = None
    message: str | None | object = _DEFAULT_MESSAGE
    resume: bool = False
    answer: str | None = None
    state_dir: Path | None = None
    max_steps: int | None = None
    workflow_params: dict[str, Any] | None = None
    workflow_input: dict[str, Any] | None = None
    parent_run: RunWorkspace | None = None
    record_task_message: bool = True
    runtime_config: RuntimeConfig = field(default_factory=RuntimeConfig)
    provider_policy_config: ProviderPolicyRuntimeConfig = field(default_factory=ProviderPolicyRuntimeConfig)
    sdk_default_policy: PolicyInput = None
    run_policy: PolicyInput = None


@dataclass(frozen=True, slots=True)
class PreparedRunContext:
    """Resolved generic runtime context for one run."""

    compiled: CompiledWorkflow
    task_workspace: TaskWorkspace
    workflow_workspace: WorkflowWorkspace
    run_workspace: RunWorkspace
    session_store: FilesystemSessionStore
    checkpoint_store: FilesystemCheckpointStore
    prompt_registry: FilesystemPromptRegistry
    logger: EventLogger


@dataclass(frozen=True, slots=True)
class PlannedRunContext:
    """Resolved run paths before any workspace mutation."""

    task_workspace: TaskWorkspace
    workflow_workspace: WorkflowWorkspace
    run_workspace: RunWorkspace


@dataclass(frozen=True, slots=True)
class RunExecution:
    """Execution result plus resolved runtime metadata for CLI summaries."""

    result: RunResult
    compiled: CompiledWorkflow
    task_workspace: TaskWorkspace
    workflow_workspace: WorkflowWorkspace
    run_workspace: RunWorkspace
    workflow_params: dict[str, Any]
    workflow_input: BaseModel | None


def run_workflow_package(
    workflow_reference: str | type[Any],
    *,
    provider: LLMProvider,
    options: RunnerOptions,
) -> RunResult:
    return execute_workflow_package(workflow_reference, provider=provider, options=options).result


def execute_workflow_package(
    workflow_reference: str | type[Any],
    *,
    provider: LLMProvider,
    options: RunnerOptions,
) -> RunExecution:
    resolved = resolve_workflow_reference(options.root, workflow_reference)
    compiled = compile_workflow(resolved.workflow_cls)
    capability = inspect_workflow_reference(options.root, resolved.workflow_cls)
    execution_options = _normalize_execution_options(options, parameters_cls=resolved.parameters_cls)
    return _execute_compiled_workflow(
        compiled,
        reference=resolved.reference,
        parameters_cls=resolved.parameters_cls,
        capability_prompt_paths=capability.prompt_paths,
        provider=provider,
        options=execution_options,
    )


def _execute_compiled_workflow(
    compiled: CompiledWorkflow,
    *,
    reference: WorkflowReference,
    parameters_cls: type[Any] | None,
    capability_prompt_paths: tuple[Path, ...] = (),
    provider: LLMProvider,
    options: RunnerOptions,
) -> RunExecution:
    max_steps = resolve_max_steps(options.max_steps)
    planned = _plan_workspaces(compiled, options, reference=reference)
    git_tracker = RuntimeGitTracker(
        root=options.root,
        run_dir=None,
        workflow_name=compiled.workflow_name,
        task_id=options.task_id,
        run_id=planned.run_workspace.run_id,
        config=options.runtime_config.git_tracking,
    )
    git_tracker.prepare_before_workspace_creation()
    task_workspace, workflow_workspace, run_workspace = _prepare_workspaces(
        compiled,
        options,
        reference=reference,
        planned=planned,
    )
    effective_compiled, workflow_git_tracking_warnings = _runtime_compiled_workflow(compiled)
    session_path_strategy = resolve_session_path_strategy(effective_compiled)
    prepared = prepare_runtime_services(
        effective_compiled,
        task_workspace=task_workspace,
        workflow_workspace=workflow_workspace,
        run_workspace=run_workspace,
        session_path_strategy=session_path_strategy,
        capability_prompt_paths=capability_prompt_paths,
    )
    resume_git_tracking_warnings = _resume_git_tracking_warnings(prepared.run_workspace, options)
    resolved_workflow_params = resolve_run_workflow_params(prepared.run_workspace, options.workflow_params)
    resolved_params = materialize_workflow_params(parameters_cls, resolved_workflow_params)
    resolved_workflow_input_payload = resolve_run_workflow_input(prepared.run_workspace, options.workflow_input)
    resolved_workflow_input = _materialize_workflow_input(effective_compiled, resolved_workflow_input_payload)
    if options.parent_run is not None:
        write_parent_run_metadata(prepared.run_workspace, options.parent_run)
    update_run_metadata(
        prepared.run_workspace,
        workflow_params=resolved_workflow_params,
        workflow_input=resolved_workflow_input_payload,
        status="running",
        pending_input=None,
        finalization=None,
    )
    if options.resume:
        resume_warning = _resume_topology_mismatch_warning(
            prepared.run_workspace,
            prepared.compiled,
            behavior=options.runtime_config.resume_topology_mismatch_behavior,
        )
        if resume_warning is not None:
            append_run_warning(prepared.run_workspace.run_dir, resume_warning)
            prepared.logger.emit(
                resume_warning["event_type"],
                workflow=prepared.compiled.workflow_name,
                task_id=prepared.task_workspace.task_id,
                message=resume_warning["message"],
            )
    trace_writer = RuntimeTraceWriter(
        run_dir=prepared.run_workspace.run_dir,
        workflow_name=prepared.compiled.workflow_name,
        task_id=prepared.task_workspace.task_id,
        run_id=prepared.run_workspace.run_id,
        config=options.runtime_config.tracing,
        static_step_graph=workflow_static_step_graph_payload(prepared.compiled),
        compiled_workflow=prepared.compiled,
    )
    update_run_metadata(
        prepared.run_workspace,
        topology=_run_topology_metadata(prepared.run_workspace, prepared.compiled),
    )
    git_tracker.bind_run_dir(prepared.run_workspace.run_dir)
    for warning in resume_git_tracking_warnings:
        append_run_warning(prepared.run_workspace.run_dir, warning)
    for warning in workflow_git_tracking_warnings:
        append_run_warning(prepared.run_workspace.run_dir, warning)
        prepared.logger.emit(
            warning["event_type"],
            workflow=prepared.compiled.workflow_name,
            task_id=prepared.task_workspace.task_id,
            message=warning["message"],
        )
    git_tracker.commit_run_initialized()
    runtime_observability = BoundRuntimeObservability(
        git_tracker=git_tracker,
        trace_writer=trace_writer,
        initial_sequence=next_observability_sequence(prepared.run_workspace.run_dir),
    )

    def emit_hook_event(event_type: str, payload: Mapping[str, Any]) -> None:
        prepared.logger.emit(event_type, **payload)
        trace_writer.runtime_event(event_type=event_type, **payload)

    def emit_runtime_event(event_type: str, payload: Mapping[str, Any]) -> None:
        prepared.logger.emit(event_type, **payload)
        trace_writer.runtime_event(event_type=event_type, **payload)

    provider_policy_resolver = create_provider_policy_resolver(
        sdk_default_policy=options.sdk_default_policy,
        workflow_policy=prepared.compiled.provider_policy,
        run_policy=options.run_policy,
        workspace_root=prepared.task_workspace.root,
        provider_policy=options.provider_policy_config,
        runtime=options.runtime_config,
        provider=ProviderConfig(),
    )
    engine = Engine(
        prepared.compiled,
        provider=provider,
        session_store=prepared.session_store,
        checkpoint_store=prepared.checkpoint_store,
        prompt_registry=prepared.prompt_registry,
        operation_replay_mismatch_behavior=options.runtime_config.replay_mismatch_behavior,
        interaction_policy=RuntimeInteractionPolicy(
            allow_provider_questions=not options.runtime_config.full_auto,
        ),
        runtime_extension_factories=(
            lambda binding: runtime_observability,
        ),
        hook_event_sink=emit_hook_event,
        runtime_event_sink=emit_runtime_event,
        provider_policy_resolver=provider_policy_resolver,
    )
    workflow_invoker = _build_workflow_invoker(
        provider=provider,
        options=options,
        task_workspace=prepared.task_workspace,
        workflow_workspace=prepared.workflow_workspace,
        run_workspace=prepared.run_workspace,
    )
    prepared.logger.emit(
        "run_resumed" if options.resume else "run_started",
        workflow=prepared.compiled.workflow_name,
        task_id=prepared.task_workspace.task_id,
    )
    try:
        if options.resume:
            result = engine.resume(
                task_id=prepared.task_workspace.task_id,
                run_id=prepared.run_workspace.run_id,
                task_folder=prepared.task_workspace.task_dir,
                workflow_folder=prepared.workflow_workspace.workflow_dir,
                run_folder=prepared.run_workspace.run_dir,
                package_folder=prepared.workflow_workspace.package_dir,
                root=prepared.task_workspace.root,
                request_file=prepared.run_workspace.request_file,
                task_request_file=prepared.task_workspace.task_request_file,
                params=resolved_params,
                workflow_params=resolved_workflow_params,
                message=options.message,
                workflow_input=resolved_workflow_input,
                workflow_invoker=workflow_invoker,
                answer=options.answer,
                max_steps=max_steps,
            )
        else:
            result = engine.run(
                task_id=prepared.task_workspace.task_id,
                run_id=prepared.run_workspace.run_id,
                task_folder=prepared.task_workspace.task_dir,
                workflow_folder=prepared.workflow_workspace.workflow_dir,
                run_folder=prepared.run_workspace.run_dir,
                package_folder=prepared.workflow_workspace.package_dir,
                root=prepared.task_workspace.root,
                request_file=prepared.run_workspace.request_file,
                task_request_file=prepared.task_workspace.task_request_file,
                params=resolved_params,
                workflow_params=resolved_workflow_params,
                message=options.message,
                workflow_input=resolved_workflow_input,
                workflow_invoker=workflow_invoker,
                max_steps=max_steps,
            )

        for step_name in result.history:
            prepared.logger.emit("step_executed", workflow=prepared.compiled.workflow_name, step_name=step_name)

        prepared.logger.emit(
            "run_finished",
            workflow=prepared.compiled.workflow_name,
            terminal=result.terminal,
            status=_run_status(result.terminal, result.last_event),
            last_step=result.history[-1] if result.history else None,
        )
        update_run_metadata(
            prepared.run_workspace,
            workflow_params=resolved_workflow_params,
            workflow_input=resolved_workflow_input_payload,
            status=_run_status(result.terminal, result.last_event),
            terminal=result.terminal,
            pending_input=_pending_input_metadata(result.checkpoint),
            finalization=_last_transition_payload(result.last_transition),
        )
        _ensure_default_session_binding(prepared)
        child_metadata = _typed_output_metadata(execution_result=result, compiled=prepared.compiled)
        _persist_child_runtime_metadata(prepared.run_workspace, child_metadata)
        runtime_observability.commit_terminal(terminal=result.terminal)
        execution = RunExecution(
            result=result,
            compiled=prepared.compiled,
            task_workspace=prepared.task_workspace,
            workflow_workspace=prepared.workflow_workspace,
            run_workspace=prepared.run_workspace,
            workflow_params=resolved_workflow_params,
            workflow_input=resolved_workflow_input,
        )
        if options.parent_run is not None:
            append_child_run_record(options.parent_run, _child_run_record_payload(_build_child_workflow_result(execution)))
        return execution
    except Exception as exc:
        prepared.logger.emit(
            "run_finished",
            workflow=prepared.compiled.workflow_name,
            status="fatal_error",
            error_type=type(exc).__name__,
            error=str(exc),
        )
        update_run_metadata(
            prepared.run_workspace,
            workflow_params=resolved_workflow_params,
            workflow_input=resolved_workflow_input_payload,
            status="fatal_error",
            error=str(exc),
        )
        runtime_observability.commit_fatal(error=_runtime_observability_error(exc))
        if options.parent_run is not None:
            append_child_run_record(
                options.parent_run,
                _child_run_record_payload_from_parts(
                    workflow_name=prepared.compiled.workflow_name,
                    run_id=prepared.run_workspace.run_id,
                    terminal="fatal",
                    status="fatal_error",
                    event=None,
                    output_metadata={},
                    output_artifacts={},
                    task_folder=prepared.task_workspace.task_dir,
                    workflow_folder=prepared.workflow_workspace.workflow_dir,
                    run_folder=prepared.run_workspace.run_dir,
                    package_folder=prepared.workflow_workspace.package_dir,
                    request_file=prepared.run_workspace.request_file,
                    run_meta_file=prepared.run_workspace.run_meta_file,
                    events_file=prepared.run_workspace.events_file,
                    checkpoint_file=prepared.run_workspace.checkpoint_file,
                    sessions_dir=prepared.run_workspace.sessions_dir,
                    trace_file=prepared.run_workspace.trace_file,
                    raw_dir=prepared.run_workspace.raw_dir,
                    parent_file=prepared.run_workspace.parent_file,
                    error=str(exc),
                ),
            )
        raise


def prepare_runtime_services(
    compiled: CompiledWorkflow,
    *,
    task_workspace: TaskWorkspace,
    workflow_workspace: WorkflowWorkspace,
    run_workspace: RunWorkspace,
    session_path_strategy=None,
    capability_prompt_paths: tuple[Path, ...] = (),
) -> PreparedRunContext:
    workflow_parent = workflow_workspace.package_dir
    path_strategy = (
        resolve_session_path_strategy(compiled)
        if session_path_strategy is None
        else session_path_strategy
    )
    return PreparedRunContext(
        compiled=compiled,
        task_workspace=task_workspace,
        workflow_workspace=workflow_workspace,
        run_workspace=run_workspace,
        session_store=FilesystemSessionStore(
            task_folder=task_workspace.task_dir,
            workflow_folder=workflow_workspace.workflow_dir,
            run_folder=run_workspace.run_dir,
            path_strategy=path_strategy,
        ),
        checkpoint_store=FilesystemCheckpointStore(run_workspace.checkpoint_file, compiled.state_cls),
        prompt_registry=FilesystemPromptRegistry(
            *_prompt_registry_roots(
                workflow_parent,
                compiled=compiled,
                capability_prompt_paths=capability_prompt_paths,
            )
        ),
        logger=EventLogger(run_workspace.run_id, run_workspace.events_file),
    )


def _prompt_registry_roots(
    workflow_parent: Path,
    *,
    compiled: CompiledWorkflow,
    capability_prompt_paths: tuple[Path, ...] = (),
) -> tuple[Path, ...]:
    roots: list[Path] = [workflow_parent.resolve()]

    for prompt_path in capability_prompt_paths:
        resolved = prompt_path.resolve()
        roots.append(resolved.parent if resolved.is_file() else resolved)

    for step in compiled.steps.values():
        for prompt in (step.producer_prompt, step.verifier_prompt):
            if prompt is None:
                continue
            if isinstance(prompt, str):
                roots.append((workflow_parent / prompt).resolve().parent)
                continue
            if prompt.source == "inline":
                continue
            roots.append((workflow_parent / prompt.path).resolve().parent)

    return tuple(dict.fromkeys(roots))


def _ensure_default_session_binding(prepared: PreparedRunContext) -> None:
    if not prepared.compiled.default_session_name:
        return
    if prepared.session_store.snapshot().bindings:
        return
    prepared.session_store.open(prepared.compiled.default_session_name)


def _resolved_state_dir(options: RunnerOptions) -> Path | None:
    root = options.root.resolve()
    state_dir = options.state_dir
    if options.resume and state_dir is None:
        state_dir = resolve_resume_state_root(root)
    return state_dir


def _assert_workflow_identity_consistency(
    task_workspace: TaskWorkspace,
    workflow_name: str,
    reference: WorkflowReference,
) -> None:
    workflow_meta_file = task_workspace.task_dir / f"wf_{workflow_name}" / "workflow.json"
    if not workflow_meta_file.is_file():
        return
    payload = json.loads(workflow_meta_file.read_text(encoding="utf-8"))
    stored = payload.get("workflow")
    if not isinstance(stored, dict):
        return

    requested_source = None if reference.source_path is None else str(reference.source_path.resolve())
    requested_manifest = None if reference.manifest_path is None else str(reference.manifest_path.resolve())
    stored_source = stored.get("source_path")
    stored_manifest = stored.get("manifest_path")
    if isinstance(stored_source, str):
        stored_source = str((task_workspace.root / stored_source).resolve())
    if isinstance(stored_manifest, str):
        stored_manifest = str((task_workspace.root / stored_manifest).resolve())

    comparable_pairs = (
        ("source_path", stored_source, requested_source),
        ("manifest_path", stored_manifest, requested_manifest),
        ("class_name", stored.get("class_name"), reference.class_name),
        ("authoring_shape", stored.get("authoring_shape"), reference.authoring_shape),
        ("source_root_kind", stored.get("source_root_kind"), reference.source_root_kind),
        ("package_name", stored.get("package_name"), reference.package_name),
        ("package_module", stored.get("package_module"), reference.package_module),
        ("workflow_module", stored.get("workflow_module"), reference.workflow_module),
    )
    conflicts = [field for field, stored_value, requested_value in comparable_pairs if stored_value != requested_value]
    if conflicts:
        raise WorkflowExecutionError(
            f"workflow {workflow_name!r} for task {task_workspace.task_id!r} is already associated with a different "
            f"origin; conflicting fields: {', '.join(conflicts)}"
        )


def _ensure_workflow_workspace(
    compiled: CompiledWorkflow,
    task_workspace: TaskWorkspace,
    *,
    reference: WorkflowReference,
) -> WorkflowWorkspace:
    _assert_workflow_identity_consistency(task_workspace, compiled.workflow_name, reference)
    return ensure_workflow_workspace(
        task_workspace,
        compiled.workflow_name,
        package_dir=reference.package_dir,
        reference=reference.original,
        source_path=reference.source_path,
        manifest_path=reference.manifest_path,
        module_name=reference.module_name,
        class_name=reference.class_name,
        authoring_shape=reference.authoring_shape,
        source_root_kind=reference.source_root_kind,
        source_root=reference.source_root,
        package_name=reference.package_name,
        package_module=reference.package_module,
        workflow_module=reference.workflow_module,
    )


def _prepare_workspaces(
    compiled: CompiledWorkflow,
    options: RunnerOptions,
    *,
    reference: WorkflowReference,
    planned: PlannedRunContext,
) -> tuple[TaskWorkspace, WorkflowWorkspace, RunWorkspace]:
    explicit_message = None if options.message is _DEFAULT_MESSAGE else options.message
    task_workspace = ensure_workspace(
        planned.task_workspace.root,
        planned.task_workspace.task_id,
        message=explicit_message,
        record_message=options.record_task_message,
        state_dir=planned.task_workspace.state_root,
    )
    workflow_workspace = _ensure_workflow_workspace(compiled, task_workspace, reference=reference)
    if not options.resume:
        run_workspace = create_run(
            workflow_workspace,
            run_id=planned.run_workspace.run_id,
            message=(
                task_request_text(task_workspace.task_request_file)
                if options.record_task_message
                else explicit_message or task_request_text(task_workspace.task_request_file)
            ),
            workflow_params=options.workflow_params,
            workflow_input=options.workflow_input,
        )
        return task_workspace, workflow_workspace, run_workspace

    return task_workspace, workflow_workspace, open_existing_run(workflow_workspace, planned.run_workspace.run_id)


def _plan_workspaces(
    compiled: CompiledWorkflow,
    options: RunnerOptions,
    *,
    reference: WorkflowReference,
) -> PlannedRunContext:
    state_dir = _resolved_state_dir(options)
    task_workspace = resolve_task_workspace(options.root, options.task_id, state_dir=state_dir)
    workflow_workspace = resolve_workflow_workspace(
        task_workspace,
        compiled.workflow_name,
        package_dir=reference.package_dir,
        reference=reference.original,
        source_path=reference.source_path,
        manifest_path=reference.manifest_path,
        module_name=reference.module_name,
        class_name=reference.class_name,
        authoring_shape=reference.authoring_shape,
        source_root_kind=reference.source_root_kind,
        source_root=reference.source_root,
        package_name=reference.package_name,
        package_module=reference.package_module,
        workflow_module=reference.workflow_module,
    )
    if options.resume and options.state_dir is None and not _resume_run_available(workflow_workspace, options.run_id):
        fallback_state_dir = legacy_state_root(options.root.resolve())
        if fallback_state_dir != task_workspace.state_root:
            fallback_task_workspace = resolve_task_workspace(options.root, options.task_id, state_dir=fallback_state_dir)
            fallback_workflow_workspace = resolve_workflow_workspace(
                fallback_task_workspace,
                compiled.workflow_name,
                package_dir=reference.package_dir,
                reference=reference.original,
                source_path=reference.source_path,
                manifest_path=reference.manifest_path,
                module_name=reference.module_name,
                class_name=reference.class_name,
                authoring_shape=reference.authoring_shape,
                source_root_kind=reference.source_root_kind,
                source_root=reference.source_root,
                package_name=reference.package_name,
                package_module=reference.package_module,
                workflow_module=reference.workflow_module,
            )
            if _resume_run_available(fallback_workflow_workspace, options.run_id):
                task_workspace = fallback_task_workspace
                workflow_workspace = fallback_workflow_workspace
    _assert_workflow_identity_consistency(task_workspace, compiled.workflow_name, reference)
    if not options.resume:
        return PlannedRunContext(
            task_workspace=task_workspace,
            workflow_workspace=workflow_workspace,
            run_workspace=resolve_run_workspace(workflow_workspace, options.run_id or create_run_id()),
        )

    run_id = options.run_id or latest_run_id(workflow_workspace.runs_dir)
    if run_id is None:
        raise FileNotFoundError(f"no runs exist under {workflow_workspace.runs_dir}")
    run_workspace = resolve_run_workspace(workflow_workspace, run_id)
    validate_resume_state(run_workspace.run_dir)
    return PlannedRunContext(
        task_workspace=task_workspace,
        workflow_workspace=workflow_workspace,
        run_workspace=run_workspace,
    )


def resolve_max_steps(max_steps: int | None) -> int:
    if max_steps is None:
        return DEFAULT_MAX_STEPS
    if max_steps <= 0:
        raise ConfigError("max_steps must be a positive integer.")
    return max_steps


def _runtime_observability_error(exc: BaseException) -> BaseException:
    cause = exc.__cause__
    if isinstance(cause, BaseException):
        return cause
    return exc


def resolve_session_path_strategy(compiled: CompiledWorkflow):
    try:
        return extract_session_path_strategy(compiled.extensions)
    except ValueError as exc:
        raise WorkflowExecutionError(str(exc)) from exc


def validate_resume_state(run_dir: Path) -> None:
    if not run_dir.is_dir():
        raise FileNotFoundError(f"run {run_dir.name!r} does not exist under {run_dir.parent}")
    checkpoint_file = run_dir / "checkpoint.json"
    if checkpoint_file.exists():
        return
    sessions_dir = run_dir / "sessions"
    events_file = run_dir / "events.jsonl"
    has_session_files = any(sessions_dir.rglob("*.json"))
    has_event_history = events_file.exists() and events_file.stat().st_size > 0
    if has_session_files or has_event_history:
        raise WorkflowExecutionError(
            "resume requested for a run without checkpoint.json. "
            "This run only has persisted session or event state, which the generic runtime does not reconstruct into "
            "engine checkpoints. Resume it with the workflow-owned harness that created it or start a new run."
        )


def _resume_run_available(workflow_workspace: WorkflowWorkspace, run_id: str | None) -> bool:
    if not workflow_workspace.runs_dir.is_dir():
        return False
    if run_id is None:
        return latest_run_id(workflow_workspace.runs_dir) is not None
    return (workflow_workspace.runs_dir / run_id).is_dir()


def _resume_topology_mismatch_warning(
    run_workspace: RunWorkspace,
    compiled: CompiledWorkflow,
    *,
    behavior: Literal["warn", "fail"],
) -> dict[str, str] | None:
    saved_topology = _load_saved_run_topology_payload(run_workspace)
    if saved_topology is None:
        return None
    saved_source_hash = saved_topology.get("source_hash")
    saved_topology_hash = saved_topology.get("topology_hash")
    source_mismatch = isinstance(saved_source_hash, str) and bool(saved_source_hash) and saved_source_hash != compiled.source_hash
    topology_mismatch = (
        isinstance(saved_topology_hash, str)
        and bool(saved_topology_hash)
        and saved_topology_hash != compiled.topology_hash
    )
    if not source_mismatch and not topology_mismatch:
        return None
    message = (
        "resume is continuing with the current compiled workflow despite a saved-contract mismatch: "
        f"saved_source={saved_source_hash!r} current_source={compiled.source_hash!r} "
        f"saved_topology={saved_topology_hash!r} current_topology={compiled.topology_hash!r}"
    )
    if behavior == "fail":
        raise WorkflowExecutionError(message)
    return {
        "event_type": "runtime_resume_topology_mismatch",
        "message": message,
    }


def _load_saved_run_topology_payload(run_workspace: RunWorkspace) -> dict[str, Any] | None:
    topology_file = run_workspace.run_dir / TOPOLOGY_FILENAME
    if topology_file.is_file():
        payload = json.loads(topology_file.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise WorkflowExecutionError(f"{topology_file} must contain a JSON object")
        return _validate_saved_run_topology_payload(payload, artifact_name=str(topology_file))
    if run_workspace.run_meta_file.is_file():
        payload = _load_run_metadata_payload(run_workspace.run_meta_file)
        topology = payload.get("topology")
        if isinstance(topology, dict):
            return _validate_saved_run_topology_payload(
                topology,
                artifact_name=f"{run_workspace.run_meta_file}:topology",
            )
    return None


def _validate_saved_run_topology_payload(
    payload: dict[str, Any],
    *,
    artifact_name: str,
) -> dict[str, Any]:
    validate_persisted_schema(
        payload,
        expected=WORKFLOW_TOPOLOGY_SCHEMA,
        artifact_name=artifact_name,
        legacy_migrator=lambda value: migrate_schemaless_payload(value, expected=WORKFLOW_TOPOLOGY_SCHEMA),
    )
    return payload


def _run_topology_metadata(run_workspace: RunWorkspace, compiled: CompiledWorkflow) -> dict[str, Any]:
    return {
        "schema": WORKFLOW_TOPOLOGY_SCHEMA,
        "workflow_name": compiled.workflow_name,
        "entry": compiled.entry_step_name,
        "source_hash": compiled.source_hash,
        "topology_hash": compiled.topology_hash,
        "compiled_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": {
            "static_step_graph": STATIC_GRAPH_FILENAME,
            "topology": TOPOLOGY_FILENAME,
            "topology_mermaid": TOPOLOGY_MERMAID_FILENAME,
            "route_table": ROUTE_TABLE_FILENAME,
            "artifact_contracts": ARTIFACT_CONTRACTS_FILENAME,
            "prompt_refs": PROMPT_REFS_FILENAME,
            "state_contracts": STATE_CONTRACTS_FILENAME,
            "session_contracts": SESSION_CONTRACTS_FILENAME,
            "compile_report": COMPILE_REPORT_FILENAME,
        },
    }


def _runtime_compiled_workflow(compiled: CompiledWorkflow) -> tuple[CompiledWorkflow, tuple[dict[str, str], ...]]:
    return compiled, ()


def _resume_git_tracking_warnings(run_workspace: RunWorkspace, options: RunnerOptions) -> tuple[dict[str, str], ...]:
    if not options.resume or not run_workspace.run_meta_file.exists():
        return ()
    payload = _load_run_metadata_payload(run_workspace.run_meta_file)
    git_tracking = payload.get("git_tracking")
    if not isinstance(git_tracking, dict):
        return ()
    if git_tracking.get("enabled") is True and not options.runtime_config.git_tracking.enabled:
        return (
            {
                "event_type": "runtime_git_tracking_disabled_on_resume",
                "message": "Git tracking is disabled for this resumed segment even though an earlier segment recorded git tracking.",
            },
        )
    return ()


def _build_workflow_invoker(
    *,
    provider: LLMProvider,
    options: RunnerOptions,
    task_workspace: TaskWorkspace,
    workflow_workspace: WorkflowWorkspace,
    run_workspace: RunWorkspace,
) -> Callable[..., ChildWorkflowResult]:
    def invoke(
        workflow_reference: str | type[Any],
        *,
        message: str,
        parameters: dict[str, Any],
        input: BaseModel | dict[str, Any] | None = None,
    ) -> ChildWorkflowResult:
        resolved = resolve_workflow_reference(task_workspace.root, workflow_reference)
        compiled = compile_workflow(resolved.workflow_cls)
        child_workflow_params = coerce_workflow_parameter_mapping(resolved.parameters_cls, parameters)
        child_workflow_input = _coerce_workflow_input_payload(compiled, input)
        execution = _execute_child_workflow_package(
            resolved.workflow_cls,
            provider=provider,
            options=RunnerOptions(
                root=options.root,
                task_id=task_workspace.task_id,
                message=message,
                state_dir=options.state_dir,
                max_steps=options.max_steps,
                workflow_params=child_workflow_params,
                workflow_input=child_workflow_input,
                parent_run=run_workspace,
                record_task_message=False,
                runtime_config=options.runtime_config,
                provider_policy_config=options.provider_policy_config,
                sdk_default_policy=options.sdk_default_policy,
                run_policy=options.run_policy,
            ),
        )
        return _build_child_workflow_result(execution)

    return invoke


def _execute_child_workflow_package(
    workflow_reference: str | type[Any],
    *,
    provider: LLMProvider,
    options: RunnerOptions,
) -> RunExecution:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return execute_workflow_package(
            workflow_reference,
            provider=provider,
            options=options,
        )

    # Child workflow invocations may originate from synchronous Python-step handlers
    # that are already running inside the parent engine's event loop.
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="botlane-child-workflow") as executor:
        future = executor.submit(
            execute_workflow_package,
            workflow_reference,
            provider=provider,
            options=options,
        )
        return future.result()


def _normalize_execution_options(
    options: RunnerOptions,
    *,
    parameters_cls: type[Any] | None,
) -> RunnerOptions:
    normalized_params = options.workflow_params
    if not options.resume and options.workflow_params is not None:
        if parameters_cls is None:
            normalized_params = normalize_mapping(options.workflow_params)
        else:
            normalized_params = coerce_workflow_parameter_mapping(parameters_cls, options.workflow_params)

    normalized_input = options.workflow_input
    if not options.resume and options.workflow_input is not None:
        normalized_input = normalize_mapping(options.workflow_input)

    if normalized_params is options.workflow_params and normalized_input is options.workflow_input:
        return options
    return replace(options, workflow_params=normalized_params, workflow_input=normalized_input)


def _coerce_workflow_input_payload(
    compiled: CompiledWorkflow,
    raw_input: BaseModel | dict[str, Any] | None,
) -> dict[str, Any] | None:
    if raw_input is None:
        return None
    if compiled.input_model is None:
        raise WorkflowExecutionError(
            f"workflow {compiled.workflow_name!r} does not declare Input and does not accept typed child input"
        )
    if isinstance(raw_input, BaseModel):
        candidate = raw_input.model_dump(mode="python")
    else:
        candidate = dict(raw_input)
    try:
        validated = compiled.input_model.model_validate(candidate)
    except ValidationError as exc:
        raise WorkflowExecutionError(
            f"invalid typed input for workflow {compiled.workflow_name!r}: {exc}"
        ) from exc
    return validated.model_dump(mode="json")


def _materialize_workflow_input(
    compiled: CompiledWorkflow,
    raw_input: dict[str, Any] | None,
) -> BaseModel | None:
    if raw_input is None:
        return None
    if compiled.input_model is None:
        raise WorkflowExecutionError(
            f"workflow {compiled.workflow_name!r} has persisted input but does not declare Input"
        )
    try:
        return compiled.input_model.model_validate(raw_input)
    except ValidationError as exc:
        raise WorkflowExecutionError(
            f"persisted typed input for workflow {compiled.workflow_name!r} is invalid: {exc}"
        ) from exc


def _typed_output_metadata(
    *,
    execution_result: RunResult,
    compiled: CompiledWorkflow,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if compiled.output_model is not None or compiled.output_builder is not None:
        model_name = None
        if compiled.output_model is not None:
            model_name = f"{compiled.output_model.__module__}.{compiled.output_model.__qualname__}"
        metadata["typed_output"] = {
            "declared": compiled.output_model is not None,
            "model": model_name,
            "available": execution_result.output is not None,
            "validation_error": execution_result.output_validation_error,
        }
    transition = _last_transition_payload(execution_result.last_transition)
    if transition is not None:
        metadata["finalization"] = transition
    pending_input = _pending_input_metadata(execution_result.checkpoint)
    if pending_input is not None:
        metadata["pending_input"] = pending_input
    return metadata


def _persist_child_runtime_metadata(run_workspace: RunWorkspace, metadata: dict[str, Any]) -> None:
    if not metadata:
        return
    payload = _load_run_metadata_payload(run_workspace.run_meta_file)
    payload.setdefault("schema", RUN_METADATA_SCHEMA)
    payload.update(metadata)
    run_workspace.run_meta_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_child_runtime_metadata(run_workspace: RunWorkspace) -> dict[str, Any]:
    if not run_workspace.run_meta_file.exists():
        return {}
    payload = _load_run_metadata_payload(run_workspace.run_meta_file)
    metadata: dict[str, Any] = {}
    typed_output = payload.get("typed_output")
    if isinstance(typed_output, dict):
        metadata["typed_output"] = dict(typed_output)
    finalization = payload.get("finalization")
    if isinstance(finalization, dict):
        metadata["finalization"] = dict(finalization)
    pending_input = payload.get("pending_input")
    if isinstance(pending_input, dict):
        metadata["pending_input"] = dict(pending_input)
    return metadata


def _load_run_metadata_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise WorkflowExecutionError(f"{path} must contain a JSON object")
    validate_persisted_schema(
        payload,
        expected=RUN_METADATA_SCHEMA,
        artifact_name=str(path),
        legacy_migrator=lambda value: migrate_schemaless_payload(value, expected=RUN_METADATA_SCHEMA),
    )
    return payload


def _json_safe_output_value(output: Any | None) -> Any | None:
    if output is None:
        return None
    if isinstance(output, BaseModel):
        return output.model_dump(mode="json")
    return output


def _build_child_workflow_result(execution: RunExecution) -> ChildWorkflowResult:
    context = SimpleNamespace(
        root=execution.task_workspace.root,
        task_id=execution.task_workspace.task_id,
        run_id=execution.run_workspace.run_id,
        workflow_name=execution.compiled.workflow_name,
        task_folder=execution.task_workspace.task_dir,
        workflow_folder=execution.workflow_workspace.workflow_dir,
        run_folder=execution.run_workspace.run_dir,
        package_folder=execution.workflow_workspace.package_dir,
        state=execution.result.state,
    )
    output_artifacts: dict[str, Path] = {}
    for name, artifact in execution.compiled.artifact_items(authoritative=True):
        path = _resolve_compiled_artifact_path(artifact, context)
        if path.exists():
            output_artifacts[name] = path
    for name, artifact in execution.compiled.artifact_items():
        path = _resolve_compiled_artifact_path(artifact, context)
        if path.exists():
            output_artifacts.setdefault(name, path)
    output_metadata = {}
    if execution.result.last_outcome is not None:
        output_metadata = dict(execution.result.last_outcome.payload)
    metadata = _load_child_runtime_metadata(execution.run_workspace)
    return ChildWorkflowResult(
        workflow_name=execution.compiled.workflow_name,
        run_id=execution.run_workspace.run_id,
        terminal=execution.result.terminal,
        status=_run_status(execution.result.terminal, execution.result.last_event),
        last_event=execution.result.last_event,
        output_metadata=output_metadata,
        output_artifacts=output_artifacts,
        task_folder=execution.task_workspace.task_dir,
        workflow_folder=execution.workflow_workspace.workflow_dir,
        run_folder=execution.run_workspace.run_dir,
        package_folder=execution.workflow_workspace.package_dir,
        request_file=execution.run_workspace.request_file,
        run_meta_file=execution.run_workspace.run_meta_file,
        events_file=execution.run_workspace.events_file,
        checkpoint_file=execution.run_workspace.checkpoint_file,
        sessions_dir=execution.run_workspace.sessions_dir,
        trace_file=execution.run_workspace.trace_file,
        raw_dir=execution.run_workspace.raw_dir,
        parent_file=execution.run_workspace.parent_file,
        output=execution.result.output,
        artifacts=dict(output_artifacts),
        metadata=metadata,
        checkpoint=execution.result.checkpoint,
    )


def _resolve_compiled_artifact_path(artifact: CompiledArtifact, context: Any) -> Path:
    candidate = Path(artifact.template)
    if not candidate.is_absolute() and artifact.owner_step is not None and "{" not in artifact.template and "}" not in artifact.template:
        return context.workflow_folder / artifact.owner_step / artifact.template
    return resolve_artifact_template(artifact.template, context)


def _child_run_record_payload(result: ChildWorkflowResult) -> dict[str, Any]:
    return _child_run_record_payload_from_parts(
        workflow_name=result.workflow_name,
        run_id=result.run_id,
        terminal=result.terminal,
        status=result.status,
        event=result.last_event,
        output_metadata=result.output_metadata,
        output_artifacts=result.output_artifacts,
        task_folder=result.task_folder,
        workflow_folder=result.workflow_folder,
        run_folder=result.run_folder,
        package_folder=result.package_folder,
        request_file=result.request_file,
        run_meta_file=result.run_meta_file,
        events_file=result.events_file,
        checkpoint_file=result.checkpoint_file,
        sessions_dir=result.sessions_dir,
        trace_file=result.trace_file,
        raw_dir=result.raw_dir,
        parent_file=result.parent_file,
        output=result.output,
        artifacts=result.artifacts,
        metadata=result.metadata,
    )


def _child_run_record_payload_from_parts(
    *,
    workflow_name: str,
    run_id: str,
    terminal: str,
    status: str,
    event,
    output_metadata: dict[str, Any],
    output_artifacts: dict[str, Path],
    task_folder: Path,
    workflow_folder: Path,
    run_folder: Path,
    package_folder: Path,
    request_file: Path,
    run_meta_file: Path,
    events_file: Path,
    checkpoint_file: Path,
    sessions_dir: Path,
    trace_file: Path,
    raw_dir: Path,
    parent_file: Path,
    output: Any | None = None,
    artifacts: dict[str, Path] | None = None,
    metadata: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    last_event = None
    if event is not None:
        last_event = {
            "tag": event.tag,
            "reason": event.reason,
            "question": event.question,
            "handoff": event.handoff,
        }
    finalization = None
    metadata_payload = dict(metadata or {})
    raw_finalization = metadata_payload.get("finalization")
    if isinstance(raw_finalization, dict):
        finalization = dict(raw_finalization)
    payload = {
        "workflow_name": workflow_name,
        "run_id": run_id,
        "terminal": terminal,
        "status": status,
        "last_event": last_event,
        "finalization": finalization,
        "output_metadata": dict(output_metadata),
        "output_artifacts": {name: str(path) for name, path in output_artifacts.items()},
        "task_folder": str(task_folder),
        "workflow_folder": str(workflow_folder),
        "run_folder": str(run_folder),
        "package_folder": str(package_folder),
        "request_file": str(request_file),
        "run_meta_file": str(run_meta_file),
        "events_file": str(events_file),
        "checkpoint_file": str(checkpoint_file),
        "sessions_dir": str(sessions_dir),
        "trace_file": str(trace_file),
        "raw_dir": str(raw_dir),
        "parent_file": str(parent_file),
        "output": _json_safe_output_value(output),
        "artifacts": {name: str(path) for name, path in (artifacts or output_artifacts).items()},
        "metadata": metadata_payload,
    }
    if error is not None:
        payload["error"] = error
    return payload


def _pending_input_metadata(checkpoint) -> dict[str, Any] | None:
    pending_input = getattr(checkpoint, "pending_input", None)
    if pending_input is None:
        return None
    return {
        "pending_input_id": pending_input.pending_input_id,
        "source_step": pending_input.source_step,
        "source_hook": pending_input.source_hook,
        "source_phase": pending_input.source_phase,
        "question": pending_input.question,
        "reason": pending_input.reason,
        "best_supposition": pending_input.best_supposition,
        "input_schema": dict(pending_input.input_schema) if pending_input.input_schema is not None else None,
        "input_schema_model": pending_input.input_schema_model,
        "created_at": pending_input.created_at,
    }


def _last_transition_payload(transition: StepFinalizationRecord | None) -> dict[str, Any] | None:
    if transition is None:
        return None
    payload: dict[str, Any] = {
        "candidate_route": transition.candidate_route,
        "final_route": transition.final_route,
        "runtime_control": transition.runtime_control,
        "pending_input_id": transition.pending_input_id,
        "target_step": transition.target_step,
        "terminal": transition.terminal,
        "provider_attributable": transition.provider_attributable,
        "provider_attempted": transition.provider_attempted,
        "producer_attempted": transition.producer_attempted,
        "verifier_attempted": transition.verifier_attempted,
        "source_hook": transition.source_hook,
        "source_phase": transition.source_phase,
        "hook_route_redirects": [
            {
                "hook": redirect.hook,
                "phase": redirect.phase,
                "from_route": redirect.from_route,
                "to_route": redirect.to_route,
                "redirect_index": redirect.redirect_index,
            }
            for redirect in transition.hook_route_redirects
        ],
    }
    return payload


def _run_status(terminal: str, last_event=None) -> str:
    return terminal_to_run_status(
        terminal,
        final_route=getattr(last_event, "tag", None) if last_event is not None else None,
    ) or terminal.lower()
