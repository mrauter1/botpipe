"""Branch-local session store overlays."""

from __future__ import annotations

from ..sessions import SessionKey
from ..stores.protocols import SessionBinding, SessionSnapshot, SessionStore


class BranchSessionStoreView:
    """Overlay session store that keeps branch activation local."""

    def __init__(self, parent_store: SessionStore, *, namespace: str = "branch") -> None:
        self._parent_store = parent_store
        self._namespace = namespace
        self._bindings: dict[SessionKey, SessionBinding] = {}
        self._active_keys_by_slot: dict[str, SessionKey] = {}

    def open(self, ref_name: str | SessionKey, scope: str | None = None) -> SessionBinding:
        key = self._resolve_key(ref_name, scope=scope, for_lookup=False)
        binding = self._binding_for_key(key)
        if binding is None:
            binding = SessionBinding(
                key=key,
                session_id=None,
            )
        self._bindings[key] = binding
        self._active_keys_by_slot[key.slot] = key
        return binding

    def get(self, ref_name: str | SessionKey, scope: str | None = None) -> SessionBinding | None:
        key = self._resolve_key(ref_name, scope=scope, for_lookup=True)
        return self._binding_for_key(key)

    def upsert(self, binding: SessionBinding, *, activate: bool = True) -> SessionBinding:
        self._bindings[binding.key] = binding
        if activate:
            self._active_keys_by_slot[binding.key.slot] = binding.key
        return binding

    def snapshot(self) -> SessionSnapshot:
        parent_snapshot = self._parent_store.snapshot()
        bindings_by_key = {binding.key: binding for binding in parent_snapshot.bindings}
        bindings_by_key.update(self._bindings)
        active_keys_by_slot = dict(parent_snapshot.active_keys_by_slot)
        active_keys_by_slot.update(self._active_keys_by_slot)
        ordered = tuple(
            bindings_by_key[key]
            for key in sorted(bindings_by_key, key=lambda item: (item.slot, item.domain, item.value))
        )
        return SessionSnapshot(bindings=ordered, active_keys_by_slot=active_keys_by_slot)

    def restore(self, snapshot: SessionSnapshot) -> None:
        self._bindings = {binding.key: binding for binding in snapshot.bindings}
        self._active_keys_by_slot = dict(snapshot.active_keys_by_slot)

    def _binding_for_key(self, key: SessionKey) -> SessionBinding | None:
        binding = self._bindings.get(key)
        if binding is not None:
            return binding
        if key.domain == "fresh":
            return None
        return self._parent_store.get(key)

    def _resolve_key(self, ref_name: str | SessionKey, *, scope: str | None, for_lookup: bool) -> SessionKey:
        if isinstance(ref_name, SessionKey):
            if ref_name.domain == "fresh":
                active = self._active_keys_by_slot.get(ref_name.slot)
                if for_lookup and active is not None and active.domain == "fresh":
                    return active
                return self._branch_fresh_key(ref_name)
            return ref_name
        if scope is not None:
            return SessionKey(slot=ref_name, domain="explicit_scope", value=scope)
        if for_lookup:
            active = self._active_keys_by_slot.get(ref_name)
            if active is not None:
                return active
            parent_active = self._parent_store.snapshot().active_keys_by_slot.get(ref_name)
            if parent_active is not None:
                return parent_active
        return SessionKey(slot=ref_name, domain="run", value=ref_name)

    def _branch_fresh_key(self, key: SessionKey) -> SessionKey:
        value = key.value
        if not value.startswith(f"{self._namespace}:"):
            value = f"{self._namespace}:{value}"
        return SessionKey(slot=key.slot, domain="fresh", value=value)


__all__ = ["BranchSessionStoreView"]
