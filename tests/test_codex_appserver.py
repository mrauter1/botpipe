from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from contextlib import nullcontext
from pathlib import Path

import pytest

from botpipe.codex_appserver import (
    AUDITED_CONFIG_OVERRIDES,
    CURRENT_VERIFIED_CODEX_VERSION,
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
from botpipe.providers import (
    CapabilityError,
    ProviderInterruptedError,
    ProviderRequest,
    get_provider,
    receipt_path,
)
from botpipe.recovery import Completed, Unknown


@pytest.fixture(autouse=True)
def local_process_containment(monkeypatch: pytest.MonkeyPatch):
    """Unit protocol stubs use a process group; kernel backend has separate tests."""

    if os.name == "nt":
        yield
        return

    class LocalContainment:
        def spawn(self, argv, **kwargs):
            return subprocess.Popen(argv, start_new_session=True, **kwargs)

        def ensure_tree_exited(self, process, *, grace_seconds):
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                return
            try:
                process.wait(timeout=grace_seconds)
            except subprocess.TimeoutExpired:
                pass
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=2)

        def close(self):
            return None

    monkeypatch.setattr(
        "botpipe.codex_appserver.ProcessContainment.require_available", lambda: None
    )
    monkeypatch.setattr(
        "botpipe.codex_appserver.ProcessContainment.create", lambda: LocalContainment()
    )
    yield


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
    call_tool: bool = True,
    effective_model: str = "gpt-5.4",
) -> tuple[str, ...]:
    transcript = tmp_path / "transcript.jsonl"
    script = tmp_path / "app_server.py"
    arguments = {"path": "README.md"} if arguments is None else arguments
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
send({{'id': request['id'], 'result': {{'thread': {{'id': 'thread-1'}}, 'model': {effective_model!r}, 'reasoningEffort': 'medium'}}}})
request = receive()
assert request['method'] == 'turn/start'
send({{'id': request['id'], 'result': {{'turn': {{'id': 'turn-1', 'status': 'inProgress', 'items': []}}}}}})
if {unexpected_request!r}:
    send({{'id': 77, 'method': 'item/tool/requestUserInput', 'params': {{'threadId': 'thread-1', 'turnId': 'turn-1'}}}})
elif {call_tool!r}:
    send({{'id': 77, 'method': 'item/tool/call', 'params': {{'threadId': 'thread-1', 'turnId': 'turn-1', 'callId': 'call-1', 'namespace': {namespace!r}, 'tool': {tool_name!r}, 'arguments': {arguments!r}}}}})
if {unexpected_request!r} or {call_tool!r}:
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
        version_probe=lambda: f"codex-cli {CURRENT_VERIFIED_CODEX_VERSION}",
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
    assert len(result.session.tool_fingerprint) == 64
    assert result.session.tool_fingerprint != tool_fingerprint([tool()])
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
    assert "model" not in params
    assert "developerInstructions" not in params
    assert "baseInstructions" not in params
    assert messages[5]["method"] == "turn/start"
    assert messages[5]["params"]["environments"] == []
    assert messages[5]["params"]["sandboxPolicy"] == {
        "type": "readOnly",
        "networkAccess": False,
    }
    collaboration = messages[5]["params"]["collaborationMode"]
    assert collaboration["mode"] == "default"
    assert collaboration["settings"]["model"] == "gpt-5.4"
    assert collaboration["settings"]["reasoning_effort"] == "medium"
    assert collaboration["settings"]["developer_instructions"].endswith(
        "Use only the mediated evidence."
    )
    assert messages[6]["result"]["success"] is True
    evidence = json.loads(messages[6]["result"]["contentItems"][0]["text"])
    assert evidence == {"path": "README.md", "text": "bounded evidence"}


