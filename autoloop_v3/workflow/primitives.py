"""Core workflow primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .stores.protocols import CheckpointPayload

SUCCESS = "SUCCESS"
PAUSE = "PAUSE"
FAIL = "FAIL"
GLOBAL = "GLOBAL"


@dataclass(frozen=True, slots=True)
class Event:
    """Routing event."""

    tag: str
    reason: str = ""
    question: str | None = None


@dataclass(frozen=True, slots=True)
class Outcome:
    """Typed provider outcome."""

    raw_output: str
    tag: str
    reason: str = ""
    clarification: str | None = None
    question: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


Verdict = Outcome
Checkpoint = CheckpointPayload

from .artifacts import ResolvedArtifacts  # noqa: E402

__all__ = [
    "Checkpoint",
    "Event",
    "FAIL",
    "GLOBAL",
    "Outcome",
    "PAUSE",
    "ResolvedArtifacts",
    "SUCCESS",
    "Verdict",
]
