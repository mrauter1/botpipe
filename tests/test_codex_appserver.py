from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from botpipe.codex_appserver import (
    AUDITED_CONFIG_OVERRIDES,
    PINNED_CODEX_VERSION,
    CodexAppServerBridge,
    CodexAppServerCapabilityError,
    CodexAppServerProtocolError,
    CodexAppServerProvider,
    CodexAppServerSession,
    DynamicTool,
    tool_fingerprint,
)
from botpipe.native_tools import ToolObservation
from botpipe.policy import OperationKind, Policy
from botpipe.providers import CapabilityError, ProviderRequest, receipt_path
from botpipe.recovery import Completed, Unknown


def tool() -> DynamicTool:
    return DynamicTool(
        "read_file",
        "Read one root-confined file through the Botpipe mediator.",
        {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    )


def stub(
    tmp_path: Path,
    *,
    unexpected_request: bool = False,
    tool_name: str = "read_file",
    namespace: str | None = None,
    arguments: dict[str, object] | None = None,
    resume: bool = False,
) -> tuple[str, ...]:
    transcript = tmp_path / "transcript.jsonl"
    script = tmp_path / "app_server.py"
    arguments = arguments or {"path": "README.md"}
    script.write_text(
        f"""import json, pathlib, sys
out = pathlib.Path({str(transcript)!r})
def receive():
    value = json.loads(sys.stdin.readline())
    with out.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(value, sort_keys=True) + '\\n')
    return value
def send(value):
    print(json.dumps(value), flush=True)

request = receive()
assert request['method'] == 'initialize'
send({{'id': request['id'], 'result': {{'userAgent': 'stub', 'codexHome': '/tmp/codex', 'platformFamily': 'unix', 'platformOs': 'linux'}}}})
assert receive()['method'] == 'initialized'
request = receive()
assert request['method'] == 'config/read'
send({{'id': request['id'], 'result': {{'config': {{}}, 'origins': {{}}, 'layers': []}}}})
request = receive()
assert request['method'] == 'configRequirements/read'
send({{'id': request['id'], 'result': {{'requirements': None}}}})
request = receive()
assert request['method'] == {'thread/resume' if resume else 'thread/start'!r}
send({{'id': request['id'], 'result': {{'thread': {{'id': 'thread-1'}}}}}})
request = receive()
assert request['method'] == 'turn/start'
send({{'id': request['id'], 'result': {{'turn': {{'id': 'turn-1', 'status': 'inProgress', 'items': []}}}}}})
if {unexpected_request!r}:
    send({{'id': 77, 'method': 'item/tool/requestUserInput', 'params': {{'threadId': 'thread-1', 'turnId': 'turn-1'}}}})
else:
    send({{'id': 77, 'method': 'item/tool/call', 'params': {{'threadId': 'thread-1', 'turnId': 'turn-1', 'callId': 'call-1', 'namespace': {namespace!r}, 'tool': {tool_name!r}, 'arguments': {arguments!r}}}}})
tool_response = receive()
assert tool_response['id'] == 77
send({{'method': 'thread/tokenUsage/updated', 'params': {{'threadId': 'thread-1', 'tokenUsage': {{'total': {{'inputTokens': 30, 'outputTokens': 20}}, 'last': {{'inputTokens': 3, 'cachedInputTokens': 1, 'outputTokens': 2, 'reasoningOutputTokens': 1, 'totalTokens': 5}}}}}}}})
send({{'method': 'item/completed', 'params': {{'threadId': 'thread-1', 'turnId': 'turn-1', 'item': {{'type': 'agentMessage', 'id': 'message-1', 'text': 'answer'}}}}}})
send({{'method': 'turn/completed', 'params': {{'threadId': 'thread-1', 'turn': {{'id': 'turn-1', 'status': 'completed', 'items': []}}}}}})
""",
        encoding="utf-8",
    )
    return sys.executable, str(script)


def bridge(tmp_path: Path, command: tuple[str, ...]) -> CodexAppServerBridge:
    home = tmp_path / "codex-home"
    home.mkdir()
    return CodexAppServerBridge(
        command=command,
        codex_home=home,
        version_probe=lambda: f"codex-cli {PINNED_CODEX_VERSION}",
    )


def read_transcript(tmp_path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (tmp_path / "transcript.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def test_bridge_closes_effectful_inventory_and_services_dynamic_tool(
    tmp_path: Path,
) -> None:
    command = stub(tmp_path)
    mediated: list[tuple[str, dict[str, object]]] = []
    evidence_calls: list[object] = []

    class Observation:
        def to_record(self):
            return {"path": "README.md", "text": "bounded evidence"}

    class Evidence:
        def prepare(self, envelopes=()):
            evidence_calls.append(("prepare", tuple(envelopes)))
            return tmp_path / "manifest.json"

        def record(self, observation):
            evidence_calls.append(("record", observation))
            return tmp_path / "observation.json"

    def mediate(name: str, arguments) -> Observation:
        mediated.append((name, dict(arguments)))
        return Observation()

    result = bridge(tmp_path, command).execute(
        prompt="Summarize the file",
        workspace=tmp_path,
        tools=[tool()],
        mediator=mediate,
        timeout=5,
        output_schema={"type": "string"},
        instructions="Use only the mediated evidence.",
        evidence=Evidence(),
        envelopes=({"grant_id": "read-root"},),
    )

    assert result.text == "answer"
    assert result.session.thread_id == "thread-1"
    assert result.session.tool_fingerprint == tool_fingerprint([tool()])
    assert result.turn_id == "turn-1"
    assert result.usage["total"] == {"inputTokens": 30, "outputTokens": 20}
    assert result.usage["last"]["totalTokens"] == 5
    assert mediated == [("read_file", {"path": "README.md"})]
    assert evidence_calls[0] == ("prepare", ({"grant_id": "read-root"},))
    assert evidence_calls[1][0] == "record"

    messages = read_transcript(tmp_path)
    assert messages[0]["method"] == "initialize"
    assert messages[0]["params"]["capabilities"] == {"experimentalApi": True}
    assert messages[1] == {"method": "initialized"}
    assert messages[2]["method"] == "config/read"
    assert messages[2]["params"] == {"includeLayers": True, "cwd": str(tmp_path)}
    assert messages[3]["method"] == "configRequirements/read"
    assert messages[4]["method"] == "thread/start"
    params = messages[4]["params"]
    assert params["environments"] == []
    assert params["approvalPolicy"] == "never"
    assert params["sandbox"] == "read-only"
    assert params["config"] == dict(AUDITED_CONFIG_OVERRIDES)
    assert params["config"]["features.shell_tool"] is False
    assert params["config"]["features.hooks"] is False
    assert params["config"]["features.apps"] is False
    assert params["config"]["features.plugins"] is False
    assert params["config"]["web_search"] == "disabled"
    assert params["dynamicTools"] == [tool().to_wire()]
    assert messages[5]["method"] == "turn/start"
    assert messages[5]["params"]["environments"] == []
    assert messages[5]["params"]["sandboxPolicy"] == {
        "type": "readOnly",
        "networkAccess": False,
    }
    assert messages[6]["result"]["success"] is True
    evidence = json.loads(messages[6]["result"]["contentItems"][0]["text"])
    assert evidence == {"path": "README.md", "text": "bounded evidence"}


def test_tool_free_profile_fails_before_version_probe_or_dispatch(tmp_path: Path) -> None:
    marker = tmp_path / "started"
    script = tmp_path / "should_not_start.py"
    script.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('started')\n",
        encoding="utf-8",
    )
    probes: list[str] = []
    home = tmp_path / "home"
    home.mkdir()
    adapter = CodexAppServerBridge(
        command=(sys.executable, str(script)),
        codex_home=home,
        version_probe=lambda: probes.append("called") or "codex-cli 0.131.0",
    )
    with pytest.raises(CodexAppServerCapabilityError, match="tool-free generate"):
        adapter.execute(
            prompt="hello",
            workspace=tmp_path,
            tools=[],
            mediator=lambda _name, _args: "unused",
            timeout=2,
        )
    assert probes == []
    assert not marker.exists()


def test_unknown_version_fails_before_app_server_dispatch(tmp_path: Path) -> None:
    marker = tmp_path / "started"
    script = tmp_path / "should_not_start.py"
    script.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('started')\n",
        encoding="utf-8",
    )
    home = tmp_path / "home"
    home.mkdir()
    adapter = CodexAppServerBridge(
        command=(sys.executable, str(script)),
        codex_home=home,
        version_probe=lambda: "codex-cli 0.132.0",
    )
    with pytest.raises(CodexAppServerCapabilityError, match="requires codex-cli 0.131.0"):
        adapter.execute(
            prompt="hello",
            workspace=tmp_path,
            tools=[tool()],
            mediator=lambda _name, _args: "unused",
            timeout=2,
        )
    assert not marker.exists()


