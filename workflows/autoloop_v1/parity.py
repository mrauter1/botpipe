"""Workflow-owned Autoloop-v1 parity extension."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from autoloop.core.compiler import CompiledWorkflow, compile_workflow
from autoloop.core.extensions import RunBinding, StepFinish, StepStart, TerminalFinish
from autoloop.runtime.stores.filesystem import ensure_session_payload_placeholder, load_session_payload, set_pending_session_note

from .conventions import autoloop_v1_session_path


DECISIONS_VERSION = 1
_DECISIONS_HEADER_RE = re.compile(r"<autoloop-decisions-header\b([^>]*)/>")
_DECISIONS_ATTR_RE = re.compile(r'([a-zA-Z0-9_]+)="([^"]*)"')


@dataclass(frozen=True, slots=True)
class AutoloopV1Parity:
    """Workflow-owned parity extension for the Autoloop-v1 package."""

    workflow_cls: type[Any] | None = None

    def bind(self, binding: RunBinding) -> "_BoundAutoloopV1ParityExtension":
        workflow_cls = self.workflow_cls
        if workflow_cls is None:
            from .workflow import AutoloopV1

            workflow_cls = AutoloopV1
        compiled = compile_workflow(workflow_cls)
        runtime = _AutoloopV1ParityRuntime.create(compiled=compiled, binding=binding)
        return _BoundAutoloopV1ParityExtension(runtime)


@dataclass(slots=True)
class _AutoloopV1ParityRuntime:
    compiled: CompiledWorkflow
    binding: RunBinding
    task_raw_log: Path
    run_raw_log: Path
    decisions_file: Path
    step_progress: dict[tuple[str, str, str | None], tuple[int, int]] = field(default_factory=dict)
    last_turn_kind: dict[tuple[str, str | None], str] = field(default_factory=dict)

    @classmethod
    def create(cls, *, compiled: CompiledWorkflow, binding: RunBinding) -> "_AutoloopV1ParityRuntime":
        task_raw_log = binding.task_folder / "raw_phase_log.md"
        run_raw_log = binding.run_folder / "raw_phase_log.md"
        decisions_file = binding.task_folder / "decisions.txt"

        if not task_raw_log.exists():
            task_raw_log.write_text("# Autoloop Raw Phase Log\n", encoding="utf-8")
        if not run_raw_log.exists():
            run_raw_log.write_text(f"# Autoloop Raw Phase Log ({binding.run_id})\n", encoding="utf-8")
        if not decisions_file.exists():
            decisions_file.write_text("", encoding="utf-8")

        ensure_session_payload_placeholder(autoloop_v1_session_path(binding.run_folder, "plan_session", None))
        return cls(
            compiled=compiled,
            binding=binding,
            task_raw_log=task_raw_log,
            run_raw_log=run_raw_log,
            decisions_file=decisions_file,
        )

    def before_step(self, event: StepStart) -> None:
        if event.answer is not None:
            self._append_resume_clarification(event)

    def after_step(self, event: StepFinish) -> None:
        self._record_step_raw_outputs(event)

        current_phase_id = _phase_id(event.state_before)
        next_phase_id = _phase_id(event.state_after)
        if event.step_name == "activate_next_phase" and event.event.tag == "phase_selected" and next_phase_id is not None:
            _emit_runtime_event(
                self.binding.run_folder / "events.jsonl",
                self.binding.run_id,
                "phase_started",
                workflow=self.binding.workflow_name,
                phase_id=next_phase_id,
            )
        if event.step_name == "test" and event.outcome is not None and event.outcome.tag == "phase_passed":
            completed_phase_id = current_phase_id or next_phase_id
            if completed_phase_id is not None:
                _emit_runtime_event(
                    self.binding.run_folder / "events.jsonl",
                    self.binding.run_id,
                    "phase_completed",
                    workflow=self.binding.workflow_name,
                    phase_id=completed_phase_id,
                )

    def on_terminal(self, event: TerminalFinish) -> None:
        if event.step_name is None or event.event is None:
            return
        if event.event.tag not in {"question", "blocked", "failed"}:
            return

        _emit_runtime_event(
            self.binding.run_folder / "events.jsonl",
            self.binding.run_id,
            event.event.tag,
            workflow=self.binding.workflow_name,
            step_name=event.step_name,
            phase_id=_phase_id(event.state),
            reason=event.event.reason or None,
            question=event.event.question,
        )
        self._append_terminal_notice(event)

    def _record_step_raw_outputs(self, event: StepFinish) -> None:
        state = event.state_before
        if event.producer_raw_output is not None:
            if event.step_kind == "pair":
                self._record_provider_turn(
                    step_name=event.step_name,
                    turn_kind="producer",
                    state=state,
                    raw_output=event.producer_raw_output,
                )
            elif event.step_kind == "llm":
                self._record_provider_turn(
                    step_name=event.step_name,
                    turn_kind="llm",
                    state=state,
                    raw_output=event.producer_raw_output,
                )
        if event.verifier_raw_output is not None:
            self._record_provider_turn(
                step_name=event.step_name,
                turn_kind="verifier",
                state=state,
                raw_output=event.verifier_raw_output,
            )

    def _record_provider_turn(
        self,
        *,
        step_name: str,
        turn_kind: str,
        state: BaseModel,
        raw_output: str,
    ) -> None:
        key = self._progress_key(step_name, state)
        cycle, attempt = self._advance_progress(key, turn_kind)
        phase_id = _phase_id(state)
        self.last_turn_kind[(step_name, phase_id)] = turn_kind
        session_id = self._session_id_for_step(step_name, state)

        for raw_log in (self.task_raw_log, self.run_raw_log):
            _append_runtime_raw_log(
                raw_log,
                self.binding.run_id,
                "phase_output",
                raw_output,
                pair=step_name,
                phase=turn_kind,
                cycle=cycle,
                attempt=attempt,
                session_id=session_id,
            )

    def _append_resume_clarification(self, event: StepStart) -> None:
        payload = _load_checkpoint_payload(self.binding.run_folder / "checkpoint.json")
        pending_question = payload.get("pending_question")
        stage = payload.get("stage")
        if not isinstance(pending_question, str) or not pending_question:
            return
        if not isinstance(stage, str) or not stage:
            return

        step = self.compiled.steps.get(stage)
        if step is None:
            return
        phase_name = "verifier" if step.kind == "pair" else "llm"
        cycle, attempt = _latest_logged_progress(
            self.run_raw_log,
            entry="question",
            pair=stage,
            phase=phase_name,
        )
        session_file = None
        if step.session_name is not None:
            session_file = autoloop_v1_session_path(
                self.binding.run_folder,
                step.session_name,
                self._scope_for_step(step.session_name, event.state),
            )
        _append_clarification(
            run_raw_phase_log=self.run_raw_log,
            task_raw_phase_log=self.task_raw_log,
            decisions_path=self.decisions_file,
            session_file=session_file,
            pair=stage,
            phase_id=_phase_id(event.state) or "plan",
            phase=phase_name,
            cycle=cycle,
            attempt=attempt,
            question=pending_question,
            answer=event.answer or "",
            run_id=self.binding.run_id,
            source="resume",
        )

    def _append_terminal_notice(self, event: TerminalFinish) -> None:
        body = event.event.question or event.event.reason or ""
        if not body and event.outcome is not None:
            body = event.outcome.raw_output
        phase_name = self.last_turn_kind.get((event.step_name, _phase_id(event.state)), "runtime")
        cycle, attempt = self._progress_for_terminal(event.step_name, event.state)
        for raw_log in (self.task_raw_log, self.run_raw_log):
            _append_runtime_raw_log(
                raw_log,
                self.binding.run_id,
                event.event.tag,
                body,
                pair=event.step_name,
                phase=phase_name,
                cycle=cycle,
                attempt=attempt,
            )

    def _progress_key(self, step_name: str, state: BaseModel) -> tuple[str, str, str | None]:
        step = self.compiled.steps.get(step_name)
        session_name = step.session_name if step is not None else ""
        return step_name, session_name or "", self._scope_for_step(session_name, state)

    def _scope_for_step(self, session_name: str | None, state: BaseModel) -> str | None:
        if session_name == "phase_session":
            return _phase_id(state)
        return None

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
        if step is None:
            return 1, 1
        key = (step_name, step.session_name or "", self._scope_for_step(step.session_name, state) if state else None)
        return self.step_progress.get(key, (1, 1))

    def _session_id_for_step(self, step_name: str, state: BaseModel) -> str | None:
        step = self.compiled.steps.get(step_name)
        if step is None or step.session_name is None:
            return None
        session_file = autoloop_v1_session_path(
            self.binding.run_folder,
            step.session_name,
            self._scope_for_step(step.session_name, state),
        )
        payload = load_session_payload(session_file, "persistent", "codex")
        session_id = payload.get("session_id")
        return session_id if isinstance(session_id, str) else None


class _BoundAutoloopV1ParityExtension:
    def __init__(self, runtime: _AutoloopV1ParityRuntime) -> None:
        self._runtime = runtime

    def before_step(self, event: StepStart) -> None:
        self._runtime.before_step(event)

    def after_step(self, event: StepFinish) -> None:
        self._runtime.after_step(event)

    def on_terminal(self, event: TerminalFinish) -> None:
        self._runtime.on_terminal(event)


def _append_clarification(
    *,
    run_raw_phase_log: Path,
    task_raw_phase_log: Path,
    decisions_path: Path,
    session_file: Path | None,
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
    if session_file is not None:
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
    session_id: str | None = None,
    source: str | None = None,
) -> None:
    header = " | ".join(
        f"{key}={value}"
        for key, value in {
            "run_id": run_id,
            "entry": entry,
            "pair": pair,
            "phase": phase,
            "cycle": cycle,
            "attempt": attempt,
            "session_id": session_id,
            "source": source,
        }.items()
        if value is not None
    )
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


def _phase_id(state: BaseModel | object | None) -> str | None:
    if state is None:
        return None
    phase = getattr(state, "phase", None)
    phase_id = getattr(phase, "id", None)
    return phase_id if isinstance(phase_id, str) and phase_id else None


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


def _load_checkpoint_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _emit_runtime_event(events_file: Path, run_id: str, event_type: str, **fields: object) -> None:
    seq = _latest_event_seq(events_file) + 1
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "seq": seq,
        "event_type": event_type,
        **fields,
    }
    events_file.parent.mkdir(parents=True, exist_ok=True)
    with events_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _latest_event_seq(events_file: Path) -> int:
    if not events_file.exists():
        return 0
    latest = 0
    for raw in events_file.read_text(encoding="utf-8").splitlines():
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        seq = payload.get("seq")
        if isinstance(seq, int):
            latest = max(latest, seq)
    return latest


__all__ = ["AutoloopV1Parity"]
