"""Host-local, durable ownership for overlapping workspace trees.

The registry deliberately lives outside every workspace and Botpipe state
directory.  SQLite makes admission atomic; one OS lock per admitted claim
distinguishes a live holder from a durable claim left by an interrupted run.
"""

from __future__ import annotations

import hashlib
import os
import platform
import sqlite3
import sys
import threading
import uuid
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .errors import RunBusy
from .journal import Journal, workspace_lock


_SCHEMA_VERSION = 2
_APPLICATION_ID = 0x4250574F  # "BPWO"


def user_state_dir() -> Path:
    """Return the host-specific per-user directory for ownership state.

    This small location function is intentionally patchable.  Tests and
    embedders can redirect the coordinator without coupling it to a runtime's
    configurable ``state_dir``.
    """

    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    host = platform.node() or "unknown-host"
    host_id = hashlib.sha256(host.encode("utf-8", "surrogatepass")).hexdigest()[:16]
    return base / "botpipe" / "workspace-ownership" / host_id


def _canonical_directory(path: str | os.PathLike[str]) -> tuple[str, tuple[int, int]]:
    resolved = Path(path).expanduser().resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError(f"Workspace is not a directory: {resolved}")
    stat = resolved.stat()
    return os.path.normcase(str(resolved)), (stat.st_dev, stat.st_ino)


def _canonical_journal(journal: object) -> str:
    path = getattr(journal, "path", journal)
    try:
        return os.path.normcase(str(Path(path).expanduser().resolve(strict=False)))
    except TypeError as exc:
        raise TypeError("journal must be a path or expose a path attribute") from exc


def _overlaps(left: str, right: str) -> bool:
    try:
        common = os.path.commonpath((left, right))
    except ValueError:
        return False
    return common == left or common == right


def _covers(parent: str, child: str) -> bool:
    return _overlaps(parent, child) and os.path.commonpath((parent, child)) == parent


@dataclass(frozen=True)
class Lease:
    """A live claim token that may be delegated to nested operations."""

    token: str
    workspace: Path
    journal: Path
    run_id: str
    operation_id: str | None
    mode: str
    _identity: tuple[int, int] = field(repr=False, compare=False)
    _coordinator: "WorkspaceCoordinator" = field(repr=False, compare=False)

    def validate(self) -> None:
        """Fail if the claimed directory was replaced or the lease ended."""

        self._coordinator._validate_lease(self)


@dataclass
class _HeldClaim:
    lease: Lease
    lock_context: object
    handle: object


