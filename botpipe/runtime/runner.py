"""Thin generic workflow runner for the filesystem runtime."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Literal, Mapping

from pydantic import BaseModel, ValidationError

from botpipe.policy import PolicyInput
from botpipe.core.artifact_plan import ArtifactSpec
from botpipe.core.artifacts import resolve_artifact_template
from botpipe.core.compiler import compile_workflow
from botpipe.core.context import ChildWorkflowResult, _DEFAULT_MESSAGE
from botpipe.core.engine import Engine, RunResult, StepFinalizationRecord
from botpipe.core.errors import WorkflowExecutionError
from botpipe.core.mappings import normalize_mapping
from botpipe.core.primitives import AWAIT_INPUT, FINISH
from botpipe.core.providers.models import RuntimeInteractionPolicy
from botpipe.core.providers.protocols import LLMProvider
from botpipe.core.schema_registry import RUN_METADATA_SCHEMA, WORKFLOW_TOPOLOGY_SCHEMA, migrate_schemaless_payload, validate_persisted_schema
from botpipe.core.statuses import terminal_to_run_status
from botpipe.extensions.session_paths import extract_session_path_strategy
from .config import (
    ConfigError,
    DEFAULT_MAX_STEPS,
    ProviderConfig,
    ProviderPolicyRuntimeConfig,
    RuntimeConfig,
    RuntimeConfigSources,
    SUPPORTED_PROVIDER_NAMES,
)
from .events import EventLogger
from .git_tracking import RuntimeGitTracker
from .loader import (
    WorkflowReference,
    WorkflowParameterError,
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
    resolve_run_record,
    resolve_run_workspace,
    write_parent_run_metadata,
    update_run_metadata,
    open_existing_run,
    resolve_task_workspace,
    resolve_workflow_workspace,
    resolve_run_workflow_input,
    resolve_run_workflow_params,
    resolve_resume_state_root,
    task_request_text,
)
from botpipe.core.workflow_plan import WorkflowPlan


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
    provider_config: ProviderConfig | None = None
    config_sources: RuntimeConfigSources | None = None
    sticky_overrides: Mapping[str, Any] | None = None
    created_by: str | None = None
    sdk_default_policy: PolicyInput = None
    run_policy: PolicyInput = None
    event_callback: Callable[[Mapping[str, object]], None] | None = None


@dataclass(frozen=True, slots=True)
class PreparedRunContext:
    """Resolved generic runtime context for one run."""

    compiled: WorkflowPlan
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
    compiled: WorkflowPlan
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


def execute_workflow_plan(
    compiled: WorkflowPlan,
    *,
    reference: WorkflowReference,
    provider: LLMProvider,
    options: RunnerOptions,
) -> RunExecution:
    execution_options = _normalize_execution_options(options, parameters_cls=compiled.parameters_cls)
    return _execute_compiled_workflow(
        compiled,
        reference=reference,
        parameters_cls=compiled.parameters_cls,
        capability_prompt_paths=(),
        provider=provider,
        options=execution_options,
    )


def _execute_compiled_workflow(
    compiled: WorkflowPlan,
    *,
    reference: WorkflowReference,
    parameters_cls: type[Any] | None,
    capability_prompt_paths: tuple[Path, ...] = (),
    provider: LLMProvider,
    options: RunnerOptions,
) -> RunExecution:
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
    git_tracking_prepare_warnings = git_tracker.prepare_warnings
    task_workspace, workflow_workspace, run_workspace = _prepare_workspaces(
        compiled,
        options,
        reference=reference,
        planned=planned,
    )
    max_steps = _resolve_effective_max_steps(options, run_workspace)
    sticky_overrides = _resolve_effective_sticky_overrides(options, run_workspace)
    effective_compiled, workflow_git_tracking_warnings = _runtime_compiled_workflow(compiled)
    session_path_strategy = resolve_session_path_strategy(effective_compiled)
    prepared = prepare_runtime_services(
        effective_compiled,
        task_workspace=task_workspace,
        workflow_workspace=workflow_workspace,
        run_workspace=run_workspace,
        session_path_strategy=session_path_strategy,
        capability_prompt_paths=capability_prompt_paths,
        event_callback=options.event_callback,
    )
    resume_git_tracking_warnings = _resume_git_tracking_warnings(prepared.run_workspace, options)
    resolved_workflow_params = _resolve_effective_workflow_params(
        parameters_cls,
        prepared.run_workspace,
        options,
    )
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
        execution_config=_execution_config_metadata(
            options,
            effective_max_steps=max_steps,
            workflow_policy=prepared.compiled.provider_policy,
        ),
        sticky_overrides=sticky_overrides,
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
    for warning in git_tracking_prepare_warnings:
        append_run_warning(prepared.run_workspace.run_dir, warning)
        prepared.logger.emit(
            warning["event_type"],
            workflow=prepared.compiled.workflow_name,
            task_id=prepared.task_workspace.task_id,
            message=warning["message"],
        )
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
        event_sink=prepared.logger.emit,
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
    run_started_payload = {
        "workflow": prepared.compiled.workflow_name,
        "task_id": prepared.task_workspace.task_id,
        "task_folder": str(prepared.task_workspace.task_dir),
        "workflow_folder": str(prepared.workflow_workspace.workflow_dir),
        "run_folder": str(prepared.run_workspace.run_dir),
        "events_file": str(prepared.run_workspace.events_file),
        "trace_enabled": options.runtime_config.tracing.enabled,
    }
    if options.runtime_config.tracing.enabled:
        run_started_payload["trace_file"] = str(trace_writer.trace_path)
    if options.parent_run is not None:
        run_started_payload.update(
            {
                "parent_run_id": options.parent_run.run_id,
                "parent_workflow": options.parent_run.workflow_workspace.workflow_name,
                "parent_run_folder": str(options.parent_run.run_dir),
            }
        )
    prepared.logger.emit(
        "run_resumed" if options.resume else "run_started",
        **run_started_payload,
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
    compiled: WorkflowPlan,
    *,
    task_workspace: TaskWorkspace,
    workflow_workspace: WorkflowWorkspace,
    run_workspace: RunWorkspace,
    session_path_strategy=None,
    capability_prompt_paths: tuple[Path, ...] = (),
    event_callback: Callable[[Mapping[str, object]], None] | None = None,
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
        logger=EventLogger(run_workspace.run_id, run_workspace.events_file, event_callback=event_callback),
    )


def _prompt_registry_roots(
    workflow_parent: Path,
    *,
    compiled: WorkflowPlan,
    capability_prompt_paths: tuple[Path, ...] = (),
) -> tuple[Path, ...]:
    roots: list[Path] = [workflow_parent]

    for prompt_path in capability_prompt_paths:
        roots.append(prompt_path.parent if prompt_path.is_file() else prompt_path)

    for step in compiled.steps.values():
        for prompt in (step.producer_prompt, step.verifier_prompt):
            if prompt is None:
                continue
            if isinstance(prompt, str):
                roots.append((workflow_parent / prompt).parent)
                continue
            if prompt.source == "inline":
                continue
            roots.append((workflow_parent / prompt.path).parent)

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
    compiled: WorkflowPlan,
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
    compiled: WorkflowPlan,
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
        created_by=options.created_by,
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
    compiled: WorkflowPlan,
    options: RunnerOptions,
    *,
    reference: WorkflowReference,
) -> PlannedRunContext:
    state_dir = _resolved_state_dir(options)
    resume_run_id = options.run_id
    if options.resume and options.state_dir is None:
        resume_record = resolve_run_record(
            options.root,
            workflow_name=compiled.workflow_name,
            task_id=options.task_id,
            run_id=options.run_id,
            selector="latest",
        )
        state_dir = resume_record.task_dir.parent.parent
        resume_run_id = resume_record.run_id
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
    _assert_workflow_identity_consistency(task_workspace, compiled.workflow_name, reference)
    if not options.resume:
        return PlannedRunContext(
            task_workspace=task_workspace,
            workflow_workspace=workflow_workspace,
            run_workspace=resolve_run_workspace(workflow_workspace, options.run_id or create_run_id()),
        )

    run_id = resume_run_id or latest_run_id(workflow_workspace.runs_dir)
    if run_id is None:
        raise FileNotFoundError(f"no runs exist under {workflow_workspace.runs_dir}")
    run_workspace = resolve_run_workspace(workflow_workspace, run_id)
    validate_resume_state(run_workspace.run_dir)
    return PlannedRunContext(
        task_workspace=task_workspace,
        workflow_workspace=workflow_workspace,
        run_workspace=run_workspace,
    )


def resolve_max_steps(max_steps: int | None, *, runtime_config: RuntimeConfig | None = None) -> int:
    if max_steps is None:
        configured_max_steps = DEFAULT_MAX_STEPS if runtime_config is None else runtime_config.max_steps
        return _validate_max_steps(configured_max_steps, label="runtime max_steps")
    return _validate_max_steps(max_steps, label="max_steps")


def _validate_max_steps(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConfigError(f"{label} must be a non-negative integer.")
    return value


def _resolve_effective_max_steps(options: RunnerOptions, run_workspace: RunWorkspace) -> int:
    if not options.resume or options.max_steps is not None:
        return resolve_max_steps(options.max_steps, runtime_config=options.runtime_config)

    _validate_max_steps(options.runtime_config.max_steps, label="runtime max_steps")
    current_max_steps = _runtime_max_steps_from_sticky_overrides(options.sticky_overrides)
    if current_max_steps is not None:
        return resolve_max_steps(current_max_steps, runtime_config=options.runtime_config)

    sticky_exists, sticky_overrides = _load_sticky_overrides(run_workspace)
    if sticky_exists:
        sticky_max_steps = _runtime_max_steps_from_sticky_overrides(sticky_overrides)
        if sticky_max_steps is not None:
            return resolve_max_steps(sticky_max_steps, runtime_config=options.runtime_config)
        return resolve_max_steps(None, runtime_config=options.runtime_config)

    stored_max_steps = _latest_recorded_runtime_max_steps(run_workspace)
    if stored_max_steps is not None:
        return resolve_max_steps(stored_max_steps, runtime_config=options.runtime_config)
    return resolve_max_steps(None, runtime_config=options.runtime_config)


def _resolve_effective_sticky_overrides(options: RunnerOptions, run_workspace: RunWorkspace) -> dict[str, Any]:
    stored_exists, stored_sticky = _load_sticky_overrides(run_workspace)
    current_sticky = _normalize_sticky_overrides(options.sticky_overrides)
    if options.max_steps is not None:
        current_sticky = _merge_sticky_overrides(
            current_sticky,
            {"runtime": {"max_steps": _validate_max_steps(options.max_steps, label="max_steps")}},
        )

    legacy_sticky: dict[str, Any] = {}
    if (
        options.resume
        and not stored_exists
        and _runtime_max_steps_from_sticky_overrides(current_sticky) is None
    ):
        legacy_max_steps = _latest_recorded_runtime_max_steps(run_workspace)
        if legacy_max_steps is not None:
            legacy_sticky = {"runtime": {"max_steps": legacy_max_steps}}

    return _sanitize_sticky_overrides(
        _merge_sticky_overrides(stored_sticky, legacy_sticky, current_sticky)
    )


def _load_sticky_overrides(run_workspace: RunWorkspace) -> tuple[bool, dict[str, Any]]:
    try:
        payload = _load_run_metadata_payload(run_workspace.run_meta_file)
    except (json.JSONDecodeError, OSError):
        return False, {}
    if "sticky_overrides" not in payload:
        return False, {}
    sticky_overrides = payload.get("sticky_overrides")
    if not isinstance(sticky_overrides, Mapping):
        return True, {}
    return True, normalize_mapping(sticky_overrides)


def _normalize_sticky_overrides(sticky_overrides: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(sticky_overrides, Mapping):
        return {}
    return normalize_mapping(sticky_overrides)


def _merge_sticky_overrides(*payloads: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for payload in payloads:
        for section in ("runtime", "provider"):
            section_payload = payload.get(section)
            if not isinstance(section_payload, Mapping):
                continue
            section_target = merged.setdefault(section, {})
            if not isinstance(section_target, dict):  # pragma: no cover - defensive
                section_target = {}
                merged[section] = section_target
            for key, value in section_payload.items():
                if isinstance(value, Mapping):
                    existing = section_target.get(key)
                    nested = dict(existing) if isinstance(existing, Mapping) else {}
                    nested.update(normalize_mapping(value))
                    section_target[key] = nested
                else:
                    section_target[key] = value
    return merged


def _sanitize_sticky_overrides(payload: Mapping[str, Any]) -> dict[str, Any]:
    sticky: dict[str, Any] = {}

    runtime = payload.get("runtime")
    if isinstance(runtime, Mapping):
        max_steps = runtime.get("max_steps")
        if _is_valid_max_steps(max_steps):
            sticky["runtime"] = {"max_steps": max_steps}

    provider = _sanitize_provider_sticky_overrides(payload.get("provider"))
    if provider:
        sticky["provider"] = provider

    return sticky


def _sanitize_provider_sticky_overrides(provider: object) -> dict[str, Any]:
    if not isinstance(provider, Mapping):
        return {}
    name = provider.get("name")
    if not isinstance(name, str) or name not in SUPPORTED_PROVIDER_NAMES:
        return {}

    sticky: dict[str, Any] = {"name": name}
    if name == "codex":
        codex = provider.get("codex")
        if isinstance(codex, Mapping):
            codex_sticky: dict[str, str] = {}
            model = _non_empty_string(codex.get("model"))
            model_effort = _non_empty_string(codex.get("model_effort"))
            if model is not None:
                codex_sticky["model"] = model
            if model_effort is not None:
                codex_sticky["model_effort"] = model_effort
            if codex_sticky:
                sticky["codex"] = codex_sticky
    elif name == "claude":
        claude = provider.get("claude")
        if isinstance(claude, Mapping):
            claude_sticky: dict[str, str] = {}
            model = _non_empty_string(claude.get("model"))
            effort = _non_empty_string(claude.get("effort"))
            if model is not None:
                claude_sticky["model"] = model
            if effort is not None:
                claude_sticky["effort"] = effort
            if claude_sticky:
                sticky["claude"] = claude_sticky
    return sticky


def _non_empty_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _runtime_max_steps_from_sticky_overrides(sticky_overrides: Mapping[str, Any] | None) -> int | None:
    if not isinstance(sticky_overrides, Mapping):
        return None
    runtime = sticky_overrides.get("runtime")
    if not isinstance(runtime, Mapping):
        return None
    max_steps = runtime.get("max_steps")
    return max_steps if _is_valid_max_steps(max_steps) else None


def _latest_recorded_runtime_max_steps(run_workspace: RunWorkspace) -> int | None:
    try:
        payload = _load_run_metadata_payload(run_workspace.run_meta_file)
    except (json.JSONDecodeError, OSError):
        return None

    execution_config = payload.get("execution_config")
    if not isinstance(execution_config, dict):
        return None

    candidates: list[object] = [execution_config.get("last_used")]
    invocations = execution_config.get("invocations")
    if isinstance(invocations, list):
        candidates.extend(reversed(invocations))
    candidates.extend((execution_config.get("created_with"), execution_config.get("first_recorded_with")))

    for candidate in candidates:
        max_steps = _runtime_max_steps_from_execution_config(candidate)
        if max_steps is not None:
            return max_steps
    return None


def _runtime_max_steps_from_execution_config(entry: object) -> int | None:
    if not isinstance(entry, Mapping):
        return None
    runtime = entry.get("runtime")
    if not isinstance(runtime, Mapping):
        return None
    max_steps = runtime.get("max_steps")
    return max_steps if _is_valid_max_steps(max_steps) else None


def _is_valid_max_steps(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def _runtime_observability_error(exc: BaseException) -> BaseException:
    cause = exc.__cause__
    if isinstance(cause, BaseException):
        return cause
    return exc


def resolve_session_path_strategy(compiled: WorkflowPlan):
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


def _resume_topology_mismatch_warning(
    run_workspace: RunWorkspace,
    compiled: WorkflowPlan,
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


def _run_topology_metadata(run_workspace: RunWorkspace, compiled: WorkflowPlan) -> dict[str, Any]:
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


def _runtime_compiled_workflow(compiled: WorkflowPlan) -> tuple[WorkflowPlan, tuple[dict[str, str], ...]]:
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
                provider_config=options.provider_config,
                config_sources=options.config_sources,
                sticky_overrides=options.sticky_overrides,
                created_by=options.created_by,
                sdk_default_policy=options.sdk_default_policy,
                run_policy=options.run_policy,
                event_callback=options.event_callback,
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
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="botpipe-child-workflow") as executor:
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


def _resolve_effective_workflow_params(
    parameters_cls: type[Any] | None,
    run_workspace: RunWorkspace,
    options: RunnerOptions,
) -> dict[str, Any]:
    if not options.resume:
        return resolve_run_workflow_params(run_workspace, options.workflow_params)

    stored_params = resolve_run_workflow_params(run_workspace, None)
    if options.workflow_params is None:
        if parameters_cls is None:
            return normalize_mapping(stored_params)
        return coerce_workflow_parameter_mapping(parameters_cls, stored_params)

    override_params = normalize_mapping(options.workflow_params)
    if parameters_cls is None:
        if override_params:
            raise WorkflowParameterError("workflow does not declare Params and does not accept workflow parameters")
        return normalize_mapping(stored_params)

    candidate = {
        **stored_params,
        **override_params,
    }
    return coerce_workflow_parameter_mapping(parameters_cls, candidate)


def _coerce_workflow_input_payload(
    compiled: WorkflowPlan,
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
    compiled: WorkflowPlan,
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


def _execution_config_metadata(
    options: RunnerOptions,
    *,
    effective_max_steps: int,
    workflow_policy: PolicyInput,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "resume": options.resume,
        "runtime": _runtime_config_metadata(options.runtime_config, effective_max_steps=effective_max_steps),
        "provider_policy_config": _provider_policy_config_metadata(options.provider_policy_config),
        "policy_layers": {
            "sdk_default_policy_configured": options.sdk_default_policy is not None,
            "workflow_policy_configured": workflow_policy is not None,
            "run_policy_configured": options.run_policy is not None,
        },
    }
    if options.created_by is not None:
        metadata["created_by"] = options.created_by
    if options.provider_config is not None:
        metadata["provider"] = _provider_config_metadata(options.provider_config)
    if options.config_sources is not None:
        metadata["config_sources"] = _config_sources_metadata(options.config_sources)
    return metadata


def _provider_config_metadata(config: ProviderConfig) -> dict[str, Any]:
    payload: dict[str, Any] = {"name": config.name}
    if config.name == "codex":
        payload["model"] = config.codex.model
        if config.codex.model_effort is not None:
            payload["model_effort"] = config.codex.model_effort
    elif config.name == "claude":
        if config.claude.model is not None:
            payload["model"] = config.claude.model
        if config.claude.effort is not None:
            payload["model_effort"] = config.claude.effort
        payload["permission_strategy"] = config.claude.permission_strategy
    return payload


def _runtime_config_metadata(config: RuntimeConfig, *, effective_max_steps: int) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "max_steps": effective_max_steps,
        "full_auto": config.full_auto,
        "replay_mismatch_behavior": config.replay_mismatch_behavior,
        "resume_topology_mismatch_behavior": config.resume_topology_mismatch_behavior,
        "git_tracking": {
            "enabled": config.git_tracking.enabled,
            "required": config.git_tracking.required,
            "commit_policy": config.git_tracking.commit_policy,
            "failure_policy": config.git_tracking.failure_policy,
        },
        "tracing": {
            "enabled": config.tracing.enabled,
            "path": config.tracing.path,
            "failure_policy": config.tracing.failure_policy,
            "include_state_snapshots": config.tracing.include_state_snapshots,
        },
    }
    if effective_max_steps != config.max_steps:
        payload["configured_max_steps"] = config.max_steps
    return payload


def _provider_policy_config_metadata(config: ProviderPolicyRuntimeConfig) -> dict[str, Any]:
    default_policy = config.default
    network = default_policy.sandbox.workspace.network
    payload = config.model_dump(mode="json", warnings=False)
    summary: dict[str, Any] = {
        "redacted_hash": "sha256:" + sha256(
            json.dumps(
                _redacted_provider_policy_fingerprint_payload(payload),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        ).hexdigest(),
        "validation": config.validation.model_dump(mode="json", warnings=False),
        "default": {
            "model": {
                "provider": default_policy.model.provider,
                "default": default_policy.model.default,
                "effort": default_policy.model.effort,
                "verbosity": default_policy.model.verbosity,
                "reasoning_summary": default_policy.model.reasoning_summary,
                "base_url_configured": default_policy.model.base_url is not None,
                "override_count": len(default_policy.model.overrides),
            },
            "permissions": {
                "mode": default_policy.permissions.mode,
                "allow_dangerous_bypass": default_policy.permissions.allow_dangerous_bypass,
                "disable_dangerous_bypass": default_policy.permissions.disable_dangerous_bypass,
            },
            "sandbox": {
                "enabled": default_policy.sandbox.enabled,
                "required": default_policy.sandbox.required,
                "mode": default_policy.sandbox.mode,
            },
            "network": {
                "enabled": network.enabled,
                "mode": network.mode,
                "allow_domain_count": len(network.allow_domains),
                "deny_domain_count": len(network.deny_domains),
            },
            "env": {"inherit": default_policy.env.inherit},
        },
        "strict": {"configured": config.strict is not None},
    }
    return summary


_SECRET_FINGERPRINT_KEY_PARTS = ("token", "secret", "key", "password", "credential", "auth")
_SECRET_FINGERPRINT_KEYS = {"headers", "set"}


def _redacted_provider_policy_fingerprint_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.casefold()
            if lowered in _SECRET_FINGERPRINT_KEYS or any(part in lowered for part in _SECRET_FINGERPRINT_KEY_PARTS):
                redacted[key_text] = "<redacted>"
                continue
            redacted[key_text] = _redacted_provider_policy_fingerprint_payload(item)
        return redacted
    if isinstance(value, list):
        return [_redacted_provider_policy_fingerprint_payload(item) for item in value]
    return value


def _config_sources_metadata(sources: RuntimeConfigSources) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if sources.user_config is not None:
        payload["user_config"] = str(sources.user_config)
    if sources.workspace_config is not None:
        payload["workspace_config"] = str(sources.workspace_config)
    if sources.policy_file is not None:
        payload["policy_file"] = str(sources.policy_file)
    if sources.cli_overrides:
        payload["cli_overrides"] = list(sources.cli_overrides)
    if sources.sdk_overrides:
        payload["sdk_overrides"] = list(sources.sdk_overrides)
    return payload


def _typed_output_metadata(
    *,
    execution_result: RunResult,
    compiled: WorkflowPlan,
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


def _resolve_compiled_artifact_path(artifact: ArtifactSpec, context: Any) -> Path:
    candidate = Path(artifact.template)
    if not candidate.is_absolute() and artifact.owner_step is not None and "{" not in artifact.template and "}" not in artifact.template:
        return context.workflow_folder / artifact.owner_step / artifact.template
    return resolve_artifact_template(artifact, context)


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
