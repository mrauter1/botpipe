from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from botpipe import Botpipe, Provider
from botpipe.capabilities import (
    CapabilityError,
    CapabilityStatus,
    CodexCapabilities,
    probe_codex,
)
from botpipe.codex_appserver import CodexAppServerAdapter
from botpipe.policy import NetworkMode, Policy, SandboxMode
from botpipe.providers import (
    CodexProvider,
    ProviderInterruptedError,
    ProviderRequest,
    ProviderTimeoutError,
)

FIXTURE = Path(__file__).parent / "fixtures" / "codex_appserver.py"
ITEM_TYPES = frozenset(
    {
        "agentMessage",
        "collabAgentToolCall",
        "commandExecution",
        "contextCompaction",
        "dynamicToolCall",
        "enteredReviewMode",
        "exitedReviewMode",
        "fileChange",
        "functionCallOutput",
        "hookPrompt",
        "imageGeneration",
        "imageView",
        "mcpToolCall",
        "plan",
        "reasoning",
        "sleep",
        "subAgentActivity",
        "userMessage",
        "webSearch",
    }
)


def capabilities(*, output_schema: bool = True) -> CodexCapabilities:
    return CodexCapabilities(
        executable=sys.executable,
        version="codex-cli contract-fixture",
        identity="fixture-probe-hash",
        methods=frozenset(
            {"initialize", "thread/start", "thread/resume", "thread/unsubscribe", "turn/start", "turn/interrupt"}
        ),
        features=(
            {"name": "apps", "stage": "stable", "enabled": True},
            {"name": "shell_tool", "stage": "stable", "enabled": True},
            {"name": "standalone_web_search", "stage": "stable", "enabled": True},
        ),
        supports_turn_sandbox=True,
        supports_interrupt=True,
        supports_output_schema=output_schema,
        supports_dynamic_tools=True,
        supports_tool_config=True,
        supports_mcp_config=True,
        supports_effort=True,
        supports_instructions=True,
        presets={name: CapabilityStatus(True) for name in ("run", "query", "generate")},
        item_types=ITEM_TYPES,
    )


def request(
    tmp_path: Path,
    *,
    preset: str = "run",
    tools: tuple[str, ...] | None = None,
    session_id: str | None = None,
    timeout: float = 2,
    output_schema: dict | None = None,
    cancel_event: threading.Event | None = None,
) -> ProviderRequest:
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    return ProviderRequest(
        operation_id=f"{preset}-operation",
        prompt="Try to write changed.txt, then answer.",
        workspace=workspace,
        session_id=session_id,
        output_schema=output_schema,
        policy=Policy(
            sandbox_mode=(
                SandboxMode.READ_ONLY if preset in {"query", "generate"} else SandboxMode.WORKSPACE_WRITE
            ),
            network=NetworkMode.NONE,
        ),
        artifacts={},
        receipt_dir=tmp_path / "receipts",
        timeout=timeout,
        preset=preset,
        tools=tools,
        cancel_event=cancel_event,
    )


def adapter(tmp_path: Path, scenario: str = "complete", **extra_env: str) -> CodexAppServerAdapter:
    transcript = tmp_path / "codex-transcript.jsonl"
    return CodexAppServerAdapter(
        (sys.executable, str(FIXTURE)),
        env={
            "BOTPIPE_FAKE_TRANSCRIPT": str(transcript),
            "BOTPIPE_FAKE_SCENARIO": scenario,
            **extra_env,
        },
        capabilities=capabilities(),
        interrupt_grace_seconds=0.1,
    )