class WorkspaceCoordinator:
    """Coordinate component-overlapping workspace readers and writers."""

    def __init__(
        self,
        registry_dir: str | os.PathLike[str] | None = None,
        *,
        busy_timeout: float = 0.5,
    ):
        if busy_timeout < 0:
            raise ValueError("busy_timeout must be non-negative")
        self.registry_dir = (
            Path(registry_dir) if registry_dir is not None else user_state_dir()
        )
        self.registry_dir = self.registry_dir.expanduser().resolve(strict=False)
        self.registry_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock_dir = self.registry_dir / "workspace-ownership-locks"
        self.lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.run_lock_dir = self.registry_dir / "run-locks"
        self.run_lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database = self.registry_dir / "workspace-ownership.sqlite3"
        self.busy_timeout = busy_timeout
        self._live: dict[str, _HeldClaim] = {}
        self._live_lock = threading.RLock()
        self._initialize()

    @contextmanager
    def execution_guard(self, journal: object, run_id: str):
        """Exclude another executor for the same durable run.

        This guard is acquired before workspace claims.  Its identity excludes
        workspace paths deliberately: clients configured with different roots
        must still not recover or execute one journal/run concurrently.
        """

        if type(run_id) is not str or not run_id:
            raise ValueError("run_id must be a non-empty string")
        journal_text = _canonical_journal(journal)
        identity = hashlib.sha256(
            f"{journal_text}\0{run_id}".encode("utf-8", "surrogatepass")
        ).hexdigest()
        with workspace_lock(self.run_lock_dir / f"{identity}.lock"):
            yield

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(
            self.database,
            timeout=self.busy_timeout,
            isolation_level=None,
        )
        db.row_factory = sqlite3.Row
        db.execute(f"PRAGMA busy_timeout={max(0, int(self.busy_timeout * 1000))}")
        return db

    def _initialize(self) -> None:
        try:
            with closing(self._connect()) as db:
                self._begin(db)
                try:
                    application_id = db.execute("PRAGMA application_id").fetchone()[0]
                    version = db.execute("PRAGMA user_version").fetchone()[0]
                    objects = db.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE name NOT LIKE 'sqlite_%'"
                    ).fetchall()
                    fresh = application_id == 0 and version == 0 and not objects
                    if not fresh and (
                        application_id != _APPLICATION_ID
                        or version != _SCHEMA_VERSION
                    ):
                        raise ValueError(
                            "Incompatible workspace ownership registry at "
                            f"{self.database}"
                        )
                    if fresh:
                        db.execute(
                            """CREATE TABLE claims (
                      token TEXT PRIMARY KEY,
                      workspace TEXT NOT NULL,
                      journal TEXT NOT NULL,
                      run_id TEXT NOT NULL,
                      operation_id TEXT,
                      mode TEXT NOT NULL CHECK(mode IN ('read', 'write'))
                    )"""
                        )
                        db.execute(
                            "CREATE INDEX claims_workspace ON claims(workspace)"
                        )
                        db.execute(f"PRAGMA application_id={_APPLICATION_ID}")
                        db.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")
                    else:
                        table = db.execute(
                            "SELECT 1 FROM sqlite_master "
                            "WHERE type='table' AND name='claims'"
                        ).fetchone()
                        if table is None:
                            raise ValueError(
                                "Incompatible workspace ownership registry at "
                                f"{self.database}"
                            )
                    db.execute("COMMIT")
                except BaseException:
                    if db.in_transaction:
                        db.execute("ROLLBACK")
                    raise
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("PRAGMA synchronous=FULL")
            try:
                os.chmod(self.database, 0o600)
            except OSError:
                pass
        except sqlite3.Error as exc:
            raise RunBusy("Workspace ownership registry is busy") from exc

    @contextmanager
    def claim(
        self,
        workspace: str | os.PathLike[str],
        journal: object,
        run_id: str,
        mode: str,
        *,
        parent: Lease | Iterable[Lease] | None = None,
        recovery: bool = False,
        operation_id: str | None = None,
    ):
        """Atomically acquire a read or write claim for ``workspace``.

        Active claims are never inferred dead from process metadata.  A
        recovery claim may replace overlapping, inactive claims only when they
        have the same journal/run identity.  Other inactive claims remain until
        their journal proves that all possible effects are settled.
        """

        if mode not in {"read", "write"}:
            raise ValueError("mode must be 'read' or 'write'")
        if type(run_id) is not str or not run_id:
            raise ValueError("run_id must be a non-empty string")
        if operation_id is not None and (
            type(operation_id) is not str or not operation_id
        ):
            raise ValueError("operation_id must be a non-empty string or None")
        workspace_text, identity = _canonical_directory(workspace)
        journal_text = _canonical_journal(journal)
        parent_tokens = self._parent_tokens(
            parent, workspace_text, journal_text, run_id, operation_id, mode
        )
        held = self._acquire(
            workspace_text,
            identity,
            journal_text,
            run_id,
            operation_id,
            mode,
            parent_tokens,
            recovery,
        )
        try:
            yield held.lease
        finally:
            self._finish(held)

    def _parent_tokens(
        self,
        parent: Lease | Iterable[Lease] | None,
        workspace: str,
        journal: str,
        run_id: str,
        operation_id: str | None,
        mode: str,
    ) -> frozenset[str]:
        if parent is None:
            return frozenset()
        parents = (parent,) if isinstance(parent, Lease) else tuple(parent)
        tokens: set[str] = set()
        with self._live_lock:
            for lease in parents:
                if not isinstance(lease, Lease):
                    raise TypeError("parent must contain Lease objects")
                if not _overlaps(str(lease.workspace), workspace):
                    # Callers may pass all leases in their current context.
                    # Only a lease in the same workspace tree can be delegated.
                    continue
                held = self._live.get(lease.token)
                if held is None or held.lease is not lease:
                    raise RunBusy("Parent workspace lease is no longer active")
                lease.validate()
                if str(lease.journal) != journal or lease.run_id != run_id:
                    raise RunBusy("Parent workspace lease belongs to another run")
                if (
                    lease.operation_id is not None
                    and lease.operation_id != operation_id
                ):
                    raise RunBusy(
                        "Parent workspace lease belongs to another operation"
                    )
                if mode == "write" and lease.mode != "write":
                    raise RunBusy("A read lease cannot delegate a write claim")
                tokens.add(lease.token)
        return frozenset(tokens)

    def _rows(
        self, workspace: str, mode: str, recovery: bool
    ) -> list[sqlite3.Row]:
        with closing(self._connect()) as db:
            rows = db.execute("SELECT * FROM claims").fetchall()
        return [
            row
            for row in rows
            if _overlaps(row["workspace"], workspace)
            and (recovery or mode == "write" or row["mode"] == "write")
        ]

    def _try_existing_lock(self, token: str):
        context = workspace_lock(self.lock_dir / f"{token}.lock")
        try:
            handle = context.__enter__()
        except RunBusy:
            return None
        return context, handle

    def _begin(self, db: sqlite3.Connection) -> None:
        try:
            db.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as exc:
            raise RunBusy("Workspace ownership registry is busy") from exc

    def _acquire(
        self,
        workspace: str,
        identity: tuple[int, int],
        journal: str,
        run_id: str,
        operation_id: str | None,
        mode: str,
        parent_tokens: frozenset[str],
        recovery: bool,
    ) -> _HeldClaim:
        token = uuid.uuid4().hex
        own_context = workspace_lock(self.lock_dir / f"{token}.lock")
        own_handle = own_context.__enter__()
        stale_locks: dict[str, tuple[object, object]] = {}
        removable: set[str] = set()
        retained: set[str] = set()
        deleted: set[str] = set()
        try:
            # Probe outside the write transaction so journal inspection never
            # stretches the registry's global admission lock.
            for row in self._rows(workspace, mode, recovery):
                if row["token"] in parent_tokens:
                    continue
                locked = self._try_existing_lock(row["token"])
                if locked is None:
                    if mode == "read" and row["mode"] == "read":
                        # Live readers remain compatible during recovery too.
                        continue
                    raise RunBusy(
                        f"Workspace overlaps active {row['mode']} claim for "
                        f"{row['workspace']}"
                    )
                stale_locks[row["token"]] = locked
                same_run = row["journal"] == journal and row["run_id"] == run_id
                row_operation_id = row["operation_id"]
                same_operation = row_operation_id == operation_id
                if mode == "read" and row["mode"] == "write":
                    if Journal.foreign_has_unresolved_effects(
                        row["journal"], row["run_id"], row_operation_id
                    ):
                        if recovery and same_run:
                            # A recovered reader must not downgrade or release
                            # an earlier writer fence from its own run.
                            retained.add(row["token"])
                        else:
                            raise RunBusy(
                                f"Run {row['run_id']} has unresolved effects; "
                                "resume or reconcile it first"
                            )
                    else:
                        removable.add(row["token"])
                    continue
                if (
                    mode == "read"
                    and row["mode"] == "read"
                    and (
                        not same_run
                        or (
                            recovery
                            and operation_id is not None
                            and not same_operation
                        )
                    )
                ):
                    # Compatible foreign and sibling/root read fences stay intact.
                    retained.add(row["token"])
                    continue
                if (
                    recovery
                    and same_run
                    and operation_id is None
                    and row_operation_id is not None
                ):
                    if Journal.foreign_has_unresolved_effects(
                        row["journal"], row["run_id"], row_operation_id
                    ):
                        # Root orchestration may enter so replay can recover the
                        # operation, but it must preserve that operation's fence.
                        retained.add(row["token"])
                    else:
                        removable.add(row["token"])
                elif recovery and same_run and same_operation:
                    if _covers(workspace, row["workspace"]):
                        removable.add(row["token"])
                    elif Journal.foreign_has_unresolved_effects(
                        row["journal"], row["run_id"], row_operation_id
                    ):
                        # A matching operation may narrow temporarily only
                        # while its broader durable fence remains in place.
                        retained.add(row["token"])
                    else:
                        removable.add(row["token"])
                elif not Journal.foreign_has_unresolved_effects(
                    row["journal"], row["run_id"], row_operation_id
                ):
                    removable.add(row["token"])
                else:
                    raise RunBusy(
                        f"Run {row['run_id']} has unresolved effects; "
                        "resume or reconcile it first"
                    )

            with closing(self._connect()) as db:
                self._begin(db)
                try:
                    current = db.execute("SELECT * FROM claims").fetchall()
                    for row in current:
                        if not _overlaps(row["workspace"], workspace):
                            continue
                        if (
                            mode == "read"
                            and row["mode"] == "read"
                            and not recovery
                        ):
                            continue
                        if row["token"] in parent_tokens:
                            continue
                        if row["token"] in retained:
                            continue
                        if (
                            mode == "read"
                            and row["mode"] == "read"
                            and row["token"] not in removable
                        ):
                            # A compatible reader may have arrived after the
                            # probe; recovery does not need to inspect it.
                            continue
                        if row["token"] not in removable:
                            raise RunBusy(
                                "Workspace overlaps another claim for "
                                f"{row['workspace']}"
                            )
                        db.execute("DELETE FROM claims WHERE token=?", (row["token"],))
                        deleted.add(row["token"])
                    db.execute(
                        "INSERT INTO claims"
                        "(token,workspace,journal,run_id,operation_id,mode) "
                        "VALUES (?,?,?,?,?,?)",
                        (
                            token,
                            workspace,
                            journal,
                            run_id,
                            operation_id,
                            mode,
                        ),
                    )
                    db.execute("COMMIT")
                except BaseException:
                    if db.in_transaction:
                        db.execute("ROLLBACK")
                    deleted.clear()
                    raise
            lease = Lease(
                token=token,
                workspace=Path(workspace),
                journal=Path(journal),
                run_id=run_id,
                operation_id=operation_id,
                mode=mode,
                _identity=identity,
                _coordinator=self,
            )
            held = _HeldClaim(lease, own_context, own_handle)
            with self._live_lock:
                self._live[token] = held
            try:
                lease.validate()
            except BaseException:
                self._delete_claim(token)
                with self._live_lock:
                    self._live.pop(token, None)
                own_context.__exit__(None, None, None)
                own_context = None
                raise
            return held
        except sqlite3.Error as exc:
            raise RunBusy("Workspace ownership registry is busy") from exc
        finally:
            for stale_token, (context, _handle) in stale_locks.items():
                context.__exit__(None, None, None)
                if stale_token in deleted:
                    try:
                        (self.lock_dir / f"{stale_token}.lock").unlink()
                    except FileNotFoundError:
                        pass
            if own_context is not None and token not in self._live:
                own_context.__exit__(None, None, None)
                try:
                    (self.lock_dir / f"{token}.lock").unlink()
                except FileNotFoundError:
                    pass

    def _delete_claim(self, token: str) -> None:
        with closing(self._connect()) as db:
            self._begin(db)
            try:
                db.execute("DELETE FROM claims WHERE token=?", (token,))
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    def _retire_settled_operation_claims(self, lease: Lease) -> None:
        """Remove inactive sibling claims for one settled operation."""

        if lease.operation_id is None:
            return
        locked: dict[str, tuple[object, object]] = {}
        deleted: set[str] = set()
        try:
            with closing(self._connect()) as db:
                rows = db.execute(
                    "SELECT token FROM claims WHERE journal=? AND run_id=? "
                    "AND operation_id=? AND token<>?",
                    (
                        str(lease.journal),
                        lease.run_id,
                        lease.operation_id,
                        lease.token,
                    ),
                ).fetchall()
            for row in rows:
                acquired = self._try_existing_lock(row["token"])
                if acquired is not None:
                    locked[row["token"]] = acquired
            if not locked:
                return
            with closing(self._connect()) as db:
                self._begin(db)
                try:
                    for token in locked:
                        cursor = db.execute(
                            "DELETE FROM claims WHERE token=? AND journal=? "
                            "AND run_id=? AND operation_id=?",
                            (
                                token,
                                str(lease.journal),
                                lease.run_id,
                                lease.operation_id,
                            ),
                        )
                        if cursor.rowcount:
                            deleted.add(token)
                    db.execute("COMMIT")
                except BaseException:
                    if db.in_transaction:
                        db.execute("ROLLBACK")
                    deleted.clear()
                    raise
        except (sqlite3.Error, RunBusy):
            # A later settled claim or overlapping admission can retry cleanup.
            pass
        finally:
            for token, (context, _handle) in locked.items():
                context.__exit__(None, None, None)
                if token in deleted:
                    try:
                        (self.lock_dir / f"{token}.lock").unlink()
                    except FileNotFoundError:
                        pass

    def _finish(self, held: _HeldClaim) -> None:
        lease = held.lease
        identity_valid = True
        try:
            self._check_identity(lease)
        except RunBusy:
            identity_valid = False
        settled = False
        deleted = False
        if identity_valid:
            settled = not Journal.foreign_has_unresolved_effects(
                lease.journal, lease.run_id, lease.operation_id
            )
            if settled:
                try:
                    self._check_identity(lease)
                except RunBusy:
                    identity_valid = False
                    settled = False
        if settled:
            try:
                self._delete_claim(lease.token)
                deleted = True
            except (sqlite3.Error, RunBusy):
                # Keeping a stale durable row is the conservative outcome.
                pass
            self._retire_settled_operation_claims(lease)
        with self._live_lock:
            self._live.pop(lease.token, None)
        held.lock_context.__exit__(None, None, None)
        if deleted:
            try:
                (self.lock_dir / f"{lease.token}.lock").unlink()
            except FileNotFoundError:
                pass
        if not identity_valid:
            raise RunBusy(
                f"Workspace directory changed while claim {lease.token} was active"
            )

    def _check_identity(self, lease: Lease) -> None:
        try:
            stat = lease.workspace.stat()
        except OSError as exc:
            raise RunBusy(
                f"Claimed workspace is no longer available: {lease.workspace}"
            ) from exc
        if (
            not lease.workspace.is_dir()
            or (stat.st_dev, stat.st_ino) != lease._identity
        ):
            raise RunBusy(f"Claimed workspace was replaced: {lease.workspace}")

    def _validate_lease(self, lease: Lease) -> None:
        with self._live_lock:
            held = self._live.get(lease.token)
            if held is None or held.lease is not lease:
                raise RunBusy("Workspace lease is no longer active")
            self._check_identity(lease)


__all__ = ["Lease", "WorkspaceCoordinator", "user_state_dir"]
