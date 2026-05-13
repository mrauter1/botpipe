"""Plain-text runtime progress rendering for CLI workflow executions."""

from __future__ import annotations

from dataclasses import dataclass
import sys
import threading
from collections.abc import Mapping
from time import monotonic
from typing import TextIO


StepKey = tuple[str, str]
AttemptKey = tuple[str, str, str, str]


def build_run_progress_printer(mode: str, stream: TextIO | None = None) -> "RunProgressPrinter | None":
    """Return a progress printer for the requested mode."""

    resolved_stream = stream or sys.stderr
    if mode == "off":
        return None
    if mode == "plain":
        return RunProgressPrinter(resolved_stream)
    if mode == "auto":
        return RunProgressPrinter(resolved_stream) if resolved_stream.isatty() else None
    raise ValueError(f"unsupported progress mode {mode!r}")


@dataclass(slots=True)
class _RunFrame:
    run_id: str
    workflow: str
    parent_run_id: str | None
    depth: int
    finished: bool = False


class RunProgressPrinter:
    """Plain stderr progress rendering for CLI-triggered workflow executions."""

    _HEARTBEAT_SECONDS = 30.0

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream
        self._started = monotonic()
        self._lock = threading.RLock()
        self._timer: threading.Timer | None = None
        self._closed = False
        self._sequence = 0
        self._runs: dict[str, _RunFrame] = {}
        self._active_steps: dict[StepKey, dict[str, object]] = {}
        self._active_provider_attempts: dict[AttemptKey, dict[str, object]] = {}

    def __enter__(self) -> "RunProgressPrinter":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._cancel_timer()
            self._runs.clear()
            self._active_steps.clear()
            self._active_provider_attempts.clear()

    def event_callback(self, event: Mapping[str, object]) -> None:
        with self._lock:
            if self._closed:
                return
            event_type = _event_string(event, "event_type")
            if event_type in {"run_started", "run_resumed"}:
                self._run_started(event, resumed=event_type == "run_resumed")
            elif event_type == "step_started":
                self._step_started(event)
            elif event_type == "step_finished":
                self._step_finished(event)
            elif event_type == "provider_attempt_started":
                self._provider_attempt_started(event)
            elif event_type == "provider_attempt_finished":
                self._provider_attempt_finished(event)
            elif event_type == "provider_attempt_failed":
                self._provider_attempt_failed(event)
            elif event_type == "run_finished":
                self._run_finished(event)

    def _run_started(self, event: Mapping[str, object], *, resumed: bool) -> None:
        frame = self._ensure_run_frame(event)
        if frame.depth == 0:
            self._print_top_level_run_summary(event, resumed=resumed)
            return
        action = "resumed" if resumed else "started"
        self._print_timed(
            f"child workflow {frame.workflow} {action} (run {frame.run_id})",
            indent=self._indent(frame),
        )

    def _print_top_level_run_summary(self, event: Mapping[str, object], *, resumed: bool) -> None:
        heading = "Resuming Botpipe run" if resumed else "Starting Botpipe run"
        self._write(heading)
        for label, key in (
            ("workflow", "workflow"),
            ("task_id", "task_id"),
            ("run_id", "run_id"),
            ("task_folder", "task_folder"),
            ("workflow_folder", "workflow_folder"),
            ("run_folder", "run_folder"),
            ("events", "events_file"),
        ):
            value = _event_string(event, key)
            if value:
                self._write(f"  {label}: {value}")
        if _event_bool(event, "trace_enabled") is False:
            self._write("  trace: disabled")
        else:
            trace_file = _event_string(event, "trace_file")
            if trace_file:
                self._write(f"  trace: {trace_file}")

    def _provider_attempt_started(self, event: Mapping[str, object]) -> None:
        event_copy = self._event_with_order(event)
        key = _attempt_key(event_copy)
        self._active_provider_attempts[key] = event_copy
        self._cancel_timer()
        self._print_timed(
            f"provider {_turn_kind(event)} attempt {_attempt(event)} started"
            f" for step {_event_string(event, 'step_name') or '<unknown>'}",
            indent=self._indent_for_event(event),
        )
        self._schedule_heartbeat()

    def _provider_attempt_finished(self, event: Mapping[str, object]) -> None:
        self._active_provider_attempts.pop(_attempt_key(event), None)
        self._cancel_timer()
        self._print_timed(
            f"provider {_turn_kind(event)} attempt {_attempt(event)} finished"
            f" for step {_event_string(event, 'step_name') or '<unknown>'}{_token_suffix(event)}",
            indent=self._indent_for_event(event),
        )
        self._schedule_heartbeat()

    def _provider_attempt_failed(self, event: Mapping[str, object]) -> None:
        self._active_provider_attempts.pop(_attempt_key(event), None)
        self._cancel_timer()
        self._print_timed(
            f"provider {_turn_kind(event)} attempt {_attempt(event)} failed"
            f" for step {_event_string(event, 'step_name') or '<unknown>'}{_failure_suffix(event)}",
            indent=self._indent_for_event(event),
        )
        self._schedule_heartbeat()

    def _step_started(self, event: Mapping[str, object]) -> None:
        event_copy = self._event_with_order(event)
        self._ensure_run_frame(event_copy)
        self._active_steps[_step_key(event_copy)] = event_copy
        self._cancel_timer()
        self._print_timed(
            f"step {_event_string(event, 'step_name') or '<unknown>'} started{_scope_suffix(event)}",
            indent=self._indent_for_event(event),
        )
        self._schedule_heartbeat()

    def _step_finished(self, event: Mapping[str, object]) -> None:
        step_key = _step_key(event)
        self._active_steps.pop(step_key, None)
        self._active_provider_attempts = {
            key: attempt
            for key, attempt in self._active_provider_attempts.items()
            if key[:2] != step_key
        }
        self._cancel_timer()
        self._print_timed(
            f"step {_event_string(event, 'step_name') or '<unknown>'} finished"
            f"{_route_suffix(event)}{_target_suffix(event)}{_input_suffix(event)}",
            indent=self._indent_for_event(event),
        )
        self._schedule_heartbeat()

    def _run_finished(self, event: Mapping[str, object]) -> None:
        run_id = _run_id(event)
        frame = self._runs.get(run_id)
        self._clear_run_activity(run_id)
        if frame is not None:
            frame.finished = True
        self._cancel_timer()
        status = _event_string(event, "status") or _event_string(event, "terminal") or "finished"
        detail = _event_string(event, "error")
        suffix = f" ({detail})" if detail else ""
        if frame is not None and frame.depth > 0:
            self._print_timed(
                f"child workflow {frame.workflow} finished: {status}{suffix}",
                indent=self._indent(frame),
            )
        else:
            self._print_timed(f"run finished: {status}{suffix}")
        self._schedule_heartbeat()

    def _heartbeat(self) -> None:
        with self._lock:
            if self._closed:
                return
            event = self._latest_active_provider_attempt()
            if event is not None:
                self._print_timed(
                    f"provider {_turn_kind(event)} attempt {_attempt(event)} still running"
                    f" for step {_event_string(event, 'step_name') or '<unknown>'}",
                    indent=self._indent_for_event(event),
                )
                self._schedule_heartbeat()
                return
            event = self._latest_active_step()
            if event is not None:
                self._print_timed(
                    f"step {_event_string(event, 'step_name') or '<unknown>'} still running",
                    indent=self._indent_for_event(event),
                )
                self._schedule_heartbeat()

    def _ensure_run_frame(self, event: Mapping[str, object]) -> _RunFrame:
        run_id = _run_id(event)
        existing = self._runs.get(run_id)
        if existing is not None:
            return existing
        parent_run_id = _event_string(event, "parent_run_id")
        parent = None if parent_run_id is None else self._runs.get(parent_run_id)
        depth = 0 if parent_run_id is None else (parent.depth + 1 if parent is not None else 1)
        frame = _RunFrame(
            run_id=run_id,
            workflow=_event_string(event, "workflow") or "<unknown>",
            parent_run_id=parent_run_id,
            depth=depth,
        )
        self._runs[run_id] = frame
        return frame

    def _event_with_order(self, event: Mapping[str, object]) -> dict[str, object]:
        self._sequence += 1
        event_copy = dict(event)
        event_copy["_progress_order"] = self._sequence
        return event_copy

    def _clear_run_activity(self, run_id: str) -> None:
        self._active_steps = {
            key: step
            for key, step in self._active_steps.items()
            if key[0] != run_id
        }
        self._active_provider_attempts = {
            key: attempt
            for key, attempt in self._active_provider_attempts.items()
            if key[0] != run_id
        }

    def _latest_active_provider_attempt(self) -> Mapping[str, object] | None:
        if not self._active_provider_attempts:
            return None
        return max(self._active_provider_attempts.values(), key=_progress_order)

    def _latest_active_step(self) -> Mapping[str, object] | None:
        if not self._active_steps:
            return None
        return max(self._active_steps.values(), key=_progress_order)

    def _indent_for_event(self, event: Mapping[str, object]) -> str:
        return self._indent(self._ensure_run_frame(event))

    @staticmethod
    def _indent(frame: _RunFrame) -> str:
        return "  " * frame.depth

    def _schedule_heartbeat(self) -> None:
        if self._closed or (not self._active_provider_attempts and not self._active_steps):
            return
        timer = threading.Timer(self._HEARTBEAT_SECONDS, self._heartbeat)
        timer.daemon = True
        self._timer = timer
        timer.start()

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _print_timed(self, message: str, *, indent: str = "") -> None:
        self._write(f"{indent}[{self._elapsed()}] {message}")

    def _write(self, message: str) -> None:
        print(message, file=self._stream, flush=True)

    def _elapsed(self) -> str:
        seconds = max(0, int(monotonic() - self._started))
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"


