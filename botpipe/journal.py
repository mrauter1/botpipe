"""Transactional operation history for local durable workflows."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .errors import RunBusy


def now():
    return datetime.now(timezone.utc).isoformat()


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
                self.db.execute("COMMIT")

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
        with self.transaction() as db:
            row = db.execute(
                "SELECT run_id FROM operations WHERE id=?", (operation_id,)
            ).fetchone()
            db.execute(
                "UPDATE operations SET status='completed',result=?,error=NULL,finished_at=? WHERE id=?",
                (json.dumps(result), now(), operation_id),
            )
            self._event(db, row[0], operation_id, "operation_completed", {})

    def fail(self, operation_id, error):
        with self.transaction() as db:
            row = db.execute(
                "SELECT run_id FROM operations WHERE id=?", (operation_id,)
            ).fetchone()
            db.execute(
                "UPDATE operations SET status='failed',error=?,finished_at=? WHERE id=?",
                (json.dumps(error), now(), operation_id),
            )
            self._event(db, row[0], operation_id, "operation_failed", error)

    def response(self, operation_id, response, session_key=None):
        with self.transaction() as db:
            db.execute(
                "UPDATE operations SET status='response',response=? WHERE id=?",
                (json.dumps(response), operation_id),
            )
            if session_key and response.get("session_id"):
                db.execute(
                    "INSERT INTO sessions VALUES (?,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value",
                    (session_key, json.dumps({"session_id": response["session_id"]})),
                )

    def session(self, key):
        with self.lock:
            row = self.db.execute(
                "SELECT value FROM sessions WHERE id=?", (key,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def wait_input(self, operation_id, data):
        with self.transaction() as db:
            db.execute(
                "UPDATE operations SET status='waiting',response=? WHERE id=?",
                (json.dumps(data), operation_id),
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
