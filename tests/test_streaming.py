"""Streaming stays an observation surface over one coordinator invocation."""

import asyncio
import contextvars
import threading
from dataclasses import replace

import pytest

from botpipe.artifacts import ArtifactMap
from botpipe import Botpipe, Provider
from botpipe.models import Result
from botpipe.providers import FakeProvider, _NATIVE_EVENT_SINK
from botpipe.streaming import (
    Stream,
    StreamBufferOverflow,
    StreamCancellationUnconfirmed,
    bind_stream_identity,
    mark_stream_replay,
    require_live_capability,
    start_stream,
)


def result(value="done", run_id="run-1", operation_id="run-1:root:0"):
    return Result(value, ArtifactMap(), run_id=run_id, operation_id=operation_id)


def test_ordered_native_events_keep_payload_and_result_does_not_redispatch():
    calls = 0
    payloads = [
        {"type": "message_start", "vendor": {"index": 1}},
        {"type": "text_delta", "delta": "hello", "unknown": [1, 2]},
        {"event": "message_end", "usage": {"output_tokens": 1}},
    ]

    def invoke():
        nonlocal calls
        calls += 1
        bind_stream_identity("run-1", "run-1:root:0")
        sink = _NATIVE_EVENT_SINK.get()
        assert sink is not None
        for payload in payloads:
            sink(payload)
        return result()

    stream = Stream(invoke)
    events = list(stream)

    assert [event.sequence for event in events] == [0, 1, 2]
    assert [event.type for event in events] == [
        "message_start",
        "text_delta",
        "message_end",
    ]
    assert [event.native for event in events] == payloads
    assert all(event.run_id == "run-1" for event in events)
    assert all(event.operation_id == "run-1:root:0" for event in events)
    assert stream.result().value == stream.result().value == "done"
    assert calls == 1


def test_start_stream_calls_exact_invoke_once_and_copies_caller_context(monkeypatch):
    marker = contextvars.ContextVar("stream-test-marker", default="missing")
    marker.set("caller")
    copied = 0
    original = contextvars.copy_context

    def copy_once():
        nonlocal copied
        copied += 1
        return original()

    monkeypatch.setattr("botpipe.streaming.contextvars.copy_context", copy_once)

    class Provider:
        def __init__(self):
            self.calls = []

        def query(self, prompt, **options):
            operation = "query"
            self.calls.append((operation, prompt, options, marker.get()))
            bind_stream_identity("r", "o")
            return result("value", "r", "o")

    provider = Provider()
    stream = start_stream(
        provider,
        "prompt",
        operation="query",
        options={"reads": ("evidence.txt",)},
    )

    assert list(stream) == []
    assert stream.result().value == "value"
    assert provider.calls == [
        ("query", "prompt", {"reads": ("evidence.txt",)}, "caller")
    ]
    assert copied == 1


def test_replay_is_explicit_and_has_no_invented_live_events():
    def invoke():
        mark_stream_replay("saved-run", "saved-operation")
        return result("saved", "saved-run", "saved-operation")

    stream = Stream(invoke)

    assert list(stream) == []
    assert stream.replayed is True
    assert stream.result().value == "saved"
    assert stream.run_id == "saved-run"
    assert stream.operation_id == "saved-operation"


def test_early_context_exit_requests_cancel_and_joins_worker():
    started = threading.Event()
    release = threading.Event()
    cancelled = []

    def invoke():
        bind_stream_identity("run-cancel", "operation-cancel")
        started.set()
        assert release.wait(2)
        return result("stopped", "run-cancel", "operation-cancel")

    def cancel(run_id, operation_id):
        cancelled.append((run_id, operation_id))
        release.set()

    with Stream(invoke, cancel=cancel, close_timeout=1) as stream:
        assert started.wait(1)

    assert cancelled == [("run-cancel", "operation-cancel")]
    assert stream.done
    assert stream.result().value == "stopped"


def test_bounded_buffer_overflow_is_explicit_and_requests_cancel():
    cancelled = threading.Event()

    def invoke():
        bind_stream_identity("overflow-run", "overflow-operation")
        sink = _NATIVE_EVENT_SINK.get()
        assert sink is not None
        sink({"type": "delta", "n": 1})
        sink({"type": "delta", "n": 2})
        return result("terminal", "overflow-run", "overflow-operation")

    stream = Stream(
        invoke,
        cancel=lambda *_: cancelled.set(),
        max_events=1,
        close_timeout=1,
    )

    first = next(stream)
    assert first.native["n"] == 1
    with pytest.raises(StreamBufferOverflow, match="exceeded 1"):
        next(stream)
    assert cancelled.wait(1)
    with pytest.raises(StreamBufferOverflow):
        stream.result()