def _run_id(event: Mapping[str, object]) -> str:
    return _event_string(event, "run_id") or "<unknown>"


def _step_key(event: Mapping[str, object]) -> StepKey:
    run_id = _run_id(event)
    step_execution_id = _event_string(event, "step_execution_id")
    if step_execution_id:
        return (run_id, f"id:{step_execution_id}")
    step_name = _event_string(event, "step_name") or "<unknown>"
    scope = _event_string(event, "scope") or ""
    item_id = _event_string(event, "item_id") or ""
    visit = event.get("visit")
    visit_text = str(visit) if isinstance(visit, int) and not isinstance(visit, bool) else ""
    return (run_id, f"fallback:{step_name}:{scope}:{item_id}:{visit_text}")


def _attempt_key(event: Mapping[str, object]) -> AttemptKey:
    run_id, step_key = _step_key(event)
    return (run_id, step_key, _turn_kind(event), _attempt(event))


def _progress_order(event: Mapping[str, object]) -> int:
    order = event.get("_progress_order")
    return order if isinstance(order, int) and not isinstance(order, bool) else 0


def _event_string(event: Mapping[str, object], key: str) -> str | None:
    value = event.get(key)
    return value if isinstance(value, str) and value else None


def _event_bool(event: Mapping[str, object], key: str) -> bool | None:
    value = event.get(key)
    return value if isinstance(value, bool) else None


