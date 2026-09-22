"""Live observation of one provider invocation.

The stream is deliberately a view of the normal provider coordinator.  It does
not own an alternate dispatch path and never turns a completed response into
made-up partial events.
"""

from __future__ import annotations

import asyncio
import contextvars
import math
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Generic, Self, TypeVar

from .models import Result


T = TypeVar("T")


class StreamError(RuntimeError):
    """A streaming invocation could not be observed safely."""


class StreamBufferOverflow(StreamError):
    """The consumer fell behind the bounded live-event buffer."""


class StreamCancellationUnconfirmed(StreamError):
    """A closed stream did not settle within its control timeout."""


@dataclass(frozen=True, slots=True)
class StreamEvent:
    """One ordered native event with the provider payload intact."""

    sequence: int
    type: str
    native: Mapping[str, Any]
    run_id: str = ""
    operation_id: str = ""

    @property
    def payload(self) -> Mapping[str, Any]:
        """Readable alias for integrations that call the native object a payload."""
        return self.native


_ACTIVE_STREAM: contextvars.ContextVar[Stream[Any] | None] = contextvars.ContextVar(
    "botpipe_active_stream", default=None
)


def bind_stream_identity(run_id: str, operation_id: str) -> None:
    """Bind coordinator identity to the active stream, if there is one."""
    stream = _ACTIVE_STREAM.get()
    if stream is not None:
        stream._bind_identity(run_id, operation_id)


def mark_stream_replay(run_id: str, operation_id: str) -> None:
    """Mark that the coordinator returned recorded state without live deltas."""
    stream = _ACTIVE_STREAM.get()
    if stream is not None:
        stream._bind_identity(run_id, operation_id)
        stream._mark_replayed()


def require_live_capability(adapter: Any) -> None:
    """Reject a fresh streamed dispatch unless its native profile is proven live."""
    if _ACTIVE_STREAM.get() is None:
        return
    capabilities = getattr(adapter, "capabilities", None)
    if not bool(getattr(capabilities, "live_streaming", False)):
        from .providers import CapabilityError

        name = getattr(adapter, "name", type(adapter).__name__)
        profile = getattr(capabilities, "version", "unknown")
        raise CapabilityError(
            f"{name} adapter profile {profile!r} does not provide live streaming"
        )