def test_role_instructions_replace_and_clear_on_same_native_thread(
    tmp_path: Path,
) -> None:
    native = bridge(tmp_path, stub(tmp_path))

    first = native.execute(
        prompt="first",
        workspace=tmp_path,
        tools=[tool()],
        mediator=lambda _name, _args: "ok",
        timeout=5,
        instructions="role A",
    )
    native.command = stub(tmp_path, resume=True)
    native.execute(
        prompt="second",
        workspace=tmp_path,
        tools=[tool()],
        mediator=lambda _name, _args: "ok",
        timeout=5,
        instructions="role A",
        session=first.session,
    )
    native.execute(
        prompt="third",
        workspace=tmp_path,
        tools=[tool()],
        mediator=lambda _name, _args: "ok",
        timeout=5,
        instructions="role B",
        session=first.session,
    )
    native.execute(
        prompt="fourth",
        workspace=tmp_path,
        tools=[tool()],
        mediator=lambda _name, _args: "ok",
        timeout=5,
        instructions=None,
        session=first.session,
    )
    native.execute(
        prompt="fifth",
        workspace=tmp_path,
        tools=[tool()],
        mediator=lambda _name, _args: "ok",
        timeout=5,
        instructions="",
        session=first.session,
    )

    messages = read_transcript(tmp_path)
    thread_requests = [
        message
        for message in messages
        if message.get("method") in {"thread/start", "thread/resume"}
    ]
    assert all(
        "developerInstructions" not in request["params"]
        and "baseInstructions" not in request["params"]
        for request in thread_requests
    )
    turn_requests = [
        message for message in messages if message.get("method") == "turn/start"
    ]
    collaborations = [
        request["params"]["collaborationMode"] for request in turn_requests
    ]
    assert all(item["mode"] == "default" for item in collaborations)
    assert all(item["settings"]["model"] == "gpt-5.4" for item in collaborations)
    assert all(
        item["settings"]["reasoning_effort"] == "medium"
        for item in collaborations
    )
    role_updates = [
        item["settings"]["developer_instructions"] for item in collaborations
    ]
    assert role_updates[0].endswith("role A")
    assert collaborations[0] == collaborations[1]
    assert role_updates[2].endswith("role B")
    assert role_updates[0].split("\n\n", 1)[0] == role_updates[2].split("\n\n", 1)[0]
    assert role_updates[3] == role_updates[4]
    assert "No additional Botpipe role instructions apply" in role_updates[3]


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
def test_completed_app_server_turn_cannot_leave_stubborn_descendant(
    tmp_path: Path,
) -> None:
    child_pid = tmp_path / "child.pid"
    child_ready = tmp_path / "child.ready"
    escaped = tmp_path / "escaped"
    child = tmp_path / "child.py"
    child.write_text(
        "import signal,sys,time\n"
        "from pathlib import Path\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "Path(sys.argv[1]).write_text('ready')\n"
        "time.sleep(1)\n"
        "Path(sys.argv[2]).write_text('escaped')\n"
        "while True: time.sleep(.1)\n",
        encoding="utf-8",
    )
    server = tmp_path / "tree_server.py"
    server.write_text(
        "import json,subprocess,sys,time\n"
        "from pathlib import Path\n"
        "child=subprocess.Popen([sys.executable,sys.argv[1],sys.argv[2],sys.argv[3]])\n"
        "Path(sys.argv[4]).write_text(str(child.pid))\n"
        "while not Path(sys.argv[2]).exists(): time.sleep(.01)\n"
        "def receive(): return json.loads(sys.stdin.readline())\n"
        "def send(value): print(json.dumps(value),flush=True)\n"
        "request=receive();send({'id':request['id'],'result':{'userAgent':'stub'}});receive()\n"
        "for method,result in [('config/read',{'config':{},'layers':[]}),('configRequirements/read',{'requirements':None}),('thread/start',{'thread':{'id':'thread-1'},'model':'gpt-5.4','reasoningEffort':'medium'}),('turn/start',{'turn':{'id':'turn-1'}})]:\n"
        " request=receive();assert request['method']==method;send({'id':request['id'],'result':result})\n"
        "send({'method':'item/completed','params':{'item':{'type':'agentMessage','text':'ok'}}})\n"
        "send({'method':'turn/completed','params':{'turn':{'id':'turn-1','status':'completed'}}})\n"
        "while True: time.sleep(.1)\n",
        encoding="utf-8",
    )
    command = (
        sys.executable,
        str(server),
        str(child),
        str(child_ready),
        str(escaped),
        str(child_pid),
    )

    try:
        result = bridge(tmp_path, command).execute(
            prompt="hello",
            workspace=tmp_path,
            tools=[tool()],
            mediator=lambda _name, _args: "unused",
            timeout=5,
        )

        assert result.text == "ok"
        pid = int(child_pid.read_text(encoding="utf-8"))
        time.sleep(1.1)
        assert not escaped.exists()
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        else:
            stat = Path(f"/proc/{pid}/stat")
            assert stat.exists() and stat.read_text().split(") ", 1)[1].startswith("Z ")
    finally:
        if child_pid.exists():
            try:
                os.kill(int(child_pid.read_text(encoding="utf-8")), signal.SIGKILL)
            except (ProcessLookupError, ValueError):
                pass


