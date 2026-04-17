"""Workflow-owned Autoloop-v1 parity harness."""

from __future__ import annotations

import inspect
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ..runtime.config import DEFAULT_MAX_STEPS
from ..runtime.events import EventLogger
from ..runtime.loader import load_compiled_workflow
from ..runtime.prompts import FilesystemPromptRegistry
from ..runtime.runner import RunnerOptions
from ..runtime.stores.filesystem import (
    FilesystemCheckpointStore,
    FilesystemSessionStore,
    ensure_session_payload_placeholder,
    set_pending_session_note,
)
from ..runtime.workspace import (
    RunWorkspace,
    TaskWorkspace,
    create_run,
    ensure_workspace,
    open_existing_run,
    resolve_resume_state_root,
    task_request_text,
)
from ..workflow.compiler import CompiledWorkflow
from ..workflow.engine import Engine, RunResult
from ..workflow.errors import WorkflowExecutionError
from ..workflow.observers import ExecutionEvent, ExecutionObserver, ProviderTurnEvent, StepCompletedEvent, TerminalEvent
from ..workflow.providers.protocols import LLMProvider

from .autoloop_v1_conventions import autoloop_v1_session_path


DECISIONS_VERSION = 1
_DECISIONS_HEADER_RE = re.compile(r"<autoloop-decisions-header\b([^>]*)/>")
_DECISIONS_ATTR_RE = re.compile(r'([a-zA-Z0-9_]+)="([^"]*)"')


@dataclass(frozen=True, slots=True)
class AutoloopV1Workspace:
    task: TaskWorkspace
    task_raw_log: Path
    decisions_file: Path


@dataclass(frozen=True, slots=True)
class AutoloopV1RunWorkspace:
    workspace: AutoloopV1Workspace
    run: RunWorkspace
    run_raw_log: Path
    plan_session_file: Path


