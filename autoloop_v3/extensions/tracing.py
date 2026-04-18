"""Optional workflow-declared tracing sidecar."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from ..workflow.extensions import RunBinding, StepFinish, StepStart, TerminalFinish


FailureMode = Literal["raise", "ignore"]


class _NoOpBoundTracing:
    def before_step(self, event: StepStart) -> None:
        return None

    def after_step(self, event: StepFinish) -> None:
        return None

    def on_terminal(self, event: TerminalFinish) -> None:
        return None


@dataclass(frozen=True, slots=True)
class TracingConfig:
    """Tracing side-effect policy only."""

    enabled: bool = True
    path: str = "trace.jsonl"
    failure_mode: FailureMode = "raise"


@dataclass(frozen=True, slots=True)
class Tracing:
    """Workflow-declared tracing sidecar."""

    config: TracingConfig = TracingConfig()

    def bind(self, binding: RunBinding) -> _NoOpBoundTracing | "_BoundTracing":
        if not self.config.enabled:
            return _NoOpBoundTracing()
        return _BoundTracing(binding, self.config)


class _BoundTracing:
    def __init__(self, binding: RunBinding, config: TracingConfig) -> None:
        self._binding = binding
        self._config = config
        self._path = _resolve_trace_path(binding.run_folder, config.path)

    def before_step(self, event: StepStart) -> None:
        self._write(
            {
                "event_type": "step_started",
                "timestamp": _utcnow(),
                "workflow": self._binding.workflow_name,
                "task_id": self._binding.task_id,
                "run_id": self._binding.run_id,
                "step_name": event.step_name,
                "step_kind": event.step_kind,
                "state": event.state.model_dump(mode="json"),
            }
        )

    def after_step(self, event: StepFinish) -> None:
        self._write(
            {
                "event_type": "step_finished",
                "timestamp": _utcnow(),
                "workflow": self._binding.workflow_name,
                "task_id": self._binding.task_id,
                "run_id": self._binding.run_id,
                "step_name": event.step_name,
                "step_kind": event.step_kind,
                "state_before": event.state_before.model_dump(mode="json"),
                "state_after": event.state_after.model_dump(mode="json"),
                "event": asdict(event.event),
                "outcome": asdict(event.outcome) if event.outcome is not None else None,
            }
        )

    def on_terminal(self, event: TerminalFinish) -> None:
        self._write(
            {
                "event_type": "terminal",
                "timestamp": _utcnow(),
                "workflow": self._binding.workflow_name,
                "task_id": self._binding.task_id,
                "run_id": self._binding.run_id,
                "terminal": event.terminal,
                "step_name": event.step_name,
                "state": event.state.model_dump(mode="json") if event.state is not None else None,
                "event": asdict(event.event) if event.event is not None else None,
                "outcome": asdict(event.outcome) if event.outcome is not None else None,
            }
        )

    def _write(self, payload: dict[str, object]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True) + "\n")
        except Exception:
            if self._config.failure_mode == "ignore":
                return
            raise


def _resolve_trace_path(run_folder: Path, configured_path: str) -> Path:
    candidate = Path(configured_path)
    if candidate.is_absolute():
        return candidate
    return run_folder / candidate


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = ["Tracing", "TracingConfig"]