def test_uncertain_process_tree_cleanup_prevents_successful_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class UncertainContainment:
        def spawn(self, argv, **kwargs):
            if os.name == "posix":
                kwargs["start_new_session"] = True
            return subprocess.Popen(argv, **kwargs)

        def ensure_tree_exited(self, _process, *, grace_seconds):
            assert grace_seconds == 0.1
            raise RuntimeError("tree cleanup uncertain")

        def close(self):
            return None

    monkeypatch.setattr(
        "botpipe.codex_appserver.ProcessContainment.create",
        lambda: UncertainContainment(),
    )

    with pytest.raises(RuntimeError, match="tree cleanup uncertain"):
        bridge(tmp_path, stub(tmp_path)).execute(
            prompt="hello",
            workspace=tmp_path,
            tools=[tool()],
            mediator=lambda _name, _args: "ok",
            timeout=5,
        )


def test_app_server_spawn_failure_closes_containment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import botpipe.codex_appserver as appserver

    calls: list[object] = []

    class FailedContainment:
        def spawn(self, _argv, **_kwargs):
            calls.append("spawn")
            raise RuntimeError("job assignment failed")

        def close(self):
            calls.append("close")

    monkeypatch.setattr(
        appserver.ProcessContainment, "create", lambda: FailedContainment()
    )

    with pytest.raises(RuntimeError, match="job assignment failed"):
        appserver._JsonlProcess(
            ("stub",),
            cwd=tmp_path,
            env={},
            max_message_bytes=1,
            max_messages=1,
        )

    assert calls == ["spawn", "close"]


def test_tool_free_profile_dispatches_with_exact_empty_inventory(tmp_path: Path) -> None:
    adapter = bridge(tmp_path, stub(tmp_path, call_tool=False))
    result = adapter.execute(
        prompt="hello",
        workspace=tmp_path,
        tools=[],
        mediator=lambda _name, _args: "unused",
        timeout=2,
    )
    assert result.text == "answer"
    thread_start = next(
        message
        for message in read_transcript(tmp_path)
        if message.get("method") == "thread/start"
    )
    assert thread_start["params"]["dynamicTools"] == []
    assert thread_start["params"]["config"][
        "tools.experimental_request_user_input.enabled"
    ] is False
    assert thread_start["params"]["config"]["tools.update_plan.enabled"] is False
    assert thread_start["params"]["config"]["orchestrator.skills.enabled"] is False


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
        version_probe=lambda: "codex-cli 0.156.0",
    )
    with pytest.raises(CodexAppServerCapabilityError, match="no conformance evidence"):
        adapter.execute(
            prompt="hello",
            workspace=tmp_path,
            tools=[tool()],
            mediator=lambda _name, _args: "unused",
            timeout=2,
        )
    assert not marker.exists()


def test_unreviewed_effective_model_fails_before_turn_without_implicit_override(
    tmp_path: Path,
) -> None:
    adapter = bridge(
        tmp_path,
        stub(tmp_path, call_tool=False, effective_model="account-model"),
    )
    with pytest.raises(CodexAppServerCapabilityError, match="effective model"):
        adapter.execute(
            prompt="hello",
            workspace=tmp_path,
            tools=[],
            mediator=lambda _name, _args: "unused",
            timeout=2,
        )
    transcript = read_transcript(tmp_path)
    thread_start = next(
        message for message in transcript if message.get("method") == "thread/start"
    )
    assert "model" not in thread_start["params"]
    assert not any(message.get("method") == "turn/start" for message in transcript)


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


def test_overlong_protocol_line_is_rejected_before_materialization(tmp_path: Path) -> None:
    script = tmp_path / "overlong.py"
    script.write_text(
        "import sys\n"
        "sys.stdin.buffer.readline()\n"
        "sys.stdout.buffer.write(b'{\"x\":\"' + b'x' * 512 + b'\"}\\n')\n"
        "sys.stdout.buffer.flush()\n",
        encoding="utf-8",
    )
    home = tmp_path / "home"
    home.mkdir()
    adapter = CodexAppServerBridge(
        command=(sys.executable, str(script)),
        codex_home=home,
        version_probe=lambda: f"codex-cli {CURRENT_VERIFIED_CODEX_VERSION}",
        max_event_bytes=128,
        max_events=2,
    )
    with pytest.raises(CodexAppServerProtocolError, match="line exceeds"):
        adapter.execute(
            prompt="hello",
            workspace=tmp_path,
            tools=[tool()],
            mediator=lambda _name, _args: "unused",
            timeout=2,
        )


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