class _AutoloopV1ParityObserver(ExecutionObserver):
    """Observer that rebuilds Autoloop-v1 parity from generic execution facts."""

    def __init__(
        self,
        *,
        compiled: CompiledWorkflow,
        logger: EventLogger,
        run: AutoloopV1RunWorkspace,
    ) -> None:
        self._compiled = compiled
        self._logger = logger
        self._run = run
        self._step_progress: dict[tuple[str, str, str | None], tuple[int, int]] = {}
        self._last_turn_kind: dict[tuple[str, str | None], str] = {}

    def record(self, event: ExecutionEvent) -> None:
        if isinstance(event, ProviderTurnEvent):
            self._record_provider_turn(event)
            return
        if isinstance(event, StepCompletedEvent):
            self._record_step_completed(event)
            return
        self._record_terminal(event)

    def _record_provider_turn(self, event: ProviderTurnEvent) -> None:
        binding = event.response_session or event.request_session
        key = self._progress_key(event.step_name, binding)
        cycle, attempt = self._advance_progress(key, event.turn_kind)
        self._last_turn_kind[(event.step_name, _phase_id(event.state))] = event.turn_kind
        for raw_log in (self._run.workspace.task_raw_log, self._run.run_raw_log):
            _append_runtime_raw_log(
                raw_log,
                event.run_id,
                "phase_output",
                event.raw_output,
                pair=event.step_name,
                phase=event.turn_kind,
                cycle=cycle,
                attempt=attempt,
                thread_id=_thread_id(binding),
            )

    def _record_step_completed(self, event: StepCompletedEvent) -> None:
        current_phase_id = _phase_id(event.state_before)
        next_phase_id = _phase_id(event.state_after)
        step_fields: dict[str, object] = {
            "workflow": event.workflow_name,
            "step_name": event.step_name,
        }
        step_phase_id = _step_phase_id(event.step_name, current_phase_id, next_phase_id, event.event)
        if step_phase_id is not None:
            step_fields["phase_id"] = step_phase_id
        self._logger.emit("step_executed", **step_fields)

        if event.step_name == "activate_next_phase" and event.event is not None and event.event.tag == "phase_selected":
            if next_phase_id is not None:
                self._logger.emit(
                    "phase_started",
                    workflow=event.workflow_name,
                    pair="implement",
                    phase_id=next_phase_id,
                )

        if event.step_name == "test" and event.outcome is not None and event.outcome.tag == "phase_passed":
            completed_phase_id = current_phase_id or next_phase_id
            if completed_phase_id is not None:
                self._logger.emit(
                    "phase_completed",
                    workflow=event.workflow_name,
                    pair="test",
                    phase_id=completed_phase_id,
                )

    def _record_terminal(self, event: TerminalEvent) -> None:
        step_name = event.history[-1] if event.history else None
        phase_id = _phase_id(event.state)

        if step_name is not None and event.last_event is not None and event.last_event.tag in {"question", "blocked", "failed"}:
            self._logger.emit(
                event.last_event.tag,
                workflow=event.workflow_name,
                step_name=step_name,
                phase_id=phase_id,
                reason=event.last_event.reason or None,
                question=event.last_event.question,
            )
            self._append_terminal_notice(step_name, event)

        if event.terminal_kind == "fatal":
            self._logger.emit(
                "run_finished",
                workflow=event.workflow_name,
                status="fatal_error",
                error_type=event.exception_type,
                error=event.exception_message,
            )
            return

        self._logger.emit(
            "run_finished",
            workflow=event.workflow_name,
            terminal=event.terminal_kind.upper(),
            status=_autoloop_terminal_status(event),
            last_step=step_name,
            phase_id=phase_id,
        )

    def _append_terminal_notice(self, step_name: str, event: TerminalEvent) -> None:
        if event.last_event is None:
            return
        body = event.last_event.question or event.last_event.reason or ""
        if not body and event.last_outcome is not None:
            body = event.last_outcome.raw_output
        phase_name = self._last_turn_kind.get((step_name, _phase_id(event.state)), "runtime")
        cycle, attempt = self._progress_for_terminal(step_name, event.state)
        for raw_log in (self._run.workspace.task_raw_log, self._run.run_raw_log):
            _append_runtime_raw_log(
                raw_log,
                event.run_id,
                event.last_event.tag,
                body,
                pair=step_name,
                phase=phase_name,
                cycle=cycle,
                attempt=attempt,
            )

    @staticmethod
    def _progress_key(step_name: str, binding: Any) -> tuple[str, str, str | None]:
        if binding is None:
            return step_name, "", None
        return step_name, binding.ref_name, binding.scope

    def _advance_progress(self, key: tuple[str, str, str | None], turn_kind: str) -> tuple[int, int]:
        current_cycle, current_attempt = self._step_progress.get(key, (0, 1))
        if turn_kind in {"producer", "llm"}:
            next_progress = (current_cycle + 1, 1)
        else:
            next_progress = (current_cycle or 1, current_attempt or 1)
        self._step_progress[key] = next_progress
        return next_progress

    def _progress_for_terminal(self, step_name: str, state: BaseModel | None) -> tuple[int, int]:
        step = self._compiled.steps.get(step_name)
        if step is None or step.session_name is None:
            return 1, 1
        scope = _phase_id(state) if step.session_name == "phase_session" else None
        return self._step_progress.get((step_name, step.session_name, scope), (1, 1))


def run_autoloop_v1(
    workflow_target: str | Path,
    *,
    provider: LLMProvider,
    options: RunnerOptions,
) -> RunResult:
    max_steps = _resolve_max_steps(options.max_steps)
    workspace, run = _prepare_autoloop_v1_workspaces(options)

    compiled = load_compiled_workflow(workflow_target, class_name=options.class_name)
    session_store = FilesystemSessionStore(run.run.run_dir, path_resolver=autoloop_v1_session_path)
    checkpoint_store = FilesystemCheckpointStore(run.run.checkpoint_file, compiled.state_cls)
    workflow_parent = Path(inspect.getfile(compiled.workflow_cls)).resolve().parent
    prompt_registry = FilesystemPromptRegistry(workflow_parent, workspace.task.root, Path.cwd())
    logger = EventLogger(run.run.run_id, run.run.events_file)
    observer = _AutoloopV1ParityObserver(compiled=compiled, logger=logger, run=run)
    engine = Engine(
        compiled,
        provider=provider,
        session_store=session_store,
        checkpoint_store=checkpoint_store,
        prompt_registry=prompt_registry,
        observers=(observer,),
    )

    logger.emit(
        "run_resumed" if options.resume else "run_started",
        workflow=compiled.workflow_name,
        task_id=workspace.task.task_id,
    )
    if options.resume:
        _append_resume_clarification(compiled, checkpoint_store, run, answer=options.answer)
        return engine.resume(
            task_id=workspace.task.task_id,
            run_id=run.run.run_id,
            task_folder=workspace.task.task_dir,
            run_folder=run.run.run_dir,
            answer=options.answer,
            max_steps=max_steps,
        )
    return engine.run(
        task_id=workspace.task.task_id,
        run_id=run.run.run_id,
        task_folder=workspace.task.task_dir,
        run_folder=run.run.run_dir,
        max_steps=max_steps,
    )


