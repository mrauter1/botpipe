"""Runtime-owned observability bound into engine extension hooks."""

from __future__ import annotations

from collections.abc import Callable

from botpipe.core.extensions import StepFinish, StepStart, TerminalFinish
from .git_tracking import RuntimeGitTracker
from .tracing import RuntimeTraceWriter


class BoundRuntimeObservability:
    """Bind runtime git tracking and tracing into engine lifecycle hooks."""

    propagate_fatal_exceptions = True

    def __init__(
        self,
        *,
        git_tracker: RuntimeGitTracker,
        trace_writer: RuntimeTraceWriter,
        event_sink: Callable[..., None] | None = None,
        initial_sequence: int,
    ) -> None:
        self._git_tracker = git_tracker
        self._trace_writer = trace_writer
        self._event_sink = event_sink
        self._next_sequence = initial_sequence
        self._active_sequence: int | None = None
        self._active_commit_before_step: str | None = None
        self._fatal_step_name: str | None = None

    def before_step(self, event: StepStart) -> None:
        sequence = self._next_sequence
        self._next_sequence += 1
        git_payload = self._git_tracker.before_step(sequence=sequence, step_name=event.step_name)
        commit_before_step = git_payload.get("commit_before_step")
        if not isinstance(commit_before_step, str):
            commit_before_step = None
        self._active_sequence = sequence
        self._active_commit_before_step = commit_before_step
        self._trace_writer.step_started(
            sequence=sequence,
            event=event,
            commit_before_step=commit_before_step,
        )
        self._emit_runtime_event(
            "step_started",
            workflow=event.binding.workflow_name,
            task_id=event.binding.task_id,
            step_name=event.step_name,
            step_kind=event.step_kind,
            visit=event.visit,
            step_execution_id=event.step_execution_id,
            scope=event.scope,
            item_id=event.item_id,
        )

    def after_step(self, event: StepFinish) -> None:
        sequence = self._active_sequence
        if sequence is None:
            raise RuntimeError("runtime observability received after_step without a matching before_step")
        commit_before_step = self._active_commit_before_step
        self._trace_writer.step_finished(
            sequence=sequence,
            event=event,
            commit_before_step=commit_before_step,
        )
        self._emit_runtime_event(
            "step_finished",
            workflow=event.binding.workflow_name,
            task_id=event.binding.task_id,
            step_name=event.step_name,
            step_kind=event.step_kind,
            visit=event.visit,
            step_execution_id=event.step_execution_id,
            scope=event.scope,
            item_id=event.item_id,
            candidate_route=event.candidate_route,
            final_route=event.final_route,
            runtime_control=event.runtime_control,
            pending_input_id=event.pending_input_id,
            target_step=event.target_step,
            terminal=event.terminal,
            provider_attempted=event.provider_attempted,
            producer_attempted=event.producer_attempted,
            verifier_attempted=event.verifier_attempted,
        )
        self._git_tracker.after_step(
            sequence=sequence,
            step_name=event.step_name,
            commit_before_step=commit_before_step,
        )
        self._active_sequence = None
        self._active_commit_before_step = None

    def on_terminal(self, event: TerminalFinish) -> None:
        if event.terminal == "fatal":
            return
        self._trace_writer.terminal(event=event)

    def on_fatal(self, event: TerminalFinish, error: BaseException) -> None:
        self._fatal_step_name = event.step_name
        errors: list[Exception] = []
        try:
            self._trace_writer.fatal(event=event, error=error)
        except Exception as exc:
            errors.append(exc)
        if len(errors) == 1:
            raise errors[0]
        if errors:
            raise ExceptionGroup("runtime observability fatal persistence failed", errors)

    def commit_terminal(self, *, terminal: str | None) -> dict[str, object]:
        return self._git_tracker.after_run(terminal=terminal)

    def commit_fatal(self, *, error: BaseException) -> dict[str, object]:
        payload = self._git_tracker.on_fatal(step_name=self._fatal_step_name, error=error)
        self._fatal_step_name = None
        return payload

    def _emit_runtime_event(self, event_type: str, **payload: object) -> None:
        if self._event_sink is None:
            return
        self._event_sink(event_type, **{key: value for key, value in payload.items() if value is not None})


__all__ = ["BoundRuntimeObservability"]
