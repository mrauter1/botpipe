"""Cross-process coordination for durable runs and sessions."""

from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path

from .errors import CancellationRequested, RunBusy
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

    return _canonical_path(path)


def _canonical_path(path: str | os.PathLike[str]) -> str:
    value = str(Path(path).resolve())
    if os.name == "nt" or sys.platform == "darwin":
        value = value.casefold()
    return value


def _digest(*parts: str) -> str:
    value = "\0".join(parts).encode("utf-8", "surrogatepass")
    return hashlib.sha256(value).hexdigest()


def default_state_dir(workspace: str | os.PathLike[str]) -> Path:
    """Return the per-user state directory for a canonical workspace."""

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
            "Operation cancelled while waiting for a lock"
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
        # Windows byte-range locks may extend beyond EOF. Initializing a byte
        # before acquiring the lock races with another caller already holding it.
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


__all__ = [
    "canonical_workspace",
    "default_state_dir",
    "run_lock",
    "session_lock",
]
