"""Runtime-owned observability bound into engine extension hooks."""

from __future__ import annotations

try:  # pragma: no branch - prefer installed-package imports when available
    from autoloop_v3.core.extensions import StepFinish, StepStart, TerminalFinish
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from core.extensions import StepFinish, StepStart, TerminalFinish
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
        initial_sequence: int,
    ) -> None:
        self._git_tracker = git_tracker
        self._trace_writer = trace_writer
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


__all__ = ["BoundRuntimeObservability"]
