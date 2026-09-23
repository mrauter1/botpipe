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


def workspace_fence_path(workspace: str | os.PathLike[str]) -> Path:
    """Return the exact coordination path for one workspace effect fence."""

    identity = _digest(canonical_workspace(workspace))
    return _coordination_root() / "workspaces" / f"{identity}.json"


def _fence_diagnostic(
    workspace: str, path: Path, *, status: str, fence: dict[str, Any] | None = None
) -> dict[str, Any]:
    recorded_workspace = workspace if fence is None else fence.get("workspace")
    fence = fence or {}
    return {
        "status": status,
        "workspace": recorded_workspace,
        "run_id": fence.get("run_id"),
        "operation_id": fence.get("operation_id"),
        "journal": fence.get("journal"),
        "fence_path": str(path),
    }


def inspect_workspace_fence(
    workspace: str | os.PathLike[str],
) -> dict[str, Any]:
    """Describe a workspace fence without creating coordination or journal state."""

    canonical = canonical_workspace(workspace)
    path = workspace_fence_path(canonical)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _fence_diagnostic(canonical, path, status="clear")
    except (OSError, UnicodeError) as exc:
        return {
            **_fence_diagnostic(canonical, path, status="unreadable"),
            "error": str(exc),
        }
    try:
        value = json.loads(raw)
    except ValueError as exc:
        return {
            **_fence_diagnostic(canonical, path, status="unreadable"),
            "error": f"invalid JSON: {exc}",
        }
    if type(value) is not dict:
        return {
            **_fence_diagnostic(canonical, path, status="unreadable"),
            "error": "fence record is not an object",
        }
    return _fence_diagnostic(canonical, path, status="unresolved", fence=value)


def _describe_fence(fence: dict[str, Any], path: Path, workspace: str) -> str:
    return (
        f"workspace={fence.get('workspace', workspace)!r}, "
        f"run_id={fence.get('run_id')!r}, "
        f"operation_id={fence.get('operation_id')!r}, "
        f"journal={fence.get('journal')!r}, fence_path={str(path)!r}"
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
        self._fence_path = workspace_fence_path(self.workspace)
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
                    "Workspace has unresolved effects "
                    f"({_describe_fence(fence, self._fence_path, self.workspace)}); "
                    "resolve the owning run before another writable turn"
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
            value = json.loads(self._fence_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            raise WorkspaceUnresolved(
                "Workspace effect fence is unreadable "
                f"(workspace={self.workspace!r}, "
                f"fence_path={str(self._fence_path)!r})"
            ) from exc
        if type(value) is not dict:
            raise WorkspaceUnresolved(
                "Workspace effect fence is invalid "
                f"(workspace={self.workspace!r}, "
                f"fence_path={str(self._fence_path)!r})"
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


def clear_abandoned_workspace_fence(
    workspace: str | os.PathLike[str],
    run_id: str,
    operation_id: str,
) -> dict[str, Any]:
    """Archive an exact fence whose owning journal is demonstrably absent.

    Calling this function is an operator assertion that the abandoned writer has
    stopped.  It deliberately does not infer process liveness or search for a
    journal that may have moved.
    """

    canonical = canonical_workspace(workspace)
    path = workspace_fence_path(canonical)
    root = path.parent
    mutex = _FileMutex(
        root / f"{_digest(canonical)}.lock",
        timeout=0,
        error=WorkspaceBusy,
        message=f"Workspace is busy: {canonical}",
    )
    with mutex:
        diagnostic = inspect_workspace_fence(canonical)
        if diagnostic["status"] == "clear":
            raise WorkspaceUnresolved(
                "Workspace has no effect fence "
                f"(workspace={canonical!r}, fence_path={str(path)!r})"
            )
        if diagnostic["status"] != "unresolved":
            detail = diagnostic.get("error", "unknown read error")
            raise WorkspaceUnresolved(
                "Workspace effect fence cannot be safely cleared "
                f"(workspace={canonical!r}, fence_path={str(path)!r}): {detail}"
            )
        fence = {
            key: diagnostic.get(key)
            for key in ("workspace", "run_id", "operation_id", "journal")
        }
        if (
            fence["workspace"] != canonical
            or fence["run_id"] != run_id
            or fence["operation_id"] != operation_id
        ):
            raise WorkspaceUnresolved(
                "Workspace effect fence does not match the requested owner "
                f"({_describe_fence(fence, path, canonical)})"
            )
        journal = fence["journal"]
        if (
            not isinstance(journal, str)
            or not journal
            or not Path(journal).is_absolute()
        ):
            raise WorkspaceUnresolved(
                "Workspace effect fence has no valid absolute owning journal identity "
                f"({_describe_fence(fence, path, canonical)})"
            )
        try:
            os.stat(journal)
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as exc:
            raise WorkspaceUnresolved(
                "Cannot verify that the owning journal is absent; use normal "
                f"run resolution ({_describe_fence(fence, path, canonical)}): {exc}"
            ) from exc
        else:
            raise WorkspaceUnresolved(
                "The owning journal still exists; use normal run resolution "
                f"({_describe_fence(fence, path, canonical)})"
            )

        # Re-read while holding the workspace mutex so a changed record is never
        # archived under ownership facts checked from an earlier read.
        current = inspect_workspace_fence(canonical)
        current_fence = {
            key: current.get(key)
            for key in ("workspace", "run_id", "operation_id", "journal")
        }
        if current["status"] != "unresolved" or current_fence != fence:
            raise WorkspaceUnresolved(
                "Workspace effect fence changed while it was being cleared "
                f"(workspace={canonical!r}, fence_path={str(path)!r})"
            )
        receipt = root / (
            f"{_digest(canonical)}.cleared.{time.time_ns()}."
            f"{os.getpid()}.{threading.get_ident()}.json"
        )
        os.replace(path, receipt)
        _sync_directory(root)
        return {
            **fence,
            "fence_path": str(path),
            "receipt_path": str(receipt),
            "cleared": True,
            "operator_assertion": "abandoned work has stopped",
        }


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
    "clear_abandoned_workspace_fence",
    "default_state_dir",
    "inspect_workspace_fence",
    "run_lock",
    "session_lock",
    "workspace_fence_path",
    "workspace_turn",
]