def transcript(tmp_path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (tmp_path / "codex-transcript.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def workspace_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_default_run_routes_nested_completion_and_records_protocol(tmp_path: Path) -> None:
    client = adapter(tmp_path)
    try:
        response = client.start_turn(request(tmp_path))
    finally:
        client.close()

    assert response.text == "fixture answer"
    assert response.session_id == "thread-fixture"
    assert response.usage == {"inputTokens": 7, "outputTokens": 3}
    assert response.metadata["turn_id"] == "turn-1"
    assert response.metadata["codex_version"] == "codex-cli contract-fixture"
    assert response.metadata["enforcement"]["sandbox"] == "codex:workspace-write"
    assert response.metadata["enforcement"]["network"] == "codex:off"
    assert any(event["type"] == "turn/completed" for event in response.metadata["audit"])
    methods = [entry["method"] for entry in transcript(tmp_path)]
    assert methods == ["initialize", "initialized", "thread/start", "turn/start"]


def test_query_is_read_only_and_workspace_remains_byte_identical(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "kept.bin").write_bytes(b"\x00unchanged\xff")
    before = workspace_bytes(workspace)
    client = adapter(tmp_path)
    try:
        response = client.start_turn(request(tmp_path, preset="query", tools=()))
    finally:
        client.close()

    assert response.text == "fixture answer"
    assert workspace_bytes(workspace) == before
    assert response.metadata["enforcement"]["sandbox"] == "codex:read-only"
    assert response.metadata["enforcement"]["audit"] == "no-tool-calls-observed"
    turn = next(item for item in transcript(tmp_path) if item.get("method") == "turn/start")
    assert turn["params"]["sandboxPolicy"] == {
        "type": "readOnly",
        "networkAccess": False,
    }
    thread = next(item for item in transcript(tmp_path) if item.get("method") == "thread/start")
    assert thread["params"]["sandbox"] == "read-only"
    config = thread["params"]["config"]
    assert config["features.apps"] is False
    assert not any(key.startswith("mcp_servers.") for key in config)


def test_generate_has_exact_empty_inventory_and_rejects_disallowed_tool_with_evidence(
    tmp_path: Path,
) -> None:
    client = adapter(tmp_path, "disallowed_shell")
    with pytest.raises(CapabilityError) as caught:
        client.start_turn(request(tmp_path, preset="generate", tools=()))
    client.close()

    message = str(caught.value)
    assert "disallowed tool 'shell'" in message
    assert '"id": "forbidden-command"' in message
    thread = next(item for item in transcript(tmp_path) if item.get("method") == "thread/start")
    config = thread["params"]["config"]
    assert config["features.shell_tool"] is False
    assert config["features.standalone_web_search"] is False
    assert config["features.apps"] is False
    assert config["tools.experimental_request_user_input.enabled"] is False
    assert config["tools.update_plan.enabled"] is False
    assert not any(key.startswith("mcp_servers.") for key in config)
    assert thread["params"]["dynamicTools"] == []


@pytest.mark.parametrize(
    ("method", "tool", "params"),
    [
        ("turn/plan/updated", "update_plan", {"plan": []}),
        ("item/tool/requestUserInput", "request_user_input", {"questions": []}),
        ("item/tool/call", "dynamic", {"tool": "unexpected"}),
    ],
)
def test_generate_audits_control_tools_and_declines_interactive_requests(
    tmp_path, monkeypatch, method, tool, params
):
    from botpipe.codex_appserver import _Turn

    client = adapter(tmp_path)
    turn = _Turn("thread", "turn", (), None)
    client._turns[("thread", "turn")] = turn
    sent = []
    monkeypatch.setattr(client, "_send", sent.append)
    event = {
        "method": method,
        "params": {"threadId": "thread", "turnId": "turn", **params},
    }
    if method.startswith("item/tool/"):
        event["id"] = 123

    client._receive(event)

    assert isinstance(turn.error, CapabilityError)
    assert tool in str(turn.error)
    assert turn.tools_observed
    assert turn.events[0]["type"] == method
    if "id" in event:
        assert sent[0]["id"] == 123
        assert "error" in sent[0]
    client._record_event(turn, "error", {"error": "tool stopped"})
    assert isinstance(turn.error, CapabilityError)


def test_query_then_run_resumes_same_native_thread(tmp_path: Path) -> None:
    client = adapter(tmp_path)
    try:
        first = client.start_turn(request(tmp_path, preset="query", tools=()))
        second = client.start_turn(
            request(tmp_path, preset="run", session_id=first.session_id)
        )
    finally:
        client.close()

    assert second.session_id == first.session_id == "thread-fixture"
    calls = transcript(tmp_path)
    assert [item["method"] for item in calls if item["method"].startswith("thread/")] == [
        "thread/start",
        "thread/unsubscribe",
        "thread/resume",
    ]
    resume = next(item for item in calls if item["method"] == "thread/resume")
    assert resume["params"]["threadId"] == "thread-fixture"
    turns = [item for item in calls if item["method"] == "turn/start"]
    assert [item["params"]["sandboxPolicy"]["type"] for item in turns] == [
        "readOnly",
        "workspaceWrite",
    ]


def test_unchanged_thread_profile_needs_no_unsubscribe_but_changes_require_it(
    tmp_path: Path,
) -> None:
    client = adapter(tmp_path)
    client._capabilities = replace(
        capabilities(), methods=capabilities().methods - {"thread/unsubscribe"}
    )
    try:
        first = client.start_turn(request(tmp_path, preset="query", tools=()))
        second = client.start_turn(
            request(tmp_path, preset="query", tools=(), session_id=first.session_id)
        )
        with pytest.raises(CapabilityError, match="thread/unsubscribe"):
            client.start_turn(request(tmp_path, session_id=second.session_id))
    finally:
        client.close()

    calls = transcript(tmp_path)
    assert [item["method"] for item in calls if item["method"].startswith("thread/")] == [
        "thread/start", "thread/resume",
    ]
    assert sum(item["method"] == "turn/start" for item in calls) == 2


@pytest.mark.skipif(os.name != "posix", reason="separate POSIX process group")
def test_terminal_notification_still_cleans_native_background_groups(tmp_path):
    marker = tmp_path / "background-survived"
    client = adapter(
        tmp_path,
        "native_background",
        BOTPIPE_FAKE_DESCENDANT_MARKER=str(marker),
        BOTPIPE_FAKE_DESCENDANT_PID=str(tmp_path / "background.pid"),
    )
    client._capabilities = replace(
        capabilities(),
        methods=capabilities().methods | {"thread/backgroundTerminals/clean"},
    )
    try:
        client._start()
        client._thread_profiles["previous-thread"] = "previous-profile"
        with pytest.raises(ProviderTimeoutError):
            client.start_turn(request(tmp_path, timeout=0.2))
    finally:
        client.close()

    calls = transcript(tmp_path)
    methods = [item["method"] for item in calls]
    assert methods.index("turn/interrupt") < methods.index("thread/backgroundTerminals/clean")
    assert {
        item["params"]["threadId"]
        for item in calls
        if item["method"] == "thread/backgroundTerminals/clean"
    } == {"previous-thread", "thread-fixture"}
    time.sleep(1.1)
    assert not marker.exists(), "native background group survived turn cancellation"


@pytest.mark.parametrize("cancel", [False, True], ids=["timeout", "cancellation"])
def test_timeout_and_cancellation_kill_actual_descendant_tree(
    tmp_path: Path, cancel: bool
) -> None:
    marker = tmp_path / "descendant-escaped"
    pid_file = tmp_path / "descendant.pid"
    event = threading.Event() if cancel else None
    client = adapter(
        tmp_path,
        "stall_tree",
        BOTPIPE_FAKE_DESCENDANT_MARKER=str(marker),
        BOTPIPE_FAKE_DESCENDANT_PID=str(pid_file),
    )
    call = request(
        tmp_path,
        timeout=3 if cancel else 0.2,
        cancel_event=event,
    )
    if not cancel:
        with pytest.raises(ProviderTimeoutError):
            client.start_turn(call)
    else:
        errors: list[BaseException] = []

        def run() -> None:
            try:
                client.start_turn(call)
            except ProviderInterruptedError as exc:
                errors.append(exc)

        worker = threading.Thread(target=run)
        worker.start()
        deadline = time.monotonic() + 2
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert pid_file.exists(), "fixture descendant was never started"
        event.set()
        worker.join(timeout=2)
        assert not worker.is_alive(), "cancellation returned before process cleanup"
        assert len(errors) == 1 and isinstance(errors[0], ProviderInterruptedError)
    client.close()
    time.sleep(1.1)
    assert not marker.exists(), "a descendant survived adapter cleanup"


def test_turn_start_ack_timeout_kills_unknown_dispatched_turn_tree(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "pre-ack-descendant-escaped"
    pid_file = tmp_path / "pre-ack-descendant.pid"
    client = adapter(
        tmp_path,
        "stall_turn_start",
        BOTPIPE_FAKE_DESCENDANT_MARKER=str(marker),
        BOTPIPE_FAKE_DESCENDANT_PID=str(pid_file),
    )

    with pytest.raises(ProviderTimeoutError, match="turn start"):
        client.start_turn(request(tmp_path, timeout=0.2))
    client.close()

    assert pid_file.exists(), "fixture never dispatched its unknown turn"
    assert not any(
        item.get("method") == "turn/interrupt" for item in transcript(tmp_path)
    ), "an unknown turn id must not be guessed"
    time.sleep(1.1)
    assert not marker.exists(), "pre-acknowledgement turn survived RPC timeout"


@pytest.mark.asyncio
async def test_sdk_async_cancel_waits_for_pre_ack_turn_tree_cleanup(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "pre-ack-cancel-descendant-escaped"
    pid_file = tmp_path / "pre-ack-cancel-descendant.pid"
    client = adapter(
        tmp_path,
        "stall_turn_start",
        BOTPIPE_FAKE_DESCENDANT_MARKER=str(marker),
        BOTPIPE_FAKE_DESCENDANT_PID=str(pid_file),
    )
    backend = CodexProvider(adapter=client)
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    runtime = Botpipe(workspace, provider=backend, state_dir=tmp_path / "state")
    sdk = Provider(runtime=runtime)
    task = asyncio.create_task(sdk.arun("Start the edit.", timeout=10, session=None))
    deadline = time.monotonic() + 2
    while not pid_file.exists() and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
    assert pid_file.exists(), "fixture never dispatched its unknown turn"

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=3)
    # Returning cancellation is the quiescence boundary: a delayed editor must
    # already be dead and cannot mutate the workspace afterward.
    if os.name == "posix":
        from botpipe.processes import _posix_group_is_quiescent

        assert _posix_group_is_quiescent(int(pid_file.read_text()))
    await asyncio.sleep(1.1)
    assert not marker.exists(), "SDK cancellation returned while editing continued"
    client.close()


def _write_probe_schema(root: Path, methods: set[str], *, output_schema: bool = True) -> None:
    (root / "v2").mkdir(parents=True)
    protocol = {"properties": {"method": {"enum": sorted(methods)}}}
    (root / "codex_app_server_protocol.schemas.json").write_text(json.dumps(protocol))

    def properties(**values: dict) -> dict:
        return {"properties": values}

    (root / "v2" / "ThreadStartParams.json").write_text(
        json.dumps(properties(cwd={"type": "string"}, sandbox={"type": "string"}, config={"type": "object"}, dynamicTools={"type": "array"}, developerInstructions={"type": "string"}))
    )
    (root / "v2" / "ThreadResumeParams.json").write_text(
        json.dumps(properties(threadId={"type": "string"}, cwd={"type": "string"}, sandbox={"type": "string"}, config={"type": "object"}, developerInstructions={"type": "string"}))
    )
    turn = {
        "threadId": {"type": "string"},
        "input": {"type": "array"},
        "sandboxPolicy": {"type": "object"},
        "effort": {"type": "string"},
    }
    if output_schema:
        turn["outputSchema"] = {"type": "object"}
    (root / "v2" / "TurnStartParams.json").write_text(json.dumps(properties(**turn)))
    item_variants = [{"properties": {"type": {"enum": [name]}}} for name in sorted(ITEM_TYPES)]
    (root / "v2" / "ItemCompletedNotification.json").write_text(
        json.dumps({"definitions": {"ThreadItem": {"oneOf": item_variants}}})
    )
    (root / "v2" / "ConfigReadResponse.json").write_text(
        json.dumps(
            {
                "definitions": {
                    "Config": {
                        "type": "object",
                        "properties": {
                            "apps": {"type": "object"},
                            "tools": {"type": "object"},
                            "web_search": {"type": "string"},
                        },
                        "additionalProperties": True,
                    }
                }
            }
        )
    )


def test_probe_rejects_missing_required_method_before_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "codex"
    executable.write_bytes(b"probe identity")
    appserver_started = tmp_path / "appserver-started"

    def fake_run(command, *, env, timeout):
        if command[-1] == "--version":
            return "codex-cli fixture\n"
        if tuple(command[-2:]) == ("features", "list"):
            return "shell_tool stable true\n"
        if "generate-json-schema" in command:
            root = Path(command[command.index("--out") + 1])
            _write_probe_schema(
                root,
                {"initialize", "thread/start", "thread/resume", "turn/start"},
            )
            return ""
        appserver_started.write_text("dispatched")
        raise AssertionError(command)

    monkeypatch.setattr("botpipe.capabilities._run", fake_run)
    with pytest.raises(CapabilityError, match=r"methods: turn/interrupt"):
        probe_codex(executable, state_dir=tmp_path / "state")
    assert not appserver_started.exists()


def test_output_schema_falls_back_to_prompt_when_protocol_field_is_optional(
    tmp_path: Path,
) -> None:
    transcript_path = tmp_path / "codex-transcript.jsonl"
    client = CodexAppServerAdapter(
        (sys.executable, str(FIXTURE)),
        env={
            "BOTPIPE_FAKE_TRANSCRIPT": str(transcript_path),
            "BOTPIPE_FAKE_SCENARIO": "complete",
        },
        capabilities=capabilities(output_schema=False),
    )
    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
    }
    try:
        client.start_turn(request(tmp_path, output_schema=schema))
    finally:
        client.close()
    turn = next(item for item in transcript(tmp_path) if item.get("method") == "turn/start")
    assert "outputSchema" not in turn["params"]
    prompt = turn["params"]["input"][0]["text"]
    assert "Return only JSON matching this schema:" in prompt
    assert json.dumps(schema, sort_keys=True) in prompt
