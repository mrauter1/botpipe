"""In-memory store implementations for deterministic tests."""

from __future__ import annotations

from dataclasses import replace

from .protocols import CheckpointPayload
from .session_store import InMemorySessionBackend, InMemorySessionStore


class InMemoryCheckpointStore:
    """Single-slot in-memory checkpoint store."""

    def __init__(self) -> None:
        self._checkpoint: CheckpointPayload | None = None

    def save(self, checkpoint: CheckpointPayload) -> None:
        self._checkpoint = replace(checkpoint)

    def load(self) -> CheckpointPayload | None:
        return self._checkpoint

    def clear(self) -> None:
        self._checkpoint = None


__all__ = [
    "InMemoryCheckpointStore",
    "InMemorySessionBackend",
    "InMemorySessionStore",
]
