"""Late messages and cleanup records must not keep or affect replaced transports."""

import gc
import io
import threading
import weakref

import pytest

from botpipe.capabilities import CodexCapabilities
from botpipe.codex_appserver import CodexAppServerAdapter, CodexProtocolError, _Turn


class MemoryProcess:
    def __init__(self):
        self.stdin = io.BytesIO()
        self.alive = True

    def poll(self):
        return None if self.alive else 0


def adapter():
    return CodexAppServerAdapter(
        ["unused"],
        capabilities=CodexCapabilities(
            executable="unused", version="fixture", identity="fixture", methods=frozenset()
        ),
    )


def receive_in_thread(client, message, process):
    errors = []

    def receive():
        try:
            client._receive(message, process=process)
        except BaseException as exc:
            errors.append(exc)

    worker = threading.Thread(target=receive)
    worker.start()
    return worker, errors


@pytest.mark.parametrize(
    "method",
    ["applyPatchApproval", "item/permissions/requestApproval", "item/tool/call"],
)
def test_late_server_reply_never_reaches_replacement(monkeypatch, method):
    client = adapter()
    old, replacement = MemoryProcess(), MemoryProcess()
    client._process = old
    answering, release = threading.Event(), threading.Event()
    answer = client._answer_server_request

    def delay_answer(*args, **kwargs):
        answering.set()
        assert release.wait(30)
        answer(*args, **kwargs)

    monkeypatch.setattr(client, "_answer_server_request", delay_answer)
    worker, errors = receive_in_thread(
        client, {"id": 7, "method": method, "params": {}}, old
    )
    try:
        assert answering.wait(30)
        with client._lock:
            client._process = replacement
    finally:
        release.set()
        worker.join(timeout=30)

    assert not worker.is_alive()
    assert all(isinstance(error, CodexProtocolError) for error in errors)
    assert replacement.stdin.getvalue() == b""


@pytest.mark.parametrize("active_turn", [False, True], ids=["orphan", "active-turn"])
def test_late_notification_cannot_enter_replacement_history(active_turn):
    client = adapter()
    old, replacement = MemoryProcess(), MemoryProcess()
    client._process = old
    parsing, release = threading.Event(), threading.Event()

    class DelayedMessage(dict):
        def get(self, key, default=None):
            if key == "params":
                parsing.set()
                assert release.wait(30)
            return super().get(key, default)

    message = DelayedMessage(
        method="item/started",
        params={
            "threadId": "shared-history",
            "turnId": "old-turn",
            "item": {"type": "commandExecution", "id": "old-command"},
        },
    )
    new_turn = _Turn("shared-history", "new-turn", (), None, process=replacement)
    worker, errors = receive_in_thread(client, message, old)
    try:
        assert parsing.wait(30)
        with client._lock:
            client._process = replacement
            if active_turn:
                client._turns[(new_turn.thread_id, new_turn.turn_id)] = new_turn
    finally:
        release.set()
        worker.join(timeout=30)

    assert not worker.is_alive()
    assert not errors
    assert new_turn.error is None
    assert new_turn.events == []
    assert client._orphan_events == {}


def test_failed_cleanup_does_not_retain_replaced_process_or_turn():
    client = adapter()

    class FailedContainment:
        def capture_descendant_groups(self, process):
            pass

        def terminate(self, process, *, grace_seconds):
            process.alive = False

        def ensure_tree_exited(self, process, *, grace_seconds):
            raise RuntimeError("descendant cleanup could not be verified")

    class Checkpoints:
        def __call__(self, update):
            pass

    def stop_and_replace():
        process = MemoryProcess()
        checkpoints = Checkpoints()
        turn = _Turn("thread", "turn", None, None, checkpoints, process=process)
        process_ref, checkpoint_ref = weakref.ref(process), weakref.ref(checkpoints)
        client._process = process
        client._containment = FailedContainment()
        client._turns[(turn.thread_id, turn.turn_id)] = turn
        try:
            client._kill_transport(CodexProtocolError("stopped"), cleanup_seconds=0)
        except CodexProtocolError as exc:
            assert "cleanup could not be verified" in str(exc)
        else:
            pytest.fail("unverified cleanup must remain an error")
        client._process = MemoryProcess()
        client._containment = None
        client._tearing_down_process = None
        client._turns.clear()
        return process_ref, checkpoint_ref

    process_ref, checkpoint_ref = stop_and_replace()
    gc.collect()
    assert process_ref() is None
    assert checkpoint_ref() is None


def test_cached_failed_cleanup_remains_unverified_after_replacement():
    client = adapter()
    old, replacement = MemoryProcess(), MemoryProcess()

    class FailedContainment:
        def capture_descendant_groups(self, process):
            pass

        def terminate(self, process, *, grace_seconds):
            process.alive = False

        def ensure_tree_exited(self, process, *, grace_seconds):
            raise RuntimeError("descendant cleanup could not be verified")

    client._process = old
    client._containment = FailedContainment()
    with pytest.raises(CodexProtocolError, match="cleanup could not be verified"):
        client._kill_transport(CodexProtocolError("stopped"), cleanup_seconds=0)

    client._process = replacement
    client._tearing_down_process = None
    with pytest.raises(CodexProtocolError, match="cleanup could not be verified"):
        client._kill_transport(CodexProtocolError("late caller"), expected_process=old)
    assert replacement.alive


def test_replacement_start_does_not_suppress_cleanup_checkpoint_failure(monkeypatch):
    client = adapter()
    old = MemoryProcess()
    old.alive = False

    class EmptyContainment:
        def capture_descendant_groups(self, process):
            pass

        def ensure_tree_exited(self, process, *, grace_seconds):
            pass

    def fail_checkpoint(update):
        raise RuntimeError("receipt write failed")

    def unexpected_probe(**kwargs):
        pytest.fail("replacement startup ignored a checkpoint write failure")

    client._process = old
    client._containment = EmptyContainment()
    client._pre_exit_captured.add(old)
    client._turns[("thread", "turn")] = _Turn(
        "thread", "turn", None, None, fail_checkpoint, process=old
    )
    monkeypatch.setattr(client, "probe", unexpected_probe)
    with pytest.raises(CodexProtocolError, match="receipt write failed"):
        client._start()
