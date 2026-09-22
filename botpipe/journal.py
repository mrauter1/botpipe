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


JOURNAL_VERSION = 3
JOURNAL_APPLICATION_ID = 0x42505432  # "BPT2"


def _reject_incompatible_store(path):
    """Identify the rewrite journal before opening it in write mode."""

    if not path.exists():
        return
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(
            f"Incompatible Botpipe state store at {path}; use a fresh state directory"
        )
    try:
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            application_id = connection.execute("PRAGMA application_id").fetchone()[0]
            version = connection.execute("PRAGMA user_version").fetchone()[0]
        finally:
            connection.close()
    except (OSError, sqlite3.Error) as exc:
        raise ValueError(
            f"Incompatible Botpipe state store at {path}; use a fresh state directory"
        ) from exc
    if application_id != JOURNAL_APPLICATION_ID or version != JOURNAL_VERSION:
        raise ValueError(
            f"Incompatible Botpipe state store at {path}; use a fresh state directory"
        )


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
        _reject_incompatible_store(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(
            self.path, timeout=30, isolation_level=None, check_same_thread=False
        )
        self.db.row_factory = sqlite3.Row
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
            session_id TEXT, session_revision INTEGER,
            started_at TEXT NOT NULL, finished_at TEXT,
            UNIQUE(run_id,scope,ordinal));
          CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY, scope TEXT NOT NULL, affinity TEXT NOT NULL,
            continuation TEXT, revision INTEGER NOT NULL,
            owner_run_id TEXT, owner_operation_id TEXT,
            CHECK(revision >= 0),
            CHECK((owner_run_id IS NULL) = (owner_operation_id IS NULL)));
          CREATE TABLE IF NOT EXISTS provider_budgets (id TEXT PRIMARY KEY, state TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL, operation_id TEXT, event TEXT NOT NULL, data TEXT NOT NULL, at TEXT NOT NULL);
          PRAGMA application_id=1112560690;
          PRAGMA user_version=3;
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

    def discard_created_run(self, run_id):
        """Remove an admission placeholder only if execution never began."""
        with self.transaction() as db:
            row = db.execute(
                "SELECT metadata FROM runs WHERE id=?", (run_id,)
            ).fetchone()
            if row is None or json.loads(row[0]).get("status") != "created":
                return
            if db.execute(
                "SELECT 1 FROM operations WHERE run_id=? LIMIT 1", (run_id,)
            ).fetchone() or db.execute(
                "SELECT 1 FROM events WHERE run_id=? LIMIT 1", (run_id,)
            ).fetchone():
                return
            db.execute("DELETE FROM runs WHERE id=?", (run_id,))

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
            application_id = connection.execute("PRAGMA application_id").fetchone()[0]
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if (
                application_id != JOURNAL_APPLICATION_ID
                or version != JOURNAL_VERSION
            ):
                raise ValueError(
                    "Incompatible Botpipe state store; use a fresh state directory"
                )
            return cls._snapshot(connection, run_id)
        finally:
            connection.close()

    @classmethod
    def read_only_history(
        cls,
        path,
        *,
        max_runs,
        max_operations_per_run,
        max_events_per_run,
    ):
        """Return bounded current-format history without creating state."""

        limits = (max_runs, max_operations_per_run, max_events_per_run)
        if any(type(value) is not int or value <= 0 for value in limits):
            raise ValueError("Journal history limits must be positive integers")
        path = Path(path)
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA query_only=ON")
            application_id = connection.execute("PRAGMA application_id").fetchone()[0]
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if (
                application_id != JOURNAL_APPLICATION_ID
                or version != JOURNAL_VERSION
            ):
                raise ValueError(
                    "Incompatible Botpipe state store; use a fresh state directory"
                )
            connection.execute("BEGIN")
            run_rows = list(
                connection.execute(
                    "SELECT id,metadata FROM runs ORDER BY rowid DESC LIMIT ?",
                    (max_runs,),
                )
            )
            snapshots = []
            for run_row in run_rows:
                run = json.loads(run_row["metadata"])
                run_id = run.get("run_id") if type(run) is dict else None
                if type(run_id) is not str or run_id != run_row["id"]:
                    raise ValueError("Run metadata does not match its journal identity")
                operation_rows = list(
                    connection.execute(
                        "SELECT * FROM operations WHERE run_id=? "
                        "ORDER BY started_at,id LIMIT ?",
                        (run_id, max_operations_per_run),
                    )
                )
                event_rows = list(
                    connection.execute(
                        "SELECT * FROM events WHERE run_id=? ORDER BY seq LIMIT ?",
                        (run_id, max_events_per_run),
                    )
                )
                snapshots.append(
                    JournalSnapshot(
                        run=run,
                        operations=tuple(
                            cls._record(row) for row in operation_rows
                        ),
                        events=tuple(
                            {
                                **dict(row),
                                "data": json.loads(row["data"]),
                            }
                            for row in event_rows
                        ),
                    )
                )
            connection.execute("COMMIT")
            return tuple(snapshots)
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
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
    def foreign_has_unresolved_effects(cls, path, run_id, operation_id=None):
        """Conservatively decide whether a foreign claim may still own effects."""

        try:
            snapshot = cls.read_only_snapshot(path, run_id)
            operations = snapshot.operations
            if operation_id is not None:
                operations = tuple(
                    record
                    for record in operations
                    if record.get("id") == operation_id
                )
                if len(operations) != 1:
                    return True
            return cls._has_unresolved_effects(operations)
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

    def response(
        self,
        operation_id,
        response,
        *,
        session_update=None,
    ):
        self._checkpoint(
            operation_id,
            expected=("started", "waiting", "response"),
            status="response",
            response=response,
            session_update=session_update,
        )

    @staticmethod
    def _session_record(row):
        if row is None:
            return None
        result = dict(row)
        result["scope"] = json.loads(result["scope"])
        result["affinity"] = json.loads(result["affinity"])
        continuation = result.get("continuation")
        if continuation is not None:
            from .providers import ProviderContinuation
            result["continuation"] = ProviderContinuation.from_record(
                json.loads(continuation)
            )
        return result

    def session(self, key):
        with self.lock:
            row = self.db.execute(
                "SELECT * FROM sessions WHERE id=?", (key,)
            ).fetchone()
        return self._session_record(row)

    def bind_session(
        self, session_id, *, scope, affinity, require_existing=False
    ):
        encoded_scope = json.dumps(scope, sort_keys=True, allow_nan=False)
        encoded_affinity = json.dumps(affinity, sort_keys=True, allow_nan=False)
        with self.transaction() as db:
            row = db.execute(
                "SELECT * FROM sessions WHERE id=?", (session_id,)
            ).fetchone()
            if row is None:
                if require_existing:
                    raise KeyError(f"Unknown session {session_id}")
                db.execute(
                    "INSERT INTO sessions(id,scope,affinity,revision) VALUES (?,?,?,0)",
                    (session_id, encoded_scope, encoded_affinity),
                )
                row = db.execute(
                    "SELECT * FROM sessions WHERE id=?", (session_id,)
                ).fetchone()
            result = self._session_record(row)
            if result["affinity"] != affinity:
                from .sessions import SessionAffinityError

                raise SessionAffinityError(
                    "Session backend, account, model, or workspace affinity changed"
                )
            if scope.get("scope") != "loaded" and result["scope"] != scope:
                from .sessions import SessionAffinityError

                raise SessionAffinityError(
                    "Session scope does not match its canonical durable identity"
                )
            return result

    def claim_session(
        self,
        session_id,
        *,
        run_id,
        operation_id,
        expected_revision,
        affinity,
    ):
        with self.transaction() as db:
            row = db.execute(
                "SELECT * FROM sessions WHERE id=?", (session_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown session {session_id}")
            record = self._session_record(row)
            from .sessions import (
                SessionAffinityError,
                SessionBusy,
                SessionHistoryConflict,
            )

            if record["affinity"] != affinity:
                raise SessionAffinityError(
                    "Session backend, account, model, or workspace affinity changed"
                )
            owner = (record["owner_run_id"], record["owner_operation_id"])
            requested_owner = (run_id, operation_id)
            if owner != (None, None) and owner != requested_owner:
                raise SessionBusy(
                    f"Session {session_id} is fenced by unresolved operation "
                    f"{record['owner_operation_id']}"
                )
            if record["revision"] != expected_revision:
                raise SessionHistoryConflict(
                    f"Session {session_id} is at revision {record['revision']}; "
                    f"this invocation expected {expected_revision}"
                )
            if owner == (None, None):
                cursor = db.execute(
                    "UPDATE sessions SET owner_run_id=?,owner_operation_id=? "
                    "WHERE id=? AND revision=? AND owner_run_id IS NULL",
                    (run_id, operation_id, session_id, expected_revision),
                )
                if cursor.rowcount != 1:
                    raise SessionBusy(f"Session {session_id} could not be acquired")
            return record

    def release_session(self, session_id, *, run_id, operation_id):
        with self.transaction() as db:
            row = db.execute(
                "SELECT owner_run_id,owner_operation_id FROM sessions WHERE id=?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown session {session_id}")
            if (row[0], row[1]) != (run_id, operation_id):
                from .sessions import SessionBusy

                raise SessionBusy(
                    f"Session {session_id} is not owned by operation {operation_id}"
                )
            db.execute(
                "UPDATE sessions SET owner_run_id=NULL,owner_operation_id=NULL "
                "WHERE id=? AND owner_run_id=? AND owner_operation_id=?",
                (session_id, run_id, operation_id),
            )

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
        session_update=None,
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
            if session_update is not None:
                self._advance_session(db, current, session_update)
            if event is not None:
                self._event(
                    db,
                    current["run_id"],
                    operation_id,
                    event,
                    event_data or {},
                )

    @staticmethod
    def _advance_session(db, operation, update):
        if type(update) is not dict or type(update.get("session_id")) is not str:
            raise TypeError("Malformed session advancement")
        row = db.execute(
            "SELECT * FROM sessions WHERE id=?", (update["session_id"],)
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown session {update['session_id']}")
        record = Journal._session_record(row)
        owner = (record["owner_run_id"], record["owner_operation_id"])
        expected_owner = (operation["run_id"], operation["id"])
        expected_revision = update.get("expected_revision")
        continuation = update.get("continuation")
        if type(expected_revision) is not int or expected_revision < 0:
            raise TypeError("Malformed expected session revision")
        if continuation is not None:
            from .providers import ProviderContinuation
            if not isinstance(continuation, ProviderContinuation):
                raise TypeError("Malformed provider continuation")
            encoded_continuation = json.dumps(
                continuation.to_record(), sort_keys=True, allow_nan=False
            )
        else:
            encoded_continuation = None
        from .sessions import SessionBusy, SessionHistoryConflict

        if owner != expected_owner:
            raise SessionBusy(
                f"Session {update['session_id']} is not owned by "
                f"operation {operation['id']}"
            )
        if record["revision"] != expected_revision:
            raise SessionHistoryConflict(
                f"Session {update['session_id']} changed before response commit"
            )
        cursor = db.execute(
            "UPDATE sessions SET continuation=COALESCE(?,continuation),"
            "revision=revision+1,owner_run_id=NULL,owner_operation_id=NULL "
            "WHERE id=? AND revision=? AND owner_run_id=? AND owner_operation_id=?",
            (
                encoded_continuation,
                update["session_id"],
                expected_revision,
                operation["run_id"],
                operation["id"],
            ),
        )
        if cursor.rowcount != 1:
            raise SessionHistoryConflict(
                f"Session {update['session_id']} could not be advanced atomically"
            )
        db.execute(
            "UPDATE operations SET session_id=?,session_revision=? WHERE id=?",
            (update["session_id"], expected_revision + 1, operation["id"]),
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