class Stream(Generic[T]):
    """A bounded sync/async event iterator and terminal-result owner."""

    def __init__(
        self,
        invoke: Callable[[], Result[T]],
        *,
        cancel: Callable[[str, str], Any] | None = None,
        max_events: int = 256,
        max_event_bytes: int = 1_000_000,
        max_buffer_bytes: int = 4 * 1024 * 1024,
        close_timeout: float = 5.0,
    ) -> None:
        if isinstance(max_events, bool) or not isinstance(max_events, int) or max_events < 1:
            raise ValueError("max_events must be a positive integer")
        for name, value in (
            ("max_event_bytes", max_event_bytes),
            ("max_buffer_bytes", max_buffer_bytes),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if max_event_bytes > max_buffer_bytes:
            raise ValueError("max_event_bytes cannot exceed max_buffer_bytes")
        if (
            isinstance(close_timeout, bool)
            or not isinstance(close_timeout, (int, float))
            or not math.isfinite(close_timeout)
            or close_timeout <= 0
        ):
            raise ValueError("close_timeout must be finite and positive")
        self._invoke = invoke
        self._cancel = cancel
        self._max_events = max_events
        self._max_event_bytes = max_event_bytes
        self._max_buffer_bytes = max_buffer_bytes
        self._event_sizes: deque[int] = deque()
        self._buffered_bytes = 0
        self._close_timeout = float(close_timeout)
        self._events: deque[StreamEvent] = deque()
        self._condition = threading.Condition()
        self._thread: threading.Thread | None = None
        self._result: Result[T] | None = None
        self._error: BaseException | None = None
        self._done = False
        self._closed = False
        self._cancel_requested = False
        self._cancel_thread: threading.Thread | None = None
        self._cancel_error: BaseException | None = None
        self._overflow = False
        self._run_id = ""
        self._operation_id = ""
        self._replayed = False
        self._sequence = 0
        # Capture exactly once, before the worker exists. The provider call and
        # observer registration then share the caller's workflow context.
        context = contextvars.copy_context()
        self._thread = threading.Thread(
            target=context.run,
            args=(self._work,),
            name="botpipe-stream",
            daemon=True,
        )
        self._thread.start()

    @property
    def run_id(self) -> str:
        with self._condition:
            return self._run_id

    @property
    def operation_id(self) -> str:
        with self._condition:
            return self._operation_id

    @property
    def replayed(self) -> bool:
        with self._condition:
            return self._replayed

    @property
    def done(self) -> bool:
        with self._condition:
            return self._done

    def _bind_identity(self, run_id: str, operation_id: str) -> None:
        with self._condition:
            if self._run_id and self._run_id != run_id:
                raise StreamError("A stream cannot observe more than one run")
            if self._operation_id and self._operation_id != operation_id:
                raise StreamError("A stream cannot observe more than one operation")
            self._run_id = run_id
            self._operation_id = operation_id
            self._condition.notify_all()

    def _mark_replayed(self) -> None:
        with self._condition:
            self._replayed = True
            self._condition.notify_all()

    def _emit(self, native: Mapping[str, Any]) -> None:
        if not isinstance(native, Mapping):
            return
        with self._condition:
            if self._closed or self._overflow:
                return
            try:
                event_bytes = self._measure_native(native, self._max_event_bytes)
            except Exception as exc:
                self._overflow = True
                self._error = StreamBufferOverflow(
                    f"Native event could not be bounded safely: {exc}; cancellation requested"
                )
                self._condition.notify_all()
                self._request_cancel_locked()
                return
            if event_bytes > self._max_event_bytes:
                self._overflow = True
                self._error = StreamBufferOverflow(
                    f"Native event exceeded {self._max_event_bytes} bytes; cancellation requested"
                )
                self._condition.notify_all()
                self._request_cancel_locked()
                return
            if len(self._events) >= self._max_events:
                self._overflow = True
                self._error = StreamBufferOverflow(
                    f"Live event buffer exceeded {self._max_events} events; "
                    "cancellation requested"
                )
                self._condition.notify_all()
                self._request_cancel_locked()
                return
            if self._buffered_bytes + event_bytes > self._max_buffer_bytes:
                self._overflow = True
                self._error = StreamBufferOverflow(
                    f"Live event buffer exceeded {self._max_buffer_bytes} bytes; "
                    "cancellation requested"
                )
                self._condition.notify_all()
                self._request_cancel_locked()
                return
            kind = native.get("type", native.get("event", "native"))
            if not isinstance(kind, str) or not kind:
                kind = "native"
            self._events.append(
                StreamEvent(
                    sequence=self._sequence,
                    type=kind,
                    native=native,
                    run_id=self._run_id,
                    operation_id=self._operation_id,
                )
            )
            self._event_sizes.append(event_bytes)
            self._buffered_bytes += event_bytes
            self._sequence += 1
            self._condition.notify_all()

    @staticmethod
    def _measure_native(value: Any, limit: int) -> int:
        """Conservatively bound a JSON-like event without copying its payload."""
        active: set[int] = set()

        def string_size(item: str, remaining: int) -> int:
            total = 2
            for character in item:
                codepoint = ord(character)
                if character in {'"', "\\"} or codepoint in (8, 9, 10, 12, 13):
                    total += 2
                elif codepoint < 32:
                    total += 6
                elif codepoint < 128:
                    total += 1
                elif codepoint < 2048:
                    total += 2
                elif codepoint < 65536:
                    total += 3
                else:
                    total += 4
                if total > remaining:
                    break
            return total

        def measure(item: Any, depth: int, remaining: int) -> int:
            if depth > 64:
                raise ValueError("native event nesting exceeds 64 levels")
            if item is None or type(item) is bool:
                return 5
            if type(item) in (int, float):
                if type(item) is float and not math.isfinite(item):
                    raise ValueError("native event contains a non-finite number")
                return len(str(item))
            if type(item) is str:
                return string_size(item, remaining)
            identity = id(item)
            if identity in active:
                raise ValueError("native event contains a cycle")
            active.add(identity)
            try:
                total = 2
                if isinstance(item, Mapping):
                    values = item.items()
                    for key, child in values:
                        if type(key) is not str:
                            raise TypeError("native event keys must be strings")
                        total += 3 + string_size(key, remaining - total)
                        total += measure(child, depth + 1, remaining - total)
                        if total > remaining:
                            return total
                    return total
                if isinstance(item, (list, tuple)):
                    for child in item:
                        total += 1 + measure(child, depth + 1, remaining - total)
                        if total > remaining:
                            return total
                    return total
                raise TypeError(
                    f"native event contains unsupported {type(item).__name__}"
                )
            finally:
                active.remove(identity)

        return measure(value, 0, limit)

    def _work(self) -> None:
        # Import lazily so provider adapters remain usable without this module's
        # worker machinery and the module dependency stays one-way.
        from .providers import observe_native_events

        active = _ACTIVE_STREAM.set(self)
        try:
            with observe_native_events(self._emit):
                result = self._invoke()
            if not isinstance(result, Result):
                raise TypeError("A streaming provider invocation must return Result")
            self._bind_identity(result.run_id, result.operation_id)
            with self._condition:
                self._result = result
        except BaseException as exc:
            with self._condition:
                if self._error is None:
                    self._error = exc
                self._run_id = self._run_id or str(getattr(exc, "run_id", "") or "")
                self._operation_id = self._operation_id or str(
                    getattr(exc, "operation_id", "") or ""
                )
        finally:
            _ACTIVE_STREAM.reset(active)
            with self._condition:
                self._done = True
                self._condition.notify_all()

    def _request_cancel_locked(self) -> None:
        if self._cancel_requested:
            return
        self._cancel_requested = True
        cancel = self._cancel
        if cancel is None:
            return
        def request() -> None:
            try:
                # Dispatch supplies identity before effects start. A context can
                # be exited immediately after construction, so allow that bind
                # to win its small startup race before asking runtime to stop.
                deadline = time.monotonic() + self._close_timeout
                with self._condition:
                    while not self._run_id and not self._done:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            break
                        self._condition.wait(remaining)
                    run_id, operation_id = self._run_id, self._operation_id
                if not run_id and self._done:
                    return
                cancel(run_id, operation_id)
            except BaseException as exc:
                with self._condition:
                    self._cancel_error = exc
                    if self._error is None:
                        self._error = exc
                    self._condition.notify_all()

        self._cancel_thread = threading.Thread(
            target=request, name="botpipe-stream-cancel", daemon=True
        )
        self._cancel_thread.start()

    def cancel(self) -> None:
        """Request cancellation without claiming that provider effects stopped."""
        with self._condition:
            if not self._done:
                self._request_cancel_locked()

    def __iter__(self) -> Iterator[StreamEvent]:
        return self

    def __next__(self) -> StreamEvent:
        with self._condition:
            while not self._events and not self._done and self._error is None:
                self._condition.wait()
            if self._events:
                event = self._events.popleft()
                self._buffered_bytes -= self._event_sizes.popleft()
                return event
            if self._error is not None:
                raise self._error
            raise StopIteration

    def _next_async(self) -> tuple[bool, StreamEvent | None]:
        try:
            return True, next(self)
        except StopIteration:
            return False, None

    def __aiter__(self):
        return self

    async def __anext__(self) -> StreamEvent:
        found, event = await asyncio.to_thread(self._next_async)
        if not found:
            raise StopAsyncIteration
        return event  # type: ignore[return-value]

    def result(self, timeout: float | None = None) -> Result[T]:
        """Wait for and return the invocation's result without redispatching."""
        if timeout is not None and (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout < 0
        ):
            raise ValueError("timeout must be finite and nonnegative or None")
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._condition:
            while not self._done:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    raise TimeoutError("Streaming invocation has not completed")
                self._condition.wait(remaining)
            if self._error is not None:
                raise self._error
            assert self._result is not None
            return self._result

    async def aresult(self, timeout: float | None = None) -> Result[T]:
        return await asyncio.to_thread(self.result, timeout)

    def close(self) -> None:
        """Cancel an unfinished invocation and wait a bounded control interval."""
        with self._condition:
            if self._closed:
                return
            self._closed = True
            unfinished = not self._done
            if unfinished:
                self._request_cancel_locked()
            cancel_thread = self._cancel_thread
        thread = self._thread
        if not unfinished and cancel_thread is None:
            return
        deadline = time.monotonic() + self._close_timeout
        if cancel_thread is not None:
            cancel_thread.join(max(0.0, deadline - time.monotonic()))
        if unfinished and thread is not None:
            thread.join(max(0.0, deadline - time.monotonic()))
        if (cancel_thread is not None and cancel_thread.is_alive()) or (
            thread is not None and thread.is_alive()
        ):
            error = StreamCancellationUnconfirmed(
                "Streaming invocation did not stop within the control timeout; its run remains interrupted"
            )
            with self._condition:
                if self._error is None:
                    self._error = error
                self._condition.notify_all()
            raise error
        with self._condition:
            cancel_error = self._cancel_error
        if cancel_error is not None:
            raise cancel_error

    async def aclose(self) -> None:
        await asyncio.to_thread(self.close)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_):
        self.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_):
        await self.aclose()


