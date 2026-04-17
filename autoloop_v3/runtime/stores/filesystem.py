"""Filesystem implementations of workflow session and checkpoint stores."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ...workflow.stores.memory import InMemorySessionStore
from ...workflow.stores.protocols import CheckpointPayload, SessionBinding, SessionSnapshot
from ..workspace import phase_dir_key, phase_session_path, plan_session_path


class FilesystemSessionStore:
    """Session store with compatibility-aware JSON files on disk."""

    def __init__(
        self,
        run_dir: Path,
        *,
        default_mode: str = "persistent",
        default_provider: str = "codex",
    ) -> None:
        self.run_dir = run_dir
        self.default_mode = default_mode
        self.default_provider = default_provider
        self._memory = InMemorySessionStore()
        self._touched_paths: set[Path] = set()

    def open(self, ref_name: str, scope: str | None = None) -> SessionBinding:
        self._load_binding_if_present(ref_name, scope)
        binding = self._memory.open(ref_name, scope=scope)
        self._write_binding(binding)
        return binding

    def get(self, ref_name: str, scope: str | None = None) -> SessionBinding | None:
        self._load_binding_if_present(ref_name, scope)
        return self._memory.get(ref_name, scope=scope)

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

    def path_for(self, ref_name: str, scope: str | None = None) -> Path:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        if ref_name == "plan_session" and scope is None:
            return plan_session_path(self.run_dir)
        if ref_name == "phase_session" and scope is not None:
            return phase_session_path(self.run_dir, scope)
        if scope is not None:
            key = phase_dir_key(scope)
            return self.run_dir / "sessions" / "phases" / f"{key}--{ref_name}.json"
        return self.run_dir / "sessions" / f"{ref_name}.json"

    def _load_binding_if_present(self, ref_name: str, scope: str | None) -> None:
        candidate_scopes = []
        if scope is not None:
            candidate_scopes.append(scope)
        else:
            snapshot = self._memory.snapshot()
            if ref_name in snapshot.active_scopes:
                candidate_scopes.append(snapshot.active_scopes[ref_name])
            candidate_scopes.append(None)

        for candidate_scope in candidate_scopes:
            if self._memory.get(ref_name, scope=candidate_scope) is not None:
                return
            path = self.path_for(ref_name, candidate_scope)
            if not path.exists():
                continue
            payload = load_session_payload(path, self.default_mode, self.default_provider)
            if payload["session_id"] is None:
                continue
            binding = SessionBinding(
                ref_name=ref_name,
                scope=candidate_scope,
                session_id=payload["session_id"],
                metadata=dict(payload["metadata"]),
            )
            self._memory.upsert(binding, activate=candidate_scope is not None or scope is None)
            self._touched_paths.add(path)
            return

    def _write_binding(self, binding: SessionBinding) -> None:
        path = self.path_for(binding.ref_name, binding.scope)
        existing = load_session_payload(path, self.default_mode, self.default_provider)
        merged_metadata = dict(existing["metadata"])
        merged_metadata.update(binding.metadata)
        payload = _session_payload_from_binding(
            SessionBinding(
                ref_name=binding.ref_name,
                scope=binding.scope,
                session_id=binding.session_id,
                metadata=merged_metadata,
            ),
            default_mode=self.default_mode,
            default_provider=self.default_provider,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        self._touched_paths.add(path)


class FilesystemCheckpointStore:
    """JSON checkpoint store for one run."""

    def __init__(self, path: Path, state_cls: type[BaseModel]) -> None:
        self.path = path
        self.state_cls = state_cls

    def save(self, checkpoint: CheckpointPayload) -> None:
        payload = {
            "stage": checkpoint.stage,
            "state": checkpoint.state.model_dump(mode="json"),
            "session_bindings": {
                "bindings": [asdict(binding) for binding in checkpoint.session_bindings.bindings],
                "active_scopes": checkpoint.session_bindings.active_scopes,
            },
            "pending_question": checkpoint.pending_question,
            "pending_answer": checkpoint.pending_answer,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def load(self) -> CheckpointPayload | None:
        if not self.path.exists():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        session_payload = payload.get("session_bindings") or {}
        bindings = tuple(
            SessionBinding(
                ref_name=str(item.get("ref_name")),
                scope=item.get("scope") if isinstance(item.get("scope"), str) else None,
                session_id=str(item.get("session_id")),
                metadata=dict(item.get("metadata") or {}),
            )
            for item in session_payload.get("bindings", [])
            if isinstance(item, dict)
        )
        return CheckpointPayload(
            stage=str(payload.get("stage") or ""),
            state=self.state_cls.model_validate(payload.get("state") or {}),
            session_bindings=SessionSnapshot(
                bindings=bindings,
                active_scopes={
                    str(key): value if isinstance(value, str) else None
                    for key, value in dict(session_payload.get("active_scopes") or {}).items()
                },
            ),
            pending_question=payload.get("pending_question")
            if isinstance(payload.get("pending_question"), str)
            else None,
            pending_answer=payload.get("pending_answer")
            if isinstance(payload.get("pending_answer"), str)
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
                has_explicit_provider = "provider" in payload
                provider = payload.get("provider") if isinstance(payload.get("provider"), str) else default_provider
                if not has_explicit_provider:
                    provider = "codex"
                session_id = payload.get("session_id") if isinstance(payload.get("session_id"), str) else None
                thread_id = payload.get("thread_id") if isinstance(payload.get("thread_id"), str) else None
                if session_id is None and thread_id is not None:
                    session_id = thread_id
                provider_metadata = payload.get("provider_metadata")
                if not isinstance(provider_metadata, dict):
                    provider_metadata = {}
                metadata = {
                    "provider": provider,
                    "mode": str(payload.get("mode") or default_mode),
                    "provider_metadata": dict(provider_metadata),
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
                    "thread_id": thread_id,
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
            "thread_id": None,
        },
    }


def set_pending_session_note(session_file: Path, note: str) -> None:
    payload = load_session_payload(session_file, default_mode="persistent", default_provider="codex")
    metadata = dict(payload["metadata"])
    metadata["pending_clarification_note"] = note
    payload["metadata"] = metadata
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(
        json.dumps(
            {
                "mode": metadata["mode"],
                "provider": metadata["provider"],
                "session_id": payload["session_id"],
                "thread_id": payload["session_id"] if metadata["provider"] == "codex" else metadata.get("thread_id"),
                "provider_metadata": metadata["provider_metadata"],
                "model_override": metadata["model_override"],
                "effort_override": metadata["effort_override"],
                "pending_clarification_note": metadata["pending_clarification_note"],
                "created_at": metadata["created_at"],
                "last_used_at": metadata["last_used_at"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _session_payload_from_binding(
    binding: SessionBinding,
    *,
    default_mode: str,
    default_provider: str,
) -> dict[str, Any]:
    metadata = dict(binding.metadata)
    provider = metadata.get("provider") if isinstance(metadata.get("provider"), str) else default_provider
    provider_metadata = metadata.get("provider_metadata")
    if not isinstance(provider_metadata, dict):
        provider_metadata = {}
    return {
        "mode": metadata.get("mode") if isinstance(metadata.get("mode"), str) else default_mode,
        "provider": provider,
        "session_id": binding.session_id,
        "thread_id": binding.session_id if provider == "codex" else metadata.get("thread_id"),
        "provider_metadata": provider_metadata,
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
