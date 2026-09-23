from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from botpipe import Botpipe, Provider
from botpipe.capabilities import CapabilityError, CapabilityStatus, CodexCapabilities
from botpipe.codex_appserver import CodexAppServerAdapter
from botpipe.policy import NetworkMode, Policy, SandboxMode
from botpipe.providers import CodexProvider, ProviderRequest, receipt_path
from botpipe.recovery import Completed, Unknown, recover_outcome


def capabilities() -> CodexCapabilities:
    return CodexCapabilities(
        executable=sys.executable,
        version="fixture-version",
        identity="fixture-probe",
        methods=frozenset({"thread/read"}),
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


def history_adapter(monkeypatch: pytest.MonkeyPatch, *, tools: bool):
    adapter = CodexAppServerAdapter("unused", capabilities=capabilities())
    calls = []

    def rpc(method, params, timeout):
        calls.append(method)
        items = [{"type": "agentMessage", "text": "recovered answer"}]
        if tools:
            items.insert(0, {"type": "commandExecution", "id": "forbidden-command"})
        return {
            "thread": {"turns": [{"id": "turn", "status": "completed", "items": items}]}
        }

    monkeypatch.setattr(adapter, "_start", lambda: None)
    monkeypatch.setattr(adapter, "_rpc", rpc)
    return adapter, calls


def test_recovered_disallowed_tool_is_terminal_and_keeps_evidence(
    tmp_path, monkeypatch
):
    request = interrupted_request(tmp_path)
    adapter, calls = history_adapter(monkeypatch, tools=True)
    provider = CodexProvider(adapter=adapter)

    for _ in range(2):
        with pytest.raises(CapabilityError, match="disallowed tool 'shell'"):
            recover_outcome(provider, request)

    assert calls == ["thread/resume", "thread/read"]
    receipt = json.loads(receipt_path(request).read_text())
    assert receipt["status"] == "failed" and receipt["policy_error"] is True
    assert receipt["enforcement"]["audit"] == "tool-policy-violation"
    assert receipt["audit"][0]["data"]["item"]["id"] == "forbidden-command"


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


def test_recovered_run_policy_violation_remains_unresolved(tmp_path, monkeypatch):
    request = interrupted_request(tmp_path, preset="run")
    adapter, _ = history_adapter(monkeypatch, tools=True)
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
