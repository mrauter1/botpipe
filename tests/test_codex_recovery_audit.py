from __future__ import annotations

import sys
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from botpipe import Botpipe, Provider, codec
from botpipe.capabilities import CapabilityError, CapabilityStatus, CodexCapabilities
from botpipe.codex_appserver import CodexAppServerAdapter
from botpipe.policy import NetworkMode, Policy, SandboxMode
from botpipe.providers import (
    CodexProvider,
    ProviderRequest,
    ProviderResponse,
)
from botpipe.recovery import Completed, Stopped, Unknown, recover_outcome
from botpipe.session_bindings import SessionBinding


def capabilities() -> CodexCapabilities:
    return CodexCapabilities(
        executable=sys.executable,
        version="fixture-version",
        identity="fixture-probe",
        methods=frozenset(
            {
                "thread/read",
                "thread/backgroundTerminals/clean",
                "thread/backgroundTerminals/list",
            }
        ),
        features=({"name": "shell_tool", "enabled": True},),
        presets={name: CapabilityStatus(True) for name in ("run", "query", "generate")},
        item_types=frozenset({"agentMessage", "commandExecution"}),
    )


def interrupted_request(tmp_path: Path, *, preset: str = "generate") -> ProviderRequest:
    checkpoint = {
        "status": "turn_acknowledged",
        "session_id": "thread",
        "turn_id": "turn",
        "probe_hash": "original-probe",
        "enforcement": {
            "sandbox": "codex:read-only",
            "codex_version": "original-version",
        },
    }

    def save(update: dict) -> None:
        checkpoint.update(update)

    return ProviderRequest(
        operation_id="interrupted",
        prompt="answer",
        workspace=tmp_path,
        session_id="thread",
        output_schema=None,
        policy=Policy(sandbox_mode=SandboxMode.READ_ONLY, network=NetworkMode.NONE),
        artifacts={},
        timeout=1,
        session_key="test:interrupted",
        preset=preset,
        tools=(),
        checkpoint=checkpoint,
        on_checkpoint=save,
    )


def history_adapter(
    monkeypatch: pytest.MonkeyPatch, *, tools: bool, status: str = "completed"
):
    adapter = CodexAppServerAdapter("unused", capabilities=capabilities())
    calls = []

    def rpc(method, params, timeout, *args, **kwargs):
        calls.append(method)
        if method == "thread/backgroundTerminals/clean":
            return {}
        if method == "thread/backgroundTerminals/list":
            return {"data": [], "nextCursor": None}
        items = [{"type": "agentMessage", "text": "recovered answer"}]
        if tools:
            items.insert(0, {"type": "commandExecution", "id": "forbidden-command"})
        return {
            "thread": {"turns": [{"id": "turn", "status": status, "items": items}]}
        }

    monkeypatch.setattr(adapter, "_start", lambda **kwargs: None)
    monkeypatch.setattr(adapter, "_rpc", rpc)
    return adapter, calls


def running_history_adapter(
    monkeypatch: pytest.MonkeyPatch,
    *,
    terminal: str,
    supports_background_cleanup: bool = True,
    background_lists: list[object] | None = None,
):
    methods = {"thread/read", "turn/interrupt"}
    if supports_background_cleanup:
        methods.update(
            {
                "thread/backgroundTerminals/clean",
                "thread/backgroundTerminals/list",
            }
        )
    adapter = CodexAppServerAdapter(
        "unused",
        capabilities=replace(
            capabilities(), methods=frozenset(methods), supports_interrupt=True
        ),
        interrupt_grace_seconds=2,
    )
    calls = []
    reads = 0

    def rpc(method, params, timeout, *args, **kwargs):
        nonlocal reads
        calls.append(method)
        if method == "thread/read":
            reads += 1
            status = "inProgress" if reads == 1 else terminal
            items = (
                [{"type": "agentMessage", "text": "recovered answer"}]
                if status == "completed"
                else []
            )
            return {
                "thread": {
                    "turns": [{"id": "turn", "status": status, "items": items}]
                }
            }
        if method == "thread/backgroundTerminals/list":
            value = background_lists.pop(0) if background_lists else []
            if isinstance(value, dict):
                return value
            return {"data": value, "nextCursor": None}
        return {}

    monkeypatch.setattr(adapter, "_start", lambda **kwargs: None)
    monkeypatch.setattr(adapter, "_rpc", rpc)
    return adapter, calls