def test_provider_registry_selects_explicit_app_server_interface(tmp_path: Path) -> None:
    command = (sys.executable, str(tmp_path / "unused.py"))
    adapter = get_provider(
        "codex",
        {"interface": "app_server", "bridge": bridge(tmp_path, command)},
    )
    assert isinstance(adapter, CodexAppServerProvider)


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
    assert binding["instruction_mode"] == "collaboration-mode-v1"
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

    legacy_binding = json.loads(bindings[0].read_text())
    legacy_binding.pop("instruction_mode")
    bindings[0].write_text(json.dumps(legacy_binding), encoding="utf-8")
    with pytest.raises(CapabilityError, match="role-instruction mode"):
        adapter.run(
            provider_request(
                tmp_path,
                operation_id="scope/codex:3",
                session_id="thread-1",
            )
        )


def test_provider_empty_generate_uses_strict_empty_inventory(tmp_path: Path) -> None:
    adapter = CodexAppServerProvider(
        bridge=bridge(tmp_path, stub(tmp_path, call_tool=False))
    )
    request = provider_request(tmp_path, allow_commands=())
    response = adapter.run(request)
    assert response.text == "answer"
    thread_start = next(
        message
        for message in read_transcript(tmp_path)
        if message.get("method") == "thread/start"
    )
    assert thread_start["params"]["dynamicTools"] == []


def test_provider_run_uses_native_app_server_profile_on_every_turn(
    tmp_path: Path,
) -> None:
    adapter = CodexAppServerProvider(
        bridge=bridge(tmp_path, stub(tmp_path, call_tool=False))
    )
    request = provider_request(
        tmp_path,
        operation_id="scope/codex-run:1",
        operation=OperationKind.RUN,
        allow_commands=(),
    )

    response = adapter.run(request)

    assert response.text == "answer"
    assert response.session_id == "thread-1"
    transcript = read_transcript(tmp_path)
    thread_start = next(
        message for message in transcript if message.get("method") == "thread/start"
    )["params"]
    turn_start = next(
        message for message in transcript if message.get("method") == "turn/start"
    )["params"]
    environment = {
        "environmentId": "local",
        "cwd": str(tmp_path.resolve()),
        "runtimeWorkspaceRoots": [str(tmp_path.resolve())],
    }
    assert thread_start["dynamicTools"] == []
    assert thread_start["config"] == {}
    assert thread_start["environments"] == [environment]
    assert thread_start["approvalPolicy"] == "on-request"
    assert thread_start["sandbox"] == "workspace-write"
    assert turn_start["environments"] == [environment]
    assert turn_start["approvalPolicy"] == "on-request"
    assert turn_start["sandboxPolicy"] == {
        "type": "workspaceWrite",
        "writableRoots": [],
        "networkAccess": False,
    }
    assert turn_start["collaborationMode"]["settings"][
        "developer_instructions"
    ]

    with pytest.raises(CapabilityError, match="tool-registry binding"):
        adapter.run(
            provider_request(
                tmp_path,
                operation_id="scope/codex-generate-after-run:1",
                operation=OperationKind.GENERATE,
                session_id="thread-1",
                allow_commands=(),
            )
        )


def test_newer_codex_is_accepted_for_native_run_but_not_unreviewed_strict_inventory(
    tmp_path: Path,
) -> None:
    home = tmp_path / "newer-home"
    home.mkdir()
    native = CodexAppServerBridge(
        command=stub(tmp_path, call_tool=False),
        codex_home=home,
        version_probe=lambda: "codex-cli 0.156.0",
    )
    adapter = CodexAppServerProvider(bridge=native)

    response = adapter.run(
        provider_request(
            tmp_path,
            operation_id="scope/newer-run:1",
            operation=OperationKind.RUN,
            allow_commands=(),
        )
    )
    assert response.text == "answer"

    with pytest.raises(CodexAppServerCapabilityError, match="no conformance evidence"):
        native.preflight(tmp_path, strict_inventory=True)


