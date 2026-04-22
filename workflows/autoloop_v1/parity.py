"""Workflow-owned Autoloop-v1 parity harness."""

from __future__ import annotations

import json
import inspect
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

try:  # pragma: no branch - supports both `workflows.*` and `autoloop_v3.workflows.*` imports
    from autoloop_v3.core.compiler import CompiledWorkflow
    from autoloop_v3.core.engine import Engine, RunResult
    from autoloop_v3.core.errors import WorkflowExecutionError
    from autoloop_v3.core.extensions import RunBinding, StepFinish, StepStart, TerminalFinish
    from autoloop_v3.core.providers.models import (
        LLMRequest,
        OutcomeResponse,
        ProducerRequest,
        ProducerResponse,
        VerifierRequest,
    )
    from autoloop_v3.core.providers.protocols import LLMProvider
    from autoloop_v3.runtime.events import EventLogger
    from autoloop_v3.runtime.loader import load_compiled_workflow
    from autoloop_v3.runtime.runner import (
        RunnerOptions,
        prepare_runtime_services,
        resolve_max_steps,
        resolve_session_path_strategy,
        validate_resume_state,
    )
    from autoloop_v3.runtime.stores.filesystem import (
        FilesystemCheckpointStore,
        ensure_session_payload_placeholder,
        set_pending_session_note,
    )
    from autoloop_v3.runtime.workspace import (
        RunWorkspace,
        TaskWorkspace,
        WorkflowWorkspace,
        create_run,
        ensure_workspace,
        ensure_workflow_workspace,
        latest_run_id,
        update_run_metadata,
        open_existing_run,
        resolve_resume_state_root,
        task_request_text,
    )
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from core.compiler import CompiledWorkflow
    from core.engine import Engine, RunResult
    from core.errors import WorkflowExecutionError
    from core.extensions import RunBinding, StepFinish, StepStart, TerminalFinish
    from core.providers.models import LLMRequest, OutcomeResponse, ProducerRequest, ProducerResponse, VerifierRequest
    from core.providers.protocols import LLMProvider
    from runtime.events import EventLogger
    from runtime.loader import load_compiled_workflow
    from runtime.runner import (
        RunnerOptions,
        prepare_runtime_services,
        resolve_max_steps,
        resolve_session_path_strategy,
        validate_resume_state,
    )
    from runtime.stores.filesystem import (
        FilesystemCheckpointStore,
        ensure_session_payload_placeholder,
        set_pending_session_note,
    )
    from runtime.workspace import (
        RunWorkspace,
        TaskWorkspace,
        WorkflowWorkspace,
        create_run,
        ensure_workspace,
        ensure_workflow_workspace,
        latest_run_id,
        update_run_metadata,
        open_existing_run,
        resolve_resume_state_root,
        task_request_text,
    )

from .conventions import autoloop_v1_session_path


DECISIONS_VERSION = 1
_DECISIONS_HEADER_RE = re.compile(r"<autoloop-decisions-header\b([^>]*)/>")
_DECISIONS_ATTR_RE = re.compile(r'([a-zA-Z0-9_]+)="([^"]*)"')


@dataclass(frozen=True, slots=True)
class AutoloopV1Workspace:
    task: TaskWorkspace
    workflow: WorkflowWorkspace
    task_raw_log: Path
    decisions_file: Path


@dataclass(frozen=True, slots=True)
class AutoloopV1RunWorkspace:
    workspace: AutoloopV1Workspace
    run: RunWorkspace
    run_raw_log: Path
    plan_session_file: Path