def ensure_autoloop_v1_workspace(
    root: Path,
    task_id: str,
    product_intent: str | None = None,
    intent_mode: str = "replace",
    *,
    state_dir: Path | None = None,
) -> AutoloopV1Workspace:
    task = ensure_workspace(
        root,
        task_id,
        product_intent=product_intent,
        intent_mode=intent_mode,
        state_dir=state_dir,
    )
    task_raw_log = task.task_dir / "raw_phase_log.md"
    if not task_raw_log.exists():
        task_raw_log.write_text("# Autoloop Raw Phase Log\n", encoding="utf-8")
    decisions_file = task.task_dir / "decisions.txt"
    if not decisions_file.exists():
        decisions_file.write_text("", encoding="utf-8")
    _set_phase_plan_path(task)
    return AutoloopV1Workspace(task=task, task_raw_log=task_raw_log, decisions_file=decisions_file)


def create_autoloop_v1_run(
    workspace: AutoloopV1Workspace,
    *,
    run_id: str | None = None,
    request_text: str | None = None,
) -> AutoloopV1RunWorkspace:
    run = create_run(workspace.task, run_id=run_id, request_text=request_text)
    run_raw_log = run.run_dir / "raw_phase_log.md"
    run_raw_log.write_text(f"# Autoloop Raw Phase Log ({run.run_id})\n", encoding="utf-8")
    plan_session_file = autoloop_v1_session_path(run.run_dir, "plan_session", None)
    ensure_session_payload_placeholder(plan_session_file)
    return AutoloopV1RunWorkspace(
        workspace=workspace,
        run=run,
        run_raw_log=run_raw_log,
        plan_session_file=plan_session_file,
    )


def open_existing_autoloop_v1_run(workspace: AutoloopV1Workspace, run_id: str) -> AutoloopV1RunWorkspace:
    run = open_existing_run(workspace.task, run_id)
    run_raw_log = run.run_dir / "raw_phase_log.md"
    if not run_raw_log.exists():
        run_raw_log.write_text(f"# Autoloop Raw Phase Log ({run.run_id})\n", encoding="utf-8")
    plan_session_file = autoloop_v1_session_path(run.run_dir, "plan_session", None)
    ensure_session_payload_placeholder(plan_session_file)
    return AutoloopV1RunWorkspace(
        workspace=workspace,
        run=run,
        run_raw_log=run_raw_log,
        plan_session_file=plan_session_file,
    )


def _prepare_autoloop_v1_workspaces(options: RunnerOptions) -> tuple[AutoloopV1Workspace, AutoloopV1RunWorkspace]:
    if not options.resume:
        workspace = _ensure_autoloop_workspace_for_options(options)
        run = create_autoloop_v1_run(
            workspace,
            run_id=options.run_id,
            request_text=options.request_text
            or task_request_text(workspace.task.task_meta_file, workspace.task.legacy_context_file),
        )
        return workspace, run

    root = options.root.resolve()
    state_dir = options.state_dir
    if state_dir is None:
        state_dir = resolve_resume_state_root(root, task_id=options.task_id, run_id=options.run_id)
    run_id = options.run_id or ""
    run_dir = state_dir / "tasks" / options.task_id / "runs" / run_id
    _validate_resume_state(run_dir)
    workspace = ensure_autoloop_v1_workspace(
        root,
        options.task_id,
        product_intent=options.request_text,
        intent_mode=options.intent_mode,
        state_dir=state_dir,
    )
    return workspace, open_existing_autoloop_v1_run(workspace, run_id)


def _ensure_autoloop_workspace_for_options(options: RunnerOptions) -> AutoloopV1Workspace:
    root = options.root.resolve()
    state_dir = options.state_dir
    if options.resume and state_dir is None:
        state_dir = resolve_resume_state_root(root, task_id=options.task_id, run_id=options.run_id)
    return ensure_autoloop_v1_workspace(
        root,
        options.task_id,
        product_intent=options.request_text,
        intent_mode=options.intent_mode,
        state_dir=state_dir,
    )