@pytest.mark.parametrize(
    "policy",
    [
        Policy(allow_read=("docs",)),
        Policy(allow_read=(".",), deny_read=("private",)),
    ],
)
def test_provider_exact_grants_cannot_override_read_scope(
    tmp_path: Path, policy: Policy
) -> None:
    probes: list[str] = []
    home = tmp_path / "home"
    home.mkdir()
    native = CodexAppServerBridge(
        command=(sys.executable, "unused.py"),
        codex_home=home,
        version_probe=lambda: probes.append("called") or f"codex-cli {CURRENT_VERIFIED_CODEX_VERSION}",
    )
    adapter = CodexAppServerProvider(bridge=native)
    request = provider_request(tmp_path, policy=policy)
    with pytest.raises(CapabilityError, match="workspace-wide"):
        adapter.run(request)
    assert probes == []
    assert not receipt_path(request).exists()


def test_evidence_prepare_failure_precedes_dispatch_and_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "started"
    script = tmp_path / "should_not_start.py"
    script.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('started')\n",
        encoding="utf-8",
    )

    class Envelope:
        def to_record(self):
            return {"grant_id": "grant_1", "public_argv": ["git", "status"]}

    class Commands:
        def __init__(self, *_args, **_kwargs):
            self.envelopes = {"grant_1": Envelope()}

        def close(self):
            return None

    class FailingEvidence:
        def __init__(self, *_args, **_kwargs):
            pass

        def prepare(self, _envelopes=()):
            raise OSError("manifest unavailable")

    monkeypatch.setattr("botpipe.codex_appserver.ExactCommandTools", Commands)
    monkeypatch.setattr("botpipe.codex_appserver.ToolEvidence", FailingEvidence)
    adapter = CodexAppServerProvider(
        bridge=bridge(tmp_path, (sys.executable, str(script)))
    )
    request = provider_request(tmp_path)

    with pytest.raises(OSError, match="manifest unavailable"):
        adapter.run(request)

    assert not marker.exists()
    assert not receipt_path(request).exists()


def test_evidence_record_failure_aborts_native_turn_and_marks_uncertain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Envelope:
        def to_record(self):
            return {"grant_id": "grant_1", "public_argv": ["git", "status"]}

    class Commands:
        def __init__(self, *_args, **_kwargs):
            self.envelopes = {"grant_1": Envelope()}

        def execute(self, grant_id):
            return ToolObservation("exec_grant", {"grant_id": grant_id}, "ok")

        def close(self):
            return None

    class FailingEvidence:
        def __init__(self, *_args, **_kwargs):
            pass

        def prepare(self, _envelopes=()):
            return tmp_path / "manifest.json"

        def record(self, _observation):
            raise OSError("observation unavailable")

    monkeypatch.setattr("botpipe.codex_appserver.ExactCommandTools", Commands)
    monkeypatch.setattr("botpipe.codex_appserver.ToolEvidence", FailingEvidence)
    command = stub(
        tmp_path,
        tool_name="exec_grant",
        namespace="botpipe",
        arguments={"grant_id": "grant_1"},
    )
    adapter = CodexAppServerProvider(bridge=bridge(tmp_path, command))
    request = provider_request(tmp_path)

    with pytest.raises(ProviderInterruptedError, match="observation unavailable"):
        adapter.run(request)

    receipt = json.loads(receipt_path(request).read_text(encoding="utf-8"))
    assert receipt["status"] == "uncertain"
    assert not any(message.get("id") == 77 for message in read_transcript(tmp_path))


