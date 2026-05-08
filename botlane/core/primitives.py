"""Core workflow primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from pydantic import BaseModel

from .outcome_contract import project_questions_markdown
from .stores.protocols import CheckpointPayload, PendingHandoff

FINISH = "FINISH"
AWAIT_INPUT = "AWAIT_INPUT"
FAIL = "FAIL"
SELF = "SELF"
GLOBAL = "GLOBAL"


def _normalize_optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string when provided")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty when provided")
    return normalized


def _normalize_required_text(value: str, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _normalize_input_schema(
    value: type[BaseModel] | dict[str, object] | None,
) -> type[BaseModel] | dict[str, object] | None:
    if value is None:
        return None
    if isinstance(value, type) and issubclass(value, BaseModel):
        return value
    if isinstance(value, dict):
        return dict(value)
    raise TypeError("RequestInput.input_schema must be a Pydantic model type or schema mapping")


@dataclass(frozen=True, slots=True)
class Event:
    """Routing event."""

    tag: str
    reason: str = ""
    question: str | None = None
    handoff: str | None = None

    def __post_init__(self) -> None:
        if self.handoff is None:
            return
        handoff = self.handoff.strip() if isinstance(self.handoff, str) else ""
        if not handoff:
            raise ValueError("Event.handoff must be a non-empty string when provided.")
        object.__setattr__(self, "handoff", handoff)


@dataclass(frozen=True, slots=True)
class RequestInput:
    """Direct runtime control that awaits external input."""

    question: str
    reason: str | None = None
    best_supposition: str | None = None
    input_schema: type[BaseModel] | dict[str, object] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "question", _normalize_required_text(self.question, field_name="question"))
        object.__setattr__(self, "reason", _normalize_optional_text(self.reason, field_name="reason"))
        object.__setattr__(
            self,
            "best_supposition",
            _normalize_optional_text(self.best_supposition, field_name="best_supposition"),
        )
        object.__setattr__(self, "input_schema", _normalize_input_schema(self.input_schema))


@dataclass(frozen=True, slots=True)
class Goto:
    """Direct runtime control that jumps to a declared step."""

    target: str | object
    reason: str | None = None
    handoff: str | None = None

    def __post_init__(self) -> None:
        if self.target is None:
            raise ValueError("Goto.target must not be None")
        object.__setattr__(self, "reason", _normalize_optional_text(self.reason, field_name="reason"))
        object.__setattr__(self, "handoff", _normalize_optional_text(self.handoff, field_name="handoff"))


@dataclass(frozen=True, slots=True)
class Fail:
    """Direct runtime control that terminates the run as failed."""

    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason", _normalize_required_text(self.reason, field_name="reason"))


@dataclass(frozen=True, slots=True)
class Outcome:
    """Typed provider outcome."""

    raw_output: str
    tag: str
    reason: str = ""
    clarification: str | None = None
    question: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    route_fields: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.payload, Mapping) and not isinstance(self.payload, dict):
            object.__setattr__(self, "payload", dict(self.payload))
        if isinstance(self.route_fields, Mapping) and not isinstance(self.route_fields, dict):
            object.__setattr__(self, "route_fields", dict(self.route_fields))
        route_fields = self.route_fields if isinstance(self.route_fields, dict) else None
        if route_fields is None:
            return
        projected_question = project_questions_markdown(route_fields.get("questions"))
        if projected_question is not None:
            object.__setattr__(self, "question", projected_question)
        route_reason = route_fields.get("reason")
        if isinstance(route_reason, str):
            object.__setattr__(self, "reason", route_reason)
        elif route_reason is None and "reason" in route_fields and self.reason == "":
            object.__setattr__(self, "reason", "")


Checkpoint = CheckpointPayload

from .artifacts import ResolvedArtifacts  # noqa: E402

__all__ = [
    "AWAIT_INPUT",
    "Checkpoint",
    "Event",
    "FAIL",
    "Fail",
    "FINISH",
    "GLOBAL",
    "Goto",
    "Outcome",
    "PendingHandoff",
    "RequestInput",
    "ResolvedArtifacts",
    "SELF",
]
