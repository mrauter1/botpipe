"""Typed route-effect declarations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable


@runtime_checkable
class Effect(Protocol):
    """Marker protocol for route effects."""


@dataclass(frozen=True, slots=True)
class Refresh:
    worklist: object | str


@dataclass(frozen=True, slots=True)
class ResetCompletion:
    worklist: object | str


@dataclass(frozen=True, slots=True)
class SetStatus:
    worklist: object | str
    status: str


@dataclass(frozen=True, slots=True)
class Advance:
    worklist: object | str
    if_exhausted: Literal["complete", "pause", "fail", "route"] = "complete"
    route_to: object | None = None


@dataclass(frozen=True, slots=True)
class BoardMutation:
    worklist: object | str
    kind: Literal[
        "split_active_work_item",
        "reprioritize_remaining_work_items",
        "retire_active_work_item",
    ]


@dataclass(frozen=True, slots=True)
class Handoff:
    message: str

    def __post_init__(self) -> None:
        message = self.message.strip() if isinstance(self.message, str) else ""
        if not message:
            raise ValueError("Handoff.message must be a non-empty string.")
        object.__setattr__(self, "message", message)


__all__ = [
    "Advance",
    "BoardMutation",
    "Effect",
    "Handoff",
    "Refresh",
    "ResetCompletion",
    "SetStatus",
]