@pytest.mark.parametrize("status", ["completed", "failed", "interrupted", "cancelled"])
def test_recovered_disallowed_tool_is_terminal_and_keeps_evidence(
    tmp_path, monkeypatch, status
):
    request = interrupted_request(tmp_path)
    adapter, calls = history_adapter(monkeypatch, tools=True, status=status)
    provider = CodexProvider(adapter=adapter)

    for _ in range(2):
        with pytest.raises(CapabilityError, match="disallowed tool 'shell'"):
            recover_outcome(provider, request)

    expected = [
        "thread/resume",
        "thread/read",
        "thread/backgroundTerminals/clean",
        "thread/backgroundTerminals/list",
    ]
    assert calls == expected
    checkpoint = request.checkpoint
    assert checkpoint is not None
    assert checkpoint["status"] == "failed" and checkpoint["policy_error"] is True
    assert checkpoint["cleanup"] == {"status": "completed"}
    assert checkpoint["enforcement"]["audit"] == "tool-policy-violation"
    assert checkpoint["audit"][0]["data"]["item"]["id"] == "forbidden-command"


@pytest.mark.parametrize("status", ["failed", "interrupted", "cancelled"])
def test_recovered_clean_terminal_turn_is_stopped_with_audit(
    tmp_path, monkeypatch, status
):
    request = interrupted_request(tmp_path)
    adapter, calls = history_adapter(monkeypatch, tools=False, status=status)

    outcome = recover_outcome(CodexProvider(adapter=adapter), request)

    assert isinstance(outcome, Stopped)
    assert calls == [
        "thread/resume",
        "thread/read",
        "thread/backgroundTerminals/clean",
        "thread/backgroundTerminals/list",
    ]
    checkpoint = request.checkpoint
    assert checkpoint is not None
    assert checkpoint["status"] == "failed"
    assert checkpoint["cleanup"] == {"status": "completed"}
    assert checkpoint["disposal"] == {"status": "pending"}
    assert checkpoint["enforcement"]["audit"] == "no-tool-calls-observed"
    assert checkpoint["audit"][0]["data"]["item"]["type"] == "agentMessage"


def test_recovery_invalidates_exit_evidence_before_start(tmp_path, monkeypatch):
    request = interrupted_request(tmp_path)
    request.checkpoint["disposal"] = {"status": "completed"}
    adapter, _ = history_adapter(monkeypatch, tools=False, status="failed")

    def crash_at_start(**kwargs):
        assert request.checkpoint["disposal"] == {"status": "pending"}
        raise SystemExit("recovery startup interrupted")

    monkeypatch.setattr(adapter, "_start", crash_at_start)
    with pytest.raises(SystemExit, match="recovery startup interrupted"):
        adapter.recover_turn(request, thread_id="thread", turn_id="turn")
    assert request.checkpoint["disposal"] == {"status": "pending"}


def test_recovery_requires_durable_invalidation_before_start(tmp_path, monkeypatch):
    request = interrupted_request(tmp_path)
    adapter, _ = history_adapter(monkeypatch, tools=False, status="failed")

    def reject_checkpoint(update):
        raise OSError("ledger unavailable")

    def unexpected_start(**kwargs):
        pytest.fail("server started before its exit evidence was invalidated")

    monkeypatch.setattr(adapter, "_start", unexpected_start)
    request = replace(request, on_checkpoint=reject_checkpoint)
    with pytest.raises(OSError, match="ledger unavailable"):
        adapter.recover_turn(request, thread_id="thread", turn_id="turn")


def test_recovered_safe_result_keeps_audit_and_original_enforcement(
    tmp_path, monkeypatch
):
    request = interrupted_request(tmp_path)
    adapter, _ = history_adapter(monkeypatch, tools=False)
    outcome = recover_outcome(CodexProvider(adapter=adapter), request)

    assert isinstance(outcome, Completed)
    assert outcome.response.text == "recovered answer"
    metadata = outcome.response.metadata
    assert metadata["probe_hash"] == "original-probe"
    assert metadata["codex_version"] == "original-version"
    assert metadata["enforcement"]["sandbox"] == "codex:read-only"
    assert metadata["enforcement"]["audit"] == "no-tool-calls-observed"
    assert metadata["audit"][0]["data"]["item"]["type"] == "agentMessage"