def _attempt(event: Mapping[str, object]) -> str:
    value = event.get("attempt")
    return str(value) if isinstance(value, int) and not isinstance(value, bool) else "?"


def _turn_kind(event: Mapping[str, object]) -> str:
    return _event_string(event, "turn_kind") or "turn"


def _scope_suffix(event: Mapping[str, object]) -> str:
    scope = _event_string(event, "scope")
    item_id = _event_string(event, "item_id")
    if scope and item_id:
        return f" ({scope}:{item_id})"
    if scope:
        return f" ({scope})"
    return ""


def _route_suffix(event: Mapping[str, object]) -> str:
    route = _event_string(event, "final_route") or _event_string(event, "candidate_route") or _event_string(event, "terminal")
    return f" -> {route}" if route else ""


def _target_suffix(event: Mapping[str, object]) -> str:
    target = _event_string(event, "target_step")
    return f" (next {target})" if target else ""


def _input_suffix(event: Mapping[str, object]) -> str:
    return " (awaiting input)" if _event_string(event, "pending_input_id") else ""


def _token_suffix(event: Mapping[str, object]) -> str:
    usage = event.get("token_usage")
    if not isinstance(usage, Mapping):
        return ""
    total = usage.get("total_tokens")
    if isinstance(total, int) and not isinstance(total, bool):
        return f" ({total} tokens)"
    return ""


def _failure_suffix(event: Mapping[str, object]) -> str:
    failure = event.get("failure_context")
    if not isinstance(failure, Mapping):
        return ""
    kind = failure.get("kind")
    details = failure.get("details")
    message = None
    if isinstance(details, Mapping):
        raw_message = details.get("error")
        if isinstance(raw_message, str) and raw_message:
            message = raw_message
    if isinstance(kind, str) and kind and message:
        return f" ({kind}: {message})"
    if isinstance(kind, str) and kind:
        return f" ({kind})"
    if message:
        return f" ({message})"
    return ""


__all__ = ["RunProgressPrinter", "build_run_progress_printer"]
