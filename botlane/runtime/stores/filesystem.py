"""Filesystem implementations of workflow session and checkpoint stores."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from botlane.core.mappings import normalize_mapping
from botlane.core.schema_registry import CHECKPOINT_SCHEMA, migrate_schemaless_payload, validate_persisted_schema
from botlane.core.sessions import SessionKey, canonical_session_slot_name
from botlane.core.stores import SessionStore
from botlane.core.stores.session_store import InMemorySessionBackend, SessionBackend
from botlane.core.stores.protocols import (
    CheckpointPayload,
    PendingHandoff,
    PendingInput,
    SessionBinding,
    SessionSnapshot,
    normalize_persisted_session_key,
)
from botlane.core.worklists import SelectionSnapshot, WorkItemSnapshot
from botlane.extensions.session_paths import SessionPathStrategy


SessionPathResolver = Callable[[Path, str, str | None], Path]
SAFE_SCOPE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def scope_key(scope: str) -> str:
    normalized = scope.strip()
    if not normalized:
        raise ValueError("scope must be a non-empty string")
    if SAFE_SCOPE_RE.fullmatch(normalized):
        return normalized
    return f"_scope-{normalized.encode('utf-8').hex()}"


class FilesystemSessionBackend(SessionBackend):
    """Filesystem-backed session backend."""

    def __init__(
        self,
        run_dir: Path | None = None,
        *,
        task_folder: Path | None = None,
        workflow_folder: Path | None = None,
        run_folder: Path | None = None,
        default_mode: str = "persistent",
        default_provider: str = "codex",
        provider: str | None = None,
        path_strategy: SessionPathStrategy | None = None,
        path_resolver: SessionPathResolver | None = None,
    ) -> None:
        resolved_run_dir = (run_folder or run_dir)
        if resolved_run_dir is None:
            raise TypeError("FilesystemSessionStore requires run_dir=... or run_folder=...")
        self.task_folder = task_folder
        self.workflow_folder = workflow_folder or resolved_run_dir
        self.run_dir = resolved_run_dir
        self.default_mode = default_mode
        self.default_provider = provider or default_provider
        self.path_strategy = path_strategy
        self.path_resolver = path_resolver
        self._memory = InMemorySessionBackend()

    def open(self, ref_name: str | SessionKey, scope: str | None = None) -> SessionBinding:
        key = self._normalize_key(ref_name, scope=scope)
        self._load_binding_if_present(key)
        binding = self._memory.open(key)
        self._write_binding(binding)
        return binding

    def get(self, ref_name: str | SessionKey, scope: str | None = None) -> SessionBinding | None:
        key = self._normalize_key(ref_name, scope=scope, prefer_active=True)
        self._load_binding_if_present(key)
        return self._memory.get(key)

    def upsert(self, binding: SessionBinding, *, activate: bool = True) -> SessionBinding:
        stored = self._memory.upsert(binding, activate=activate)
        self._write_binding(stored)
        return stored

    def snapshot(self) -> SessionSnapshot:
        return self._memory.snapshot()

    def restore(self, snapshot: SessionSnapshot) -> None:
        self._memory.restore(snapshot)
        for binding in snapshot.bindings:
            self._write_binding(binding)

    def path_for(
        self,
        ref_name: str | None = None,
        scope: str | None = None,
        *,
        key: SessionKey | None = None,
    ) -> Path:
        resolved_key = key or self._normalize_key(ref_name or "", scope=scope)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        if self.path_strategy is not None:
            return self.path_strategy.path_for(self.run_dir, resolved_key.slot, _legacy_scope(resolved_key))
        if self.path_resolver is not None:
            return self.path_resolver(self.run_dir, resolved_key.slot, _legacy_scope(resolved_key))
        sessions_dir = self.run_dir / "sessions"
        if resolved_key.domain == "run":
            return sessions_dir / f"{resolved_key.slot}.json"
        if resolved_key.domain == "explicit_scope":
            return sessions_dir / "scopes" / scope_key(resolved_key.value) / f"{resolved_key.slot}.json"
        if resolved_key.domain == "task":
            return self.workflow_folder / "sessions" / "task" / f"{resolved_key.slot}.json"
        if resolved_key.domain == "work_item":
            worklist_name, item_key = _split_work_item_value(resolved_key.value)
            return self.workflow_folder / "sessions" / "work_items" / worklist_name / scope_key(item_key) / (
                f"{resolved_key.slot}.json"
            )
        if resolved_key.domain == "explicit_key":
            return self.workflow_folder / "sessions" / "keys" / resolved_key.slot / f"{scope_key(resolved_key.value)}.json"
        if resolved_key.domain == "fresh":
            return self.run_dir / "sessions" / "fresh" / resolved_key.slot / f"{scope_key(resolved_key.value)}.json"
        raise ValueError(f"unsupported session key domain {resolved_key.domain!r}")

    def _normalize_key(
        self,
        ref_name: str | SessionKey,
        *,
        scope: str | None,
        prefer_active: bool = False,
    ) -> SessionKey:
        if isinstance(ref_name, SessionKey):
            return ref_name
        if scope is not None:
            return SessionKey(slot=ref_name, domain="explicit_scope", value=scope)
        if prefer_active:
            active_key = self._memory.snapshot().active_keys_by_slot.get(ref_name)
            if active_key is not None:
                return active_key
        return SessionKey(slot=ref_name, domain="run", value=ref_name)

    def _load_binding_if_present(self, key: SessionKey) -> None:
        if self._memory.get(key) is not None:
            return
        path = self.path_for(key=key)
        if not path.exists():
            return
        payload = load_session_payload(path, self.default_mode, self.default_provider)
        if payload["session_id"] is None:
            return
        binding = SessionBinding(
            key=key,
            session_id=payload["session_id"],
            provider=payload["metadata"]["provider"],
            provider_metadata=payload["metadata"]["provider_metadata"],
            metadata=normalize_mapping(payload["metadata"]),
        )
        self._memory.upsert(binding, activate=True)

    def _write_binding(self, binding: SessionBinding) -> None:
        path = self.path_for(key=binding.key)
        existing = load_session_payload(path, self.default_mode, self.default_provider)
        merged_metadata = normalize_mapping(existing["metadata"])
        merged_metadata.update(binding.metadata)
        if binding.provider is not None:
            merged_metadata["provider"] = binding.provider
        if binding.provider_metadata or "provider_metadata" in binding.metadata:
            merged_metadata["provider_metadata"] = normalize_mapping(binding.provider_metadata)
        write_session_payload(
            path,
            binding.session_id,
            merged_metadata,
            default_mode=self.default_mode,
            default_provider=self.default_provider,
        )


class FilesystemSessionStore(SessionStore):
    """Filesystem-backed concrete session store."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(FilesystemSessionBackend(*args, **kwargs))

    def __getattr__(self, item: str) -> Any:
        return getattr(self.backend, item)