def test_async_iteration_and_context_manager_use_the_same_terminal_result():
    release = threading.Event()

    def invoke():
        bind_stream_identity("async-run", "async-operation")
        sink = _NATIVE_EVENT_SINK.get()
        assert sink is not None
        sink({"type": "delta", "text": "one"})
        release.wait(1)
        return result("async-result", "async-run", "async-operation")

    async def consume():
        async with Stream(invoke) as stream:
            events = []
            async for event in stream:
                events.append(event)
                release.set()
            terminal = await stream.aresult()
        return events, terminal

    events, terminal = asyncio.run(consume())
    assert [event.native["text"] for event in events] == ["one"]
    assert terminal.value == "async-result"


def test_invocation_error_follows_already_observed_events():
    failure = ValueError("native failure")

    def invoke():
        bind_stream_identity("failed-run", "failed-operation")
        sink = _NATIVE_EVENT_SINK.get()
        assert sink is not None
        sink({"type": "diagnostic", "message": "before failure"})
        raise failure

    stream = Stream(invoke)
    assert next(stream).type == "diagnostic"
    with pytest.raises(ValueError, match="native failure"):
        next(stream)
    with pytest.raises(ValueError, match="native failure"):
        stream.result()
    assert stream.run_id == "failed-run"
    assert stream.operation_id == "failed-operation"


@pytest.mark.parametrize("operation", ["generate", "query", "run"])
def test_public_provider_stream_matches_normal_coordinator_result(tmp_path, operation):
    class LiveFake(FakeProvider):
        capabilities = replace(
            FakeProvider.capabilities, live_streaming=True, cancellation=True
        )

        def run(self, request):
            sink = _NATIVE_EVENT_SINK.get()
            if sink is not None:
                sink({"type": "native_delta", "vendor_field": {"text": "live"}})
            return super().run(request)

    native = LiveFake(["terminal response", "terminal response"])
    with Botpipe(tmp_path, provider=native) as runtime:
        stream = Provider(runtime=runtime).stream(
            "say it", operation=operation
        )
        events = list(stream)
        terminal = stream.result()
        normal = getattr(Provider(runtime=runtime), operation)("say it")

    assert len(native.calls) == 2
    assert [event.type for event in events] == ["native_delta"]
    assert events[0].native == {
        "type": "native_delta",
        "vendor_field": {"text": "live"},
    }
    assert events[0].run_id == terminal.run_id == stream.run_id
    assert events[0].operation_id == terminal.operation_id == stream.operation_id
    assert terminal.value == normal.value == "terminal response"


def test_live_capability_gate_only_applies_to_active_fresh_stream():
    adapter = FakeProvider([])
    require_live_capability(adapter)  # ordinary and replayed calls remain readable

    def invoke():
        require_live_capability(adapter)
        raise AssertionError("unreachable")

    stream = Stream(invoke)
    with pytest.raises(Exception, match="does not provide live streaming"):
        stream.result()


def test_unsupported_profile_fails_before_native_dispatch(tmp_path):
    native = FakeProvider(["must remain unused"])
    with Botpipe(tmp_path, provider=native) as runtime:
        stream = Provider(runtime=runtime).stream("prompt", operation="generate")
        with pytest.raises(Exception, match="does not provide live streaming"):
            stream.result()
    assert native.calls == []


def test_terminal_response_without_native_events_is_not_called_a_live_delta(tmp_path):
    class QuietLiveFake(FakeProvider):
        capabilities = replace(FakeProvider.capabilities, live_streaming=True)

    native = QuietLiveFake(["only terminal"])
    with Botpipe(tmp_path, provider=native) as runtime:
        stream = Provider(runtime=runtime).stream("prompt", operation="generate")
        assert list(stream) == []
        assert stream.result().value == "only terminal"
    assert len(native.calls) == 1


def test_close_raises_when_worker_cannot_be_confirmed_stopped():
    started = threading.Event()
    release = threading.Event()

    def invoke():
        bind_stream_identity("uncertain-run", "uncertain-operation")
        started.set()
        release.wait(2)
        return result("late", "uncertain-run", "uncertain-operation")

    stream = Stream(invoke, cancel=lambda *_: None, close_timeout=0.02)
    assert started.wait(1)
    try:
        with pytest.raises(StreamCancellationUnconfirmed, match="remains interrupted"):
            stream.close()
    finally:
        release.set()
