"""Provider-first SDK for durable Codex operations."""

from __future__ import annotations

import contextvars
import math
import threading
import time
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Any, Self, TypeVar, overload

from .errors import (
    BotpipeError,
    BudgetExceeded,
    CancellationRequested,
    UncertainOperation,
)
from .models import Result
from .operations import execute_provider_operation
from .policy import NetworkMode, Policy, SandboxMode
from .prompts import Prompt
from .runtime import (
    _CURRENT,
    Botpipe,
    _async_call,
    _cancellation_event,
    _restore_exception,
    workflow,
)
from .sessions import Session

T = TypeVar("T")


class _Inherit:
    __slots__ = ()


INHERIT = _Inherit()
_CONFIG = frozenset(
    {
        "instructions",
        "model",
        "effort",
        "workspace",
        "sandbox",
        "network",
        "tools",
        "timeout",
        "output_retries",
        "name",
        "settings",
    }
)
_CALLBACK = contextvars.ContextVar("botpipe_provider_callback", default=None)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("configuration keys must be strings")
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if value is None or isinstance(value, (str, bool, int, Path)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise TypeError(f"unsupported configuration value: {type(value).__name__}")


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_plain(item) for item in value)
    return value


def _validate_config(values: Mapping[str, Any]) -> Mapping[str, Any]:
    unknown = values.keys() - _CONFIG
    if unknown:
        raise TypeError(f"unknown provider configuration: {', '.join(sorted(unknown))}")
    values = {key: value for key, value in values.items() if value is not None}
    for key in ("instructions", "model", "effort", "name"):
        if values.get(key) is not None and not isinstance(values[key], str):
            raise TypeError(f"{key} must be a string or None")
    retries = values.get("output_retries", 2)
    if retries is not None and (
        isinstance(retries, bool) or not isinstance(retries, int) or retries < 0
    ):
        raise ValueError("output_retries must be a nonnegative integer or None")
    timeout = values.get("timeout")
    if timeout is not None and (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise ValueError("timeout must be finite and greater than zero")
    tools = values.get("tools")
    if tools is not None:
        if isinstance(tools, (str, bytes)):
            raise TypeError("tools must be a sequence of tool names")
        tools = tuple(tools)
        if any(not isinstance(tool, str) or not tool for tool in tools):
            raise ValueError("tools must contain nonempty strings")
        values["tools"] = tools
    from .config import validate_non_secret_settings

    validate_non_secret_settings(values)
    return _freeze(values)


class _RuntimeCell:
    def __init__(self, runtime: Botpipe | None) -> None:
        self.runtime = runtime
        self.closed = False
        self.lock = threading.Lock()
        self.direct_task_id = uuid.uuid4().hex[:12]


class _ConversationCell:
    def __init__(self, session: Session | None | _Inherit) -> None:
        self.session = session
        self.lock = threading.Lock()


class Provider:
    """Immutable operation defaults plus one lazy managed conversation."""

    backend: str | None = None

    def __init__(
        self,
        *,
        runtime: Botpipe | None = None,
        session: Session | None | _Inherit = INHERIT,
        **config: Any,
    ) -> None:
        if runtime is not None and not isinstance(runtime, Botpipe):
            raise TypeError("runtime must be a Botpipe instance")
        if (
            session is not INHERIT
            and session is not None
            and not isinstance(session, Session)
        ):
            raise TypeError("session must be a Session or None")
        self._runtime_cell = _RuntimeCell(runtime)
        self._conversation = _ConversationCell(session)
        self._config = _validate_config(config)

    @property
    def config(self) -> Mapping[str, Any]:
        return self._config

    def close(self) -> None:
        """Close the lazily created runtime and its app-server, if any."""
        with self._runtime_cell.lock:
            runtime = self._runtime_cell.runtime
            if runtime is not None:
                runtime.close()
            self._runtime_cell.closed = True

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def session(self) -> Session | None:
        value = self._conversation.session
        return None if value is INHERIT else value

    def with_config(
        self, *, session: Session | None | _Inherit = INHERIT, **changes: Any
    ) -> Self:
        merged = {**_plain(self._config), **_plain(_validate_config(changes))}
        result = object.__new__(type(self))
        result._runtime_cell = self._runtime_cell
        result._config = _validate_config(merged)
        result._conversation = (
            self._conversation if session is INHERIT else _ConversationCell(session)
        )
        selected = result._conversation.session
        if (
            selected is not INHERIT
            and selected is not None
            and not isinstance(selected, Session)
        ):
            raise TypeError("session must be a Session or None")
        return result

    def _runtime_for_call(self) -> Botpipe:
        ctx = _CURRENT.get()
        if self._runtime_cell.closed:
            raise BotpipeError("provider is closed")
        if ctx is not None:
            if (
                self._runtime_cell.runtime is not None
                and self._runtime_cell.runtime is not ctx.client
            ):
                raise BotpipeError("provider is attached to another runtime")
            return ctx.client
        if self._runtime_cell.runtime is None:
            with self._runtime_cell.lock:
                if self._runtime_cell.runtime is None:
                    from .config import load_config

                    config = load_config(
                        self._config.get("workspace", "."), provider=self.backend
                    )
                    self._runtime_cell.runtime = Botpipe(**config.client_kwargs())
        return self._runtime_cell.runtime

    def _session_for_call(
        self, override: Session | None | _Inherit, *, direct: bool
    ) -> Session | None:
        if override is not INHERIT:
            if override is not None and not isinstance(override, Session):
                raise TypeError("session must be a Session or None")
            return override
        with self._conversation.lock:
            if self._conversation.session is INHERIT:
                task = self._runtime_cell.direct_task_id
                self._conversation.session = (
                    Session.task(f"provider-{task}") if direct else Session()
                )
            return self._conversation.session

    def _invoke(
        self,
        operation: str,
        prompt: str | Prompt,
        *,
        session=INHERIT,
        on_event=None,
        **options: Any,
    ):
        ctx = _CURRENT.get()
        direct = ctx is None
        runtime = self._runtime_for_call()
        selected_session = self._session_for_call(session, direct=direct)
        call_config = {
            key: options.pop(key) for key in tuple(options) if key in _CONFIG
        }
        runtime_defaults = {
            key: value
            for key, value in runtime.provider_config.items()
            if key in _CONFIG and value is not None
        }
        config = {
            **runtime_defaults,
            **_plain(self._config),
            **_plain(_validate_config(call_config)),
        }
        policy = _policy(config, operation)
        arguments = {
            **options,
            "policy": policy,
            "name": config.get("name"),
            "output_retries": (
                2 if config.get("output_retries") is None else config["output_retries"]
            ),
            "workspace": config.get("workspace"),
            "operation": operation,
            "instructions": config.get("instructions"),
            "settings": config.get("settings", {}),
            "tools": config.get("tools"),
            "timeout": config.get("timeout"),
            "on_event": on_event if ctx is not None else None,
        }
        if ctx is not None:
            return execute_provider_operation(selected_session, prompt, **arguments)
        if on_event is not None and not callable(on_event):
            raise TypeError("on_event must be callable or None")
        spec = {
            "operation": operation,
            "prompt": prompt,
            "session": None
            if selected_session is None
            else selected_session.descriptor(direct=True),
            "options": {
                key: value for key, value in arguments.items() if key != "on_event"
            },
        }
        token = _CALLBACK.set(on_event)
        lock = selected_session._turn_lock if selected_session is not None else None
        locked = False
        try:
            if lock is not None:
                wait_timeout = config.get("timeout") or runtime.limits.timeout
                deadline = time.monotonic() + wait_timeout
                cancellation = _cancellation_event()
                while not lock.acquire(
                    timeout=min(0.1, max(0.0, deadline - time.monotonic()))
                ):
                    if cancellation is not None and cancellation.is_set():
                        raise CancellationRequested(
                            "Cancelled while waiting for the session"
                        )
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Timed out waiting for the session")
                locked = True
                if cancellation is not None and cancellation.is_set():
                    raise CancellationRequested(
                        "Cancelled while waiting for the session"
                    )
            outcome = runtime.run(
                _direct_provider_operation,
                spec,
                task_id=self._runtime_cell.direct_task_id,
            )
        finally:
            if locked:
                lock.release()
            _CALLBACK.reset(token)
        if outcome.ok:
            return outcome.value
        records = runtime.journal.operations(outcome.run_id)
        record = next(
            (item for item in reversed(records) if item["kind"] == "provider"),
            records[-1] if records else None,
        )
        operation_id = record["id"] if record is not None else None
        if outcome.status == "interrupted":
            error = UncertainOperation(
                outcome.error or "provider operation is unresolved", operation_id
            )
        elif outcome.status == "budget_exceeded":
            error = BudgetExceeded(outcome.error or "provider budget exceeded")
        elif record is not None and record.get("error") is not None:
            error = _restore_exception(record["error"])
        else:
            error = BotpipeError(
                outcome.error or f"provider operation {outcome.status}"
            )
        error.run_id = outcome.run_id
        if not getattr(error, "operation_id", None):
            error.operation_id = operation_id
        raise error

    @overload
    def run(
        self,
        prompt: str | Prompt,
        *,
        input: Any = None,
        reads: Any = (),
        writes: Any = (),
        returns: type[T],
        session: Session | None | _Inherit = INHERIT,
        sandbox: str | SandboxMode | None = None,
        network: str | bool | NetworkMode | None = None,
        tools: Sequence[str] | None = None,
        timeout: float | None = None,
        output_retries: int | None = None,
        on_event: Any = None,
    ) -> Result[T]: ...
    @overload
    def run(
        self,
        prompt: str | Prompt,
        *,
        input: Any = None,
        reads: Any = (),
        writes: Any = (),
        returns: type[str] = str,
        session: Session | None | _Inherit = INHERIT,
        sandbox: str | SandboxMode | None = None,
        network: str | bool | NetworkMode | None = None,
        tools: Sequence[str] | None = None,
        timeout: float | None = None,
        output_retries: int | None = None,
        on_event: Any = None,
    ) -> Result[str]: ...
    def run(
        self,
        prompt,
        *,
        input=None,
        reads=(),
        writes=(),
        returns=str,
        session=INHERIT,
        sandbox=None,
        network=None,
        tools=None,
        timeout=None,
        output_retries=None,
        on_event=None,
    ):
        values = {"input": input, "reads": reads, "writes": writes, "returns": returns}
        for key, value in (
            ("sandbox", sandbox),
            ("network", network),
            ("tools", tools),
            ("timeout", timeout),
            ("output_retries", output_retries),
        ):
            if value is not None:
                values[key] = value
        return self._invoke("run", prompt, session=session, on_event=on_event, **values)

    @overload
    def query(
        self,
        prompt: str | Prompt,
        *,
        input: Any = None,
        reads: Any = (),
        returns: type[T],
        session: Session | None | _Inherit = INHERIT,
        tools: Sequence[str] | None = None,
        timeout: float | None = None,
        output_retries: int | None = None,
        on_event: Any = None,
    ) -> Result[T]: ...
    @overload
    def query(
        self,
        prompt: str | Prompt,
        *,
        input: Any = None,
        reads: Any = (),
        returns: type[str] = str,
        session: Session | None | _Inherit = INHERIT,
        tools: Sequence[str] | None = None,
        timeout: float | None = None,
        output_retries: int | None = None,
        on_event: Any = None,
    ) -> Result[str]: ...
    def query(
        self,
        prompt,
        *,
        input=None,
        reads=(),
        returns=str,
        session=INHERIT,
        tools=None,
        timeout=None,
        output_retries=None,
        on_event=None,
    ):
        values = {
            "input": input,
            "reads": reads,
            "writes": (),
            "returns": returns,
        }
        if tools is not None:
            values["tools"] = tools
        if timeout is not None:
            values["timeout"] = timeout
        if output_retries is not None:
            values["output_retries"] = output_retries
        return self._invoke(
            "query", prompt, session=session, on_event=on_event, **values
        )

    @overload
    def generate(
        self,
        prompt: str | Prompt,
        *,
        input: Any = None,
        reads: Any = (),
        returns: type[T],
        session: Session | None | _Inherit = INHERIT,
        allowed_tools: Sequence[str] = (),
        timeout: float | None = None,
        output_retries: int | None = None,
        on_event: Any = None,
    ) -> Result[T]: ...
    @overload
    def generate(
        self,
        prompt: str | Prompt,
        *,
        input: Any = None,
        reads: Any = (),
        returns: type[str] = str,
        session: Session | None | _Inherit = INHERIT,
        allowed_tools: Sequence[str] = (),
        timeout: float | None = None,
        output_retries: int | None = None,
        on_event: Any = None,
    ) -> Result[str]: ...
    def generate(
        self,
        prompt,
        *,
        input=None,
        reads=(),
        returns=str,
        session=INHERIT,
        allowed_tools=(),
        timeout=None,
        output_retries=None,
        on_event=None,
    ):
        values = {
            "input": input,
            "reads": reads,
            "writes": (),
            "returns": returns,
            "tools": allowed_tools,
        }
        if timeout is not None:
            values["timeout"] = timeout
        if output_retries is not None:
            values["output_retries"] = output_retries
        return self._invoke(
            "generate", prompt, session=session, on_event=on_event, **values
        )

    @overload
    async def arun(
        self, prompt: str | Prompt, *, returns: type[T], **options: Any
    ) -> Result[T]: ...
    @overload
    async def arun(
        self, prompt: str | Prompt, *, returns: type[str] = str, **options: Any
    ) -> Result[str]: ...
    async def arun(self, prompt, **options):
        return await _async_call(self.run, prompt, **options)

    @overload
    async def aquery(
        self, prompt: str | Prompt, *, returns: type[T], **options: Any
    ) -> Result[T]: ...
    @overload
    async def aquery(
        self, prompt: str | Prompt, *, returns: type[str] = str, **options: Any
    ) -> Result[str]: ...
    async def aquery(self, prompt, **options):
        return await _async_call(self.query, prompt, **options)

    @overload
    async def agenerate(
        self, prompt: str | Prompt, *, returns: type[T], **options: Any
    ) -> Result[T]: ...
    @overload
    async def agenerate(
        self, prompt: str | Prompt, *, returns: type[str] = str, **options: Any
    ) -> Result[str]: ...
    async def agenerate(self, prompt, **options):
        return await _async_call(self.generate, prompt, **options)


class Codex(Provider):
    backend = "codex"


def _policy(config: Mapping[str, Any], operation: str) -> Policy:
    payload: dict[str, Any] = {}
    if config.get("model") is not None:
        payload["model"] = config["model"]
    if config.get("effort") is not None:
        payload["effort"] = config["effort"]
    if config.get("timeout") is not None:
        payload["timeout"] = config["timeout"]
    if operation in {"query", "generate"}:
        payload.update(sandbox_mode=SandboxMode.READ_ONLY, network=NetworkMode.NONE)
    else:
        if config.get("sandbox") is not None:
            payload["sandbox_mode"] = config["sandbox"]
        if config.get("network") is not None:
            payload["network"] = config["network"]
    return Policy(**payload)


@workflow(name="botpipe.provider.operation", version="2")
def _direct_provider_operation(spec):
    session = (
        None if spec["session"] is None else Session.from_descriptor(spec["session"])
    )
    callback = _CALLBACK.get()
    return execute_provider_operation(
        session, spec["prompt"], on_event=callback, **spec["options"]
    )


__all__ = ["INHERIT", "Codex", "Provider"]
