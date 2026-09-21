"""Synchronous, durable provider boundary for agent CLIs."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import threading
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .policy import NetworkMode, PermissionMode, Policy, SandboxMode
from .processes import ProcessContainment
from .recovery import Completed, RecoveryOutcome, Running, Stopped, Unknown
from .storage import sync_directory


class ProviderError(RuntimeError):
    """A provider request could not be completed."""


class ProviderPolicyError(ProviderError):
    """The selected provider cannot faithfully enforce the policy."""


class ProviderInterruptedError(ProviderError):
    """An attempt may have reached the provider and needs reconciliation."""

    def __init__(
        self,
        message: str,
        *,
        receipt: Path | None = None,
        process_alive: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.receipt = receipt
        self.process_alive = process_alive


class ProviderTimeoutError(ProviderError):
    pass


class _ProviderTimedOut(subprocess.TimeoutExpired):
    """Internal timeout carrying streams already drained by reader threads."""

    drained = True
    stopped = True


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    operation_id: str
    prompt: str
    workspace: Path
    session_id: str | None
    output_schema: dict[str, Any] | None
    policy: Policy
    artifacts: dict[str, Path]
    receipt_dir: Path
    timeout: float
    attempt: int = 1
    reads: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace", Path(self.workspace))
        object.__setattr__(self, "receipt_dir", Path(self.receipt_dir))
        object.__setattr__(
            self, "artifacts", {str(k): Path(v) for k, v in self.artifacts.items()}
        )
        object.__setattr__(self, "reads", tuple(Path(value) for value in self.reads))
        if not self.operation_id:
            raise ValueError("operation_id must be non-empty")
        if (
            isinstance(self.attempt, bool)
            or not isinstance(self.attempt, int)
            or self.attempt < 1
        ):
            raise ValueError("attempt must be at least 1")
        if (
            isinstance(self.timeout, bool)
            or not isinstance(self.timeout, (int, float))
            or self.timeout <= 0
        ):
            raise ValueError("timeout must be greater than zero")


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    text: str
    session_id: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        """Validate the provider protocol without silently coercing durable facts."""
        if type(self.text) is not str:
            raise TypeError("ProviderResponse.text must be a string")
        if self.session_id is not None and type(self.session_id) is not str:
            raise TypeError("ProviderResponse.session_id must be a string or None")

        def plain_json(value):
            if type(value) in (str, int, float, bool, type(None)):
                return True
            if type(value) is list:
                return all(plain_json(item) for item in value)
            if type(value) is dict:
                return all(
                    type(key) is str and plain_json(item) for key, item in value.items()
                )
            return False

        for name, value in (("usage", self.usage), ("metadata", self.metadata)):
            if type(value) is not dict or not plain_json(value):
                raise TypeError(f"ProviderResponse.{name} must be a plain JSON object")
        record = {
            "text": self.text,
            "session_id": self.session_id,
            "usage": self.usage,
            "metadata": self.metadata,
        }
        json.dumps(record, allow_nan=False)
        return record


@runtime_checkable
class Provider(Protocol):
    name: str

    def run(self, request: ProviderRequest) -> ProviderResponse: ...
    # ProviderResponse | None is the supported legacy recovery contract;
    # recover_outcome() translates it conservatively for callers.
    def recover(
        self, request: ProviderRequest
    ) -> RecoveryOutcome | ProviderResponse | None: ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_id(value: str) -> str:
    label = (
        "".join(c if c.isalnum() or c in "._-" else "-" for c in value)[:80].strip(".-")
        or "operation"
    )
    return f"{label}-{hashlib.sha256(value.encode()).hexdigest()[:10]}"


def receipt_path(request: ProviderRequest) -> Path:
    return _receipt_path_for(request, request.attempt)


def _receipt_path_for(request: ProviderRequest, attempt: int) -> Path:
    return (
        request.receipt_dir / f"{_safe_id(request.operation_id)}.attempt-{attempt}.json"
    )


def _atomic_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    _atomic_bytes(
        path,
        (
            json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        ).encode(),
    )


def _read_receipt(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProviderInterruptedError(
            f"provider receipt is unreadable: {path}", receipt=path
        ) from exc
    if not isinstance(value, dict):
        raise ProviderInterruptedError(
            f"provider receipt is malformed: {path}", receipt=path
        )
    return value


def _response_record(response: ProviderResponse) -> dict[str, Any]:
    return response.to_record()


def _record_response(value: Any, path: Path) -> ProviderResponse:
    if not isinstance(value, Mapping) or not isinstance(value.get("text"), str):
        raise ProviderInterruptedError(
            f"completed provider receipt has no valid response: {path}", receipt=path
        )
    response = ProviderResponse(
        text=value["text"],
        session_id=value.get("session_id"),
        usage=value.get("usage", {}),
        metadata=value.get("metadata", {}),
    )
    try:
        response.to_record()
    except (TypeError, ValueError, RecursionError) as exc:
        raise ProviderInterruptedError(
            f"completed provider receipt has an invalid response: {path}: {exc}",
            receipt=path,
        ) from exc
    return response


def _pid_alive(pid: Any) -> bool | None:
    if not isinstance(pid, int) or pid <= 0:
        return None
    if os.name == "nt":
        # os.kill(pid, 0) calls TerminateProcess on Windows; it is not a probe.
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False if ctypes.get_last_error() == 87 else None
        try:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                return None
            return code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return None
    return True


def _process_group_alive(process_group: Any) -> bool | None:
    if os.name == "nt" or not isinstance(process_group, int) or process_group <= 0:
        return None
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return None
    return True


def _receipt_process_alive(receipt: Mapping[str, Any]) -> bool | None:
    if "process_group" in receipt:
        group_alive = _process_group_alive(receipt.get("process_group"))
        if group_alive is not None:
            return group_alive
    return _pid_alive(receipt.get("pid"))


def _receipt_matches(
    value: Mapping[str, Any], request: ProviderRequest, attempt: int
) -> bool:
    return (
        value.get("operation_id") == request.operation_id
        and type(value.get("attempt")) is int
        and value.get("attempt") == attempt
    )


def _existing_response_or_raise(request: ProviderRequest) -> ProviderResponse | None:
    path = receipt_path(request)
    if not path.exists():
        return None
    value = _read_receipt(path)
    if not _receipt_matches(value, request, request.attempt):
        raise ProviderInterruptedError(
            f"provider receipt identity does not match {request.operation_id!r} "
            f"attempt {request.attempt}; refusing to use it",
            receipt=path,
        )
    status = value.get("status")
    if status == "completed":
        return _record_response(value.get("response"), path)
    if status == "failed":
        raise ProviderError(str(value.get("error") or "provider attempt failed"))
    alive = _receipt_process_alive(value)
    state = "still running" if alive else "has no durable result"
    raise ProviderInterruptedError(
        f"provider attempt {request_label(value)} {state}; refusing to resend it",
        receipt=path,
        process_alive=alive,
    )


def request_label(receipt: Mapping[str, Any]) -> str:
    return f"{receipt.get('operation_id', '<unknown>')!r} attempt {receipt.get('attempt', '?')}"


def _usage(payload: Any) -> dict[str, Any]:
    if isinstance(payload, Mapping):
        for key in ("usage", "token_usage", "provider_usage"):
            if isinstance(payload.get(key), Mapping):
                raw = dict(payload[key])
                aliases = {
                    "input_tokens": ("input_tokens", "prompt_tokens"),
                    "output_tokens": ("output_tokens", "completion_tokens"),
                    "total_tokens": ("total_tokens",),
                }
                normalized = dict(raw)
                for target, keys in aliases.items():
                    for source in keys:
                        if isinstance(raw.get(source), int) and not isinstance(
                            raw[source], bool
                        ):
                            normalized[target] = raw[source]
                            break
                return normalized
        for child in payload.values():
            found = _usage(child)
            if found:
                return found
    elif isinstance(payload, list):
        for child in payload:
            found = _usage(child)
            if found:
                return found
    return {}


def _json_literal(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


def _stream_usage(stdout: bytes) -> dict:
    """Retain reported partial usage from failed CLI output without guessing totals."""
    values = {}
    for line in stdout.splitlines():
        try:
            values.update(_usage(json.loads(line)))
        except (ValueError, UnicodeDecodeError):
            pass
    return values


class _CLIProvider:
    name = ""
    supports_safe_read_retry = False
    supports_timeout = True
    _reserves_dispatch = True

    def __init__(
        self, command: str | Iterable[str], *, env: Mapping[str, str] | None = None
    ) -> None:
        self.command = (command,) if isinstance(command, str) else tuple(command)
        if not self.command:
            raise ValueError("provider command cannot be empty")
        self.env = {str(k): str(v) for k, v in (env or {}).items()}

    def recover(self, request: ProviderRequest) -> RecoveryOutcome:
        """Reconcile native receipts, preferring any completed response.

        All receipt identities are verified before their contents are trusted.
        A completed response wins over other attempt states because retry
        authorization must never supersede an already durable result.
        """
        outcomes: list[RecoveryOutcome] = []
        completed: Completed | None = None
        for attempt in range(request.attempt, 0, -1):
            path = _receipt_path_for(request, attempt)
            if not path.exists():
                continue
            try:
                value = _read_receipt(path)
            except ProviderInterruptedError as exc:
                outcomes.append(Unknown(str(exc)))
                continue
            if not _receipt_matches(value, request, attempt):
                outcomes.append(
                    Unknown(
                        f"provider receipt identity does not match "
                        f"{request.operation_id!r} attempt {attempt}"
                    )
                )
                continue
            status = value.get("status")
            if status == "completed":
                try:
                    candidate = Completed(_record_response(value.get("response"), path))
                    if completed is None:
                        completed = candidate
                except ProviderInterruptedError as exc:
                    outcomes.append(Unknown(str(exc)))
                continue
            if status == "failed":
                outcomes.append(Stopped(str(value.get("error") or "attempt failed")))
                continue
            alive = _receipt_process_alive(value)
            if alive is True:
                outcomes.append(
                    Running(f"provider attempt {request_label(value)} is still running")
                )
            elif alive is False:
                outcomes.append(
                    Stopped(f"provider attempt {request_label(value)} has stopped")
                )
            else:
                outcomes.append(
                    Unknown(
                        f"provider attempt {request_label(value)} has no verifiable process id"
                    )
                )

        # A response is authoritative only once every other recorded attempt is
        # also known quiescent. Inconsistent history with a newer/live attempt
        # must not publish or roll back outputs while that attempt can edit.
        for outcome_type in (Running, Unknown):
            for outcome in outcomes:
                if isinstance(outcome, outcome_type):
                    return outcome
        if completed is not None:
            return completed
        for outcome in outcomes:
            if isinstance(outcome, Stopped):
                return outcome
        return Unknown("no matching provider receipt")

    @staticmethod
    def _reconcile_prior_attempts(request: ProviderRequest) -> ProviderResponse | None:
        """Return a prior completed result, or block an unsafe replacement.

        A higher attempt number is explicit retry authorization. It permits a
        retry after a known failed attempt or after an interrupted process is
        provably gone. It never supersedes an already completed response.
        """
        for attempt in range(request.attempt - 1, 0, -1):
            path = _receipt_path_for(request, attempt)
            if not path.exists():
                continue
            value = _read_receipt(path)
            if not _receipt_matches(value, request, attempt):
                raise ProviderInterruptedError(
                    f"prior provider receipt identity does not match "
                    f"{request.operation_id!r} attempt {attempt}; refusing replacement",
                    receipt=path,
                )
            status = value.get("status")
            if status == "completed":
                return _record_response(value.get("response"), path)
            if status == "failed":
                continue
            alive = _receipt_process_alive(value)
            if alive is False:
                # The caller selected a new attempt and the old process is
                # conclusively gone. This is the explicit reconciliation gate.
                continue
            state = "still running" if alive else "has no verifiable process id"
            raise ProviderInterruptedError(
                f"prior provider attempt {request_label(value)} {state}; refusing replacement",
                receipt=path,
                process_alive=alive,
            )
        return None

    def run(self, request: ProviderRequest) -> ProviderResponse:
        path = receipt_path(request)
        existing = _existing_response_or_raise(request)
        if existing is not None:
            return existing
        prior = self._reconcile_prior_attempts(request)
        if prior is not None:
            return prior
        request.receipt_dir.mkdir(parents=True, exist_ok=True)
        effective = request.policy.effective()
        command, env, emission = self._build(request, effective)
        from .dispatches import Dispatch

        dispatch = Dispatch(self, request)
        effective_timeout = dispatch.timeout
        started: dict[str, Any] = {
            "version": 1,
            "provider": self.name,
            "operation_id": request.operation_id,
            "attempt": request.attempt,
            "dispatch_id": dispatch.id,
            "status": "starting",
            "started_at": _now(),
            "command": command,
            "session_id": request.session_id,
            "policy": effective.to_dict(),
            "emission": emission,
        }
        process: subprocess.Popen[bytes] | None = None
        containment = None
        stdout = b""
        stderr = b""
        try:
            _atomic_json(
                path, started
            )  # intent precedes the potentially effectful spawn
            containment = ProcessContainment.create()
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=request.workspace,
                env={**os.environ, **env},
                **containment.creation_kwargs,
            )
            try:
                containment.attach_and_start(process)
            except BaseException:
                # Windows children start suspended; assignment failure must
                # terminate that child before any user code is allowed to run.
                process.kill()
                process.wait()
                raise
            process._botpipe_containment = containment
            dispatch.started()
            started.update(status="running", pid=process.pid, spawned_at=_now())
            if os.name != "nt":
                started["process_group"] = process.pid
            _atomic_json(path, started)
            try:
                stdout, stderr = self._communicate(
                    process,
                    request.prompt.encode(),
                    effective_timeout,
                    receipt=path,
                    started=started,
                )
                containment.ensure_tree_exited(process, grace_seconds=0.1)
                dispatch.stopped()
            except subprocess.TimeoutExpired as exc:
                if not getattr(exc, "stopped", False):
                    self._stop(process)
                if getattr(exc, "drained", False):
                    stdout = exc.output or b""
                    stderr = exc.stderr or b""
                else:
                    stdout, stderr = process.communicate()
                dispatch.stopped()
                raw = self._save_streams(path, stdout, stderr)
                failed = {
                    **started,
                    "status": "failed",
                    "finished_at": _now(),
                    "returncode": process.returncode,
                    "raw": raw,
                    "error": f"provider timed out after {effective_timeout:g} seconds",
                }
                _atomic_json(path, failed)
                raise ProviderTimeoutError(failed["error"])
            except BaseException:
                self._stop(process)
                raise
            raw = self._save_streams(path, stdout, stderr)
            if process.returncode != 0:
                message = (
                    stderr.decode(errors="replace").strip()
                    or stdout.decode(errors="replace").strip()
                )
                failed = {
                    **started,
                    "status": "failed",
                    "finished_at": _now(),
                    "returncode": process.returncode,
                    "raw": raw,
                    "error": f"provider {self.name!r} exited {process.returncode}: {message}",
                }
                _atomic_json(path, failed)
                raise ProviderError(failed["error"])
            try:
                response = self._parse(
                    stdout.decode(errors="replace"), request, emission
                )
            except ProviderError as exc:
                failed = {
                    **started,
                    "status": "failed",
                    "finished_at": _now(),
                    "returncode": process.returncode,
                    "raw": raw,
                    "error": str(exc),
                }
                _atomic_json(path, failed)
                raise
            completed = {
                **started,
                "status": "completed",
                "finished_at": _now(),
                "returncode": process.returncode,
                "raw": raw,
                "response": _response_record(response),
            }
            _atomic_json(path, completed)
            dispatch.finish("completed", usage=response.usage)
            return response
        except ProviderError as exc:
            dispatch.finish(
                "timed_out" if isinstance(exc, ProviderTimeoutError) else "failed",
                usage=_stream_usage(stdout),
                error=exc,
            )
            if path.exists() and process is not None and process.poll() is not None:
                current = _read_receipt(path)
                if current.get("status") not in ("completed", "failed"):
                    current.update(
                        status="failed",
                        finished_at=_now(),
                        returncode=process.returncode,
                        error=str(exc),
                    )
                    _atomic_json(path, current)
            raise
        except (KeyboardInterrupt, SystemExit) as exc:
            if (
                process is not None
                and getattr(process, "_botpipe_containment", None) is not None
            ):
                self._stop(process)
            dispatch.finish("interrupted", usage=_stream_usage(stdout), error=exc)
            raise
        except BaseException as exc:
            if (
                process is not None
                and getattr(process, "_botpipe_containment", None) is not None
            ):
                self._stop(process)
            dispatch.finish("failed", usage=_stream_usage(stdout), error=exc)
            if path.exists():
                current = _read_receipt(path)
                if current.get("status") not in ("completed", "failed"):
                    current.update(
                        status="failed",
                        finished_at=_now(),
                        error=f"adapter failure: {exc}",
                    )
                    _atomic_json(path, current)
            raise ProviderError(
                f"provider {self.name!r} adapter failed: {exc}"
            ) from exc
        finally:
            if containment is not None:
                containment.close()

    def _communicate(
        self,
        process: subprocess.Popen[bytes],
        prompt: bytes,
        timeout: float,
        *,
        receipt: Path,
        started: dict[str, Any],
    ) -> tuple[bytes, bytes]:
        return process.communicate(prompt, timeout=timeout)

    @staticmethod
    def _stop(process: subprocess.Popen[bytes]) -> None:
        containment = getattr(process, "_botpipe_containment", None)
        if containment is None:
            raise RuntimeError("Cannot terminate a process without verified ownership")
        containment.terminate(process, grace_seconds=1.0)

    @staticmethod
    def _save_streams(receipt: Path, stdout: bytes, stderr: bytes) -> dict[str, str]:
        stdout_path, stderr_path = (
            receipt.with_suffix(".stdout"),
            receipt.with_suffix(".stderr"),
        )
        _atomic_bytes(stdout_path, stdout)
        _atomic_bytes(stderr_path, stderr)
        return {
            "stdout": stdout_path.name,
            "stderr": stderr_path.name,
            "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        }

    def _build(
        self, request: ProviderRequest, policy: Policy
    ) -> tuple[list[str], dict[str, str], dict[str, Any]]:
        raise NotImplementedError

    def _parse(
        self, stdout: str, request: ProviderRequest, emission: dict[str, Any]
    ) -> ProviderResponse:
        raise NotImplementedError


def _provider_check(policy: Policy, name: str) -> None:
    if policy.provider is not None and policy.provider.value != name:
        raise ProviderPolicyError(
            f"policy requires provider {policy.provider.value!r}, not {name!r}"
        )
    unsupported = []
    if policy.base_url is not None:
        unsupported.append("base_url")
    if policy.model_overrides:
        unsupported.append("model_overrides")
    if unsupported:
        raise ProviderPolicyError(
            f"{name.title()} CLI cannot enforce: " + ", ".join(unsupported)
        )


def _resolved_paths(request: ProviderRequest, values: Iterable[str]) -> list[str]:
    workspace = request.workspace.resolve()
    result: list[str] = []
    for value in values:
        raw = Path(value)
        resolved = raw.resolve() if raw.is_absolute() else (workspace / raw).resolve()
        if not raw.is_absolute() and not resolved.is_relative_to(workspace):
            raise ProviderPolicyError(
                f"relative policy path escapes workspace: {value!r}"
            )
        result.append(str(resolved))
    return result


def _artifact_write_roots(request: ProviderRequest) -> list[str]:
    roots: list[str] = []
    for destination in request.artifacts.values():
        path = (
            destination
            if destination.is_absolute()
            else request.workspace / destination
        )
        parent = str(path.resolve().parent)
        if parent not in roots:
            roots.append(parent)
    return roots


class CodexProvider(_CLIProvider):
    name = "codex"

    def __init__(
        self,
        command: str | Iterable[str] = ("codex", "exec"),
        *,
        env: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(command, env=env)

    def _communicate(
        self,
        process: subprocess.Popen[bytes],
        prompt: bytes,
        timeout: float,
        *,
        receipt: Path,
        started: dict[str, Any],
    ) -> tuple[bytes, bytes]:
        """Drain JSONL while running so a newly known thread ID is durable."""
        stdout_parts: list[bytes] = []
        stderr_parts: list[bytes] = []
        errors: list[BaseException] = []

        def read_stdout() -> None:
            try:
                assert process.stdout is not None
                for line in iter(process.stdout.readline, b""):
                    stdout_parts.append(line)
                    try:
                        event = json.loads(line)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
                    if (
                        isinstance(event, Mapping)
                        and event.get("type") == "thread.started"
                        and isinstance(event.get("thread_id"), str)
                    ):
                        started["session_id"] = event["thread_id"]
                        started["session_known_at"] = _now()
                        _atomic_json(receipt, started)
            except BaseException as exc:  # surfaced on the caller thread
                errors.append(exc)

        def read_stderr() -> None:
            try:
                assert process.stderr is not None
                stderr_parts.append(process.stderr.read())
            except BaseException as exc:
                errors.append(exc)

        def write_stdin() -> None:
            try:
                assert process.stdin is not None
                process.stdin.write(prompt)
                process.stdin.close()
            except BrokenPipeError:
                pass
            except BaseException as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=target, daemon=True)
            for target in (read_stdout, read_stderr, write_stdin)
        ]
        for thread in threads:
            thread.start()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            self._stop(process)
            for thread in threads:
                thread.join(timeout=1)
            raise _ProviderTimedOut(
                exc.cmd,
                exc.timeout,
                output=b"".join(stdout_parts),
                stderr=b"".join(stderr_parts),
            ) from exc
        except BaseException:
            self._stop(process)
            for thread in threads:
                thread.join(timeout=1)
            raise
        process._botpipe_containment.ensure_tree_exited(process, grace_seconds=0.1)
        for thread in threads:
            thread.join()
        if errors:
            raise errors[0]
        return b"".join(stdout_parts), b"".join(stderr_parts)

    def _build(
        self, request: ProviderRequest, policy: Policy
    ) -> tuple[list[str], dict[str, str], dict[str, Any]]:
        _provider_check(policy, self.name)
        unsupported: list[str] = []
        if policy.allow_read not in (None, (".",)):
            unsupported.append("allow_read")
        policy_write_roots = _resolved_paths(request, policy.allow_write or ())
        workspace = str(request.workspace.resolve())
        if (
            policy.sandbox_mode == SandboxMode.WORKSPACE_WRITE
            and workspace not in policy_write_roots
        ):
            unsupported.append(
                "allow_write (Codex workspace-write cannot narrow its working directory)"
            )
        for name in (
            "deny_read",
            "network_domains",
            "deny_network_domains",
            "allow_permissions",
            "ask_permissions",
            "deny_permissions",
        ):
            if getattr(policy, name):
                unsupported.append(name)
        if policy.deny_write and policy.sandbox_mode != SandboxMode.READ_ONLY:
            unsupported.append("deny_write")
        if policy.network == NetworkMode.LIMITED:
            unsupported.append("network=limited")
        if (
            policy.sandbox_mode == SandboxMode.READ_ONLY
            and policy.network == NetworkMode.FULL
        ):
            unsupported.append("network=full under read_only sandbox")
        if (
            policy.sandbox_mode == SandboxMode.DANGER_FULL_ACCESS
            and policy.network != NetworkMode.FULL
        ):
            unsupported.append(
                f"network={policy.network.value} under danger_full_access"
            )
        if policy.sandbox_mode == SandboxMode.DANGER_FULL_ACCESS and policy.allow_write:
            unsupported.append("allow_write under danger_full_access")
        if policy.sandbox_mode == SandboxMode.READ_ONLY and request.artifacts:
            unsupported.append("declared artifact writes under read_only sandbox")
        if policy.allow_local_binding:
            unsupported.append("allow_local_binding")
        if policy.permission_mode in (
            PermissionMode.AUTO_EDIT,
            PermissionMode.DENY_ALL,
        ):
            unsupported.append(f"permission_mode={policy.permission_mode.value}")
        if policy.verbosity is not None:
            unsupported.append("verbosity")
        if policy.reasoning_summary is not None:
            unsupported.append("reasoning_summary")
        if unsupported:
            raise ProviderPolicyError(
                "Codex CLI cannot enforce: " + ", ".join(unsupported)
            )
        sandbox = {
            SandboxMode.READ_ONLY: "read-only",
            SandboxMode.WORKSPACE_WRITE: "workspace-write",
            SandboxMode.DANGER_FULL_ACCESS: "danger-full-access",
        }[policy.sandbox_mode]
        approval = (
            "never"
            if policy.permission_mode
            in (
                PermissionMode.FULL_AUTO_SANDBOXED,
                PermissionMode.FULL_AUTO_UNSANDBOXED,
            )
            else "on-request"
        )
        if (
            policy.permission_mode == PermissionMode.FULL_AUTO_UNSANDBOXED
            and policy.sandbox_mode != SandboxMode.DANGER_FULL_ACCESS
        ):
            raise ProviderPolicyError(
                "unsandboxed automation requires danger_full_access"
            )
        options = [
            "--json",
            f"--config=sandbox_mode={_json_literal(sandbox)}",
            f"--config=approval_policy={_json_literal(approval)}",
        ]
        if policy.model:
            options += ["--model", policy.model]
        if policy.effort:
            options += [
                f"--config=model_reasoning_effort={_json_literal(policy.effort.value)}"
            ]
        if policy.sandbox_mode == SandboxMode.WORKSPACE_WRITE:
            extra_roots = [
                path
                for path in (*policy_write_roots, *_artifact_write_roots(request))
                if path != workspace
            ]
            extra_roots = list(dict.fromkeys(extra_roots))
            if extra_roots:
                options += [
                    f"--config=sandbox_workspace_write.writable_roots={_json_literal(extra_roots)}"
                ]
            options += [
                f"--config=sandbox_workspace_write.network_access={'true' if policy.network == NetworkMode.FULL else 'false'}"
            ]
        emission: dict[str, Any] = {
            "sandbox": sandbox,
            "approval": approval,
            "structured_output": "none",
        }
        if request.output_schema is not None and request.session_id is None:
            schema = receipt_path(request).with_suffix(".schema.json")
            _atomic_json(schema, request.output_schema)
            options += ["--output-schema", str(schema)]
            emission["structured_output"] = "native"
            emission["schema"] = schema.name
        elif request.output_schema is not None:
            emission["structured_output"] = "prompt_only"
            emission["structured_output_reason"] = (
                "codex resume does not support --output-schema"
            )
        if request.session_id:
            # `codex exec resume` resumes the native thread; the prompt remains stdin.
            command = (
                [*self.command, "resume", *options, request.session_id]
                if self.command[-1] == "exec"
                else [*self.command, *options, request.session_id]
            )
        else:
            command = [*self.command, *options]
        command.append("-")
        return command, dict(self.env), emission

    def _parse(
        self, stdout: str, request: ProviderRequest, emission: dict[str, Any]
    ) -> ProviderResponse:
        messages: list[str] = []
        session_id = request.session_id
        events: list[Any] = []
        malformed = 0
        for line in stdout.splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            events.append(item)
            if (
                isinstance(item, Mapping)
                and item.get("type") == "thread.started"
                and isinstance(item.get("thread_id"), str)
            ):
                session_id = item["thread_id"]
            if isinstance(item, Mapping) and item.get("type") == "item.completed":
                child = item.get("item")
                if (
                    isinstance(child, Mapping)
                    and child.get("type") == "agent_message"
                    and isinstance(child.get("text"), str)
                ):
                    messages.append(child["text"])
        if not events or not messages:
            raise ProviderError("Codex returned no usable assistant message")
        return ProviderResponse(
            messages[-1],
            session_id,
            _usage(events),
            {
                "provider": self.name,
                "event_count": len(events),
                "malformed_lines": malformed,
                **emission,
            },
        )


class ClaudeProvider(_CLIProvider):
    name = "claude"

    def __init__(
        self,
        command: str | Iterable[str] = ("claude",),
        *,
        env: Mapping[str, str] | None = None,
        native_schema: bool = True,
    ) -> None:
        super().__init__(command, env=env)
        self.native_schema = native_schema

    def _build(
        self, request: ProviderRequest, policy: Policy
    ) -> tuple[list[str], dict[str, str], dict[str, Any]]:
        _provider_check(policy, self.name)
        if policy.verbosity is not None or policy.reasoning_summary is not None:
            raise ProviderPolicyError(
                "Claude CLI cannot enforce verbosity or reasoning_summary"
            )
        if policy.effort is not None and policy.effort.value == "minimal":
            raise ProviderPolicyError("Claude CLI does not support effort='minimal'")
        mode_map = {
            PermissionMode.ASK: "default",
            PermissionMode.AUTO_EDIT: "acceptEdits",
            PermissionMode.FULL_AUTO_SANDBOXED: "auto",
            PermissionMode.DENY_ALL: "dontAsk",
        }
        settings: dict[str, Any] = {
            "permissions": {},
            "sandbox": {
                "enabled": policy.sandbox_mode != SandboxMode.DANGER_FULL_ACCESS
            },
        }
        if policy.sandbox_mode == SandboxMode.DANGER_FULL_ACCESS:
            constrained = bool(
                policy.deny_read
                or policy.deny_write
                or policy.allow_write
                or policy.network != NetworkMode.FULL
                or policy.network_domains
                or policy.deny_network_domains
            )
            if constrained:
                raise ProviderPolicyError(
                    "Claude cannot enforce filesystem or network restrictions with danger_full_access"
                )
        if policy.sandbox_mode == SandboxMode.READ_ONLY and request.artifacts:
            raise ProviderPolicyError(
                "Claude cannot create declared artifacts under a read_only sandbox"
            )
        command = [
            *self.command,
            "--print",
            "--output-format",
            "json",
            "--permission-prompts",
            "none",
        ]
        if policy.permission_mode == PermissionMode.FULL_AUTO_UNSANDBOXED:
            if policy.sandbox_mode != SandboxMode.DANGER_FULL_ACCESS:
                raise ProviderPolicyError(
                    "unsandboxed automation requires danger_full_access"
                )
            command.append("--dangerously-skip-permissions")
            settings["sandbox"]["allowUnsandboxedCommands"] = True
        else:
            command += ["--permission-mode", mode_map[policy.permission_mode]]
            settings["sandbox"]["allowUnsandboxedCommands"] = False
            settings["sandbox"]["failIfUnavailable"] = True
            settings["sandbox"]["autoAllowBashIfSandboxed"] = (
                policy.permission_mode == PermissionMode.FULL_AUTO_SANDBOXED
            )
        fs: dict[str, Any] = {}
        resolve = lambda values: _resolved_paths(request, values or ())
        workspace = str(request.workspace.resolve())
        policy_allow_read = resolve(policy.allow_read)
        declared_reads = [
            str((path if path.is_absolute() else request.workspace / path).resolve())
            for path in request.reads
        ]
        allow_read = list(dict.fromkeys([*policy_allow_read, *declared_reads]))
        policy_allow_write = resolve(policy.allow_write)
        artifact_roots = _artifact_write_roots(request)
        allow_write = list(dict.fromkeys([*policy_allow_write, *artifact_roots]))
        explicit_deny_read = resolve(policy.deny_read)
        explicit_deny_write = resolve(policy.deny_write)
        deny_read = list(explicit_deny_read)
        deny_write = list(explicit_deny_write)
        settings["permissions"]["blockReadsOutsideWorkingDirectories"] = True
        if policy_allow_read != [workspace]:
            deny_read.insert(0, workspace)
            fs["allowRead"] = allow_read
        elif declared_reads:
            fs["allowRead"] = declared_reads
        if policy.sandbox_mode == SandboxMode.READ_ONLY:
            deny_write.insert(0, workspace)
        elif policy_allow_write != [workspace]:
            deny_write.insert(0, workspace)
            fs["allowWrite"] = allow_write
        elif artifact_roots:
            fs["allowWrite"] = artifact_roots
        if deny_write:
            fs["denyWrite"] = list(dict.fromkeys(deny_write))
        if deny_read:
            fs["denyRead"] = list(dict.fromkeys(deny_read))
        if fs:
            settings["sandbox"]["filesystem"] = fs
        allow = list(policy.allow_permissions or ())
        deny = list(policy.deny_permissions or ())
        ask = list(policy.ask_permissions or ())
        rule_path = lambda path: (
            f"//{path.lstrip('/')}" if Path(path).is_absolute() else path
        )
        allow += [f"Read({rule_path(p)})" for p in allow_read]
        if policy.sandbox_mode != SandboxMode.READ_ONLY:
            allow += [f"Edit({rule_path(p)})" for p in allow_write]
        deny += [f"Read({rule_path(p)})" for p in explicit_deny_read]
        deny += [f"Edit({rule_path(p)})" for p in explicit_deny_write]
        if policy.sandbox_mode == SandboxMode.READ_ONLY:
            deny.append("Edit")
        if policy.permission_mode == PermissionMode.DENY_ALL:
            deny.append("*")
        if allow:
            settings["permissions"]["allow"] = list(dict.fromkeys(allow))
        if deny:
            settings["permissions"]["deny"] = list(dict.fromkeys(deny))
        if ask:
            settings["permissions"]["ask"] = list(dict.fromkeys(ask))
        network: dict[str, Any] = {
            "allowLocalBinding": bool(policy.allow_local_binding)
        }
        if policy.network == NetworkMode.NONE:
            network.update(allowedDomains=[], strictAllowlist=True)
            deny += ["WebFetch", "WebSearch"]
        elif policy.network == NetworkMode.LIMITED:
            network.update(
                allowedDomains=list(policy.network_domains or ()), strictAllowlist=True
            )
            allow += [
                f"WebFetch(domain:{domain})" for domain in policy.network_domains or ()
            ]
            deny.append("WebSearch")
        if policy.deny_network_domains:
            network["deniedDomains"] = list(policy.deny_network_domains)
        deny += [
            f"WebFetch(domain:{domain})" for domain in policy.deny_network_domains or ()
        ]
        if allow:
            settings["permissions"]["allow"] = list(dict.fromkeys(allow))
        if deny:
            settings["permissions"]["deny"] = list(dict.fromkeys(deny))
        settings["sandbox"]["network"] = network
        settings_path = receipt_path(request).with_suffix(".settings.json")
        _atomic_json(settings_path, settings)
        command += [
            "--settings",
            str(settings_path),
            "--add-dir",
            str(request.workspace.resolve()),
        ]
        if policy.model:
            command += ["--model", policy.model]
        if policy.effort:
            command += ["--effort", policy.effort.value]
        if request.session_id:
            command += ["--resume", request.session_id]
        emission: dict[str, Any] = {
            "settings": settings_path.name,
            "structured_output": "none",
        }
        if request.output_schema is not None:
            if self.native_schema:
                command += [
                    "--json-schema",
                    json.dumps(request.output_schema, separators=(",", ":")),
                ]
                emission["structured_output"] = "native"
            else:
                emission.update(
                    structured_output="prompt_only",
                    structured_output_reason="native schema disabled or unavailable",
                )
        return command, dict(self.env), emission

    def _parse(
        self, stdout: str, request: ProviderRequest, emission: dict[str, Any]
    ) -> ProviderResponse:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ProviderError("Claude returned malformed JSON") from exc
        if not isinstance(payload, Mapping):
            raise ProviderError("Claude response must be a JSON object")
        if payload.get("is_error") is True:
            raise ProviderError(
                f"Claude reported an error: {payload.get('result') or 'unknown error'}"
            )
        structured = (
            payload.get("structured_output")
            if request.output_schema is not None
            else None
        )
        if structured is not None:
            result = json.dumps(structured, ensure_ascii=False)
        else:
            result = payload.get("result")
            if not isinstance(result, str):
                raise ProviderError("Claude returned no result")
        session = (
            payload.get("session_id")
            if isinstance(payload.get("session_id"), str)
            else request.session_id
        )
        return ProviderResponse(
            result, session, _usage(payload), {"provider": self.name, **emission}
        )


class FakeProvider:
    name = "fake"
    supports_safe_read_retry = True

    def __init__(self, responses: Iterable[Any]) -> None:
        self._responses = iter(responses)
        self.calls: list[ProviderRequest] = []
        self._recovery: dict[tuple[str, int], RecoveryOutcome] = {}

    def run(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        key = (request.operation_id, request.attempt)
        callback_started = False
        try:
            item = next(self._responses)
            if callable(item):
                callback_started = True
                item = item(request)
            if isinstance(item, BaseException):
                raise item
            if isinstance(item, ProviderResponse):
                response = item
            elif isinstance(item, str):
                response = ProviderResponse(item, request.session_id)
            elif isinstance(item, Mapping):
                response = ProviderResponse(
                    json.dumps(item, ensure_ascii=False), request.session_id
                )
            else:
                raise TypeError(f"unsupported fake response: {type(item).__name__}")
        except StopIteration as exc:
            self._recovery[key] = Stopped("fake call ended without a response")
            raise ProviderError("FakeProvider has no response left") from exc
        except (KeyboardInterrupt, SystemExit):
            # A control interruption does not prove where execution stopped or
            # whether an external effect started by the callback is still live.
            self._recovery[key] = Unknown("fake call was interrupted")
            raise
        except BaseException as exc:
            if callback_started:
                self._recovery[key] = Unknown(
                    f"fake callback failed without proving its effects stopped: {exc}"
                )
            else:
                self._recovery[key] = Stopped(f"fake call stopped: {exc}")
            raise
        outcome = Completed(response)
        self._recovery[key] = outcome
        return response

    def recover(self, request: ProviderRequest) -> RecoveryOutcome:
        return self._recovery.get(
            (request.operation_id, request.attempt),
            Unknown("fake provider has no record of this attempt"),
        )


def get_provider(name: str, config: Mapping[str, Any] | None = None) -> Provider:
    normalized = name.strip().lower()
    options = dict(config or {})
    if normalized == "codex":
        return CodexProvider(**options)
    if normalized == "claude":
        return ClaudeProvider(**options)
    raise ValueError(f"unknown provider {name!r}; expected 'codex' or 'claude'")


__all__ = [
    "ClaudeProvider",
    "CodexProvider",
    "FakeProvider",
    "Provider",
    "ProviderError",
    "ProviderInterruptedError",
    "ProviderPolicyError",
    "ProviderRequest",
    "ProviderResponse",
    "ProviderTimeoutError",
    "get_provider",
    "receipt_path",
]