def _resolve_max_steps(max_steps: int | None) -> int:
    if max_steps is None:
        return DEFAULT_MAX_STEPS
    if max_steps <= 0:
        raise WorkflowExecutionError("max_steps must be a positive integer.")
    return max_steps


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
            "This run only has persisted session or event state, which the strict engine does not reconstruct "
            "without a checkpoint. Resume it from a checkpointed run or start a new run."
        )


def _append_resume_clarification(
    compiled: CompiledWorkflow,
    checkpoint_store: FilesystemCheckpointStore,
    run: AutoloopV1RunWorkspace,
    *,
    answer: str | None,
) -> None:
    if answer is None:
        return
    checkpoint = checkpoint_store.load()
    if checkpoint is None or checkpoint.pending_question is None:
        return
    step = compiled.steps.get(checkpoint.stage)
    if step is None or step.session_name is None:
        return
    scope = checkpoint.session_bindings.active_scopes.get(step.session_name)
    cycle, attempt = _latest_logged_progress(
        run.run_raw_log,
        entry="question",
        pair=checkpoint.stage,
        phase="verifier" if step.kind == "pair" else "llm",
    )
    session_file = autoloop_v1_session_path(run.run.run_dir, step.session_name, scope)
    _append_clarification(
        run_raw_phase_log=run.run_raw_log,
        task_raw_phase_log=run.workspace.task_raw_log,
        decisions_path=run.workspace.decisions_file,
        session_file=session_file,
        pair=checkpoint.stage,
        phase_id=_phase_id(checkpoint.state) or "plan",
        phase="verifier" if step.kind == "pair" else "llm",
        cycle=cycle,
        attempt=attempt,
        question=checkpoint.pending_question,
        answer=answer,
        run_id=run.run.run_id,
        source="resume",
    )


def _append_clarification(
    *,
    run_raw_phase_log: Path,
    task_raw_phase_log: Path,
    decisions_path: Path,
    session_file: Path,
    pair: str,
    phase_id: str,
    phase: str,
    cycle: int,
    attempt: int,
    question: str,
    answer: str,
    run_id: str,
    source: str,
) -> str:
    note = f"Question:\n{question}\n\nAnswer:\n{answer}"
    body = f"{note}\n"
    for raw_log in (task_raw_phase_log, run_raw_phase_log):
        _append_runtime_raw_log(
            raw_log,
            run_id,
            "clarification",
            body,
            pair=pair,
            phase=phase,
            cycle=cycle,
            attempt=attempt,
            source=source,
        )
    turn_seq, qa_seq = _append_decisions_runtime_block(
        decisions_path,
        pair=pair,
        phase_id=phase_id,
        run_id=run_id,
        entry="questions",
        body=question,
        source=source,
    )
    _append_decisions_runtime_block(
        decisions_path,
        pair=pair,
        phase_id=phase_id,
        run_id=run_id,
        entry="answers",
        body=answer,
        turn_seq=turn_seq,
        qa_seq=qa_seq,
        source=source,
    )
    set_pending_session_note(session_file, note)
    return note


def _append_runtime_raw_log(
    raw_phase_log: Path,
    run_id: str,
    entry: str,
    body: str,
    *,
    pair: str | None = None,
    phase: str | None = None,
    cycle: int | None = None,
    attempt: int | None = None,
    thread_id: str | None = None,
    source: str | None = None,
) -> None:
    _append_raw_log_entry(
        raw_phase_log,
        body,
        run_id=run_id,
        entry=entry,
        pair=pair,
        phase=phase,
        cycle=cycle,
        attempt=attempt,
        thread_id=thread_id,
        source=source,
    )


def _append_raw_log_entry(raw_phase_log: Path, body: str, **fields: object) -> None:
    header = " | ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
    raw_phase_log.parent.mkdir(parents=True, exist_ok=True)
    with raw_phase_log.open("a", encoding="utf-8") as handle:
        handle.write("\n\n---\n")
        handle.write(f"{header}\n")
        handle.write("---\n")
        text = body if body else "[empty stdout]\n"
        handle.write(text)
        if not text.endswith("\n"):
            handle.write("\n")


