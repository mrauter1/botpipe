"""Small durable provider boundary backed by Codex app-server."""

from __future__ import annotations

import json
import math
import os
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .capabilities import CapabilityError, CodexCapabilities
from .errors import BudgetExceeded, SessionError
from .models import StreamEvent
from .policy import Policy
from .recovery import Completed, RecoveryOutcome, Stopped, Unknown


class ProviderError(RuntimeError):
    pass


class ProviderPolicyError(CapabilityError, ProviderError):
    pass


class ProviderInterruptedError(ProviderError):
    def __init__(
        self,
        message: str,
        *,
        process_alive: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.process_alive = process_alive


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
    timeout: float
    session_key: str | None = None
    operation_key: str | None = None
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
        object.__setattr__(
            self, "artifacts", {str(k): Path(v) for k, v in self.artifacts.items()}
        )
        object.__setattr__(self, "reads", tuple(Path(v) for v in self.reads))
        if not self.operation_id:
            raise ValueError("operation_id must be non-empty")
        if self.session_key is not None and not self.session_key:
            raise ValueError("session_key must be non-empty or None")
        if self.operation_key is not None and not self.operation_key:
            raise ValueError("operation_key must be non-empty or None")
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
    def dispose(self) -> None: ...
    def close(self) -> None: ...


def _response(value: Any) -> ProviderResponse:
    if not isinstance(value, Mapping):
        raise ProviderInterruptedError("completed checkpoint has no response")
    text = value.get("text")
    if not isinstance(text, str):
        raise ProviderInterruptedError("completed checkpoint has invalid response text")
    response = ProviderResponse(
        text, value.get("session_id"), value.get("usage", {}), value.get("metadata", {})
    )
    try:
        response.to_record()
    except TypeError as exc:
        raise ProviderInterruptedError(
            f"completed checkpoint has invalid response: {exc}"
        ) from exc
    return response


class CodexProvider:
    """Lazy provider facade with one app-server per logical operation."""

    name = "codex"
    _reserves_dispatch = True
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
        adapter_factory: Callable[[], Any] | None = None,
    ) -> None:
        if adapter is not None and adapter_factory is not None:
            raise ValueError("adapter and adapter_factory are mutually exclusive")
        self.command, self.env, self.state_dir = command, dict(env or {}), state_dir
        self.interrupt_grace_seconds = interrupt_grace_seconds
        self._injected_adapter = adapter
        self._injected_adapter_used = False
        self._adapter_factory = adapter_factory
        self._owners: dict[str, Any] = {}
        self._owner_lock = threading.RLock()
        self._probe_adapter: Any | None = adapter
        self._factory_probe_available = False
        self._closed = False

    @staticmethod
    def _owner_key(request: ProviderRequest) -> str:
        return request.operation_key or request.operation_id

    def _new_adapter(self) -> Any:
        if self._adapter_factory is not None:
            if self._factory_probe_available:
                assert self._probe_adapter is not None
                self._factory_probe_available = False
                return self._probe_adapter
            return self._adapter_factory()
        if self._injected_adapter is not None:
            if self._injected_adapter_used:
                raise ProviderError(
                    "an injected adapter can own only one logical operation; "
                    "pass adapter_factory for multiple operations"
                )
            self._injected_adapter_used = True
            return self._injected_adapter
        from .codex_appserver import CodexAppServerAdapter

        capabilities = self.probe()
        assert self._probe_adapter is not None
        return CodexAppServerAdapter(
            self.command,
            env=self.env,
            state_dir=self.state_dir,
            interrupt_grace_seconds=self.interrupt_grace_seconds,
            capabilities=capabilities,
            capability_probe_stat=self._probe_adapter._probe_stat,
        )

    def _adapter_for(self, request: ProviderRequest) -> Any:
        key = self._owner_key(request)
        with self._owner_lock:
            if self._closed:
                raise ProviderError("Codex provider is closed")
            owner = self._owners.get(key)
            if owner is None:
                owner = self._new_adapter()
                self._owners[key] = owner
            return owner

    def probe(self):
        with self._owner_lock:
            if self._closed:
                raise ProviderError("Codex provider is closed")
            if self._probe_adapter is None:
                if self._adapter_factory is not None:
                    self._probe_adapter = self._adapter_factory()
                    self._factory_probe_available = True
                else:
                    from .codex_appserver import CodexAppServerAdapter

                    # Adapter construction is process-free. This object owns only
                    # the capability cache and never starts an app-server.
                    self._probe_adapter = CodexAppServerAdapter(
                        self.command,
                        env=self.env,
                        state_dir=self.state_dir,
                        interrupt_grace_seconds=self.interrupt_grace_seconds,
                    )
            probe_adapter = self._probe_adapter
        return probe_adapter.probe()

    def validate_request(self, request: ProviderRequest) -> CodexCapabilities:
        try:
            with self._owner_lock:
                if self._closed:
                    raise ProviderError("Codex provider is closed")
                if self._probe_adapter is None:
                    if self._adapter_factory is not None:
                        self._probe_adapter = self._adapter_factory()
                        self._factory_probe_available = True
                    else:
                        from .codex_appserver import CodexAppServerAdapter

                        self._probe_adapter = CodexAppServerAdapter(
                            self.command,
                            env=self.env,
                            state_dir=self.state_dir,
                            interrupt_grace_seconds=self.interrupt_grace_seconds,
                        )
                probe_adapter = self._probe_adapter
            capabilities = probe_adapter.probe(deadline=request.deadline)
        except TimeoutError as exc:
            raise ProviderTimeoutError(
                f"Codex capability probe timed out (dispatch budget: {request.timeout:g} seconds)"
            ) from exc
        return capabilities

    def run(self, request: ProviderRequest) -> ProviderResponse:
        if request.on_checkpoint is None:
            raise ProviderError(
                "Codex requests require a durable on_checkpoint callback"
            )
        owner = self._adapter_for(request)
        durable_checkpoint = request.on_checkpoint
        dispatch = None

        def checkpoint(update: dict[str, Any]) -> None:
            nonlocal dispatch
            if update.get("status") == "turn_intent" and dispatch is None:
                from .dispatches import Dispatch

                dispatch = Dispatch(self, request)
                dispatch.started()
            durable_checkpoint(update)

        native_request = replace(request, on_checkpoint=checkpoint)
        try:
            try:
                response = owner.start_turn(native_request, request.on_event)
                response.to_record()
                if dispatch is None:
                    raise ProviderError(
                        "Codex adapter returned without a durable turn_intent checkpoint"
                    )
            except CapabilityError as exc:
                checkpoint(
                    {
                        "status": "failed",
                        "policy_error": request.preset in {"query", "generate"},
                        "error": str(exc),
                    }
                )
                raise ProviderPolicyError(str(exc)) from exc
            except SessionError:
                raise
            except BudgetExceeded:
                raise
            except ProviderError:
                raise
            except Exception as exc:
                raise ProviderError(f"Codex app-server failed: {exc}") from exc
            checkpoint({"status": "completed", "response": response.to_record()})
        except BaseException as exc:
            if dispatch is not None:
                dispatch.finish(
                    "timed_out"
                    if isinstance(exc, ProviderTimeoutError)
                    else "failed"
                    if isinstance(exc, Exception)
                    else "interrupted",
                    usage=getattr(exc, "usage", None),
                    error=exc,
                )
            raise
        dispatch.finish("completed", usage=response.usage)
        return response

    def recover(self, request: ProviderRequest) -> RecoveryOutcome:
        value = request.checkpoint
        if value is None:
            return Stopped("provider dispatch was not authorized")
        if not isinstance(value, Mapping):
            return Unknown("provider checkpoint is malformed")
        cleanup = value.get("cleanup")
        if value.get("policy_error"):
            if (
                isinstance(cleanup, Mapping)
                and cleanup.get("status") == "completed"
            ):
                raise ProviderPolicyError(
                    str(value.get("error") or "Codex tool policy failed")
                )
            return Unknown(
                str(
                    cleanup.get("error")
                    if isinstance(cleanup, Mapping) and cleanup.get("error")
                    else "Codex policy failure cleanup is not verified"
                )
            )
        status = value.get("status")
        if status in {"completed", "response_received"} and "response" in value:
            try:
                response = _response(value.get("response"))
            except ProviderInterruptedError as exc:
                return Unknown(str(exc))
            if status == "response_received":
                response = replace(
                    response,
                    metadata={
                        "probe_hash": value.get("probe_hash"),
                        "profile_hash": value.get("profile_hash"),
                        "enforcement": value.get("enforcement", {}),
                        **response.metadata,
                    },
                )
            return Completed(response, "adopted from the run ledger")
        cleanup_incomplete = (
            isinstance(cleanup, Mapping) and cleanup.get("status") == "incomplete"
        )
        if status == "failed" and not cleanup_incomplete:
            return Stopped(str(value.get("error") or "provider attempt failed"))
        dispatch_authorized = (
            status in {"dispatch_authorized", "turn_intent"}
            or value.get("dispatch_authorized") is True
        )
        if (
            status in {"prepared", "configured", "thread_bound"}
            and not dispatch_authorized
        ):
            if cleanup_incomplete:
                return Unknown(
                    str(cleanup.get("error") or "provider cleanup is incomplete")
                )
            return Stopped("provider dispatch was not authorized")
        thread_id, turn_id = value.get("session_id"), value.get("turn_id")
        if not isinstance(thread_id, str) or not isinstance(turn_id, str):
            if cleanup_incomplete:
                return Unknown(
                    str(cleanup.get("error") or "provider cleanup is incomplete")
                )
            return Unknown(
                "turn dispatch was authorized before its native turn id was durable"
            )
        if request.on_checkpoint is None:
            return Unknown("native recovery requires a durable on_checkpoint callback")
        owner = self._adapter_for(request)
        recovery_request = replace(
            request, session_id=thread_id, checkpoint=dict(value)
        )
        try:
            native_status, response = owner.recover_turn(
                recovery_request, thread_id=thread_id, turn_id=turn_id
            )
        except CapabilityError as exc:
            if request.preset in {"query", "generate"}:
                request.on_checkpoint(
                    {"status": "failed", "policy_error": True, "error": str(exc)}
                )
                raise ProviderPolicyError(str(exc)) from exc
            return Unknown(f"Codex native recovery failed policy audit: {exc}")
        except Exception as exc:  # noqa: BLE001 - recovery must normalize adapter failures
            return Unknown(f"Codex native recovery failed: {exc}")
        if native_status == "completed" and isinstance(response, ProviderResponse):
            metadata = {
                "probe_hash": value.get("probe_hash"),
                "profile_hash": value.get("profile_hash"),
                "enforcement": value.get("enforcement", {}),
                **response.metadata,
            }
            recovered = replace(response, metadata=metadata)
            request.on_checkpoint(
                {"status": "completed", "response": recovered.to_record()}
            )
            return Completed(recovered, "adopted from Codex thread history")
        if cleanup_incomplete:
            return Unknown(
                str(cleanup.get("error") or "provider cleanup is incomplete")
            )
        if native_status == "running":
            from .recovery import Running

            return Running("Codex reports the native turn is still running")
        if native_status == "stopped":
            request.on_checkpoint(
                {"status": "failed", "error": "Codex reports the native turn stopped"}
            )
            return Stopped("Codex reports the native turn stopped")
        return Unknown("Codex thread history does not identify the recorded turn")

    def release_operation(
        self, operation_key: str, *, require_owner: bool = False, abort: bool = False
    ) -> None:
        """Release the operation-local adapter after validation and repairs finish."""

        key = operation_key
        with self._owner_lock:
            owner = self._owners.get(key)
            if owner is None:
                if require_owner:
                    raise ProviderError(
                        f"Codex operation owner {operation_key!r} is unavailable; "
                        "cleanup cannot be verified"
                    )
                return
            # Keep the key reserved until cleanup succeeds.  Otherwise a
            # concurrent repair can install a replacement while the prior
            # process tree is still alive or its cleanup is unverified.
            if abort:
                owner.close()
            else:
                owner.dispose()
            self._owners.pop(key, None)

    def _abandon_operation(self, operation_key: str) -> None:
        """Forget an owner after a durable explicit retry accepts its uncertainty."""

        with self._owner_lock:
            owner = self._owners.pop(operation_key, None)
            if (
                owner is not None
                and self._adapter_factory is not None
                and self._probe_adapter is owner
            ):
                self._probe_adapter = None
                self._factory_probe_available = False

    def close(self) -> None:
        with self._owner_lock:
            if self._closed and not self._owners:
                return
            self._closed = True
            owners: list[Any] = []
            for owner in self._owners.values():
                if not any(owner is existing for existing in owners):
                    owners.append(owner)
            failures: list[tuple[Any, BaseException]] = []
            closed: list[Any] = []
            for owner in owners:
                try:
                    owner.close()
                except Exception as exc:  # noqa: BLE001 - close every owned adapter
                    failures.append((owner, exc))
                else:
                    closed.append(owner)
            self._owners = {
                key: owner
                for key, owner in self._owners.items()
                if not any(owner is finished for finished in closed)
            }
        if failures:
            errors = [exc for _owner, exc in failures]
            raise ProviderError(
                "failed to close one or more Codex operation adapters: "
                + "; ".join(str(exc) for exc in errors)
            ) from ExceptionGroup("Codex adapter cleanup failures", errors)


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
]