def test_running_recovery_interrupts_then_completed_history_wins(
    tmp_path, monkeypatch
):
    request = interrupted_request(tmp_path)
    adapter, calls = running_history_adapter(monkeypatch, terminal="completed")

    outcome = recover_outcome(CodexProvider(adapter=adapter), request)

    assert isinstance(outcome, Completed)
    assert outcome.response.text == "recovered answer"
    assert calls == ["thread/resume", "thread/read", "turn/interrupt", "thread/read"]


def test_running_recovery_requires_background_cleanup_before_stopped(
    tmp_path, monkeypatch
):
    request = interrupted_request(tmp_path)
    adapter, calls = running_history_adapter(monkeypatch, terminal="interrupted")

    outcome = recover_outcome(CodexProvider(adapter=adapter), request)

    assert isinstance(outcome, Stopped)
    assert calls == [
        "thread/resume",
        "thread/read",
        "turn/interrupt",
        "thread/read",
        "thread/backgroundTerminals/clean",
        "thread/backgroundTerminals/list",
    ]
    checkpoint = request.checkpoint
    assert checkpoint is not None
    assert checkpoint["enforcement"]["audit"] == "no-tool-calls-observed"


def test_running_recovery_without_background_cleanup_stays_unknown(
    tmp_path, monkeypatch
):
    request = interrupted_request(tmp_path)
    adapter, _ = running_history_adapter(
        monkeypatch,
        terminal="interrupted",
        supports_background_cleanup=False,
    )

    outcome = recover_outcome(CodexProvider(adapter=adapter), request)

    assert isinstance(outcome, Unknown)
    checkpoint = request.checkpoint
    assert checkpoint is not None
    assert checkpoint["enforcement"]["audit"] == "no-tool-calls-observed"


def test_recovery_waits_until_native_background_inventory_is_empty(
    tmp_path, monkeypatch
):
    request = replace(interrupted_request(tmp_path), timeout=5)
    adapter, calls = running_history_adapter(
        monkeypatch,
        terminal="interrupted",
        background_lists=[[{"processId": "still-running"}], []],
    )

    outcome = recover_outcome(CodexProvider(adapter=adapter), request)

    assert isinstance(outcome, Stopped)
    assert calls.count("thread/backgroundTerminals/list") == 2


def test_recovery_checks_every_background_inventory_page(tmp_path, monkeypatch):
    request = interrupted_request(tmp_path)
    adapter, calls = running_history_adapter(
        monkeypatch,
        terminal="interrupted",
        background_lists=[
            {"data": [], "nextCursor": "page-2"},
            {"data": [], "nextCursor": None},
        ],
    )

    outcome = recover_outcome(CodexProvider(adapter=adapter), request)

    assert isinstance(outcome, Stopped)
    assert calls.count("thread/backgroundTerminals/list") == 2


@pytest.mark.parametrize(
    "inventory",
    [
        {"data": "invalid", "nextCursor": None},
        {"data": [], "nextCursor": 7},
    ],
)
def test_invalid_background_inventory_stays_unknown(
    tmp_path, monkeypatch, inventory
):
    request = interrupted_request(tmp_path)
    adapter, _ = running_history_adapter(
        monkeypatch,
        terminal="interrupted",
        background_lists=[inventory],
    )

    outcome = recover_outcome(CodexProvider(adapter=adapter), request)

    assert isinstance(outcome, Unknown)
    checkpoint = request.checkpoint
    assert checkpoint is not None
    assert checkpoint["cleanup"]["status"] == "incomplete"


def test_cancelled_recovery_does_not_claim_terminal_cleanup(tmp_path, monkeypatch):
    request = interrupted_request(tmp_path)
    cancelled = threading.Event()
    cancelled.set()
    request = replace(request, cancel_event=cancelled)
    adapter, calls = history_adapter(
        monkeypatch, tools=False, status="interrupted"
    )

    outcome = recover_outcome(CodexProvider(adapter=adapter), request)

    assert isinstance(outcome, Unknown)
    assert "thread/backgroundTerminals/clean" not in calls


@pytest.mark.parametrize("status", ["completed", "failed", "interrupted", "cancelled"])
def test_recovered_run_policy_violation_remains_unresolved(
    tmp_path, monkeypatch, status
):
    request = interrupted_request(tmp_path, preset="run")
    adapter, _ = history_adapter(monkeypatch, tools=True, status=status)
    outcome = recover_outcome(CodexProvider(adapter=adapter), request)

    assert isinstance(outcome, Unknown)
    assert "disallowed tool" in outcome.detail
    checkpoint = request.checkpoint
    assert checkpoint is not None
    assert checkpoint["enforcement"]["audit"] == "tool-policy-violation"


