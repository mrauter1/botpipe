from __future__ import annotations

import dataclasses
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import botpipe.claude_sdk as claude_sdk
from botpipe.policy import OperationKind, Policy
from botpipe.providers import CapabilityError, ProviderRequest, get_provider


def _request(tmp_path: Path, **changes: Any) -> ProviderRequest:
    values = {
        "operation_id": "native-op",
        "prompt": "answer",
        "workspace": tmp_path,
        "session_id": None,
        "output_schema": None,
        "policy": Policy(model="model"),
        "artifacts": {},
        "receipt_dir": tmp_path / "receipts",
        "timeout": 10,
        "operation": OperationKind.GENERATE,
    }
    values.update(changes)
    return ProviderRequest(**values)


def _fake_claude_sdk(captured: dict[str, Any]) -> Any:
    option_names = (
        "tools allowed_tools disallowed_tools mcp_servers strict_mcp_config "
        "permission_mode cwd setting_sources skills plugins system_prompt resume "
        "model effort max_turns output_format env"
    ).split()
    options_type = dataclasses.make_dataclass(
        "ClaudeAgentOptions",
        [(name, Any, dataclasses.field(default=None)) for name in option_names],
    )

    @dataclasses.dataclass
    class Tool:
        name: str
        handler: Any

    def tool(name, _description, _schema):
        return lambda function: Tool(name, function)

    def create_sdk_mcp_server(**kwargs):
        captured["server"] = kwargs
        return {"type": "sdk", "name": kwargs["name"]}

    class ResultMessage:
        subtype = "success"
        is_error = False
        result = "native answer"
        structured_output = None
        session_id = "claude-session"
        usage = {"input_tokens": 2, "output_tokens": 3}

    class ClaudeSDKClient:
        def __init__(self, *, options):
            captured["options"] = options

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def query(self, prompt):
            captured["prompt"] = prompt

        async def receive_response(self):
            yield ResultMessage()

    return SimpleNamespace(
        ClaudeAgentOptions=options_type,
        ClaudeSDKClient=ClaudeSDKClient,
        create_sdk_mcp_server=create_sdk_mcp_server,
        tool=tool,
    )


def test_claude_sdk_tool_free_generate_closes_every_inventory_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}
    sdk = _fake_claude_sdk(captured)
    monkeypatch.setattr(claude_sdk.importlib.metadata, "version", lambda _name: claude_sdk.SDK_VERSION)
    monkeypatch.setattr(claude_sdk.importlib, "import_module", lambda _name: sdk)
    adapter = claude_sdk.ClaudeSDKProvider()

    response = adapter.run(_request(tmp_path, instructions="system"))

    assert response.text == "native answer"
    options = captured["options"]
    assert options.tools == []
    assert options.allowed_tools == []
    assert options.mcp_servers == {}
    assert options.strict_mcp_config is True
    assert options.setting_sources == []
    assert options.skills == []
    assert options.plugins == []
    assert options.permission_mode == "dontAsk"
    assert options.system_prompt == "system"
    assert options.max_turns == claude_sdk.TOOL_CALL_LIMIT


def test_claude_sdk_version_rejects_before_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(claude_sdk.importlib.metadata, "version", lambda _name: "0.2.154")
    adapter = claude_sdk.ClaudeSDKProvider()

    with pytest.raises(CapabilityError, match="0.2.155"):
        adapter.run(_request(tmp_path))

    assert not (tmp_path / "receipts").exists()


def test_native_interface_selection_is_explicit_and_versioned() -> None:
    assert get_provider("claude", {"interface": "agent_sdk"}).capabilities.version == (
        "claude-agent-sdk-0.2.155"
    )
    assert get_provider("pi", {"interface": "agent_sdk"}).capabilities.version == (
        "pi-agent-sdk-0.73.1"
    )
    with pytest.raises(ValueError, match="interface"):
        get_provider("pi", {"interface": "unknown"})