def test_resumed_session_rejects_tool_registry_drift_before_dispatch(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "started"
    script = tmp_path / "should_not_start.py"
    script.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('started')\n",
        encoding="utf-8",
    )
    other = DynamicTool(
        "search",
        "Search bounded evidence.",
        {"type": "object", "additionalProperties": False},
    )
    with pytest.raises(CodexAppServerCapabilityError, match="different dynamic-tool"):
        bridge(tmp_path, (sys.executable, str(script))).execute(
            prompt="hello",
            workspace=tmp_path,
            tools=[other],
            mediator=lambda _name, _args: "unused",
            timeout=2,
            session=CodexAppServerSession("thread-1", tool_fingerprint([tool()])),
        )
    assert not marker.exists()


def test_non_mediated_server_request_is_denied_and_turn_is_rejected(
    tmp_path: Path,
) -> None:
    command = stub(tmp_path, unexpected_request=True)
    with pytest.raises(CodexAppServerProtocolError, match="unavailable native interaction"):
        bridge(tmp_path, command).execute(
            prompt="hello",
            workspace=tmp_path,
            tools=[tool()],
            mediator=lambda _name, _args: "unused",
            timeout=5,
        )
    response = read_transcript(tmp_path)[-1]
    assert response["id"] == 77
    assert response["error"]["code"] == -32601