class FilesystemCheckpointStore:
    """JSON checkpoint store for one run."""

    def __init__(self, path: Path, state_cls: type[BaseModel]) -> None:
        self.path = path
        self.state_cls = state_cls

    def save(self, checkpoint: CheckpointPayload) -> None:
        payload = {
            "schema": CHECKPOINT_SCHEMA,
            "stage": checkpoint.stage,
            "state": checkpoint.state.model_dump(mode="json"),
            "session_bindings": {
                "bindings": [_binding_payload(binding) for binding in checkpoint.session_bindings.bindings],
                "active_keys_by_slot": {
                    slot: _session_key_payload(key)
                    for slot, key in checkpoint.session_bindings.active_keys_by_slot.items()
                },
                "active_scopes": checkpoint.session_bindings.active_scopes,
            },
            "values": checkpoint.values or {},
            "step_states": checkpoint.step_states or {},
            "item_states": checkpoint.item_states or {},
            "step_item_states": checkpoint.step_item_states or {},
            "worklist_selections": {
                name: _selection_snapshot_payload(selection)
                for name, selection in (checkpoint.worklist_selections or {}).items()
            },
            "pending_handoffs": [_pending_handoff_payload(handoff) for handoff in checkpoint.pending_handoffs],
            "pending_input": _pending_input_payload(checkpoint.pending_input),
            "pending_answer": checkpoint.pending_answer,
            "failure_context": checkpoint.failure_context,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def load(self) -> CheckpointPayload | None:
        if not self.path.exists():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        validate_persisted_schema(
            payload,
            expected=CHECKPOINT_SCHEMA,
            artifact_name=str(self.path),
            legacy_migrator=lambda value: migrate_schemaless_payload(value, expected=CHECKPOINT_SCHEMA),
        )
        session_payload = payload.get("session_bindings") or {}
        bindings = tuple(
            _binding_from_payload(item)
            for item in session_payload.get("bindings", [])
            if isinstance(item, dict)
        )
        active_keys_payload = session_payload.get("active_keys_by_slot")
        active_keys_by_slot = (
            {
                str(slot): _session_key_from_payload(item, fallback_slot=str(slot))
                for slot, item in normalize_mapping(active_keys_payload).items()
                if isinstance(item, dict)
            }
            if isinstance(active_keys_payload, dict)
            else {}
        )
        active_scopes = {
            str(key): value if isinstance(value, str) else None
            for key, value in normalize_mapping(session_payload.get("active_scopes")).items()
        }
        worklist_payload = payload.get("worklist_selections")
        worklist_selections = (
            {
                str(name): _selection_snapshot_from_payload(item, fallback_name=str(name))
                for name, item in normalize_mapping(worklist_payload).items()
                if isinstance(item, dict)
            }
            if isinstance(worklist_payload, dict)
            else None
        )
        pending_handoffs_payload = payload.get("pending_handoffs")
        pending_handoffs = (
            tuple(
                _pending_handoff_from_payload(item)
                for item in pending_handoffs_payload
                if isinstance(item, dict)
            )
            if isinstance(pending_handoffs_payload, list)
            else ()
        )
        pending_input_payload = payload.get("pending_input")
        return CheckpointPayload(
            stage=str(payload.get("stage") or ""),
            state=self.state_cls.model_validate(payload.get("state") or {}),
            session_bindings=SessionSnapshot(
                bindings=bindings,
                active_keys_by_slot=active_keys_by_slot,
                active_scopes=active_scopes,
            ),
            values=_string_key_mapping(payload.get("values")),
            step_states=_nested_string_dict(payload.get("step_states")),
            item_states=_nested_string_dict(payload.get("item_states")),
            step_item_states=_triple_nested_string_dict(payload.get("step_item_states")),
            worklist_selections=worklist_selections,
            pending_handoffs=pending_handoffs,
            pending_input=_pending_input_from_payload(pending_input_payload)
            if isinstance(pending_input_payload, Mapping)
            else None,
            pending_question=payload.get("pending_question")
            if isinstance(payload.get("pending_question"), str)
            else None,
            pending_answer=payload.get("pending_answer") if isinstance(payload.get("pending_answer"), str) else None,
            failure_context=normalize_mapping(payload.get("failure_context"))
            if isinstance(payload.get("failure_context"), dict)
            else None,
        )

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()


def load_session_payload(path: Path, default_mode: str, default_provider: str) -> dict[str, Any]:
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                provider = payload.get("provider") if isinstance(payload.get("provider"), str) else default_provider
                session_id = payload.get("session_id") if isinstance(payload.get("session_id"), str) else None
                provider_metadata = payload.get("provider_metadata")
                if not isinstance(provider_metadata, dict):
                    provider_metadata = {}
                metadata = {
                    "provider": provider,
                    "mode": str(payload.get("mode") or default_mode),
                    "provider_metadata": normalize_mapping(provider_metadata),
                    "model_override": payload.get("model_override")
                    if isinstance(payload.get("model_override"), str)
                    else None,
                    "effort_override": payload.get("effort_override")
                    if isinstance(payload.get("effort_override"), str)
                    else None,
                    "pending_clarification_note": payload.get("pending_clarification_note")
                    if isinstance(payload.get("pending_clarification_note"), str)
                    else None,
                    "created_at": str(payload.get("created_at") or datetime.now(timezone.utc).isoformat()),
                    "last_used_at": payload.get("last_used_at") if isinstance(payload.get("last_used_at"), str) else None,
                }
                return {"session_id": session_id, "metadata": metadata}
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "session_id": None,
        "metadata": {
            "provider": default_provider,
            "mode": default_mode,
            "provider_metadata": {},
            "model_override": None,
            "effort_override": None,
            "pending_clarification_note": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_used_at": None,
        },
    }


