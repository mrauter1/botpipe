"""Transactional operation history for local durable workflows."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import RunBusy


def now():
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class JournalSnapshot:
    """One committed view of a run and all of its recorded evidence."""

    run: dict[str, Any]
    operations: tuple[dict[str, Any], ...]
    events: tuple[dict[str, Any], ...]


class Journal:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(
            self.path, timeout=30, isolation_level=None, check_same_thread=False
        )
        self.db.row_factory = sqlite3.Row
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            self.db.close()
            raise ValueError(f"Unsupported Botpipe journal version {version}")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, metadata TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS operations (
            id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
            scope TEXT NOT NULL, ordinal INTEGER NOT NULL, kind TEXT NOT NULL,
            name TEXT, fingerprint TEXT NOT NULL, inputs TEXT NOT NULL,
            status TEXT NOT NULL, result TEXT, error TEXT, response TEXT,
            started_at TEXT NOT NULL, finished_at TEXT,
            UNIQUE(run_id,scope,ordinal));
          CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS provider_budgets (id TEXT PRIMARY KEY, state TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL, operation_id TEXT, event TEXT NOT NULL, data TEXT NOT NULL, at TEXT NOT NULL);
          PRAGMA user_version=1;
        """)

    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield self.db
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            else:
                try:
                    self.db.execute("COMMIT")
                except BaseException:
                    if self.db.in_transaction:
                        self.db.execute("ROLLBACK")
                    raise

    def confirmed(self, operation_id):
        """Read a checkpoint through an independent committed database view."""
        with self.lock:
            if self.db.in_transaction:
                self.db.rollback()
            connection = sqlite3.connect(
                self.path.resolve().as_uri() + "?mode=ro", uri=True
            )
            connection.row_factory = sqlite3.Row
            try:
                row = connection.execute(
                    "SELECT * FROM operations WHERE id=?", (operation_id,)
                ).fetchone()
                return self._record(row)
            finally:
                connection.close()

    def close(self):
        with self.lock:
            self.db.close()

    def create_run(self, data):
        with self.transaction() as db:
            db.execute(
                "INSERT INTO runs VALUES (?,?)", (data["run_id"], json.dumps(data))
            )

    def run(self, run_id):
        with self.lock:
            row = self.db.execute(
                "SELECT metadata FROM runs WHERE id=?", (run_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown run {run_id}")
        return json.loads(row[0])

    def update_run(self, run_id, **updates):
        with self.transaction() as db:
            row = db.execute(
                "SELECT metadata FROM runs WHERE id=?", (run_id,)
            ).fetchone()
            if row is None:
                raise KeyError(run_id)
            data = json.loads(row[0])
            data.update(updates)
            db.execute(
                "UPDATE runs SET metadata=? WHERE id=?", (json.dumps(data), run_id)
            )

    def runs(self):
        with self.lock:
            return [
                json.loads(row[0])
                for row in self.db.execute(
                    "SELECT metadata FROM runs ORDER BY rowid DESC"
                )
            ]

    @classmethod
    def read_only_snapshot(cls, path, run_id):
        """Read a foreign journal without creating or migrating anything."""

        path = Path(path)
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA query_only=ON")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version != 1:
                raise ValueError(f"Unsupported Botpipe journal version {version}")
            return cls._snapshot(connection, run_id)
        finally:
            connection.close()

    def snapshot(self, run_id):
        """Return run, operation, and event facts from one database snapshot."""

        with self.lock:
            # Inspection is a view of committed authority, including when the
            # writer connection currently has an uncommitted transaction.
            return self.read_only_snapshot(self.path, run_id)

    @classmethod
    def _snapshot(cls, db, run_id):
        db.execute("BEGIN")
        try:
            run_row = db.execute(
                "SELECT metadata FROM runs WHERE id=?", (run_id,)
            ).fetchone()
            if run_row is None:
                raise KeyError(f"Unknown run {run_id}")
            operation_rows = list(
                db.execute(
                    "SELECT * FROM operations WHERE run_id=? ORDER BY started_at,id",
                    (run_id,),
                )
            )
            event_rows = list(
                db.execute(
                    "SELECT * FROM events WHERE run_id=? ORDER BY seq", (run_id,)
                )
            )
            run = json.loads(run_row[0])
            if type(run) is not dict or run.get("run_id") != run_id:
                raise ValueError("Run metadata does not match its journal identity")
            snapshot = JournalSnapshot(
                run=run,
                operations=tuple(cls._record(row) for row in operation_rows),
                events=tuple(
                    {**dict(row), "data": json.loads(row["data"])} for row in event_rows
                ),
            )
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        else:
            db.execute("COMMIT")
            return snapshot

    @classmethod
    def foreign_has_unresolved_effects(cls, path, run_id):
        """Conservatively decide whether a foreign run may still own effects."""

        try:
            snapshot = cls.read_only_snapshot(path, run_id)
            return cls._has_unresolved_effects(snapshot.operations)
        except (OSError, sqlite3.Error, KeyError, TypeError, ValueError, UnicodeError):
            return True

    @staticmethod
    def _has_unresolved_effects(operations):
        for record in operations:
            kind = record.get("kind")
            if kind not in {"activity", "provider"}:
                continue
            status = record.get("status")
            if status in {"completed", "failed"}:
                continue
            if status not in {"started", "response"}:
                return True
            if kind == "activity":
                # Activities have no typed non-dispatch checkpoint. Until their
                # operation reaches a terminal state, their effects are unknown.
                return True
            from .provider_checkpoints import (
                ProviderCheckpoint,
                ProviderCheckpointError,
            )

            try:
                has_writes = Journal._provider_has_writes(record.get("inputs"))
                checkpoint = ProviderCheckpoint.from_record(record.get("response"))
                if checkpoint.has_unresolved_effects(has_writes=has_writes):
                    return True
            except (ProviderCheckpointError, TypeError, ValueError, KeyError):
                return True
        return False

    @staticmethod
    def _provider_has_writes(inputs):
        if (
            type(inputs) is not dict
            or inputs.get("$botpipe") != "dict"
            or set(inputs) != {"$botpipe", "value"}
            or type(inputs.get("value")) is not dict
        ):
            raise TypeError("Provider inputs are not an encoded mapping")
        if "writes" not in inputs["value"]:
            raise ValueError("Provider inputs omit their writes declaration")
        writes = inputs["value"]["writes"]
        if type(writes) is not list:
            raise TypeError("Provider writes are not an encoded list")
        return bool(writes)

    @staticmethod
    def _record(row):
        if row is None:
            return None
        result = dict(row)
        for field in ("inputs", "result", "error", "response"):
            if result.get(field) is not None:
                result[field] = json.loads(result[field])
        return result

    def get(self, operation_id):
        with self.lock:
            return self._record(
                self.db.execute(
                    "SELECT * FROM operations WHERE id=?", (operation_id,)
                ).fetchone()
            )

    def operations(self, run_id):
        with self.lock:
            return [
                self._record(row)
                for row in self.db.execute(
                    "SELECT * FROM operations WHERE run_id=? ORDER BY started_at,id",
                    (run_id,),
                )
            ]

    def begin(
        self,
        *,
        operation_id,
        run_id,
        scope,
        ordinal,
        kind,
        name,
        fingerprint,
        inputs,
        limit,
    ):
        with self.transaction() as db:
            count = db.execute(
                "SELECT count(*) FROM operations WHERE run_id=?", (run_id,)
            ).fetchone()[0]
            if count >= limit:
                from .errors import BudgetExceeded

                raise BudgetExceeded(f"Run reached its {limit} operation budget")
            db.execute(
                "INSERT INTO operations(id,run_id,scope,ordinal,kind,name,fingerprint,inputs,status,started_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    operation_id,
                    run_id,
                    scope,
                    ordinal,
                    kind,
                    name,
                    fingerprint,
                    json.dumps(inputs),
                    "started",
                    now(),
                ),
            )
            self._event(
                db,
                run_id,
                operation_id,
                "operation_started",
                {"kind": kind, "name": name},
            )

    def finish(self, operation_id, result):
        self._checkpoint(
            operation_id,
            expected=("started", "response"),
            status="completed",
            result=result,
            error=None,
            event="operation_completed",
            event_data={},
        )

    def fail(self, operation_id, error):
        # A response may be known stopped and still fail its output contract.
        # Waiting and completed records are authoritative checkpoints and must
        # never be replaced by a generic exception handler.
        self._checkpoint(
            operation_id,
            expected=("started", "response"),
            status="failed",
            error=error,
            event="operation_failed",
            event_data=error,
        )

    def response(self, operation_id, response, session_key=None):
        self._checkpoint(
            operation_id,
            expected=("started", "waiting", "response"),
            status="response",
            response=response,
            session_key=session_key,
        )

    def session(self, key):
        with self.lock:
            row = self.db.execute(
                "SELECT value FROM sessions WHERE id=?", (key,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def wait_input(self, operation_id, data):
        self._checkpoint(
            operation_id,
            expected=("started", "waiting"),
            status="waiting",
            response=data,
        )

    _MISSING = object()

    def _checkpoint(
        self,
        operation_id,
        *,
        expected,
        status,
        result=_MISSING,
        error=_MISSING,
        response=_MISSING,
        session_key=None,
        event=None,
        event_data=None,
    ):
        """Commit one operation projection from an explicitly allowed state."""
        with self.transaction() as db:
            row = db.execute(
                "SELECT * FROM operations WHERE id=?", (operation_id,)
            ).fetchone()
            if row is None:
                raise KeyError(operation_id)
            current = self._record(row)
            projection = {"status": status}
            for field, value in (
                ("result", result),
                ("error", error),
                ("response", response),
            ):
                if value is not self._MISSING:
                    projection[field] = value
            if all(current.get(key) == value for key, value in projection.items()):
                return
            if current["status"] not in expected:
                raise RuntimeError(
                    f"Operation {operation_id} changed from expected state "
                    f"{tuple(expected)!r} to {current['status']!r}"
                )
            assignments = ["status=?"]
            values = [status]
            for field, value in (
                ("result", result),
                ("error", error),
                ("response", response),
            ):
                if value is not self._MISSING:
                    assignments.append(f"{field}=?")
                    values.append(json.dumps(value) if value is not None else None)
            if status in {"completed", "failed"}:
                assignments.append("finished_at=?")
                values.append(now())
            placeholders = ",".join("?" for _ in expected)
            cursor = db.execute(
                f"UPDATE operations SET {','.join(assignments)} "
                f"WHERE id=? AND status IN ({placeholders})",
                (*values, operation_id, *expected),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(
                    f"Operation {operation_id} did not match its expected checkpoint"
                )
            if (
                session_key
                and response is not self._MISSING
                and response.get("session_id")
            ):
                db.execute(
                    "INSERT INTO sessions VALUES (?,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value",
                    (session_key, json.dumps({"session_id": response["session_id"]})),
                )
            if event is not None:
                self._event(
                    db,
                    current["run_id"],
                    operation_id,
                    event,
                    event_data or {},
                )

    def event(self, run_id, event, data=None, operation_id=None):
        with self.transaction() as db:
            self._event(db, run_id, operation_id, event, data or {})

    @staticmethod
    def _event(db, run_id, operation_id, event, data):
        db.execute(
            "INSERT INTO events(run_id,operation_id,event,data,at) VALUES (?,?,?,?,?)",
            (run_id, operation_id, event, json.dumps(data), now()),
        )

    def events(self, run_id):
        with self.lock:
            rows = list(
                self.db.execute(
                    "SELECT * FROM events WHERE run_id=? ORDER BY seq", (run_id,)
                )
            )
        return [{**dict(row), "data": json.loads(row["data"])} for row in rows]


@contextmanager
def workspace_lock(path):
    """OS-owned lock; never use an expiring lease to assume a writer stopped."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    handle = os.fdopen(descriptor, "r+b")
    try:
        try:
            if os.name == "nt":
                import msvcrt

                if os.fstat(handle.fileno()).st_size == 0:
                    handle.write(b" ")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            raise RunBusy(f"Another Botpipe run owns {path.parent}") from exc
        yield handle
    finally:
        handle.close()