def start_stream(
    provider: Any,
    prompt: Any,
    *,
    operation: str,
    options: Mapping[str, Any] | None = None,
    cancel: Callable[[str, str], Any] | None = None,
    max_events: int = 256,
    max_event_bytes: int = 1_000_000,
    max_buffer_bytes: int = 4 * 1024 * 1024,
    close_timeout: float = 5.0,
) -> Stream[Any]:
    """Observe exactly one public provider call in a copied context.

    The public method performs its operation-specific argument checks and then
    converges on ``Provider._invoke``; the stream does not add another execution
    path.
    """
    if operation not in {"generate", "query", "run"}:
        raise ValueError("stream operation must be generate, query, or run")
    call_options = dict(options or {})
    invoke = getattr(provider, operation)
    return Stream(
        lambda: invoke(prompt, **call_options),
        cancel=cancel,
        max_events=max_events,
        max_event_bytes=max_event_bytes,
        max_buffer_bytes=max_buffer_bytes,
        close_timeout=close_timeout,
    )


__all__ = [
    "Stream",
    "StreamEvent",
    "StreamError",
    "StreamBufferOverflow",
    "StreamCancellationUnconfirmed",
    "bind_stream_identity",
    "mark_stream_replay",
    "require_live_capability",
    "start_stream",
]
