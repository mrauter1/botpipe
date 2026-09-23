"""Small durable provider boundary backed by Codex app-server."""

from __future__ import annotations

import json
import math
import os
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .capabilities import CapabilityError, CodexCapabilities
from .errors import SessionError
from .models import StreamEvent
from .policy import Policy
from .recovery import Completed, RecoveryOutcome, Stopped, Unknown
from .storage import sync_directory


class ProviderError(RuntimeError):
    pass


class ProviderPolicyError(CapabilityError, ProviderError):
    pass


class ProviderInterruptedError(ProviderError):
    def __init__(
        self,
        message: str,
        *,
        receipt: Path | None = None,
        process_alive: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.receipt, self.process_alive = receipt, process_alive


class ProviderTimeoutError(ProviderError):
    pass


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
    preset: str = "run"
    tools: tuple[str, ...] | None = None
    instructions: str | None = None
    settings: Mapping[str, Any] = field(default_factory=dict)
    checkpoint: Mapping[str, Any] | None = None
    on_event: Callable[[StreamEvent], None] | None = field(
        default=None, compare=False, repr=False
    )
    on_checkpoint: Callable[[dict[str, Any]], None] | None = field(
        default=None, compare=False, repr=False
    )
    cancel_event: Any | None = field(default=None, compare=False, repr=False)
    deadline: float | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace", Path(self.workspace))
        object.__setattr__(self, "receipt_dir", Path(self.receipt_dir))
        object.__setattr__(
            self, "artifacts", {str(k): Path(v) for k, v in self.artifacts.items()}
        )
        object.__setattr__(self, "reads", tuple(Path(v) for v in self.reads))
        if not self.operation_id:
            raise ValueError("operation_id must be non-empty")
        if not isinstance(self.prompt, str):
            raise TypeError("prompt must be a string")
        if (
            isinstance(self.timeout, bool)
            or not isinstance(self.timeout, (int, float))
            or self.timeout <= 0
        ):
            raise ValueError("timeout must be greater than zero")
        if self.deadline is not None and (
            isinstance(self.deadline, bool)
            or not isinstance(self.deadline, (int, float))
            or not math.isfinite(self.deadline)
        ):
            raise ValueError("deadline must be finite or None")
        if (
            isinstance(self.attempt, bool)
            or not isinstance(self.attempt, int)
            or self.attempt < 1
        ):
            raise ValueError("attempt must be at least 1")
        if self.preset not in {"run", "query", "generate"}:
            raise ValueError("preset must be 'run', 'query', or 'generate'")
        if self.tools is not None:
            values = tuple(str(value) for value in self.tools)
            if any(not value for value in values):
                raise ValueError("tool names must be non-empty")
            object.__setattr__(self, "tools", values)


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    text: str
    session_id: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        if type(self.text) is not str:
            raise TypeError("ProviderResponse.text must be a string")
        if self.session_id is not None and type(self.session_id) is not str:
            raise TypeError("ProviderResponse.session_id must be a string or None")
        if type(self.usage) is not dict or type(self.metadata) is not dict:
            raise TypeError(
                "ProviderResponse usage and metadata must be plain JSON objects"
            )
        record = {
            "text": self.text,
            "session_id": self.session_id,
            "usage": self.usage,
            "metadata": self.metadata,
        }
        try:
            if json.loads(json.dumps(record, allow_nan=False)) != record:
                raise TypeError
        except (TypeError, ValueError, RecursionError) as exc:
            raise TypeError("ProviderResponse fields must contain plain JSON") from exc
        return record


@runtime_checkable
class ProviderBackend(Protocol):
    name: str

    def run(self, request: ProviderRequest) -> ProviderResponse: ...
    def recover(self, request: ProviderRequest) -> RecoveryOutcome: ...


@runtime_checkable
class Adapter(Protocol):
    name: str

    def probe(self, *, deadline: float | None = None) -> CodexCapabilities: ...
    def start_turn(
        self,
        request: ProviderRequest,
        on_event: Callable[[StreamEvent], None] | None = None,
    ) -> ProviderResponse: ...
    def interrupt(self, thread_id: str, turn_id: str) -> None: ...
    def close(self) -> None: ...


def _safe_id(value: str) -> str:
    import hashlib

    label = "".join(c if c.isalnum() or c in "._-" else "-" for c in value)[:80]
    return f"{label.strip('.-') or 'operation'}-{hashlib.sha256(value.encode()).hexdigest()[:10]}"


def receipt_path(request: ProviderRequest) -> Path:
    return _receipt_path_for(request, request.attempt)


def _receipt_path_for(request: ProviderRequest, attempt: int) -> Path:
    return (
        request.receipt_dir / f"{_safe_id(request.operation_id)}.attempt-{attempt}.json"
    )


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _atomic_bytes(path: Path, value: bytes) -> None:
    """Compatibility helper used by receipt durability tests."""
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


def _response(value: Any, path: Path) -> ProviderResponse:
    if not isinstance(value, Mapping):
        raise ProviderInterruptedError(
            "completed receipt has no response", receipt=path
        )
    text = value.get("text")
    if not isinstance(text, str):
        raise ProviderInterruptedError(
            "completed receipt has invalid response text", receipt=path
        )
    response = ProviderResponse(
        text, value.get("session_id"), value.get("usage", {}), value.get("metadata", {})
    )
    try:
        response.to_record()
    except TypeError as exc:
        raise ProviderInterruptedError(
            f"completed receipt has invalid response: {exc}", receipt=path
        ) from exc
    return response


class CodexProvider:
    """Lazy provider facade around one shared app-server adapter."""

    name = "codex"
    supports_safe_read_retry = True
    supports_timeout = True

    def __init__(
        self,
        command: str | os.PathLike[str] | Sequence[str] = "codex",
        *,
        env: Mapping[str, str] | None = None,
        state_dir: Path | None = None,
        interrupt_grace_seconds: float = 10.0,
        adapter: Any | None = None,
    ) -> None:
        self.command, self.env, self.state_dir = command, dict(env or {}), state_dir
        self.interrupt_grace_seconds, self._adapter = interrupt_grace_seconds, adapter

    @property
    def adapter(self):
        if self._adapter is None:
            from .codex_appserver import CodexAppServerAdapter

            self._adapter = CodexAppServerAdapter(
                self.command,
                env=self.env,
                state_dir=self.state_dir,
                interrupt_grace_seconds=self.interrupt_grace_seconds,
            )
        return self._adapter

    def probe(self):
        return self.adapter.probe()

    def validate_request(self, request: ProviderRequest) -> CodexCapabilities:
        try:
            capabilities = self.adapter.probe(deadline=request.deadline)
        except TimeoutError as exc:
            raise ProviderTimeoutError(
                f"Codex capability probe timed out (dispatch budget: {request.timeout:g} seconds)"
            ) from exc
        return capabilities

    def run(self, request: ProviderRequest) -> ProviderResponse:
        path = receipt_path(request)
        if path.exists():
            existing = _read_receipt(path)
            if (
                existing.get("operation_id") != request.operation_id
                or existing.get("attempt") != request.attempt
            ):
                raise ProviderInterruptedError(
                    "provider receipt identity mismatch", receipt=path
                )
            if existing.get("status") == "completed":
                return _response(existing.get("response"), path)
            raise ProviderInterruptedError(
                "provider attempt has no durable terminal result; refusing to resend",
                receipt=path,
            )
        if request.attempt > 1:
            for attempt in range(request.attempt - 1, 0, -1):
                prior_path = _receipt_path_for(request, attempt)
                if not prior_path.exists():
                    continue
                prior = _read_receipt(prior_path)
                session_id = prior.get("session_id")
                if isinstance(session_id, str):
                    request = replace(request, session_id=session_id)
                    break
        record: dict[str, Any] = {
            "version": 2,
            "provider": "codex",
            "operation_id": request.operation_id,
            "attempt": request.attempt,
            "status": "prepared",
            "session_id": request.session_id,
        }
        _atomic_json(path, record)

        def checkpoint(update: dict[str, Any]) -> None:
            record.update(update)
            _atomic_json(path, record)
            if request.on_checkpoint is not None:
                request.on_checkpoint(dict(record))

        try:
            response = self.adapter.start_turn(
                replace(request, on_checkpoint=checkpoint), request.on_event
            )
            response.to_record()
        except CapabilityError as exc:
            if request.preset in {"query", "generate"}:
                record.update(status="failed", policy_error=True, error=str(exc))
            elif record.get("status") in {"prepared", "thread_bound"}:
                record.update(status="failed", error=str(exc))
            else:
                record.update(error=str(exc))
            _atomic_json(path, record)
            raise ProviderPolicyError(str(exc)) from exc
        except SessionError:
            raise
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"Codex app-server failed: {exc}") from exc
        record.update(status="completed", response=response.to_record())
        _atomic_json(path, record)
        return response

    def recover(self, request: ProviderRequest) -> RecoveryOutcome:
        found = False
        for attempt in range(request.attempt, 0, -1):
            path = _receipt_path_for(request, attempt)
            if not path.exists():
                continue
            found = True
            try:
                value = _read_receipt(path)
            except ProviderInterruptedError as exc:
                return Unknown(str(exc))
            if (
                value.get("operation_id") != request.operation_id
                or value.get("attempt") != attempt
            ):
                return Unknown("provider receipt identity mismatch")
            if value.get("policy_error"):
                raise ProviderPolicyError(
                    str(value.get("error") or "Codex tool policy failed")
                )
            if value.get("status") == "completed":
                try:
                    return Completed(_response(value.get("response"), path))
                except ProviderInterruptedError as exc:
                    return Unknown(str(exc))
            cleanup = value.get("cleanup")
            cleanup_incomplete = (
                isinstance(cleanup, Mapping)
                and cleanup.get("status") == "incomplete"
            )
            if value.get("status") == "failed" and not cleanup_incomplete:
                return Stopped(str(value.get("error") or "provider attempt failed"))
            if value.get("status") in {"prepared", "configured", "thread_bound"}:
                if cleanup_incomplete:
                    return Unknown(
                        str(cleanup.get("error") or "provider cleanup is incomplete")
                    )
                continue
            thread_id, turn_id = value.get("session_id"), value.get("turn_id")
            if not isinstance(thread_id, str) or not isinstance(turn_id, str):
                if cleanup_incomplete:
                    return Unknown(
                        str(cleanup.get("error") or "provider cleanup is incomplete")
                    )
                return Unknown(
                    "turn dispatch was sent before its native turn id was durable"
                )
            def checkpoint(
                update: dict[str, Any], value=value, path=path
            ) -> None:
                value.update(update)
                _atomic_json(path, value)
                if request.on_checkpoint is not None:
                    request.on_checkpoint(dict(value))

            try:
                status, response = self.adapter.recover_turn(
                    replace(
                        request,
                        session_id=thread_id,
                        checkpoint=value,
                        on_checkpoint=checkpoint,
                    ),
                    thread_id=thread_id,
                    turn_id=turn_id,
                )
            except CapabilityError as exc:
                if request.preset in {"query", "generate"}:
                    checkpoint(
                        {"status": "failed", "policy_error": True, "error": str(exc)}
                    )
                    raise ProviderPolicyError(str(exc)) from exc
                return Unknown(f"Codex native recovery failed policy audit: {exc}")
            except Exception as exc:  # noqa: BLE001 - recovery must normalize adapter failures
                return Unknown(f"Codex native recovery failed: {exc}")
            if status == "completed" and isinstance(response, ProviderResponse):
                metadata = {
                    "probe_hash": value.get("probe_hash"),
                    "profile_hash": value.get("profile_hash"),
                    "enforcement": value.get("enforcement", {}),
                    **response.metadata,
                }
                recovered = replace(response, metadata=metadata)
                value.update(status="completed", response=recovered.to_record())
                _atomic_json(path, value)
                return Completed(recovered, "adopted from Codex thread history")
            if cleanup_incomplete:
                return Unknown(
                    str(cleanup.get("error") or "provider cleanup is incomplete")
                )
            if status == "running":
                from .recovery import Running

                return Running("Codex reports the native turn is still running")
            if status == "stopped":
                return Stopped("Codex reports the native turn stopped")
            return Unknown("Codex thread history does not identify the recorded turn")
        return (
            Stopped("provider was not dispatched")
            if found
            else Unknown("no matching provider receipt")
        )

    def close(self) -> None:
        if self._adapter is not None:
            self._adapter.close()


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
        started = False
        try:
            item = next(self._responses)
            if callable(item):
                started = True
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
            response.to_record()
        except StopIteration as exc:
            self._recovery[key] = Stopped("fake call ended without a response")
            raise ProviderError("FakeProvider has no response left") from exc
        except BaseException as exc:
            self._recovery[key] = Unknown(str(exc)) if started else Stopped(str(exc))
            raise
        self._recovery[key] = Completed(response)
        return response

    def recover(self, request: ProviderRequest) -> RecoveryOutcome:
        key = (request.operation_id, request.attempt)
        return self._recovery.get(key, Unknown(f"fake provider has no record of {key}"))


def get_provider(name: str, config: Mapping[str, Any] | None = None) -> ProviderBackend:
    if name.strip().lower() != "codex":
        raise ValueError(f"unknown provider {name!r}; expected 'codex'")
    values = dict(config or {})
    command = values.pop("path", values.pop("command", "codex"))
    allowed = {
        key: values[key]
        for key in ("env", "state_dir", "interrupt_grace_seconds")
        if key in values
    }
    if allowed.get("state_dir") is not None:
        allowed["state_dir"] = Path(allowed["state_dir"])
    return CodexProvider(command, **allowed)


__all__ = [
    "Adapter",
    "CapabilityError",
    "CodexProvider",
    "FakeProvider",
    "ProviderBackend",
    "ProviderError",
    "ProviderInterruptedError",
    "ProviderPolicyError",
    "ProviderRequest",
    "ProviderResponse",
    "ProviderTimeoutError",
    "SessionError",
    "StreamEvent",
    "get_provider",
    "receipt_path",
]
