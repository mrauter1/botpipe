"""A conversation's durable binding, protected by its existing session lock."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path

from .errors import SessionError
from .journal import Journal
from .storage import sync_directory


class SessionBinding:
    """Keep one pending logical call through all of its validation and repairs.

    The caller holds the cross-process session lock. This object's guard only
    serializes checkpoint callbacks belonging to that same lock holder.
    """

    def __init__(self, journal: Journal, key: str):
        self.journal, self.key = journal, key
        token = hashlib.sha256(key.encode()).hexdigest()
        self.path = journal.path / "sessions" / f"{token}.json"
        self._guard = threading.RLock()

    def read(self):
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"format": 1, "key": self.key, "session_id": None, "pending": None}
        except (OSError, ValueError) as exc:
            raise SessionError(
                f"Cannot read session binding {self.path}: {exc}"
            ) from exc
        if (
            not isinstance(value, dict)
            or value.get("format") != 1
            or value.get("key") != self.key
            or set(value) != {"format", "key", "session_id", "pending"}
            or (
                value["session_id"] is not None
                and not isinstance(value["session_id"], str)
            )
        ):
            raise SessionError(f"Invalid session binding {self.path}")
        pending = value["pending"]
        if pending is not None and (
            not isinstance(pending, dict)
            or set(pending)
            != {"run_id", "run_path", "operation_key", "operation_id", "attempt"}
            or not all(
                isinstance(pending[k], str) and pending[k]
                for k in ("run_id", "run_path", "operation_key", "operation_id")
            )
            or type(pending["attempt"]) is not int
            or pending["attempt"] < 1
        ):
            raise SessionError(f"Invalid pending operation in {self.path}")
        return value

    def _write(self, value):
        content = (
            json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
        ).encode()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".binding-", dir=self.path.parent
        )
        try:
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
                sync_directory(self.path.parent)
            except OSError:
                # A replacement may have succeeded before its acknowledgement
                # failed. Exact bytes plus a successful sync establish the write.
                with self.path.open("r+b") as stream:
                    if stream.read() != content:
                        raise
                    os.fsync(stream.fileno())
                sync_directory(self.path.parent)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def check(self, operation_key):
        """Reconcile only already recorded facts; never execute a foreign run."""
        with self._guard:
            value = self.read()
            pending = value["pending"]
            if pending is None:
                return value
            same_logical_call = pending["operation_key"] == operation_key
            try:
                snapshot = Journal.read_only_snapshot(
                    self.journal.path, pending["run_id"]
                )
                if (
                    Path(snapshot.run["folder"]).resolve()
                    != Path(pending["run_path"]).resolve()
                ):
                    raise ValueError(
                        "Pending owner run directory does not match its ledger"
                    )
            except (OSError, ValueError, KeyError) as exc:
                raise SessionError(
                    f"Session {self.key} refers to unavailable run {pending['run_id']}: {exc}"
                ) from exc
            owner = next(
                (
                    operation
                    for operation in snapshot.operations
                    if operation.get("id") == pending["operation_id"]
                ),
                None,
            )
            inputs = None if owner is None else owner.get("inputs")
            values = (
                inputs.get("value")
                if isinstance(inputs, dict)
                and inputs.get("$botpipe") == "dict"
                and isinstance(inputs.get("value"), dict)
                else None
            )
            if (
                owner is None
                or owner.get("run_id") != pending["run_id"]
                or owner.get("kind") != "provider"
                or values is None
                or values.get("operation_key") != pending["operation_key"]
            ):
                raise SessionError(
                    f"Session {self.key} has invalid owner operation "
                    f"{pending['run_id']}/{pending['operation_id']}"
                )

            prepared = any(
                event["event"] == "attempt_prepared"
                and event.get("operation_id") == pending["operation_id"]
                and event["data"].get("attempt") == pending["attempt"]
                for event in snapshot.events
            )
            response = owner.get("response")
            latest_retry = (
                isinstance(response, dict)
                and response.get("retry_authorized") is True
                and response.get("retry_origin") == "operator"
                and type(response.get("generation")) is int
                and response["generation"] + 1 == pending["attempt"]
            )
            selected_resolution_pending = False
            authorized_retry_in_history = False
            for event in snapshot.events:
                if event.get("operation_id") != pending["operation_id"]:
                    continue
                if event["event"] == "resolution_selected":
                    selected_resolution_pending = True
                elif event["event"] == "operation_reconciled":
                    selected_resolution_pending = False
                elif event["event"] == "operation_response":
                    historical = event["data"].get("response")
                    authorized_retry_in_history |= (
                        isinstance(historical, dict)
                        and historical.get("retry_authorized") is True
                        and historical.get("retry_origin") == "operator"
                        and type(historical.get("generation")) is int
                        and historical["generation"] + 1 == pending["attempt"]
                    )
            pending_retry = latest_retry or (
                selected_resolution_pending and authorized_retry_in_history
            )
            if not prepared and not pending_retry:
                raise SessionError(
                    f"Session {self.key} has invalid owner attempt "
                    f"{pending['run_id']}/{pending['operation_id']}/{pending['attempt']}"
                )
            if same_logical_call:
                return value
            settled = next(
                (
                    event
                    for event in reversed(snapshot.events)
                    if event["event"] == "provider_call_finished"
                    and event.get("operation_id") == pending["operation_id"]
                    and event["data"].get("operation_key") == pending["operation_key"]
                    and event["data"].get("attempt") == pending["attempt"]
                ),
                None,
            )
            members = {
                operation["id"]
                for operation in snapshot.operations
                if operation.get("kind") == "provider"
                and isinstance(operation.get("inputs"), dict)
                and operation["inputs"].get("$botpipe") == "dict"
                and isinstance(operation["inputs"].get("value"), dict)
                and operation["inputs"]["value"].get("operation_key")
                == pending["operation_key"]
            }
            dispatched = any(
                event["event"] == "provider_dispatch_reserved"
                and event.get("operation_id") in members
                for event in snapshot.events
            )
            if settled is None and (dispatched or pending_retry):
                raise SessionError(
                    f"Session {self.key} belongs to unfinished run {pending['run_id']} "
                    f"operation {pending['operation_id']} attempt {pending['attempt']}; "
                    "resume or resolve that run"
                )
            if settled is not None and settled["data"].get("session_id"):
                value["session_id"] = settled["data"]["session_id"]
            value["pending"] = None
            self._write(value)
            return value

    def claim(self, run_id, operation_key, operation_id, attempt):
        with self._guard:
            value = self.check(operation_key)
            value["pending"] = {
                "run_id": run_id,
                "run_path": self.journal.run(run_id)["folder"],
                "operation_key": operation_key,
                "operation_id": operation_id,
                "attempt": attempt,
            }
            self._write(value)

    def advance(self, operation_key, session_id):
        if not session_id:
            return
        with self._guard:
            value = self.read()
            pending = value["pending"]
            if pending is None:
                return
            if pending["operation_key"] != operation_key:
                raise SessionError("A checkpoint no longer owns its conversation")
            if value["session_id"] != session_id:
                value["session_id"] = session_id
                self._write(value)

    def finish(
        self,
        run_id,
        operation_key,
        *,
        operation_id,
        attempt,
        session_id=None,
        outcome="completed",
    ):
        with self._guard:
            settled = next(
                (
                    event
                    for event in self.journal.events(run_id)
                    if event["event"] == "provider_call_finished"
                    and event.get("operation_id") == operation_id
                    and event["data"].get("operation_key") == operation_key
                    and event["data"].get("attempt") == attempt
                ),
                None,
            )
            value = self.read()
            pending = value["pending"]
            owns_binding = pending is not None and all(
                (
                    pending["run_id"] == run_id,
                    pending["operation_key"] == operation_key,
                    pending["operation_id"] == operation_id,
                    pending["attempt"] == attempt,
                )
            )
            if settled is not None:
                if owns_binding:
                    settled_session = settled["data"].get("session_id")
                    if settled_session:
                        value["session_id"] = settled_session
                    value["pending"] = None
                    self._write(value)
                return
            if owns_binding and session_id:
                value["session_id"] = session_id
            # Recording settlement first lets another run repair a stale binding
            # after a crash between the ledger append and the atomic replacement.
            self.journal.event(
                run_id,
                "provider_call_finished",
                {
                    "operation_key": operation_key,
                    "attempt": attempt,
                    "session_id": (value["session_id"] if owns_binding else session_id),
                    "outcome": outcome,
                },
                operation_id,
            )
            if owns_binding:
                value["pending"] = None
                self._write(value)
