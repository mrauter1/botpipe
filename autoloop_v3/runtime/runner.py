"""Thin workflow runner for the filesystem runtime."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..workflow.engine import Engine, RunResult
from ..workflow.providers.protocols import LLMProvider
from .events import EventLogger, append_decisions_runtime_block
from .loader import load_compiled_workflow
from .prompts import FilesystemPromptRegistry
from .stores.filesystem import FilesystemCheckpointStore, FilesystemSessionStore
from .workspace import (
    PLAN_DECISIONS_PHASE_ID,
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
    workspace = _ensure_task_workspace(options)
    run = (
        open_existing_run(workspace, options.run_id or "")
        if options.resume
        else create_run(
            workspace,
            run_id=options.run_id,
            request_text=options.request_text or task_request_text(workspace.task_meta_file, workspace.legacy_context_file),
        )
    )

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

    if options.resume:
        logger.emit("run_resumed", workflow=compiled.workflow_name, task_id=workspace.task_id)
        if options.answer:
            checkpoint = checkpoint_store.load()
            if checkpoint is not None and checkpoint.pending_question:
                phase_id = checkpoint.session_bindings.active_scopes.get("phase_session") or PLAN_DECISIONS_PHASE_ID
                append_decisions_runtime_block(
                    workspace.decisions_file,
                    pair=checkpoint.stage,
                    phase_id=phase_id,
                    run_id=run.run_id,
                    entry="answers",
                    body=options.answer,
                    source="runtime-runner",
                )
        result = engine.resume(
            task_id=workspace.task_id,
            run_id=run.run_id,
            task_folder=workspace.task_dir,
            run_folder=run.run_dir,
            answer=options.answer,
        )
    else:
        logger.emit("run_started", workflow=compiled.workflow_name, task_id=workspace.task_id)
        result = engine.run(
            task_id=workspace.task_id,
            run_id=run.run_id,
            task_folder=workspace.task_dir,
            run_folder=run.run_dir,
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
        last_step=result.history[-1] if result.history else None,
        phase_id=phase_scope,
    )
    return result


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