@dataclass(slots=True)
class _AutoloopV1ParityRuntime:
    """Workflow-owned parity tracker rebuilt from provider turns and bound extensions."""

    compiled: CompiledWorkflow
    logger: EventLogger
    run: AutoloopV1RunWorkspace
    step_progress: dict[tuple[str, str, str | None], tuple[int, int]] = field(default_factory=dict)
    last_turn_kind: dict[tuple[str, str | None], str] = field(default_factory=dict)

    def record_provider_turn(
        self,
        *,
        step_name: str,
        turn_kind: str,
        run_id: str,
        state: BaseModel,
        binding: Any,
        raw_output: str,
    ) -> None:
        key = self._progress_key(step_name, binding)
        cycle, attempt = self._advance_progress(key, turn_kind)
        self.last_turn_kind[(step_name, _phase_id(state))] = turn_kind
        for raw_log in (self.run.workspace.task_raw_log, self.run.run_raw_log):
            _append_runtime_raw_log(
                raw_log,
                run_id,
                "phase_output",
                raw_output,
                pair=step_name,
                phase=turn_kind,
                cycle=cycle,
                attempt=attempt,
                thread_id=_thread_id(binding),
            )

    def record_step_completed(self, event: StepFinish) -> None:
        current_phase_id = _phase_id(event.state_before)
        next_phase_id = _phase_id(event.state_after)
        step_fields: dict[str, object] = {
            "workflow": event.binding.workflow_name,
            "step_name": event.step_name,
        }
        step_phase_id = _step_phase_id(event.step_name, current_phase_id, next_phase_id, event.event)
        if step_phase_id is not None:
            step_fields["phase_id"] = step_phase_id
        self.logger.emit("step_executed", **step_fields)

        if event.step_name == "activate_next_phase" and event.event is not None and event.event.tag == "phase_selected":
            if next_phase_id is not None:
                self.logger.emit(
                    "phase_started",
                    workflow=event.binding.workflow_name,
                    pair="implement",
                    phase_id=next_phase_id,
                )

        if event.step_name == "test" and event.outcome is not None and event.outcome.tag == "phase_passed":
            completed_phase_id = current_phase_id or next_phase_id
            if completed_phase_id is not None:
                self.logger.emit(
                    "phase_completed",
                    workflow=event.binding.workflow_name,
                    pair="test",
                    phase_id=completed_phase_id,
                )

    def record_terminal(self, event: TerminalFinish) -> None:
        step_name = event.step_name
        phase_id = _phase_id(event.state)

        if step_name is not None and event.event is not None and event.event.tag in {"question", "blocked", "failed"}:
            self.logger.emit(
                event.event.tag,
                workflow=event.binding.workflow_name,
                step_name=step_name,
                phase_id=phase_id,
                reason=event.event.reason or None,
                question=event.event.question,
            )
            self._append_terminal_notice(step_name, event)

        if event.terminal == "fatal":
            return

        self.logger.emit(
            "run_finished",
            workflow=event.binding.workflow_name,
            terminal=event.terminal,
            status=_autoloop_terminal_status(event),
            last_step=step_name,
            phase_id=phase_id,
        )

    def _append_terminal_notice(self, step_name: str, event: TerminalFinish) -> None:
        if event.event is None:
            return
        body = event.event.question or event.event.reason or ""
        if not body and event.outcome is not None:
            body = event.outcome.raw_output
        phase_name = self.last_turn_kind.get((step_name, _phase_id(event.state)), "runtime")
        cycle, attempt = self._progress_for_terminal(step_name, event.state)
        for raw_log in (self.run.workspace.task_raw_log, self.run.run_raw_log):
            _append_runtime_raw_log(
                raw_log,
                event.binding.run_id,
                event.event.tag,
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
        current_cycle, current_attempt = self.step_progress.get(key, (0, 1))
        if turn_kind in {"producer", "llm"}:
            next_progress = (current_cycle + 1, 1)
        else:
            next_progress = (current_cycle or 1, current_attempt or 1)
        self.step_progress[key] = next_progress
        return next_progress

    def _progress_for_terminal(self, step_name: str, state: BaseModel | None) -> tuple[int, int]:
        step = self.compiled.steps.get(step_name)
        if step is None or step.session_name is None:
            return 1, 1
        scope = _phase_id(state) if step.session_name == "phase_session" else None
        return self.step_progress.get((step_name, step.session_name, scope), (1, 1))


class _AutoloopV1LoggingProvider:
    """Workflow-owned provider wrapper for raw parity log reconstruction."""

    def __init__(self, provider: LLMProvider, parity: _AutoloopV1ParityRuntime) -> None:
        self._provider = provider
        self._parity = parity

    def run_producer(self, request: ProducerRequest) -> ProducerResponse:
        response = self._provider.run_producer(request)
        self._parity.record_provider_turn(
            step_name=request.step_name,
            turn_kind="producer",
            run_id=request.context.run_id,
            state=request.context.state,
            binding=response.session or request.session,
            raw_output=response.raw_output,
        )
        return response

    def run_verifier(self, request: VerifierRequest) -> OutcomeResponse:
        response = self._provider.run_verifier(request)
        self._parity.record_provider_turn(
            step_name=request.step_name,
            turn_kind="verifier",
            run_id=request.context.run_id,
            state=request.context.state,
            binding=response.session or request.session,
            raw_output=response.outcome.raw_output,
        )
        return response

    def run_llm(self, request: LLMRequest) -> OutcomeResponse:
        response = self._provider.run_llm(request)
        self._parity.record_provider_turn(
            step_name=request.step_name,
            turn_kind="llm",
            run_id=request.context.run_id,
            state=request.context.state,
            binding=response.session or request.session,
            raw_output=response.outcome.raw_output,
        )
        return response


class _AutoloopV1ParityExtension:
    """Workflow-owned bound extension that rebuilds parity side effects."""

    def __init__(self, parity: _AutoloopV1ParityRuntime) -> None:
        self._parity = parity

    def bind(self, binding: RunBinding) -> "_BoundAutoloopV1ParityExtension":
        return _BoundAutoloopV1ParityExtension(self._parity)


class _BoundAutoloopV1ParityExtension:
    def __init__(self, parity: _AutoloopV1ParityRuntime) -> None:
        self._parity = parity

    def before_step(self, event: StepStart) -> None:
        return None

    def after_step(self, event: StepFinish) -> None:
        self._parity.record_step_completed(event)

    def on_terminal(self, event: TerminalFinish) -> None:
        self._parity.record_terminal(event)


def run_autoloop_v1(
    workflow_target: str | Path,
    *,
    provider: LLMProvider,
    options: RunnerOptions,
) -> RunResult:
    compiled = load_compiled_workflow(workflow_target, class_name=options.class_name)
    session_path_strategy = _require_autoloop_v1_session_path_strategy(compiled)
    max_steps = resolve_max_steps(options.max_steps)
    workspace, run = _prepare_autoloop_v1_workspaces(compiled, options)
    prepared = prepare_runtime_services(
        compiled,
        task_workspace=workspace.task,
        workflow_workspace=workspace.workflow,
        run_workspace=run.run,
        session_path_strategy=session_path_strategy,
    )
    parity = _AutoloopV1ParityRuntime(compiled=prepared.compiled, logger=prepared.logger, run=run)
    wrapped_provider = _AutoloopV1LoggingProvider(provider, parity)
    engine = Engine(
        replace(prepared.compiled, extensions=(*prepared.compiled.extensions, _AutoloopV1ParityExtension(parity))),
        provider=wrapped_provider,
        session_store=prepared.session_store,
        checkpoint_store=prepared.checkpoint_store,
        prompt_registry=prepared.prompt_registry,
    )

    prepared.logger.emit(
        "run_resumed" if options.resume else "run_started",
        workflow=prepared.compiled.workflow_name,
        task_id=workspace.task.task_id,
    )
    update_run_metadata(run.run, workflow_params=options.workflow_params or {}, status="running", pending_question=None)
    try:
        if options.resume:
            _append_resume_clarification(prepared.compiled, prepared.checkpoint_store, run, answer=options.answer)
            result = engine.resume(
                task_id=workspace.task.task_id,
                run_id=run.run.run_id,
                task_folder=workspace.task.task_dir,
                workflow_folder=workspace.workflow.workflow_dir,
                run_folder=run.run.run_dir,
                package_folder=workspace.workflow.package_dir,
                root=workspace.task.root,
                workflow_params=options.workflow_params or {},
                answer=options.answer,
                max_steps=max_steps,
            )
        else:
            result = engine.run(
                task_id=workspace.task.task_id,
                run_id=run.run.run_id,
                task_folder=workspace.task.task_dir,
                workflow_folder=workspace.workflow.workflow_dir,
                run_folder=run.run.run_dir,
                package_folder=workspace.workflow.package_dir,
                root=workspace.task.root,
                workflow_params=options.workflow_params or {},
                max_steps=max_steps,
            )
        update_run_metadata(
            run.run,
            workflow_params=options.workflow_params or {},
            status=_autoloop_terminal_status_from_result(result),
            terminal=result.terminal,
            pending_question=result.last_event.question if result.terminal == "PAUSE" and result.last_event is not None else None,
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
        update_run_metadata(
            run.run,
            workflow_params=options.workflow_params or {},
            status="fatal_error",
            error=str(exc),
        )
        raise


def ensure_autoloop_v1_workspace(
    root: Path,
    task_id: str,
    workflow_name: str,
    package_dir: Path,
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
    workflow = ensure_workflow_workspace(task, workflow_name, package_dir=package_dir)
    task_raw_log = task.task_dir / "raw_phase_log.md"
    if not task_raw_log.exists():
        task_raw_log.write_text("# Autoloop Raw Phase Log\n", encoding="utf-8")
    decisions_file = task.task_dir / "decisions.txt"
    if not decisions_file.exists():
        decisions_file.write_text("", encoding="utf-8")
    _set_phase_plan_path(task)
    return AutoloopV1Workspace(task=task, workflow=workflow, task_raw_log=task_raw_log, decisions_file=decisions_file)


def create_autoloop_v1_run(
    workspace: AutoloopV1Workspace,
    *,
    run_id: str | None = None,
    request_text: str | None = None,
) -> AutoloopV1RunWorkspace:
    run = create_run(
        workspace.workflow,
        run_id=run_id,
        request_text=request_text,
    )
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
    run = open_existing_run(workspace.workflow, run_id)
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


def _prepare_autoloop_v1_workspaces(
    compiled: CompiledWorkflow,
    options: RunnerOptions,
) -> tuple[AutoloopV1Workspace, AutoloopV1RunWorkspace]:
    if not options.resume:
        workspace = _ensure_autoloop_workspace_for_options(compiled, options)
        run = create_autoloop_v1_run(
            workspace,
            run_id=options.run_id,
            request_text=task_request_text(workspace.task.task_request_file),
        )
        return workspace, run

    root = options.root.resolve()
    state_dir = options.state_dir
    if state_dir is None:
        state_dir = resolve_resume_state_root(root, task_id=options.task_id, run_id=options.run_id)
    workspace = ensure_autoloop_v1_workspace(
        root,
        options.task_id,
        compiled.workflow_name,
        Path(inspect.getfile(compiled.workflow_cls)).resolve().parent,
        product_intent=options.request_text,
        intent_mode=options.intent_mode,
        state_dir=state_dir,
    )
    run_id = options.run_id or latest_run_id(workspace.workflow.runs_dir)
    if run_id is None:
        raise FileNotFoundError(f"no runs exist under {workspace.workflow.runs_dir}")
    run_dir = workspace.workflow.runs_dir / run_id
    validate_resume_state(run_dir)
    return workspace, open_existing_autoloop_v1_run(workspace, run_id)


def _ensure_autoloop_workspace_for_options(compiled: CompiledWorkflow, options: RunnerOptions) -> AutoloopV1Workspace:
    root = options.root.resolve()
    state_dir = options.state_dir
    if options.resume and state_dir is None:
        state_dir = resolve_resume_state_root(root, task_id=options.task_id, run_id=options.run_id)
    return ensure_autoloop_v1_workspace(
        root,
        options.task_id,
        compiled.workflow_name,
        Path(inspect.getfile(compiled.workflow_cls)).resolve().parent,
        product_intent=options.request_text,
        intent_mode=options.intent_mode,
        state_dir=state_dir,
    )


def _require_autoloop_v1_session_path_strategy(compiled: CompiledWorkflow):
    strategy = resolve_session_path_strategy(compiled)
    if strategy is None:
        raise WorkflowExecutionError(
            "autoloop_v1 parity harness requires the workflow to declare SessionPaths(...) explicitly"
        )
    return strategy


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


def _autoloop_terminal_status(event: TerminalFinish) -> str:
    if event.terminal == "SUCCESS":
        return "success"
    if event.terminal == "FAIL":
        return "failed"
    if event.event is not None and event.event.tag == "blocked":
        return "blocked"
    return "paused"


def _autoloop_terminal_status_from_result(result: RunResult) -> str:
    if result.terminal == "SUCCESS":
        return "success"
    if result.terminal == "FAIL":
        if result.last_event is not None and result.last_event.tag == "blocked":
            return "blocked"
        return "failed"
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