def write_session_payload(
    path: Path,
    session_id: str | None,
    metadata: dict[str, Any],
    *,
    default_mode: str = "persistent",
    default_provider: str = "codex",
) -> None:
    payload = _session_payload_from_values(
        session_id,
        metadata,
        default_mode=default_mode,
        default_provider=default_provider,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def ensure_session_payload_placeholder(
    path: Path,
    *,
    default_mode: str = "persistent",
    default_provider: str = "codex",
) -> None:
    payload = load_session_payload(path, default_mode=default_mode, default_provider=default_provider)
    write_session_payload(
        path,
        payload["session_id"],
        normalize_mapping(payload["metadata"]),
        default_mode=default_mode,
        default_provider=default_provider,
    )


def set_pending_session_note(session_file: Path, note: str) -> None:
    payload = load_session_payload(session_file, default_mode="persistent", default_provider="codex")
    metadata = normalize_mapping(payload["metadata"])
    metadata["pending_clarification_note"] = note
    write_session_payload(
        session_file,
        payload["session_id"],
        metadata,
        default_mode="persistent",
        default_provider="codex",
    )


def _session_payload_from_values(
    session_id: str | None,
    metadata: dict[str, Any],
    *,
    default_mode: str,
    default_provider: str,
) -> dict[str, Any]:
    metadata = normalize_mapping(metadata)
    provider = metadata.get("provider") if isinstance(metadata.get("provider"), str) else default_provider
    provider_metadata = metadata.get("provider_metadata")
    if not isinstance(provider_metadata, dict):
        provider_metadata = {}
    return {
        "mode": metadata.get("mode") if isinstance(metadata.get("mode"), str) else default_mode,
        "provider": provider,
        "session_id": session_id,
        "provider_metadata": normalize_mapping(provider_metadata),
        "model_override": metadata.get("model_override") if isinstance(metadata.get("model_override"), str) else None,
        "effort_override": metadata.get("effort_override")
        if isinstance(metadata.get("effort_override"), str)
        else None,
        "pending_clarification_note": metadata.get("pending_clarification_note")
        if isinstance(metadata.get("pending_clarification_note"), str)
        else None,
        "created_at": metadata.get("created_at")
        if isinstance(metadata.get("created_at"), str)
        else datetime.now(timezone.utc).isoformat(),
        "last_used_at": metadata.get("last_used_at") if isinstance(metadata.get("last_used_at"), str) else None,
    }


def _binding_payload(binding: SessionBinding) -> dict[str, Any]:
    return {
        "key": _session_key_payload(binding.key),
        "ref_name": binding.ref_name,
        "scope": binding.scope,
        "session_id": binding.session_id,
        "provider": binding.provider,
        "provider_metadata": normalize_mapping(binding.provider_metadata),
        "metadata": normalize_mapping(binding.metadata),
    }


def _binding_from_payload(payload: dict[str, Any]) -> SessionBinding:
    key_payload = payload.get("key")
    ref_name = payload.get("ref_name")
    scope = payload.get("scope") if isinstance(payload.get("scope"), str) else None
    key = (
        _session_key_from_payload(key_payload, fallback_slot=str(ref_name or ""))
        if isinstance(key_payload, dict)
        else None
    )
    return SessionBinding(
        key=key,
        ref_name=canonical_session_slot_name(str(ref_name)) if ref_name is not None else None,
        scope=scope,
        session_id=payload.get("session_id") if isinstance(payload.get("session_id"), str) else None,
        provider=payload.get("provider") if isinstance(payload.get("provider"), str) else None,
        provider_metadata=normalize_mapping(payload.get("provider_metadata"))
        if isinstance(payload.get("provider_metadata"), dict)
        else None,
        metadata=normalize_mapping(payload.get("metadata")) if isinstance(payload.get("metadata"), dict) else None,
    )


def _session_key_payload(key: SessionKey) -> dict[str, str]:
    return {"slot": key.slot, "domain": key.domain, "value": key.value}


def _session_key_from_payload(payload: Mapping[str, Any], *, fallback_slot: str) -> SessionKey:
    slot = payload.get("slot")
    domain = payload.get("domain")
    value = payload.get("value")
    if isinstance(slot, str) and isinstance(domain, str) and isinstance(value, str):
        return normalize_persisted_session_key(SessionKey(slot=slot, domain=domain, value=value))
    normalized_fallback = canonical_session_slot_name(fallback_slot)
    return SessionKey(slot=normalized_fallback, domain="run", value=normalized_fallback)


def _selection_snapshot_payload(snapshot: SelectionSnapshot) -> dict[str, Any]:
    return {
        "worklist_name": snapshot.worklist_name,
        "mode": snapshot.mode,
        "items": [
            {
                "id": item.id,
                "title": item.title,
                "status": item.status,
                "dir_key": item.dir_key,
            }
            for item in snapshot.items
        ],
        "explicit": snapshot.explicit,
        "current_index": snapshot.current_index,
    }


def _selection_snapshot_from_payload(payload: Mapping[str, Any], *, fallback_name: str) -> SelectionSnapshot:
    raw_items = payload.get("items")
    items = (
        tuple(
            WorkItemSnapshot(
                id=str(item.get("id") or ""),
                title=str(item.get("title") or ""),
                status=item.get("status") if isinstance(item.get("status"), str) else None,
                dir_key=item.get("dir_key") if isinstance(item.get("dir_key"), str) else None,
            )
            for item in raw_items
            if isinstance(item, Mapping)
        )
        if isinstance(raw_items, list)
        else ()
    )
    return SelectionSnapshot(
        worklist_name=str(payload.get("worklist_name") or fallback_name),
        mode=str(payload.get("mode") or "all"),
        items=items,
        explicit=bool(payload.get("explicit", False)),
        current_index=int(payload.get("current_index") or 0),
    )


def _pending_handoff_payload(handoff: PendingHandoff) -> dict[str, Any]:
    return {
        "source_step": handoff.source_step,
        "route_tag": handoff.route_tag,
        "target_step": handoff.target_step,
        "message": handoff.message,
        "worklist_name": handoff.worklist_name,
        "item_id": handoff.item_id,
    }


def _pending_handoff_from_payload(payload: Mapping[str, Any]) -> PendingHandoff:
    return PendingHandoff(
        source_step=str(payload.get("source_step") or ""),
        route_tag=str(payload.get("route_tag") or ""),
        target_step=str(payload.get("target_step") or ""),
        message=str(payload.get("message") or ""),
        worklist_name=payload.get("worklist_name") if isinstance(payload.get("worklist_name"), str) else None,
        item_id=payload.get("item_id") if isinstance(payload.get("item_id"), str) else None,
    )


def _pending_input_payload(pending_input: PendingInput | None) -> dict[str, Any] | None:
    if pending_input is None:
        return None
    return {
        "pending_input_id": pending_input.pending_input_id,
        "source_step": pending_input.source_step,
        "source_hook": pending_input.source_hook,
        "source_phase": pending_input.source_phase,
        "question": pending_input.question,
        "reason": pending_input.reason,
        "best_supposition": pending_input.best_supposition,
        "input_schema": normalize_mapping(pending_input.input_schema) if isinstance(pending_input.input_schema, Mapping) else None,
        "input_schema_model": pending_input.input_schema_model,
        "created_at": pending_input.created_at,
    }


def _pending_input_from_payload(payload: Mapping[str, Any]) -> PendingInput:
    input_schema = payload.get("input_schema")
    return PendingInput(
        pending_input_id=str(payload.get("pending_input_id") or ""),
        source_step=str(payload.get("source_step") or ""),
        source_hook=payload.get("source_hook") if isinstance(payload.get("source_hook"), str) else None,
        source_phase=payload.get("source_phase") if isinstance(payload.get("source_phase"), str) else None,
        question=str(payload.get("question") or ""),
        reason=payload.get("reason") if isinstance(payload.get("reason"), str) else None,
        best_supposition=payload.get("best_supposition")
        if isinstance(payload.get("best_supposition"), str)
        else None,
        input_schema=normalize_mapping(input_schema) if isinstance(input_schema, Mapping) else None,
        input_schema_model=payload.get("input_schema_model")
        if isinstance(payload.get("input_schema_model"), str)
        else None,
        created_at=payload.get("created_at") if isinstance(payload.get("created_at"), str) else None,
    )


def _nested_string_dict(value: object) -> dict[str, dict[str, Any]] | None:
    if not isinstance(value, Mapping):
        return None
    normalized: dict[str, dict[str, Any]] = {}
    for key, nested in value.items():
        if isinstance(key, str) and isinstance(nested, Mapping):
            normalized[key] = normalize_mapping(nested)
    return normalized


def _string_key_mapping(value: object) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return {key: nested for key, nested in value.items() if isinstance(key, str)}


def _triple_nested_string_dict(value: object) -> dict[str, dict[str, dict[str, Any]]] | None:
    if not isinstance(value, Mapping):
        return None
    normalized: dict[str, dict[str, dict[str, Any]]] = {}
    for key, nested in value.items():
        if not isinstance(key, str) or not isinstance(nested, Mapping):
            continue
        normalized_nested: dict[str, dict[str, Any]] = {}
        for nested_key, nested_value in nested.items():
            if isinstance(nested_key, str) and isinstance(nested_value, Mapping):
                normalized_nested[nested_key] = normalize_mapping(nested_value)
        normalized[key] = normalized_nested
    return normalized


def _legacy_scope(key: SessionKey) -> str | None:
    return key.value if key.domain == "explicit_scope" else None


def _split_work_item_value(value: str) -> tuple[str, str]:
    if ":" not in value:
        return "_", value
    worklist_name, item_key = value.split(":", 1)
    return worklist_name or "_", item_key
