"""Thin generic workflow runner for the filesystem runtime."""

from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..extensions.session_paths import extract_session_path_strategy
from ..workflow.compiler import CompiledWorkflow
from ..workflow.errors import WorkflowExecutionError
from ..workflow.engine import Engine, RunResult
from ..workflow.providers.protocols import LLMProvider
from .config import ConfigError, DEFAULT_MAX_STEPS
from .events import EventLogger
from .loader import load_compiled_workflow
from .prompts import FilesystemPromptRegistry
from .stores.filesystem import FilesystemCheckpointStore, FilesystemSessionStore
from .workspace import (
    RunWorkspace,
    TaskWorkspace,
    create_run,
    ensure_workspace,
    open_existing_run,
    resolve_resume_state_root,
    task_request_text,
)


@dataclass(frozen=True, slots=True)
class RunnerOptions:
    root: Path
    task_id: str
    run_id: str | None = None
    request_text: str | None = None
    resume: bool = False
    answer: str | None = None
    class_name: str | None = None
    state_dir: Path | None = None
    intent_mode: str = "replace"
    max_steps: int | None = None


@dataclass(frozen=True, slots=True)
class PreparedRunContext:
    """Resolved generic runtime context for one run."""

    compiled: CompiledWorkflow
    task_workspace: TaskWorkspace
    run_workspace: RunWorkspace
    session_store: FilesystemSessionStore
    checkpoint_store: FilesystemCheckpointStore
    prompt_registry: FilesystemPromptRegistry
    logger: EventLogger


def load_provider_factory(spec: str) -> Callable[..., LLMProvider]:
    module_name, _, attr_name = spec.partition(":")
    if not module_name or not attr_name:
        raise ValueError("provider factory must be in 'module:function' form")
    module = importlib.import_module(module_name)
    factory = getattr(module, attr_name, None)
    if not callable(factory):
        raise LookupError(f"provider factory {spec!r} was not found")
    return factory


def run_workflow(
    workflow_target: str | Path,
    *,
    provider: LLMProvider,
    options: RunnerOptions,
) -> RunResult:
    max_steps = _resolve_max_steps(options.max_steps)
    compiled = load_compiled_workflow(workflow_target, class_name=options.class_name)
    prepared = _prepare_run_context(compiled, options)

    engine = Engine(
        prepared.compiled,
        provider=provider,
        session_store=prepared.session_store,
        checkpoint_store=prepared.checkpoint_store,
        prompt_registry=prepared.prompt_registry,
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
                run_folder=prepared.run_workspace.run_dir,
                root=prepared.task_workspace.root,
                answer=options.answer,
                max_steps=max_steps,
            )
        else:
            result = engine.run(
                task_id=prepared.task_workspace.task_id,
                run_id=prepared.run_workspace.run_id,
                task_folder=prepared.task_workspace.task_dir,
                run_folder=prepared.run_workspace.run_dir,
                root=prepared.task_workspace.root,
                max_steps=max_steps,
            )

        for step_name in result.history:
            prepared.logger.emit("step_executed", workflow=prepared.compiled.workflow_name, step_name=step_name)

        prepared.logger.emit(
            "run_finished",
            workflow=prepared.compiled.workflow_name,
            terminal=result.terminal,
            status=_run_status(result.terminal),
            last_step=result.history[-1] if result.history else None,
        )
        return result
    except Exception as exc:
        prepared.logger.emit(
            "run_finished",
            workflow=prepared.compiled.workflow_name,
            status="fatal_error",
            error_type=type(exc).__name__,
            error=str(exc),
        )
        raise


def _prepare_run_context(compiled: CompiledWorkflow, options: RunnerOptions) -> PreparedRunContext:
    workflow_parent = Path(inspect.getfile(compiled.workflow_cls)).resolve().parent
    path_strategy = _extract_session_path_strategy(compiled)
    workspace, run = _prepare_workspaces(options)
    return PreparedRunContext(
        compiled=compiled,
        task_workspace=workspace,
        run_workspace=run,
        session_store=FilesystemSessionStore(run.run_dir, path_strategy=path_strategy),
        checkpoint_store=FilesystemCheckpointStore(run.checkpoint_file, compiled.state_cls),
        prompt_registry=FilesystemPromptRegistry(workflow_parent, workspace.root, Path.cwd()),
        logger=EventLogger(run.run_id, run.events_file),
    )


def _ensure_task_workspace(options: RunnerOptions) -> TaskWorkspace:
    root = options.root.resolve()
    state_dir = options.state_dir
    if options.resume and state_dir is None:
        state_dir = resolve_resume_state_root(root, task_id=options.task_id, run_id=options.run_id)
    return ensure_workspace(
        root,
        options.task_id,
        product_intent=options.request_text,
        intent_mode=options.intent_mode,
        state_dir=state_dir,
    )


def _prepare_workspaces(options: RunnerOptions) -> tuple[TaskWorkspace, RunWorkspace]:
    if not options.resume:
        workspace = _ensure_task_workspace(options)
        run = create_run(
            workspace,
            run_id=options.run_id,
            request_text=options.request_text or task_request_text(workspace.task_meta_file, workspace.legacy_context_file),
        )
        return workspace, run

    root = options.root.resolve()
    state_dir = options.state_dir
    if state_dir is None:
        state_dir = resolve_resume_state_root(root, task_id=options.task_id, run_id=options.run_id)
    run_id = options.run_id or ""
    run_dir = state_dir / "tasks" / options.task_id / "runs" / run_id
    _validate_resume_state(run_dir)
    workspace = ensure_workspace(
        root,
        options.task_id,
        product_intent=options.request_text,
        intent_mode=options.intent_mode,
        state_dir=state_dir,
    )
    return workspace, open_existing_run(workspace, run_id)


def _resolve_max_steps(max_steps: int | None) -> int:
    if max_steps is None:
        return DEFAULT_MAX_STEPS
    if max_steps <= 0:
        raise ConfigError("max_steps must be a positive integer.")
    return max_steps


def _extract_session_path_strategy(compiled: CompiledWorkflow):
    try:
        return extract_session_path_strategy(compiled.extensions)
    except ValueError as exc:
        raise WorkflowExecutionError(str(exc)) from exc


def _validate_resume_state(run_dir: Path) -> None:
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
            "resume requested for a run without autoloop_v3 checkpoint.json. "
            "This run only has persisted session or event state, which the generic runtime does not reconstruct into "
            "engine checkpoints. Resume it with the workflow-owned harness that created it or start a new run."
        )


def _run_status(terminal: str) -> str:
    if terminal == "SUCCESS":
        return "success"
    if terminal == "PAUSE":
        return "paused"
    if terminal == "FAIL":
        return "failed"
    return terminal.lower()