def test_sdk_native_audit_violation_fails_without_becoming_unresolved(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "codex_appserver.py"
    adapter = CodexAppServerAdapter(
        (sys.executable, str(fixture)),
        env={
            "BOTPIPE_FAKE_SCENARIO": "disallowed_shell",
            "BOTPIPE_FAKE_TRANSCRIPT": str(tmp_path / "transcript.jsonl"),
        },
        capabilities=capabilities(),
        interrupt_grace_seconds=0.1,
    )
    with Botpipe(
        tmp_path, provider=CodexProvider(adapter=adapter), state_dir=tmp_path / "state"
    ) as runtime:
        with pytest.raises(CapabilityError, match="disallowed tool 'shell'") as caught:
            Provider(runtime=runtime).generate("answer")
        row = runtime.journal.get(caught.value.operation_id)
        assert row["status"] == "failed"
        assert row["enforcement"]["audit"] == "tool-policy-violation"
        session_key = codec.decode(row["inputs"])["session"]
        assert SessionBinding(runtime.journal, session_key).read()["pending"] is None
        assert any(
            event["event"] == "provider_call_finished"
            and event.get("operation_id") == row["id"]
            and event["data"]["outcome"] == "policy_failed"
            for event in runtime.journal.events(caught.value.run_id)
        )


def test_independent_terminal_policy_failure_releases_cached_owner(tmp_path):
    class Adapter:
        def __init__(self):
            self.closes = 0

        def probe(self, *, deadline=None):
            return capabilities()

        def start_turn(self, request, on_event=None):
            request.on_checkpoint({"status": "turn_intent"})
            request.on_checkpoint({
                "status": "failed",
                "cleanup": {"status": "completed"},
            })
            raise CapabilityError("disallowed tool")

        def close(self):
            self.closes += 1

    adapter = Adapter()
    backend = CodexProvider(adapter=adapter)
    with Botpipe(tmp_path, provider=backend) as runtime:
        with pytest.raises(CapabilityError, match="disallowed tool"):
            Provider(runtime=runtime, session=None).generate("answer")

        assert backend._owners == {}
        assert adapter.closes == 1


@pytest.mark.parametrize("native_status", ["running", "stopped"])
def test_incomplete_cleanup_blocks_retry_even_when_native_turn_is_terminal(
    tmp_path, native_status
):
    request = interrupted_request(tmp_path, preset="run")
    assert request.checkpoint is not None
    request.checkpoint.update(
        status="failed",
        cleanup={"status": "incomplete", "error": "terminal cleanup failed"},
    )

    class Adapter:
        def recover_turn(self, *args, **kwargs):
            return native_status, None

    outcome = recover_outcome(CodexProvider(adapter=Adapter()), request)

    assert isinstance(outcome, Unknown)
    assert "cleanup failed" in outcome.detail


def test_checkpointed_policy_failure_with_incomplete_cleanup_is_resolvable(tmp_path):
    request = interrupted_request(tmp_path)
    assert request.checkpoint is not None
    request.checkpoint.update(
        status="failed",
        policy_error=True,
        error="disallowed tool",
        cleanup={"status": "incomplete", "error": "cleanup is unverified"},
    )

    outcome = recover_outcome(CodexProvider(adapter=object()), request)

    assert isinstance(outcome, Unknown)
    assert outcome.detail == "cleanup is unverified"


def test_incomplete_cleanup_still_allows_completed_native_adoption(tmp_path):
    request = interrupted_request(tmp_path, preset="run")
    assert request.checkpoint is not None
    request.checkpoint.update(
        status="failed",
        cleanup={"status": "incomplete", "error": "terminal cleanup failed"},
    )

    class Adapter:
        def recover_turn(self, *args, **kwargs):
            return "completed", ProviderResponse("adopted", "thread")

    outcome = recover_outcome(CodexProvider(adapter=Adapter()), request)

    assert isinstance(outcome, Completed)
    assert outcome.response.text == "adopted"


def test_completed_cleanup_with_unknown_history_stays_unknown_and_is_not_resent(
    tmp_path,
):
    request = interrupted_request(tmp_path, preset="run")
    assert request.checkpoint is not None
    request.checkpoint["cleanup"] = {"status": "completed"}

    class Adapter:
        def recover_turn(self, *args, **kwargs):
            return "unknown", None

    outcome = recover_outcome(CodexProvider(adapter=Adapter()), request)

    assert isinstance(outcome, Unknown)
