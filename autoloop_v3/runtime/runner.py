"""Thin workflow runner for the filesystem runtime."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..workflow.errors import WorkflowExecutionError
from ..workflow.engine import Engine, RunResult
from ..workflow.providers.protocols import LLMProvider
from .config import (
    ConfigError,
    DEFAULT_FULL_AUTO_ANSWERS,
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_NO_GIT,
    DEFAULT_PAIRS,
    DEFAULT_PHASE_MODE,
    DEFAULT_TRACK_AUTOLOOP_ARTIFACTS,
)
from .events import EventLogger, append_decisions_runtime_block, append_resume_clarification
from .loader import load_compiled_workflow
from .prompts import FilesystemPromptRegistry
from .stores.filesystem import FilesystemCheckpointStore, FilesystemSessionStore
from .workspace import (
    PLAN_DECISIONS_PHASE_ID,
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
    pairs: str | None = None
    max_iterations: int | None = None
    phase_mode: str | None = None
    phase_id: str | None = None
    full_auto_answers: bool | None = None
    no_git: bool | None = None
    track_autoloop_artifacts: bool | None = None


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
    _validate_runtime_options(options)
    workspace, run = _prepare_workspaces(options)

    compiled = load_compiled_workflow(workflow_target, class_name=options.class_name)
    session_store = FilesystemSessionStore(run.run_dir)
    checkpoint_store = FilesystemCheckpointStore(run.checkpoint_file, compiled.state_cls)
    workflow_path = Path(str(workflow_target))
    workflow_parent = workflow_path.resolve().parent if workflow_path.exists() else workspace.root
    prompt_registry = FilesystemPromptRegistry(
        Path.cwd(),
        workspace.root,
        workflow_parent,
        workflow_parent / "autoloop" / "src" / "autoloop",
        workspace.root / "autoloop" / "src" / "autoloop",
    )
    logger = EventLogger(run.run_id, run.events_file)

    engine = Engine(
        compiled,
        provider=provider,
        session_store=session_store,
        checkpoint_store=checkpoint_store,
        prompt_registry=prompt_registry,
    )
    logger.emit("run_resumed" if options.resume else "run_started", workflow=compiled.workflow_name, task_id=workspace.task_id)
    resume_clarification: tuple[str, str | None, str, Path | None] | None = None
    try:
        if options.resume:
            checkpoint = checkpoint_store.load()
            if options.answer and checkpoint is not None and checkpoint.pending_question:
                phase_id = checkpoint.session_bindings.active_scopes.get("phase_session") or PLAN_DECISIONS_PHASE_ID
                resume_clarification = (
                    checkpoint.stage,
                    phase_id,
                    checkpoint.pending_question,
                    _paused_session_file(run, session_store, compiled, checkpoint),
                )
            result = engine.resume(
                task_id=workspace.task_id,
                run_id=run.run_id,
                task_folder=workspace.task_dir,
                run_folder=run.run_dir,
                answer=options.answer,
            )
        else:
            result = engine.run(
                task_id=workspace.task_id,
                run_id=run.run_id,
                task_folder=workspace.task_dir,
                run_folder=run.run_dir,
            )

        if resume_clarification is not None and options.answer is not None:
            pair, phase_id, question, session_file = resume_clarification
            append_resume_clarification(
                run.raw_phase_log,
                workspace.raw_phase_log,
                workspace.decisions_file,
                session_file,
                pair=pair,
                phase_id=phase_id,
                question=question,
                answer=options.answer,
                run_id=run.run_id,
            )

        for step_name in result.history:
            logger.emit("step_executed", workflow=compiled.workflow_name, step_name=step_name)

        phase_scope = session_store.snapshot().active_scopes.get("phase_session")
        if result.terminal == "PAUSE" and result.last_event is not None and result.last_event.question:
            append_decisions_runtime_block(
                workspace.decisions_file,
                pair=result.history[-1] if result.history else compiled.entry_step_name,
                phase_id=phase_scope or PLAN_DECISIONS_PHASE_ID,
                run_id=run.run_id,
                entry="questions",
                body=result.last_event.question,
                source="runtime-runner",
            )

        logger.emit(
            "run_finished",
            workflow=compiled.workflow_name,
            terminal=result.terminal,
            status=_legacy_status(result.terminal),
            last_step=result.history[-1] if result.history else None,
            phase_id=phase_scope,
        )
        return result
    except Exception as exc:
        if resume_clarification is not None and options.answer is not None:
            pair, phase_id, question, session_file = resume_clarification
            append_resume_clarification(
                run.raw_phase_log,
                workspace.raw_phase_log,
                workspace.decisions_file,
                session_file,
                pair=pair,
                phase_id=phase_id,
                question=question,
                answer=options.answer,
                run_id=run.run_id,
            )
        logger.emit(
            "run_finished",
            workflow=compiled.workflow_name,
            status="fatal_error",
            error_type=type(exc).__name__,
            error=str(exc),
            phase_id=session_store.snapshot().active_scopes.get("phase_session"),
        )
        raise


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


def _validate_runtime_options(options: RunnerOptions) -> None:
    unsupported: list[str] = []
    if options.pairs is not None and options.pairs != DEFAULT_PAIRS:
        unsupported.append("--pairs")
    if options.max_iterations is not None and options.max_iterations != DEFAULT_MAX_ITERATIONS:
        unsupported.append("--max-iterations")
    if options.phase_id is not None:
        unsupported.append("--phase-id")
    if options.phase_mode is not None and options.phase_mode != DEFAULT_PHASE_MODE:
        unsupported.append("--phase-mode")
    if options.full_auto_answers not in (None, DEFAULT_FULL_AUTO_ANSWERS):
        unsupported.append("--full-auto-answers")
    if options.no_git not in (None, DEFAULT_NO_GIT):
        unsupported.append("--no-git")
    if options.track_autoloop_artifacts not in (None, DEFAULT_TRACK_AUTOLOOP_ARTIFACTS):
        unsupported.append("--track-autoloop-artifacts")

    if unsupported:
        joined = ", ".join(unsupported)
        raise ConfigError(
            f"The generic autoloop_v3 workflow runner does not support {joined}. "
            "Use default values only, or run the legacy autoloop harness for pair/phase-oriented execution."
        )


def _validate_resume_state(run_dir: Path) -> None:
    if not run_dir.is_dir():
        raise FileNotFoundError(f"run {run_dir.name!r} does not exist under {run_dir.parent}")
    checkpoint_file = run_dir / "checkpoint.json"
    if checkpoint_file.exists():
        return
    sessions_dir = run_dir / "sessions"
    phase_sessions_dir = sessions_dir / "phases"
    events_file = run_dir / "events.jsonl"
    has_session_files = any(sessions_dir.glob("*.json")) or any(phase_sessions_dir.glob("*.json"))
    has_event_history = events_file.exists() and events_file.stat().st_size > 0
    if has_session_files or has_event_history:
        raise WorkflowExecutionError(
            "resume requested for a run without autoloop_v3 checkpoint.json. "
            "This run only has legacy session/event state, which the generic v3 runner does not reconstruct into "
            "engine checkpoints. Resume it with the legacy autoloop runtime or start a new autoloop_v3 run."
        )


def _paused_session_file(
    run: Any,
    session_store: FilesystemSessionStore,
    compiled: Any,
    checkpoint: Any,
) -> Path | None:
    step = compiled.steps.get(checkpoint.stage)
    if step is None or step.session_name is None:
        return None
    scope = checkpoint.session_bindings.active_scopes.get(step.session_name)
    return session_store.path_for(step.session_name, scope)


def _legacy_status(terminal: str) -> str:
    if terminal == "SUCCESS":
        return "success"
    if terminal == "PAUSE":
        return "paused"
    if terminal == "FAIL":
        return "failed"
    return terminal.lower()