def test_workspace_codex_config_fails_before_dispatch(tmp_path: Path) -> None:
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "config.toml").write_text("[mcp_servers.bad]\n")
    marker = tmp_path / "started"
    script = tmp_path / "should_not_start.py"
    script.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('started')\n",
        encoding="utf-8",
    )
    with pytest.raises(CodexAppServerCapabilityError, match="workspace-scoped"):
        bridge(tmp_path, (sys.executable, str(script))).execute(
            prompt="hello",
            workspace=tmp_path,
            tools=[tool()],
            mediator=lambda _name, _args: "unused",
            timeout=2,
        )
    assert not marker.exists()


def provider_request(tmp_path: Path, **changes: object) -> ProviderRequest:
    values = {
        "operation_id": "scope/codex:1",
        "prompt": "inspect the granted command",
        "workspace": tmp_path,
        "session_id": None,
        "output_schema": {"type": "string"},
        "policy": Policy(),
        "artifacts": {},
        "receipt_dir": tmp_path / "receipts",
        "timeout": 5,
        "operation": OperationKind.GENERATE,
        "allow_commands": (("git", "status", "--short"),),
    }
    values.update(changes)
    return ProviderRequest(**values)  # type: ignore[arg-type]


def test_provider_adapter_commits_receipt_tool_evidence_and_session_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Envelope:
        def to_record(self):
            return {
                "grant_id": "grant_1",
                "public_argv": ["git", "status", "--short"],
                "network": "none",
            }

    class Commands:
        def __init__(self, workspace, grants, **_options):
            assert Path(workspace) == tmp_path
            assert tuple(grants) == (("git", "status", "--short"),)
            self.envelopes = {"grant_1": Envelope()}

        def execute(self, grant_id):
            assert grant_id == "grant_1"
            return ToolObservation(
                "exec_grant",
                {"grant_id": grant_id},
                " M README.md",
                exit_code=0,
            )

        def close(self):
            return None

    monkeypatch.setattr("botpipe.codex_appserver.ExactCommandTools", Commands)
    command = stub(
        tmp_path,
        tool_name="exec_grant",
        namespace="botpipe",
        arguments={"grant_id": "grant_1"},
    )
    adapter = CodexAppServerProvider(bridge=bridge(tmp_path, command))
    request = provider_request(tmp_path)

    response = adapter.run(request)

    assert response.text == "answer"
    assert response.session_id == "thread-1"
    assert response.usage == {
        "input_tokens": 3,
        "cached_input_tokens": 1,
        "output_tokens": 2,
        "reasoning_tokens": 1,
        "total_tokens": 5,
    }
    assert response.metadata["tool_observations"][0]["output"] == " M README.md"
    receipt = json.loads(receipt_path(request).read_text(encoding="utf-8"))
    assert receipt["status"] == "completed"
    assert receipt["response"]["session_id"] == "thread-1"
    evidence_dir = next((tmp_path / "receipts").glob("*.tools"))
    manifest = json.loads((evidence_dir / "manifest.json").read_text())
    assert manifest["envelopes"][0]["grant_id"] == "grant_1"
    observation = json.loads(
        (evidence_dir / "observation-000001.json").read_text()
    )
    assert observation["observation"]["output"] == " M README.md"
    bindings = list((tmp_path / "receipts" / "codex-app-server-sessions").glob("*.json"))
    assert len(bindings) == 1
    binding = json.loads(bindings[0].read_text())
    assert binding["thread_id"] == "thread-1"
    assert binding["tool_fingerprint"] == response.metadata["tool_fingerprint"]
    recovered = adapter.recover(request)
    assert isinstance(recovered, Completed)
    assert recovered.response.to_record() == response.to_record()
    assert isinstance(adapter.cancel(request.operation_id), Unknown)

    adapter.bridge.command = stub(
        tmp_path,
        tool_name="exec_grant",
        namespace="botpipe",
        arguments={"grant_id": "grant_1"},
        resume=True,
    )
    continued = provider_request(
        tmp_path,
        operation_id="scope/codex:2",
        session_id="thread-1",
    )
    continued_response = adapter.run(continued)
    assert continued_response.session_id == "thread-1"
    assert any(
        message.get("method") == "thread/resume"
        for message in read_transcript(tmp_path)
    )


