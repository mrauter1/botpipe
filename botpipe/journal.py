"""Transactional operation history for local durable workflows."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def now():
    return datetime.now(UTC).isoformat()


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
        if version not in (0, 2):
            self.db.close()
            if version == 1:
                raise ValueError(
                    "Botpipe 1.x journals are not migrated; use a new state directory "
                    "and leave the existing journal untouched"
                )
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
            thread_id TEXT, turn_id TEXT, preset TEXT, enforcement TEXT,
            probe_hash TEXT,
            started_at TEXT NOT NULL, finished_at TEXT,
            UNIQUE(run_id,scope,ordinal));
          CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS provider_budgets (id TEXT PRIMARY KEY, state TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL, operation_id TEXT, event TEXT NOT NULL, data TEXT NOT NULL, at TEXT NOT NULL);
          PRAGMA user_version=2;
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
            if version != 2:
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

    @staticmethod
    def _record(row):
        if row is None:
            return None
        result = dict(row)
        for field in ("inputs", "result", "error", "response", "enforcement"):
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
        preset = None
        enforcement = None
        if kind == "provider" and type(inputs) is dict:
            values = inputs.get("value")
            if inputs.get("$botpipe") == "dict" and type(values) is dict:
                candidate = values.get("operation")
                if candidate in {"run", "query", "generate"}:
                    preset = candidate
                enforcement = {
                    "status": "requested",
                    "policy": values.get("policy"),
                    "tools": values.get("tools"),
                    "settings": values.get("settings"),
                }
        with self.transaction() as db:
            count = db.execute(
                "SELECT count(*) FROM operations WHERE run_id=?", (run_id,)
            ).fetchone()[0]
            if count >= limit:
                from .errors import BudgetExceeded

                raise BudgetExceeded(f"Run reached its {limit} operation budget")
            db.execute(
                "INSERT INTO operations(id,run_id,scope,ordinal,kind,name,fingerprint,inputs,status,"
                "preset,enforcement,started_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
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
                    preset,
                    json.dumps(enforcement) if enforcement is not None else None,
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

    def provider_metadata(
        self,
        operation_id,
        *,
        thread_id=None,
        turn_id=None,
        preset=None,
        enforcement=None,
        probe_hash=None,
    ):
        """Persist adapter identity/evidence without changing operation state."""

        values = {
            "thread_id": thread_id,
            "turn_id": turn_id,
            "preset": preset,
            "enforcement": enforcement,
            "probe_hash": probe_hash,
        }
        updates = {key: value for key, value in values.items() if value is not None}
        if not updates:
            return
        if any(
            key != "enforcement" and type(value) is not str
            for key, value in updates.items()
        ):
            raise TypeError("Provider metadata identifiers must be strings")
        if preset is not None and preset not in {"run", "query", "generate"}:
            raise ValueError("Provider preset is invalid")
        if enforcement is not None:
            json.dumps(enforcement, allow_nan=False)
        with self.transaction() as db:
            row = db.execute(
                "SELECT kind FROM operations WHERE id=?", (operation_id,)
            ).fetchone()
            if row is None:
                raise KeyError(operation_id)
            if row["kind"] != "provider":
                raise ValueError("Provider metadata belongs only to provider operations")
            assignments = ",".join(f"{field}=?" for field in updates)
            encoded = [
                json.dumps(value) if field == "enforcement" else value
                for field, value in updates.items()
            ]
            db.execute(
                f"UPDATE operations SET {assignments} WHERE id=?",
                (*encoded, operation_id),
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
            if response is not self._MISSING and type(response) is dict:
                metadata = response.get("metadata")
                metadata = metadata if type(metadata) is dict else {}
                provider_fields = {
                    "thread_id": response.get("session_id"),
                    "turn_id": metadata.get("turn_id"),
                    "probe_hash": metadata.get("probe_hash"),
                    "enforcement": metadata.get("enforcement"),
                }
                for field, value in provider_fields.items():
                    if value is None:
                        continue
                    assignments.append(f"{field}=?")
                    values.append(
                        json.dumps(value) if field == "enforcement" else value
                    )
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
