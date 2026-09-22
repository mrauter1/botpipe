"""Immutable per-attempt evidence for tools mediated inside native agent loops."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

from .storage import sync_directory


class ToolEvidenceError(RuntimeError):
    """Tool evidence could not be persisted safely; do not return its result."""


def _encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _encode_evidence(value, label):
    try:
        return _encode(value)
    except Exception as exc:
        raise ToolEvidenceError(f"{label} is not durable JSON") from exc


def _publish(path: Path, payload: bytes):
    """Publish a complete synced file without replacing any existing receipt."""
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        sync_directory(path.parent)
    finally:
        os.unlink(temporary)


class ToolEvidence:
    """Persist the authorized envelopes before dispatch and each returned result.

    A fresh recorder may reuse an identical manifest only if no observations
    exist. An observed attempt must be recovered through its native receipt,
    never silently restarted. Persistence or budget failures stop tool delivery.
    """

    def __init__(self, request, profile, *, max_observations=128,
                 max_bytes=4 * 1024 * 1024):
        for name, value in (("max_observations", max_observations),
                            ("max_bytes", max_bytes)):
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if type(profile) is not str or not profile:
            raise ValueError("tool evidence profile must be a non-empty string")
        operation_id = request.operation_id
        attempt = request.attempt
        if type(operation_id) is not str or not operation_id:
            raise ValueError("tool evidence requires an operation ID")
        if type(attempt) is not int or attempt < 1:
            raise ValueError("tool evidence requires a positive attempt")
        identity = hashlib.sha256(operation_id.encode()).hexdigest()
        self.directory = Path(request.receipt_dir) / f"{identity}.attempt-{attempt}.tools"
        self._identity = {"operation_id": operation_id, "attempt": attempt,
                          "profile": profile}
        self.max_observations = max_observations
        self.max_bytes = max_bytes
        self._lock = threading.Lock()
        self._prepared = False
        self._count = 0
        self._bytes = 0

    def prepare(self, envelopes=()):
        """Persist the exact resolved envelopes before the native dispatch."""
        try:
            if isinstance(envelopes, Mapping):
                envelopes = envelopes.values()
            records = [
                item.to_record() if hasattr(item, "to_record") else dict(item)
                for item in envelopes
            ]
        except Exception as exc:
            raise ToolEvidenceError("tool evidence envelopes are malformed") from exc
        records.sort(key=lambda item: _encode_evidence(
            item, "tool evidence envelope"
        ))
        payload = _encode_evidence(
            {"format": 1, **self._identity, "envelopes": records,
             "max_observations": self.max_observations,
             "max_bytes": self.max_bytes},
            "tool evidence manifest",
        )
        if len(payload) > self.max_bytes:
            raise ToolEvidenceError("tool evidence manifest exceeds byte budget")
        with self._lock:
            try:
                self.directory.mkdir(parents=True, exist_ok=True)
                sync_directory(self.directory.parent)
            except OSError as exc:
                raise ToolEvidenceError(
                    "tool evidence directory could not be persisted"
                ) from exc
            manifest = self.directory / "manifest.json"
            try:
                _publish(manifest, payload)
            except FileExistsError:
                try:
                    with manifest.open("rb") as stream:
                        existing = stream.read(len(payload) + 1)
                except OSError as exc:
                    raise ToolEvidenceError(
                        "tool evidence manifest could not be verified"
                    ) from exc
                if existing != payload:
                    raise ToolEvidenceError("tool evidence manifest changed for this attempt")
            except OSError as exc:
                raise ToolEvidenceError(
                    "tool evidence manifest could not be persisted"
                ) from exc
            if not self._prepared:
                try:
                    observed = next(
                        self.directory.glob("observation-*.json"), None
                    )
                except OSError as exc:
                    raise ToolEvidenceError(
                        "tool observation receipts could not be inspected"
                    ) from exc
                if observed is not None:
                    raise ToolEvidenceError("observed tool attempt requires native recovery")
                self._bytes = len(payload)
                self._prepared = True
        return manifest

    def record(self, observation):
        """Save an observation before returning its output to the native model."""
        try:
            value = observation.to_record()
        except Exception as exc:
            raise ToolEvidenceError("tool observation is malformed") from exc
        with self._lock:
            if not self._prepared:
                raise ToolEvidenceError("prepare tool evidence before dispatch")
            if self._count >= self.max_observations:
                raise ToolEvidenceError("tool observation count budget exceeded")
            sequence = self._count + 1
            payload = _encode_evidence(
                {"format": 1, **self._identity, "sequence": sequence,
                 "timestamp": datetime.now(timezone.utc).isoformat(),
                 "observation": value},
                "tool observation",
            )
            if self._bytes + len(payload) > self.max_bytes:
                raise ToolEvidenceError("tool observation byte budget exceeded")
            path = self.directory / f"observation-{sequence:06d}.json"
            try:
                _publish(path, payload)
            except FileExistsError as exc:
                raise ToolEvidenceError("tool observation receipt already exists") from exc
            except OSError as exc:
                raise ToolEvidenceError(
                    "tool observation receipt could not be persisted"
                ) from exc
            self._count = sequence
            self._bytes += len(payload)
        return path

    def close(self):
        """No open resources are retained between writes."""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
