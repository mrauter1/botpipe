from __future__ import annotations

import json
import sys
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from botpipe import Botpipe, Provider
from botpipe.capabilities import CapabilityError, CapabilityStatus, CodexCapabilities
from botpipe.codex_appserver import CodexAppServerAdapter
from botpipe.policy import NetworkMode, Policy, SandboxMode
from botpipe.providers import (
    CodexProvider,
    ProviderInterruptedError,
    ProviderRequest,
    ProviderResponse,
    receipt_path,
)
from botpipe.recovery import Completed, Stopped, Unknown, recover_outcome


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
    request = ProviderRequest(
        "interrupted",
        "answer",
        tmp_path,
        "thread",
        None,
        Policy(sandbox_mode=SandboxMode.READ_ONLY, network=NetworkMode.NONE),
        {},
        tmp_path / "receipts",
        1,
        preset=preset,
        tools=(),
    )
    path = receipt_path(request)
    path.parent.mkdir()
    path.write_text(
        json.dumps(
            {
                "operation_id": request.operation_id,
                "attempt": 1,
                "status": "turn_acknowledged",
                "session_id": "thread",
                "turn_id": "turn",
                "probe_hash": "original-probe",
                "enforcement": {
                    "sandbox": "codex:read-only",
                    "codex_version": "original-version",
                },
            }
        )
    )
    return request


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
        interrupt_grace_seconds=0.2,
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

    expected = ["thread/resume", "thread/read"]
    if status != "completed":
        expected.extend(
            [
                "thread/backgroundTerminals/clean",
                "thread/backgroundTerminals/list",
            ]
        )
    assert calls == expected
    receipt = json.loads(receipt_path(request).read_text())
    assert receipt["status"] == "failed" and receipt["policy_error"] is True
    assert receipt["enforcement"]["audit"] == "tool-policy-violation"
    assert receipt["audit"][0]["data"]["item"]["id"] == "forbidden-command"


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
    receipt = json.loads(receipt_path(request).read_text())
    assert receipt["status"] == "turn_acknowledged"
    assert receipt["enforcement"]["audit"] == "no-tool-calls-observed"
    assert receipt["audit"][0]["data"]["item"]["type"] == "agentMessage"


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
    receipt = json.loads(receipt_path(request).read_text())
    assert receipt["enforcement"]["audit"] == "no-tool-calls-observed"


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
    receipt = json.loads(receipt_path(request).read_text())
    assert receipt["enforcement"]["audit"] == "no-tool-calls-observed"


def test_recovery_waits_until_native_background_inventory_is_empty(
    tmp_path, monkeypatch
):
    request = interrupted_request(tmp_path)
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
    receipt = json.loads(receipt_path(request).read_text())
    assert receipt["cleanup"]["status"] == "incomplete"


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
    receipt = json.loads(receipt_path(request).read_text())
    assert receipt["enforcement"]["audit"] == "tool-policy-violation"


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


@pytest.mark.parametrize("native_status", ["running", "stopped"])
def test_incomplete_cleanup_blocks_retry_even_when_native_turn_is_terminal(
    tmp_path, native_status
):
    request = interrupted_request(tmp_path, preset="run")
    path = receipt_path(request)
    record = json.loads(path.read_text())
    record.update(
        status="failed",
        cleanup={"status": "incomplete", "error": "terminal cleanup failed"},
    )
    path.write_text(json.dumps(record))

    class Adapter:
        def recover_turn(self, *args, **kwargs):
            return native_status, None

    outcome = recover_outcome(CodexProvider(adapter=Adapter()), request)

    assert isinstance(outcome, Unknown)
    assert "cleanup failed" in outcome.detail


def test_incomplete_cleanup_still_allows_completed_native_adoption(tmp_path):
    request = interrupted_request(tmp_path, preset="run")
    path = receipt_path(request)
    record = json.loads(path.read_text())
    record.update(
        status="failed",
        cleanup={"status": "incomplete", "error": "terminal cleanup failed"},
    )
    path.write_text(json.dumps(record))

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
    path = receipt_path(request)
    record = json.loads(path.read_text())
    record["cleanup"] = {"status": "completed"}
    path.write_text(json.dumps(record))

    class Adapter:
        def recover_turn(self, *args, **kwargs):
            return "unknown", None

    provider = CodexProvider(adapter=Adapter())
    outcome = recover_outcome(provider, request)

    assert isinstance(outcome, Unknown)
    with pytest.raises(ProviderInterruptedError, match="refusing to resend"):
        provider.run(request)
