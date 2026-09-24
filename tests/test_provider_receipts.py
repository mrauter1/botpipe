from __future__ import annotations

import json
import threading

import pytest

import botpipe.providers as providers
from botpipe.capabilities import CapabilityError
from botpipe.policy import Policy
from botpipe.providers import (
    CodexProvider,
    ProviderInterruptedError,
    ProviderPolicyError,
    ProviderRequest,
    ProviderResponse,
    receipt_path,
)


def request(tmp_path) -> ProviderRequest:
    return ProviderRequest(
        operation_id="receipt-ordering",
        prompt="work",
        workspace=tmp_path,
        session_id=None,
        output_schema=None,
        policy=Policy(),
        artifacts={},
        receipt_dir=tmp_path / "receipts",
        timeout=2,
    )


def test_concurrent_first_access_constructs_one_shared_adapter(monkeypatch):
    import botpipe.codex_appserver as appserver

    first_constructing = threading.Event()
    second_constructing = threading.Event()
    release_first = threading.Event()
    created = []

    class Adapter:
        def __init__(self, *args, **kwargs):
            created.append(self)
            if len(created) == 1:
                first_constructing.set()
                assert release_first.wait(30)
            else:
                second_constructing.set()

    monkeypatch.setattr(appserver, "CodexAppServerAdapter", Adapter)
    provider = CodexProvider()
    observed = []

    first = threading.Thread(target=lambda: observed.append(provider.adapter))
    second = threading.Thread(target=lambda: observed.append(provider.adapter))
    first.start()
    assert first_constructing.wait(30)
    second.start()
    raced = second_constructing.wait(0.2)
    release_first.set()
    first.join(timeout=30)
    second.join(timeout=30)

    assert not first.is_alive() and not second.is_alive()
    assert not raced, "adapter construction was not serialized"
    assert len(created) == 1
    assert observed == [created[0], created[0]]


def test_concurrent_checkpoint_writes_preserve_every_update(tmp_path, monkeypatch):
    first_writing = threading.Event()
    second_writing = threading.Event()
    release_first = threading.Event()
    original = providers._atomic_json

    def delayed_atomic(path, value):
        snapshot = dict(value)
        if snapshot.get("status") == "response_received" and "cleanup" not in snapshot:
            first_writing.set()
            assert release_first.wait(30)
        elif snapshot.get("cleanup") == {"status": "completed"}:
            second_writing.set()
        original(path, snapshot)

    monkeypatch.setattr(providers, "_atomic_json", delayed_atomic)

    class Adapter:
        def start_turn(self, call, on_event=None):
            assert call.on_checkpoint is not None
            first = threading.Thread(
                target=lambda: call.on_checkpoint({"status": "response_received"})
            )
            second_started = threading.Event()

            def save_cleanup():
                second_started.set()
                call.on_checkpoint({"cleanup": {"status": "completed"}})

            second = threading.Thread(target=save_cleanup)
            first.start()
            assert first_writing.wait(30)
            second.start()
            assert second_started.wait(30)
            overlapped = second_writing.wait(0.2)
            release_first.set()
            first.join(timeout=30)
            second.join(timeout=30)
            assert not first.is_alive() and not second.is_alive()
            assert not overlapped, "receipt writes were not serialized"
            raise ProviderInterruptedError("shared transport stopped")

    call = request(tmp_path)
    with pytest.raises(ProviderInterruptedError, match="shared transport stopped"):
        CodexProvider(adapter=Adapter()).run(call)

    saved = json.loads(receipt_path(call).read_text())
    assert saved["status"] == "response_received"
    assert saved["cleanup"] == {"status": "completed"}


@pytest.mark.parametrize("terminal", ["success", "policy_error"])
def test_terminal_receipt_write_waits_for_checkpoint_write(
    tmp_path, monkeypatch, terminal
):
    checkpoint_writing = threading.Event()
    terminal_writing = threading.Event()
    release_checkpoint = threading.Event()
    original = providers._atomic_json

    def delayed_atomic(path, value):
        snapshot = dict(value)
        if (
            snapshot.get("status") == "prepared"
            and snapshot.get("cleanup") == {"status": "completed"}
        ):
            checkpoint_writing.set()
            assert release_checkpoint.wait(30)
        elif snapshot.get("status") in {"completed", "failed"}:
            terminal_writing.set()
        original(path, snapshot)

    monkeypatch.setattr(providers, "_atomic_json", delayed_atomic)

    class Adapter:
        checkpoint_thread = None

        def start_turn(self, call, on_event=None):
            assert call.on_checkpoint is not None
            self.checkpoint_thread = threading.Thread(
                target=lambda: call.on_checkpoint(
                    {"cleanup": {"status": "completed"}}
                )
            )
            self.checkpoint_thread.start()
            assert checkpoint_writing.wait(30)
            if terminal == "policy_error":
                raise CapabilityError("denied")
            return ProviderResponse("done")

    adapter = Adapter()
    call = request(tmp_path)
    result = []
    errors = []

    def run():
        try:
            result.append(CodexProvider(adapter=adapter).run(call))
        except BaseException as exc:
            errors.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    assert checkpoint_writing.wait(30)
    overlapped = terminal_writing.wait(0.2)
    release_checkpoint.set()
    worker.join(timeout=30)
    assert not worker.is_alive()
    assert adapter.checkpoint_thread is not None
    adapter.checkpoint_thread.join(timeout=30)
    assert not adapter.checkpoint_thread.is_alive()
    assert not overlapped, "terminal write bypassed the receipt lock"
    assert terminal_writing.is_set()

    saved = json.loads(receipt_path(call).read_text())
    assert saved["cleanup"] == {"status": "completed"}
    if terminal == "success":
        assert not errors
        assert result == [ProviderResponse("done")]
        assert saved["status"] == "completed"
        assert saved["response"]["text"] == "done"
    else:
        assert not result
        assert len(errors) == 1 and isinstance(errors[0], ProviderPolicyError)
        assert saved["status"] == "failed"
        assert saved["error"] == "denied"