def _append_decisions_runtime_block(
    decisions_path: Path,
    *,
    pair: str,
    phase_id: str,
    run_id: str,
    entry: str,
    body: str,
    turn_seq: int | None = None,
    qa_seq: int | None = None,
    source: str | None = None,
) -> tuple[int, int]:
    headers = _read_decisions_headers(decisions_path)
    if turn_seq is None:
        turn_seq = 1 + max(
            (
                int(header.get("turn_seq", "0"))
                for header in headers
                if header.get("run_id") == run_id and header.get("pair") == pair and header.get("phase_id") == phase_id
            ),
            default=0,
        )
    if qa_seq is None:
        qa_seq = 1 + max((int(header.get("qa_seq", "0")) for header in headers if "qa_seq" in header), default=0)
    block_seq = 1 + max((int(header.get("block_seq", "0")) for header in headers if "block_seq" in header), default=0)
    stamp = datetime.now(timezone.utc).isoformat()
    header = _format_decisions_header(
        {
            "version": str(DECISIONS_VERSION),
            "block_seq": str(block_seq),
            "owner": "runtime",
            "phase_id": phase_id,
            "pair": pair,
            "turn_seq": str(turn_seq),
            "run_id": run_id,
            "ts": stamp,
            "entry": entry,
            "qa_seq": str(qa_seq),
            "source": source or "runtime",
        }
    )
    decisions_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_body = body if body.endswith("\n") else f"{body}\n"
    with decisions_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{header}\n")
        handle.write(normalized_body)
    return turn_seq, qa_seq


def _read_decisions_headers(decisions_path: Path) -> list[dict[str, str]]:
    if not decisions_path.exists():
        return []
    text = decisions_path.read_text(encoding="utf-8")
    headers: list[dict[str, str]] = []
    for match in _DECISIONS_HEADER_RE.finditer(text):
        headers.append({key: value for key, value in _DECISIONS_ATTR_RE.findall(match.group(1))})
    return headers


def _format_decisions_header(attrs: dict[str, str | None]) -> str:
    rendered = " ".join(f'{key}="{value}"' for key, value in attrs.items() if value is not None)
    return f"<autoloop-decisions-header {rendered} />"


def _autoloop_terminal_status(event: TerminalEvent) -> str:
    if event.terminal_kind == "success":
        return "success"
    if event.terminal_kind == "fail":
        return "failed"
    if event.last_event is not None and event.last_event.tag == "blocked":
        return "blocked"
    return "paused"


def _thread_id(binding: Any) -> str | None:
    if binding is None:
        return None
    return binding.session_id


def _step_phase_id(
    step_name: str,
    current_phase_id: str | None,
    next_phase_id: str | None,
    event: Any,
) -> str | None:
    if step_name == "activate_next_phase" and event is not None and getattr(event, "tag", None) == "phase_selected":
        return next_phase_id
    return current_phase_id or next_phase_id


def _phase_id(state: BaseModel | object | None) -> str | None:
    if state is None:
        return None
    phase = getattr(state, "phase", None)
    phase_id = getattr(phase, "id", None)
    return phase_id if isinstance(phase_id, str) and phase_id else None


def _set_phase_plan_path(task: TaskWorkspace) -> None:
    if not task.task_meta_file.exists():
        return
    try:
        payload = json.loads(task.task_meta_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload.setdefault("phase_plan_path", str(task.task_root_rel / "plan" / "phase_plan.yaml"))
    task.task_meta_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _latest_logged_progress(
    raw_phase_log: Path,
    *,
    entry: str,
    pair: str,
    phase: str,
) -> tuple[int, int]:
    if not raw_phase_log.exists():
        return 1, 1
    latest = (1, 1)
    for line in raw_phase_log.read_text(encoding="utf-8").splitlines():
        if " | " not in line or "run_id=" not in line:
            continue
        fields: dict[str, str] = {}
        for item in line.split(" | "):
            key, _, value = item.partition("=")
            if key and value:
                fields[key] = value
        if fields.get("entry") != entry or fields.get("pair") != pair or fields.get("phase") != phase:
            continue
        latest = (int(fields.get("cycle", "1")), int(fields.get("attempt", "1")))
    return latest


__all__ = ["run_autoloop_v1"]