def test_cancel_requests_native_interrupt_before_returning_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ready = tmp_path / "ready"
    transcript = tmp_path / "transcript.jsonl"
    script = tmp_path / "interrupt_server.py"
    script.write_text(
        f"""import json, pathlib, sys
out = pathlib.Path({str(transcript)!r})
ready = pathlib.Path({str(ready)!r})
def receive():
    value = json.loads(sys.stdin.readline())
    with out.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(value, sort_keys=True) + '\\n')
    return value
def send(value):
    print(json.dumps(value), flush=True)
request = receive()
send({{'id': request['id'], 'result': {{'userAgent': 'stub'}}}})
assert receive()['method'] == 'initialized'
request = receive()
send({{'id': request['id'], 'result': {{'config': {{}}, 'layers': []}}}})
request = receive()
send({{'id': request['id'], 'result': {{'requirements': None}}}})
request = receive()
send({{'id': request['id'], 'result': {{'thread': {{'id': 'thread-1'}}, 'model': 'gpt-5.4', 'reasoningEffort': 'medium'}}}})
request = receive()
send({{'id': request['id'], 'result': {{'turn': {{'id': 'turn-1'}}}}}})
ready.write_text('ready')
request = receive()
assert request['method'] == 'turn/interrupt'
send({{'id': request['id'], 'result': {{}}}})
send({{'method': 'turn/completed', 'params': {{'turn': {{'id': 'turn-1', 'status': 'interrupted'}}}}}})
""",
        encoding="utf-8",
    )

    class Envelope:
        def to_record(self):
            return {"grant_id": "grant_1", "public_argv": ["git", "status"]}

    class Commands:
        def __init__(self, *_args, **_kwargs):
            self.envelopes = {"grant_1": Envelope()}

        def close(self):
            return None

    monkeypatch.setattr("botpipe.codex_appserver.ExactCommandTools", Commands)
    adapter = CodexAppServerProvider(
        bridge=bridge(tmp_path, (sys.executable, str(script)))
    )
    request = provider_request(tmp_path)
    failures: list[BaseException] = []

    def invoke() -> None:
        try:
            adapter.run(request)
        except BaseException as exc:
            failures.append(exc)

    worker = threading.Thread(target=invoke)
    worker.start()
    deadline = time.monotonic() + 3
    while not ready.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert ready.exists()

    outcome = adapter.cancel(request.operation_id)
    worker.join(timeout=3)

    assert isinstance(outcome, Unknown)
    assert "turn/interrupt was requested" in outcome.detail
    assert not worker.is_alive()
    assert len(failures) == 1
    assert isinstance(failures[0], ProviderInterruptedError)
    assert any(
        message.get("method") == "turn/interrupt"
        for message in read_transcript(tmp_path)
    )


def test_provider_query_exposes_bounded_read_surface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fence = lambda _path: nullcontext()  # noqa: E731
    class Reads:
        command_envelopes = {}

        def __init__(self, roots, *, exclusions, **_options):
            assert tuple(roots) == (tmp_path / "docs",)
            assert tuple(exclusions) == (tmp_path / "docs" / "private",)
            assert _options["read_fence"] is fence

        def read(self, path):
            assert path == "guide.md"
            return ToolObservation("read", {"path": path}, "bounded guide")

        def list(self, _path="."):
            raise AssertionError("unexpected list")

        def search(self, _query, _path="."):
            raise AssertionError("unexpected search")

        def close(self):
            return None

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
        read_fence=fence,
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
    transcript = read_transcript(tmp_path)
    thread_start = next(
        message for message in transcript
        if message.get("method") == "thread/start"
    )
    assert "developerInstructions" not in thread_start["params"]
    turn_start = next(
        message for message in transcript if message.get("method") == "turn/start"
    )
    assert turn_start["params"]["collaborationMode"]["settings"][
        "developer_instructions"
    ]
    assert "count_lines" in {
        item["name"] for item in thread_start["params"]["dynamicTools"]
    }


def test_provider_query_includes_scope_safe_finite_line_count_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Envelope:
        def to_record(self):
            return {"tool": "count_lines", "argv": ["/usr/bin/wc", "-l"]}

    class Reads:
        command_envelopes = {"count_lines": Envelope()}

        def __init__(self, roots, *, exclusions, **_options):
            assert tuple(roots) == (tmp_path,)
            assert tuple(exclusions) == ()

        def count_lines(self, path):
            assert path == "README.md"
            return ToolObservation("count_lines", {"path": path}, "42")

        def close(self):
            return None

    monkeypatch.setattr("botpipe.codex_appserver.ReadOnlyTools", Reads)
    command = stub(
        tmp_path,
        tool_name="count_lines",
        namespace="botpipe",
        arguments={"path": "README.md"},
    )
    adapter = CodexAppServerProvider(bridge=bridge(tmp_path, command))
    request = provider_request(
        tmp_path,
        operation_id="scope/codex-query-default:1",
        operation=OperationKind.QUERY,
        allow_commands=(),
        output_schema=None,
    )

    response = adapter.run(request)

    assert response.metadata["tool_observations"][0]["output"] == "42"
    thread_start = next(
        message for message in read_transcript(tmp_path)
        if message.get("method") == "thread/start"
    )
    assert "count_lines" in {
        item["name"] for item in thread_start["params"]["dynamicTools"]
    }
