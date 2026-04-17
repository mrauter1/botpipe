"""In-memory store implementations for deterministic tests."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from itertools import count

from .protocols import CheckpointPayload, SessionBinding, SessionSnapshot


class InMemorySessionStore:
    """Simple deterministic in-memory session store."""

    def __init__(self) -> None:
        self._bindings: dict[tuple[str, str | None], SessionBinding] = {}
        self._active_scopes: dict[str, str | None] = {}
        self._counter = count(1)

    def open(self, ref_name: str, scope: str | None = None) -> SessionBinding:
        resolved_scope = self._resolve_scope(ref_name, scope)
        key = (ref_name, resolved_scope)
        binding = self._bindings.get(key)
        if binding is None:
            session_id = f"{ref_name}:{resolved_scope or 'global'}:{next(self._counter)}"
            binding = SessionBinding(ref_name=ref_name, scope=resolved_scope, session_id=session_id)
            self._bindings[key] = binding
        self._active_scopes[ref_name] = resolved_scope
        return binding

    def get(self, ref_name: str, scope: str | None = None) -> SessionBinding | None:
        resolved_scope = self._resolve_scope(ref_name, scope, for_lookup=True)
        return self._bindings.get((ref_name, resolved_scope))

    def upsert(self, binding: SessionBinding, *, activate: bool = True) -> SessionBinding:
        self._bindings[(binding.ref_name, binding.scope)] = binding
        if activate:
            self._active_scopes[binding.ref_name] = binding.scope
        return binding

    def snapshot(self) -> SessionSnapshot:
        ordered = tuple(
            self._bindings[key]
            for key in sorted(self._bindings, key=lambda item: (item[0], "" if item[1] is None else item[1]))
        )
        return SessionSnapshot(bindings=ordered, active_scopes=dict(self._active_scopes))

    def restore(self, snapshot: SessionSnapshot) -> None:
        self._bindings = {(binding.ref_name, binding.scope): binding for binding in snapshot.bindings}
        self._active_scopes = dict(snapshot.active_scopes)
        highest = 0
        for binding in snapshot.bindings:
            suffix = binding.session_id.rsplit(":", 1)[-1]
            if suffix.isdigit():
                highest = max(highest, int(suffix))
        self._counter = count(highest + 1)

    def seed(self, bindings: Iterable[SessionBinding]) -> None:
        for binding in bindings:
            self.upsert(binding)

    def _resolve_scope(self, ref_name: str, scope: str | None, *, for_lookup: bool = False) -> str | None:
        if scope is not None:
            return scope
        if ref_name in self._active_scopes:
            return self._active_scopes[ref_name]
        if for_lookup:
            return None
        return None


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

