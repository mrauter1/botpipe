"""Cross-process coordination for runs and writable workspace turns."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Self

from .errors import (
    CancellationRequested,
    RunBusy,
    WorkspaceBusy,
    WorkspaceUnresolved,
)
from .providers import ProviderTimeoutError


def _coordination_root() -> Path:
    override = os.environ.get("BOTPIPE_COORDINATION_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "botpipe" / "coordination"


def canonical_workspace(path: str | os.PathLike[str]) -> str:
    """Return the platform-canonical identity for an existing workspace root."""

    value = str(Path(path).resolve())
    if os.name == "nt" or sys.platform == "darwin":
        value = value.casefold()
    return value


def _canonical_path(path: str | os.PathLike[str]) -> str:
    value = str(Path(path).resolve())
    if os.name == "nt" or sys.platform == "darwin":
        value = value.casefold()
    return value


def _sync_directory(path: Path) -> None:
    if os.name != "posix":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _digest(*parts: str) -> str:
    value = "\0".join(parts).encode("utf-8", "surrogatepass")
    return hashlib.sha256(value).hexdigest()


def default_state_dir(workspace: str | os.PathLike[str]) -> Path:
    """Return the per-user journal directory for a canonical workspace."""

    return _coordination_root().parent / "workspaces" / _digest(
        canonical_workspace(workspace)
    )


class _FileMutex:
    def __init__(
        self,
        path: Path,
        *,
        timeout: float,
        error: type[Exception],
        message: str,
        cancellation=None,
        cancellation_message: str = (
            "Operation cancelled while waiting for the workspace"
        ),
    ):
        if timeout < 0:
            raise ValueError("lock timeout must be nonnegative")
        self.path = path
        self.timeout = timeout
        self.error = error
        self.message = message
        self.cancellation = cancellation
        self.cancellation_message = cancellation_message
        self._handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        self._handle = os.fdopen(descriptor, "r+b", buffering=0)
        if os.name == "nt" and os.fstat(descriptor).st_size == 0:
            self._handle.write(b"\0")
            self._handle.seek(0)
        deadline = time.monotonic() + self.timeout
        while True:
            if self.cancellation is not None and self.cancellation.is_set():
                self._handle.close()
                self._handle = None
                raise CancellationRequested(self.cancellation_message)
            try:
                self._acquire()
                return self
            except (OSError, BlockingIOError) as exc:
                if time.monotonic() >= deadline:
                    self._handle.close()
                    self._handle = None
                    raise self.error(self.message) from exc
                time.sleep(min(0.02, max(0.0, deadline - time.monotonic())))

    def _acquire(self) -> None:
        assert self._handle is not None
        if os.name == "nt":
            import msvcrt

            self._handle.seek(0)
            msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def __exit__(self, *_exc) -> None:
        if self._handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None


def run_lock(journal: str | os.PathLike[str], run_id: str) -> _FileMutex:
    """Return the fail-fast lock for one durable run execution."""

    identity = _digest(_canonical_path(journal), run_id)
    return _FileMutex(
        _coordination_root() / "runs" / f"{identity}.lock",
        timeout=0,
        error=RunBusy,
        message=f"Run {run_id} is already executing",
    )


def session_lock(
    journal: str | os.PathLike[str],
    session_key: str,
    *,
    timeout: float,
    cancellation=None,
) -> _FileMutex:
    """Serialize turns for one durable session in one journal."""

    identity = _digest(_canonical_path(journal), session_key)
    return _FileMutex(
        _coordination_root() / "sessions" / f"{identity}.lock",
        timeout=timeout,
        error=ProviderTimeoutError,
        message="Timed out waiting for the session",
        cancellation=cancellation,
        cancellation_message="Cancelled while waiting for the session",
    )


class WorkspaceTurn:
    """A held writer lock with access to its durable unresolved-effect fence."""

    def __init__(
        self,
        workspace: str | os.PathLike[str],
        *,
        journal: str | os.PathLike[str],
        run_id: str,
        operation_id: str | None,
        timeout: float,
        cancellation=None,
    ) -> None:
        self.workspace = canonical_workspace(workspace)
        identity = _digest(self.workspace)
        root = _coordination_root() / "workspaces"
        self._fence_path = root / f"{identity}.json"
        self._mutex = _FileMutex(
            root / f"{identity}.lock",
            timeout=timeout,
            error=WorkspaceBusy,
            message=f"Workspace is busy: {self.workspace}",
            cancellation=cancellation,
        )
        self.owner = {
            "journal": _canonical_path(journal),
            "run_id": run_id,
            "workspace": self.workspace,
        }
        self.operation_id = operation_id

    def __enter__(self) -> Self:
        self._mutex.__enter__()
        try:
            fence = self.fence()
            matching_operation = (
                self.operation_id is not None
                and fence is not None
                and fence.get("operation_id") == self.operation_id
            )
            if fence is not None and (not self.owns(fence) or not matching_operation):
                raise WorkspaceUnresolved(
                    f"Run {fence.get('run_id', '<unknown>')} has unresolved effects "
                    f"in {self.workspace}; resolve it before another writable turn"
                )
            return self
        except BaseException:
            self._mutex.__exit__(None, None, None)
            raise

    def __exit__(self, *exc) -> None:
        self._mutex.__exit__(*exc)

    def owns(self, fence: dict[str, Any]) -> bool:
        return all(fence.get(key) == value for key, value in self.owner.items())

    def fence(self) -> dict[str, Any] | None:
        try:
            raw = self._fence_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            raise WorkspaceUnresolved(
                f"Workspace effect fence is unreadable: {self.workspace}"
            ) from exc
        if type(value) is not dict:
            raise WorkspaceUnresolved(
                f"Workspace effect fence is invalid: {self.workspace}"
            )
        return value

    def mark_unresolved(self, operation_id: str) -> None:
        record = {**self.owner, "operation_id": operation_id}
        self._fence_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._fence_path.with_suffix(
            f".{os.getpid()}.{threading.get_ident()}.tmp"
        )
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(record, handle, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self._fence_path)
        _sync_directory(self._fence_path.parent)

    def clear(self, operation_id: str | None = None) -> bool:
        fence = self.fence()
        if fence is None:
            return False
        if not self.owns(fence) or (
            operation_id is not None and fence.get("operation_id") != operation_id
        ):
            return False
        self._fence_path.unlink(missing_ok=True)
        _sync_directory(self._fence_path.parent)
        return True


@contextmanager
def workspace_turn(
    workspace: str | os.PathLike[str],
    *,
    journal: str | os.PathLike[str],
    run_id: str,
    operation_id: str | None = None,
    timeout: float,
    writable: bool = True,
    cancellation=None,
) -> Iterator[WorkspaceTurn | None]:
    """Serialize a writable provider turn; readers deliberately take no lock."""

    if not writable:
        yield None
        return
    turn = WorkspaceTurn(
        workspace,
        journal=journal,
        run_id=run_id,
        operation_id=operation_id,
        timeout=timeout,
        cancellation=cancellation,
    )
    with turn:
        yield turn


__all__ = [
    "WorkspaceTurn",
    "canonical_workspace",
    "default_state_dir",
    "run_lock",
    "session_lock",
    "workspace_turn",
]