def test_provider_empty_generate_fails_before_probe_and_receipt(tmp_path: Path) -> None:
    probes: list[str] = []
    home = tmp_path / "home"
    home.mkdir()
    native = CodexAppServerBridge(
        command=(sys.executable, "unused.py"),
        codex_home=home,
        version_probe=lambda: probes.append("called") or "codex-cli 0.131.0",
    )
    adapter = CodexAppServerProvider(bridge=native)
    request = provider_request(tmp_path, allow_commands=())
    with pytest.raises(CapabilityError, match="tool-free generate"):
        adapter.run(request)
    assert probes == []
    assert not receipt_path(request).exists()


def test_provider_query_exposes_bounded_read_surface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Envelope:
        def to_record(self):
            return {"grant_id": "grant_1", "recipe": "git-status", "network": "none"}

    class Commands:
        def __init__(self, _workspace, grants, **_options):
            assert tuple(grants) == (("git", "status", "--short"),)
            self.envelopes = {"grant_1": Envelope()}

        def execute(self, _grant_id):
            return ToolObservation("exec_grant", {}, "clean", exit_code=0)

        def close(self):
            return None

    class Reads:
        def __init__(self, roots, *, exclusions, **_options):
            assert tuple(roots) == (tmp_path / "docs",)
            assert tuple(exclusions) == (tmp_path / "docs" / "private",)

        def read(self, path):
            assert path == "guide.md"
            return ToolObservation("read", {"path": path}, "bounded guide")

        def list(self, _path="."):
            raise AssertionError("unexpected list")

        def search(self, _query, _path="."):
            raise AssertionError("unexpected search")

        def close(self):
            return None

    monkeypatch.setattr("botpipe.codex_appserver.ExactCommandTools", Commands)
    monkeypatch.setattr("botpipe.codex_appserver.ReadOnlyTools", Reads)
    command = stub(
        tmp_path,
        tool_name="read",
        namespace="botpipe",
        arguments={"path": "guide.md"},
    )
    adapter = CodexAppServerProvider(bridge=bridge(tmp_path, command))
    request = provider_request(
        tmp_path,
        operation_id="scope/codex-query:1",
        operation=OperationKind.QUERY,
        allow_commands=(),
        output_schema=None,
        policy=Policy(allow_read=("docs",), deny_read=("docs/private",)),
    )

    response = adapter.run(request)

    assert response.text == "answer"
    assert response.metadata["tool_observations"] == [
        {
            "tool": "read",
            "input": {"path": "guide.md"},
            "output": "bounded guide",
            "truncated": False,
            "exit_code": None,
            "identity": None,
        }
    ]
