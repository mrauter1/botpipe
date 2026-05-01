"""In-memory store implementations for deterministic tests."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from itertools import count

from ..sessions import SessionKey
from .protocols import CheckpointPayload, SessionBinding, SessionSnapshot


class InMemorySessionStore:
    """Simple deterministic in-memory session store."""

    def __init__(self) -> None:
        self._bindings: dict[SessionKey, SessionBinding] = {}
        self._active_keys_by_slot: dict[str, SessionKey] = {}
        self._counter = count(1)

    def open(self, ref_name: str | SessionKey, scope: str | None = None) -> SessionBinding:
        key = self._resolve_key(ref_name, scope=scope, for_lookup=False)
        binding = self._bindings.get(key)
        if binding is None:
            session_id = f"{key.slot}:{self._session_value_token(key)}:{next(self._counter)}"
            binding = SessionBinding(key=key, session_id=session_id)
            self._bindings[key] = binding
        self._active_keys_by_slot[key.slot] = key
        return binding

    def get(self, ref_name: str | SessionKey, scope: str | None = None) -> SessionBinding | None:
        key = self._resolve_key(ref_name, scope=scope, for_lookup=True)
        return self._bindings.get(key)

    def upsert(self, binding: SessionBinding, *, activate: bool = True) -> SessionBinding:
        self._bindings[binding.key] = binding
        if activate:
            self._active_keys_by_slot[binding.key.slot] = binding.key
        return binding

    def snapshot(self) -> SessionSnapshot:
        ordered = tuple(
            self._bindings[key]
            for key in sorted(self._bindings, key=lambda item: (item.slot, item.domain, item.value))
        )
        return SessionSnapshot(bindings=ordered, active_keys_by_slot=dict(self._active_keys_by_slot))

    def restore(self, snapshot: SessionSnapshot) -> None:
        self._bindings = {binding.key: binding for binding in snapshot.bindings}
        self._active_keys_by_slot = self._restore_active_keys(snapshot)
        highest = 0
        for binding in snapshot.bindings:
            if not binding.session_id:
                continue
            suffix = binding.session_id.rsplit(":", 1)[-1]
            if suffix.isdigit():
                highest = max(highest, int(suffix))
        self._counter = count(highest + 1)

    def seed(self, bindings: Iterable[SessionBinding]) -> None:
        for binding in bindings:
            self.upsert(binding)

    def _resolve_key(self, ref_name: str | SessionKey, *, scope: str | None, for_lookup: bool) -> SessionKey:
        if isinstance(ref_name, SessionKey):
            return ref_name
        if scope is not None:
            return SessionKey(slot=ref_name, domain="explicit_scope", value=scope)
        if ref_name in self._active_keys_by_slot:
            return self._active_keys_by_slot[ref_name]
        return SessionKey(slot=ref_name, domain="run", value=ref_name)

    def _restore_active_keys(self, snapshot: SessionSnapshot) -> dict[str, SessionKey]:
        if snapshot.active_keys_by_slot:
            return dict(snapshot.active_keys_by_slot)
        restored: dict[str, SessionKey] = {}
        bindings_by_slot = {
            binding.ref_name: [candidate for candidate in snapshot.bindings if candidate.ref_name == binding.ref_name]
            for binding in snapshot.bindings
        }
        for slot, scope in snapshot.active_scopes.items():
            if scope is not None:
                explicit = next(
                    (binding.key for binding in bindings_by_slot.get(slot, ()) if binding.scope == scope),
                    None,
                )
                if explicit is not None:
                    restored[slot] = explicit
                    continue
            fallback = next(
                (binding.key for binding in bindings_by_slot.get(slot, ()) if binding.scope is None),
                None,
            )
            if fallback is not None:
                restored[slot] = fallback
        return restored

    @staticmethod
    def _session_value_token(key: SessionKey) -> str:
        if key.domain == "run":
            return "global"
        return key.value or key.domain


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
