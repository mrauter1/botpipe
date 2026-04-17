"""Typed execution observation surface for the strict engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypeAlias

from pydantic import BaseModel

from .primitives import Checkpoint, Event, Outcome
from .stores.protocols import SessionBinding

ProviderTurnKind: TypeAlias = Literal["producer", "verifier", "llm"]
StepKind: TypeAlias = Literal["pair", "llm", "system"]
TerminalKind: TypeAlias = Literal["success", "pause", "fail", "fatal"]


@dataclass(frozen=True, slots=True)
class ProviderTurnEvent:
    """Observation emitted after a provider turn completes."""

    workflow_name: str
    task_id: str
    run_id: str
    step_name: str
    step_kind: StepKind
    turn_kind: ProviderTurnKind
    state: BaseModel
    prompt_path: str
    request_session: SessionBinding | None
    response_session: SessionBinding | None
    raw_output: str
    outcome: Outcome | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    category: Literal["provider_turn"] = field(init=False, default="provider_turn")


@dataclass(frozen=True, slots=True)
class StepCompletedEvent:
    """Observation emitted after a workflow step completes."""

    workflow_name: str
    task_id: str
    run_id: str
    step_name: str
    step_kind: StepKind
    state_before: BaseModel
    state_after: BaseModel
    event: Event | None
    outcome: Outcome | None
    destination: str
    category: Literal["step_completed"] = field(init=False, default="step_completed")


@dataclass(frozen=True, slots=True)
class TerminalEvent:
    """Observation emitted when a run reaches a terminal state."""

    workflow_name: str
    task_id: str
    run_id: str
    terminal_kind: TerminalKind
    state: BaseModel | None
    history: tuple[str, ...]
    last_event: Event | None
    last_outcome: Outcome | None
    checkpoint: Checkpoint | None = None
    exception_type: str | None = None
    exception_message: str | None = None
    category: Literal["terminal"] = field(init=False, default="terminal")


ExecutionEvent: TypeAlias = ProviderTurnEvent | StepCompletedEvent | TerminalEvent


class ExecutionObserver(Protocol):
    """Output-only sink for execution facts."""

    def record(self, event: ExecutionEvent) -> None:
        """Consume one engine observation."""


__all__ = [
    "ExecutionEvent",
    "ExecutionObserver",
    "ProviderTurnEvent",
    "ProviderTurnKind",
    "StepCompletedEvent",
    "StepKind",
    "TerminalEvent",
    "TerminalKind",
]
