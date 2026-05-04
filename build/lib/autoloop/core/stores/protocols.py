"""Store protocols for sessions and checkpoints."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel

from ..sessions import DEFAULT_SESSION_NAME, LEGACY_DEFAULT_SESSION_NAME, SessionKey, canonical_session_slot_name
from ..worklists import SelectionSnapshot


@dataclass(frozen=True, slots=True)
class PendingHandoff:
    """Persisted route handoff awaiting delivery to a provider-mediated step."""

    source_step: str
    route_tag: str
    target_step: str
    message: str
    worklist_name: str | None = None
    item_id: str | None = None


@dataclass(frozen=True, slots=True)
class PendingInput:
    """Persisted awaiting-input metadata."""

    pending_input_id: str
    source_step: str
    question: str
    source_hook: str | None = None
    source_phase: str | None = None
    reason: str | None = None
    best_supposition: str | None = None
    input_schema: dict[str, Any] | None = None
    input_schema_model: str | None = None
    created_at: str | None = None


@dataclass(frozen=True, slots=True, init=False)
class SessionBinding:
    """Concrete session binding."""

    key: SessionKey
    ref_name: str
    scope: str | None
    session_id: str | None
    provider: str | None
    provider_metadata: dict[str, Any]
    metadata: dict[str, Any]

    def __init__(
        self,
        *,
        key: SessionKey | None = None,
        ref_name: str | None = None,
        scope: str | None = None,
        session_id: str | None,
        provider: str | None = None,
        provider_metadata: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        base_metadata = dict(metadata or {})
        resolved_key = _normalize_binding_key(key=key, ref_name=ref_name, scope=scope)
        resolved_provider_metadata = dict(provider_metadata or {})
        metadata_provider = base_metadata.get("provider") if isinstance(base_metadata.get("provider"), str) else None
        resolved_provider = provider or metadata_provider
        metadata_provider_metadata = base_metadata.get("provider_metadata")
        if isinstance(metadata_provider_metadata, Mapping):
            resolved_provider_metadata = dict(metadata_provider_metadata)
        merged_metadata = dict(base_metadata)
        if resolved_provider is not None:
            merged_metadata["provider"] = resolved_provider
        if resolved_provider_metadata or "provider_metadata" in base_metadata:
            merged_metadata["provider_metadata"] = dict(resolved_provider_metadata)
        object.__setattr__(self, "key", resolved_key)
        object.__setattr__(self, "ref_name", resolved_key.slot)
        object.__setattr__(self, "scope", resolved_key.value if resolved_key.domain == "explicit_scope" else scope)
        object.__setattr__(self, "session_id", session_id)
        object.__setattr__(self, "provider", resolved_provider)
        object.__setattr__(self, "provider_metadata", dict(resolved_provider_metadata))
        object.__setattr__(self, "metadata", merged_metadata)


@dataclass(frozen=True, slots=True, init=False)
class SessionSnapshot:
    """Serializable session snapshot."""

    bindings: tuple[SessionBinding, ...]
    active_keys_by_slot: dict[str, SessionKey]
    active_scopes: dict[str, str | None]

    def __init__(
        self,
        *,
        bindings: tuple[SessionBinding, ...],
        active_keys_by_slot: Mapping[str, SessionKey] | None = None,
        active_scopes: Mapping[str, str | None] | None = None,
    ) -> None:
        normalized_keys = dict(active_keys_by_slot or {})
        normalized_scopes = dict(active_scopes or {})
        object.__setattr__(self, "bindings", tuple(bindings))
        object.__setattr__(self, "active_keys_by_slot", normalized_keys)
        object.__setattr__(
            self,
            "active_scopes",
            _normalize_active_scopes(normalized_keys) if normalized_keys else normalized_scopes,
        )


@dataclass(frozen=True, slots=True)
class CheckpointPayload:
    """Typed checkpoint persistence payload."""

    stage: str
    state: BaseModel
    session_bindings: SessionSnapshot
    values: dict[str, Any] | None = None
    step_states: dict[str, dict[str, Any]] | None = None
    item_states: dict[str, dict[str, Any]] | None = None
    step_item_states: dict[str, dict[str, dict[str, Any]]] | None = None
    worklist_selections: dict[str, SelectionSnapshot] | None = None
    pending_handoffs: tuple[PendingHandoff, ...] = ()
    pending_input: PendingInput | None = None
    pending_question: str | None = None
    pending_answer: str | None = None
    failure_context: dict[str, Any] | None = None


class SessionStore(Protocol):
    """Concrete session binding backend."""

    def open(self, ref_name: str | SessionKey, scope: str | None = None) -> SessionBinding:
        """Open or reuse a binding and set it active for the slot."""

    def get(self, ref_name: str | SessionKey, scope: str | None = None) -> SessionBinding | None:
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


def _normalize_binding_key(
    *,
    key: SessionKey | None,
    ref_name: str | None,
    scope: str | None,
) -> SessionKey:
    if key is not None:
        return key
    if ref_name is None:
        raise TypeError("SessionBinding requires either key=... or ref_name=...")
    if scope is None:
        return SessionKey(slot=ref_name, domain="run", value=ref_name)
    return SessionKey(slot=ref_name, domain="explicit_scope", value=scope)


def is_run_key_bound_to_slot(key: SessionKey | None, *, slot: str | None = None) -> bool:
    """Return whether a run-continuity key still uses the session slot as its value."""

    if key is None or key.domain != "run":
        return False
    expected_slot = slot or key.slot
    return key.slot == expected_slot and key.value == expected_slot


def normalize_session_snapshot(snapshot: SessionSnapshot, *, run_id: str) -> SessionSnapshot:
    normalized_bindings_by_key: dict[SessionKey, SessionBinding] = {}
    binding_order: list[SessionKey] = []
    changed = False
    for binding in snapshot.bindings:
        normalized_binding = _normalize_binding_for_run(binding, run_id=run_id)
        if normalized_binding.key not in normalized_bindings_by_key:
            binding_order.append(normalized_binding.key)
        normalized_bindings_by_key[normalized_binding.key] = normalized_binding
        changed = changed or normalized_binding != binding

    normalized_active_keys: dict[str, SessionKey] = {}
    for slot, key in snapshot.active_keys_by_slot.items():
        normalized_key = _normalize_session_key_for_run(key, run_id=run_id)
        normalized_slot = normalized_key.slot
        normalized_active_keys[normalized_slot] = normalized_key
        changed = changed or normalized_slot != slot or normalized_key != key

    normalized_active_scopes = {
        canonical_session_slot_name(slot): scope
        for slot, scope in snapshot.active_scopes.items()
    }
    changed = changed or normalized_active_keys != snapshot.active_keys_by_slot
    changed = changed or normalized_active_scopes != snapshot.active_scopes
    if not changed:
        return snapshot
    return SessionSnapshot(
        bindings=tuple(normalized_bindings_by_key[key] for key in binding_order),
        active_keys_by_slot=normalized_active_keys or None,
        active_scopes=normalized_active_scopes if not normalized_active_keys else None,
    )


def _normalize_active_scopes(active_keys_by_slot: Mapping[str, SessionKey]) -> dict[str, str | None]:
    return {
        slot: key.value if key.domain == "explicit_scope" else None
        for slot, key in active_keys_by_slot.items()
    }


def _normalize_binding_for_run(binding: SessionBinding, *, run_id: str) -> SessionBinding:
    normalized_key = _normalize_session_key_for_run(binding.key, run_id=run_id)
    if normalized_key == binding.key:
        return binding
    return SessionBinding(
        key=normalized_key,
        session_id=binding.session_id,
        provider=binding.provider,
        provider_metadata=binding.provider_metadata,
        metadata=binding.metadata,
    )


def _normalize_session_key_for_run(key: SessionKey, *, run_id: str) -> SessionKey:
    normalized_slot = canonical_session_slot_name(key.slot)
    normalized_value = key.value
    if key.domain == "run":
        if normalized_value == LEGACY_DEFAULT_SESSION_NAME and normalized_slot == DEFAULT_SESSION_NAME:
            normalized_value = DEFAULT_SESSION_NAME
        if normalized_value == normalized_slot:
            normalized_value = run_id
    if normalized_slot == key.slot and normalized_value == key.value:
        return key
    return SessionKey(slot=normalized_slot, domain=key.domain, value=normalized_value)


def normalize_persisted_session_key(key: SessionKey) -> SessionKey:
    """Normalize persisted legacy session slot naming without rebinding run scope."""

    slot = canonical_session_slot_name(key.slot)
    value = key.value
    if key.domain == "run":
        if value == LEGACY_DEFAULT_SESSION_NAME and slot == DEFAULT_SESSION_NAME:
            value = DEFAULT_SESSION_NAME
    if slot == key.slot and value == key.value:
        return key
    return SessionKey(slot=slot, domain=key.domain, value=value)
