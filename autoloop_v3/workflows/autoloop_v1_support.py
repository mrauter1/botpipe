"""Autoloop-v1 workflow helpers and parity runtime."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ..runtime.config import DEFAULT_MAX_STEPS
from ..runtime.events import EventLogger
from ..runtime.loader import load_compiled_workflow
from ..runtime.prompts import FilesystemPromptRegistry
from ..runtime.runner import RunnerOptions
from ..runtime.stores.filesystem import FilesystemCheckpointStore, FilesystemSessionStore, load_session_payload, scope_key
from ..runtime.workspace import (
    TaskWorkspace,
    create_run,
    ensure_workspace,
    open_existing_run,
    resolve_resume_state_root,
    task_request_text,
)
from ..workflow.compiler import CompiledStep
from ..workflow.engine import Engine, RunResult
from ..workflow.errors import WorkflowExecutionError
from ..workflow.providers.models import LLMRequest, OutcomeResponse, ProducerRequest, ProducerResponse, VerifierRequest
from ..workflow.providers.protocols import LLMProvider
from ..workflow.stores.protocols import SessionBinding


IMPLICIT_PHASE_ID = "implicit-phase"
PHASE_DIR_SAFE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
MAX_PHASE_ID_UTF8_BYTES = 96
DECISIONS_VERSION = 1
_DECISIONS_HEADER_RE = re.compile(r"<autoloop-decisions-header\b([^>]*)/>")
_DECISIONS_ATTR_RE = re.compile(r'([a-zA-Z0-9_]+)="([^"]*)"')
_AUTOLOOP_PROVIDER_METADATA_KEY = "autoloop_v1"
_AUTOLOOP_CYCLE_KEY = "step_cycles"
_AUTOLOOP_ATTEMPT_KEY = "step_attempts"


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


def parse_phase_ids(text: str) -> list[str]:
    """Extract phase ids from phase_plan content, defaulting to the implicit phase."""

    import yaml

    try:
        data = yaml.safe_load(text)
    except Exception:
        return [IMPLICIT_PHASE_ID]

    if not isinstance(data, dict):
        return [IMPLICIT_PHASE_ID]

    phases = data.get("phases")
    if not isinstance(phases, list) or not phases:
        return [IMPLICIT_PHASE_ID]

    phase_ids: list[str] = []
    for item in phases:
        if not isinstance(item, dict):
            continue
        phase_id = item.get("phase_id")
        if isinstance(phase_id, str) and phase_id.strip():
            phase_ids.append(phase_id.strip())
    return phase_ids or [IMPLICIT_PHASE_ID]


def phase_dir_key(phase_id: str) -> str:
    normalized = phase_id.strip()
    if not normalized:
        raise ValueError("phase_id must be non-empty")
    if len(normalized.encode("utf-8")) > MAX_PHASE_ID_UTF8_BYTES:
        raise ValueError(f"phase_id {normalized!r} exceeds {MAX_PHASE_ID_UTF8_BYTES} UTF-8 bytes")
    if PHASE_DIR_SAFE_RE.fullmatch(normalized):
        return normalized
    return f"_pid-{normalized.encode('utf-8').hex()}"


def phase_artifact_template(pair: str, filename: str) -> str:
    return f"{{task_folder}}/{pair}/phases/{{state.phase.dir_key}}/{filename}"


def autoloop_v1_session_path(run_dir: Path, ref_name: str, scope: str | None) -> Path:
    sessions_dir = run_dir / "sessions"
    if ref_name == "plan_session" and scope is None:
        return sessions_dir / "plan.json"
    if ref_name == "phase_session" and scope is not None:
        return sessions_dir / "phases" / f"{phase_dir_key(scope)}.json"
    if scope is None:
        return sessions_dir / f"{ref_name}.json"
    return sessions_dir / "scopes" / scope_key(scope) / f"{ref_name}.json"


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
    _ensure_session_placeholder(plan_session_file)
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
    _ensure_session_placeholder(plan_session_file)
    return AutoloopV1RunWorkspace(
        workspace=workspace,
        run=run,
        run_raw_log=run_raw_log,
        plan_session_file=plan_session_file,
    )


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
    workflow_parent = Path(workflow_target).resolve().parent if Path(str(workflow_target)).exists() else Path.cwd()
    prompt_registry = FilesystemPromptRegistry(workflow_parent, workspace.task.root, Path.cwd())
    logger = EventLogger(run.run.run_id, run.run.events_file)
    logging_provider = _AutoloopV1LoggingProvider(provider, run)
    engine = _AutoloopV1Engine(
        compiled,
        provider=logging_provider,
        session_store=session_store,
        checkpoint_store=checkpoint_store,
        prompt_registry=prompt_registry,
        logger=logger,
    )

    logger.emit(
        "run_resumed" if options.resume else "run_started",
        workflow=compiled.workflow_name,
        task_id=workspace.task.task_id,
    )
    try:
        if options.resume:
            _append_resume_clarification(compiled, checkpoint_store, run, answer=options.answer)
            result = engine.resume(
                task_id=workspace.task.task_id,
                run_id=run.run.run_id,
                task_folder=workspace.task.task_dir,
                run_folder=run.run.run_dir,
                answer=options.answer,
                max_steps=max_steps,
            )
        else:
            result = engine.run(
                task_id=workspace.task.task_id,
                run_id=run.run.run_id,
                task_folder=workspace.task.task_dir,
                run_folder=run.run.run_dir,
                max_steps=max_steps,
            )

        if result.last_event is not None and result.last_event.tag in {"question", "blocked", "failed"}:
            logger.emit(
                result.last_event.tag,
                workflow=compiled.workflow_name,
                step_name=result.history[-1] if result.history else None,
                phase_id=_phase_id(result.state),
                reason=result.last_event.reason or None,
                question=result.last_event.question,
            )
            _append_terminal_notice(compiled, run, result, logging_provider)

        logger.emit(
            "run_finished",
            workflow=compiled.workflow_name,
            terminal=result.terminal,
            status=_autoloop_run_status(result),
            last_step=result.history[-1] if result.history else None,
            phase_id=_phase_id(result.state),
        )
        return result
    except Exception as exc:
        logger.emit(
            "run_finished",
            workflow=compiled.workflow_name,
            status="fatal_error",
            error_type=type(exc).__name__,
            error=str(exc),
        )
        raise


class _AutoloopV1LoggingProvider:
    """Provider wrapper that records legacy-style raw logs without polluting the core engine."""

    def __init__(self, delegate: LLMProvider, run: AutoloopV1RunWorkspace) -> None:
        self._delegate = delegate
        self._run = run
        self._last_phase_name: dict[tuple[str, str | None], str] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    def run_producer(self, request: ProducerRequest) -> ProducerResponse:
        response = self._delegate.run_producer(request)
        session, cycle, attempt = self._advance_step_progress(request.step_name, response.session or request.session)
        if session is not None:
            response = replace(response, session=session)
        self._last_phase_name[(request.step_name, _phase_id(request.context.state))] = "producer"
        _append_runtime_raw_log(
            self._run.workspace.task_raw_log,
            self._run.run.run_id,
            "phase_output",
            response.raw_output,
            pair=request.step_name,
            phase="producer",
            cycle=cycle,
            attempt=attempt,
            thread_id=_thread_id(session),
        )
        _append_runtime_raw_log(
            self._run.run_raw_log,
            self._run.run.run_id,
            "phase_output",
            response.raw_output,
            pair=request.step_name,
            phase="producer",
            cycle=cycle,
            attempt=attempt,
            thread_id=_thread_id(session),
        )
        return response

    def run_verifier(self, request: VerifierRequest) -> OutcomeResponse:
        response = self._delegate.run_verifier(request)
        session, cycle, attempt = self._current_step_progress(request.step_name, response.session or request.session)
        if session is not None:
            response = replace(response, session=session)
        self._last_phase_name[(request.step_name, _phase_id(request.context.state))] = "verifier"
        _append_runtime_raw_log(
            self._run.workspace.task_raw_log,
            self._run.run.run_id,
            "phase_output",
            response.outcome.raw_output,
            pair=request.step_name,
            phase="verifier",
            cycle=cycle,
            attempt=attempt,
            thread_id=_thread_id(session),
        )
        _append_runtime_raw_log(
            self._run.run_raw_log,
            self._run.run.run_id,
            "phase_output",
            response.outcome.raw_output,
            pair=request.step_name,
            phase="verifier",
            cycle=cycle,
            attempt=attempt,
            thread_id=_thread_id(session),
        )
        return response

    def run_llm(self, request: LLMRequest) -> OutcomeResponse:
        response = self._delegate.run_llm(request)
        session, cycle, attempt = self._advance_step_progress(request.step_name, response.session or request.session)
        if session is not None:
            response = replace(response, session=session)
        self._last_phase_name[(request.step_name, _phase_id(request.context.state))] = "llm"
        _append_runtime_raw_log(
            self._run.workspace.task_raw_log,
            self._run.run.run_id,
            "phase_output",
            response.outcome.raw_output,
            pair=request.step_name,
            phase="llm",
            cycle=cycle,
            attempt=attempt,
            thread_id=_thread_id(session),
        )
        _append_runtime_raw_log(
            self._run.run_raw_log,
            self._run.run.run_id,
            "phase_output",
            response.outcome.raw_output,
            pair=request.step_name,
            phase="llm",
            cycle=cycle,
            attempt=attempt,
            thread_id=_thread_id(session),
        )
        return response

    def current_phase_name(self, step_name: str, state: BaseModel) -> str:
        return self._last_phase_name.get((step_name, _phase_id(state)), "runtime")

    def _advance_step_progress(
        self,
        step_name: str,
        session: SessionBinding | None,
    ) -> tuple[SessionBinding | None, int, int]:
        if session is None:
            return None, 1, 1
        cycle = _binding_step_counter(session, step_name, counter=_AUTOLOOP_CYCLE_KEY, default=0) + 1
        attempt = 1
        updated = _binding_with_step_progress(session, step_name, cycle=cycle, attempt=attempt)
        return updated, cycle, attempt

    def _current_step_progress(
        self,
        step_name: str,
        session: SessionBinding | None,
    ) -> tuple[SessionBinding | None, int, int]:
        if session is None:
            return None, 1, 1
        cycle = _binding_step_counter(session, step_name, counter=_AUTOLOOP_CYCLE_KEY, default=1)
        attempt = _binding_step_counter(session, step_name, counter=_AUTOLOOP_ATTEMPT_KEY, default=1)
        updated = _binding_with_step_progress(session, step_name, cycle=cycle, attempt=attempt)
        return updated, cycle, attempt


class _AutoloopV1Engine(Engine):
    """Workflow-owned event emitter for Autoloop-v1 parity."""

    def __init__(self, *args: Any, logger: EventLogger, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._logger = logger

    def _execute_step(
        self,
        step: CompiledStep,
        context: Any,
        state: BaseModel,
    ) -> tuple[BaseModel, str, Any, Any]:
        current_phase_id = _phase_id(state)
        next_state, destination, event, outcome = super()._execute_step(step, context, state)
        next_phase_id = _phase_id(next_state)

        step_fields: dict[str, object] = {
            "workflow": self.compiled.workflow_name,
            "step_name": step.name,
        }
        step_phase_id = _step_phase_id(step.name, current_phase_id, next_phase_id, event)
        if step_phase_id is not None:
            step_fields["phase_id"] = step_phase_id
        self._logger.emit("step_executed", **step_fields)

        if step.name == "activate_next_phase" and event is not None and event.tag == "phase_selected" and next_phase_id is not None:
            self._logger.emit(
                "phase_started",
                workflow=self.compiled.workflow_name,
                pair="implement",
                phase_id=next_phase_id,
            )
        if step.name == "test" and outcome is not None and outcome.tag == "phase_passed":
            completed_phase_id = current_phase_id or next_phase_id
            if completed_phase_id is not None:
                self._logger.emit(
                    "phase_completed",
                    workflow=self.compiled.workflow_name,
                    pair="test",
                    phase_id=completed_phase_id,
                )
        return next_state, destination, event, outcome


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


def _append_terminal_notice(
    compiled: Any,
    run: AutoloopV1RunWorkspace,
    result: RunResult,
    logging_provider: _AutoloopV1LoggingProvider,
) -> None:
    if not result.history or result.last_event is None:
        return
    step_name = result.history[-1]
    body = result.last_event.question or result.last_event.reason or ""
    if not body and result.last_outcome is not None:
        body = result.last_outcome.raw_output
    phase_name = logging_provider.current_phase_name(step_name, result.state)
    cycle, attempt = _step_progress_for_state(compiled, run.run.run_dir, step_name, result.state)
    for raw_log in (run.workspace.task_raw_log, run.run_raw_log):
        _append_runtime_raw_log(
            raw_log,
            run.run.run_id,
            result.last_event.tag,
            body,
            pair=step_name,
            phase=phase_name,
            cycle=cycle,
            attempt=attempt,
        )


def _append_resume_clarification(
    compiled: Any,
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
    session_file = autoloop_v1_session_path(run.run.run_dir, step.session_name, scope)
    _append_clarification(
        run_raw_phase_log=run.run_raw_log,
        task_raw_phase_log=run.workspace.task_raw_log,
        decisions_path=run.workspace.decisions_file,
        session_file=session_file,
        pair=checkpoint.stage,
        phase_id=_phase_id(checkpoint.state) or "plan",
        phase="verifier" if step.kind == "pair" else "llm",
        cycle=_session_step_counter(session_file, checkpoint.stage, counter=_AUTOLOOP_CYCLE_KEY, default=1),
        attempt=_session_step_counter(session_file, checkpoint.stage, counter=_AUTOLOOP_ATTEMPT_KEY, default=1),
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
    payload = load_session_payload(session_file, default_mode="persistent", default_provider="codex")
    metadata = dict(payload["metadata"])
    metadata["pending_clarification_note"] = note
    _write_session_payload(session_file, payload["session_id"], metadata)
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
        attrs = {key: value for key, value in _DECISIONS_ATTR_RE.findall(match.group(1))}
        headers.append(attrs)
    return headers


def _format_decisions_header(attrs: dict[str, str | None]) -> str:
    rendered = " ".join(f'{key}="{value}"' for key, value in attrs.items() if value is not None)
    return f"<autoloop-decisions-header {rendered} />"


def _autoloop_run_status(result: RunResult) -> str:
    if result.terminal == "SUCCESS":
        return "success"
    if result.terminal == "FAIL":
        return "failed"
    if result.last_event is not None and result.last_event.tag == "blocked":
        return "blocked"
    return "paused"


def _thread_id(binding: SessionBinding | None) -> str | None:
    if binding is None:
        return None
    return binding.session_id


def _binding_step_counter(
    binding: SessionBinding,
    step_name: str,
    *,
    counter: str,
    default: int,
) -> int:
    provider_metadata = binding.metadata.get("provider_metadata")
    if not isinstance(provider_metadata, dict):
        return default
    autoloop_metadata = provider_metadata.get(_AUTOLOOP_PROVIDER_METADATA_KEY)
    if not isinstance(autoloop_metadata, dict):
        return default
    counters = autoloop_metadata.get(counter)
    if not isinstance(counters, dict):
        return default
    value = counters.get(step_name)
    return value if isinstance(value, int) and value > 0 else default


def _binding_with_step_progress(
    binding: SessionBinding,
    step_name: str,
    *,
    cycle: int,
    attempt: int,
) -> SessionBinding:
    metadata = dict(binding.metadata)
    provider_metadata = metadata.get("provider_metadata")
    if not isinstance(provider_metadata, dict):
        provider_metadata = {}
    else:
        provider_metadata = dict(provider_metadata)
    autoloop_metadata = provider_metadata.get(_AUTOLOOP_PROVIDER_METADATA_KEY)
    if not isinstance(autoloop_metadata, dict):
        autoloop_metadata = {}
    else:
        autoloop_metadata = dict(autoloop_metadata)
    cycles = autoloop_metadata.get(_AUTOLOOP_CYCLE_KEY)
    if not isinstance(cycles, dict):
        cycles = {}
    else:
        cycles = dict(cycles)
    attempts = autoloop_metadata.get(_AUTOLOOP_ATTEMPT_KEY)
    if not isinstance(attempts, dict):
        attempts = {}
    else:
        attempts = dict(attempts)
    cycles[step_name] = cycle
    attempts[step_name] = attempt
    autoloop_metadata[_AUTOLOOP_CYCLE_KEY] = cycles
    autoloop_metadata[_AUTOLOOP_ATTEMPT_KEY] = attempts
    provider_metadata[_AUTOLOOP_PROVIDER_METADATA_KEY] = autoloop_metadata
    metadata["provider_metadata"] = provider_metadata
    return replace(binding, metadata=metadata)


def _session_step_counter(
    session_file: Path,
    step_name: str,
    *,
    counter: str,
    default: int,
) -> int:
    payload = load_session_payload(session_file, default_mode="persistent", default_provider="codex")
    binding = SessionBinding(
        ref_name=session_file.stem,
        scope=None,
        session_id=payload["session_id"] or "",
        metadata=dict(payload["metadata"]),
    )
    return _binding_step_counter(binding, step_name, counter=counter, default=default)


def _step_phase_id(
    step_name: str,
    current_phase_id: str | None,
    next_phase_id: str | None,
    event: Any,
) -> str | None:
    if step_name == "activate_next_phase" and event is not None and getattr(event, "tag", None) == "phase_selected":
        return next_phase_id
    return current_phase_id or next_phase_id


def _step_progress_for_state(
    compiled: Any,
    run_dir: Path,
    step_name: str,
    state: BaseModel,
) -> tuple[int, int]:
    step = compiled.steps.get(step_name)
    if step is None or step.session_name is None:
        return 1, 1
    scope = _phase_id(state) if step.session_name == "phase_session" else None
    session_file = autoloop_v1_session_path(run_dir, step.session_name, scope)
    return (
        _session_step_counter(session_file, step_name, counter=_AUTOLOOP_CYCLE_KEY, default=1),
        _session_step_counter(session_file, step_name, counter=_AUTOLOOP_ATTEMPT_KEY, default=1),
    )


def _phase_id(state: BaseModel | object) -> str | None:
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


def _ensure_session_placeholder(path: Path) -> None:
    payload = load_session_payload(path, default_mode="persistent", default_provider="codex")
    _write_session_payload(path, payload["session_id"], payload["metadata"])


def _write_session_payload(path: Path, session_id: str | None, metadata: dict[str, Any]) -> None:
    provider = metadata.get("provider") if isinstance(metadata.get("provider"), str) else "codex"
    provider_metadata = metadata.get("provider_metadata")
    if not isinstance(provider_metadata, dict):
        provider_metadata = {}
    payload = {
        "mode": metadata.get("mode") if isinstance(metadata.get("mode"), str) else "persistent",
        "provider": provider,
        "session_id": session_id,
        "thread_id": session_id if provider == "codex" else metadata.get("thread_id"),
        "provider_metadata": provider_metadata,
        "model_override": metadata.get("model_override") if isinstance(metadata.get("model_override"), str) else None,
        "effort_override": metadata.get("effort_override") if isinstance(metadata.get("effort_override"), str) else None,
        "pending_clarification_note": metadata.get("pending_clarification_note")
        if isinstance(metadata.get("pending_clarification_note"), str)
        else None,
        "created_at": metadata.get("created_at")
        if isinstance(metadata.get("created_at"), str)
        else datetime.now(timezone.utc).isoformat(),
        "last_used_at": metadata.get("last_used_at") if isinstance(metadata.get("last_used_at"), str) else None,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
