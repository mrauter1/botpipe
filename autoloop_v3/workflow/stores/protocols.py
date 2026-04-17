"""Store protocols for sessions and checkpoints."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel


@dataclass(frozen=True, slots=True)
class SessionBinding:
    """Concrete session binding."""

    ref_name: str
    scope: str | None
    session_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    """Serializable session snapshot."""

    bindings: tuple[SessionBinding, ...]
    active_scopes: dict[str, str | None] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CheckpointPayload:
    """Typed checkpoint persistence payload."""

    stage: str
    state: BaseModel
    session_bindings: SessionSnapshot
    pending_question: str | None = None
    pending_answer: str | None = None


class SessionStore(Protocol):
    """Concrete session binding backend."""

    def open(self, ref_name: str, scope: str | None = None) -> SessionBinding:
        """Open or reuse a binding and set it active for the slot."""

    def get(self, ref_name: str, scope: str | None = None) -> SessionBinding | None:
        """Return the active or explicit binding for a session slot."""

    def upsert(self, binding: SessionBinding, *, activate: bool = True) -> SessionBinding:
        """Persist a provider-updated binding."""

    def snapshot(self) -> SessionSnapshot:
        """Return all bindings plus the active scope table."""

    def restore(self, snapshot: SessionSnapshot) -> None:
        """Replace the current binding state from a snapshot."""


class CheckpointStore(Protocol):
    """Checkpoint backend."""

    def save(self, checkpoint: CheckpointPayload) -> None:
        """Persist a checkpoint."""

    def load(self) -> CheckpointPayload | None:
        """Load the latest checkpoint if one exists."""

    def clear(self) -> None:
        """Remove the persisted checkpoint."""

