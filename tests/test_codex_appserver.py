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
    ProviderError,
    ProviderInterruptedError,
    ProviderRequest,
    ProviderTimeoutError,
    receipt_path,
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
            {"name": "browser_use", "stage": "stable", "enabled": True},
            {"name": "code_mode_host", "stage": "stable", "enabled": True},
            {"name": "fast_mode", "stage": "stable", "enabled": True},
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
    assert config["features.browser_use"] is False
    assert config["features.code_mode_host"] is False
    assert "features.fast_mode" not in config
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
    assert config["features.browser_use"] is False
    assert config["features.code_mode_host"] is False
    assert "features.fast_mode" not in config
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
    monkeypatch.setattr(client, "_send", lambda message, **kwargs: sent.append(message))
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


def test_allowlist_accepts_new_schema_item_until_it_is_observed(tmp_path: Path) -> None:
    client = adapter(tmp_path)
    client._capabilities = replace(
        capabilities(), item_types=capabilities().item_types | {"futureToolItem"}
    )
    try:
        response = client.start_turn(request(tmp_path, preset="generate", tools=()))
    finally:
        client.close()
    assert response.text == "fixture answer"

    from botpipe.codex_appserver import _Turn

    observed = _Turn("thread", "turn", (), None)
    client._record_event(
        observed,
        "item/completed",
        {"item": {"type": "futureToolItem", "id": "future-evidence"}},
    )
    assert isinstance(observed.error, CapabilityError)
    assert "futureToolItem" in str(observed.error)
    assert "future-evidence" in str(observed.error)


def test_stale_receipt_profile_does_not_veto_native_resume(tmp_path: Path) -> None:
    client = adapter(tmp_path)
    resumed = replace(
        request(tmp_path, session_id="thread-fixture"),
        checkpoint={"profile_hash": "profile-from-prior-process"},
    )
    try:
        response = client.start_turn(resumed)
    finally:
        client.close()
    assert response.session_id == "thread-fixture"


def test_named_mcp_tool_enables_only_its_server(tmp_path: Path) -> None:
    client = adapter(tmp_path)
    client._mcp_servers = frozenset({"docs", "other"})
    try:
        client.start_turn(
            request(
                tmp_path,
                preset="generate",
                tools=("mcp:docs/search",),
            )
        )
    finally:
        client.close()

    thread = next(
        item for item in transcript(tmp_path) if item.get("method") == "thread/start"
    )
    assert thread["params"]["config"]['mcp_servers."docs".enabled'] is True
    assert thread["params"]["config"]['mcp_servers."other".enabled'] is False


def test_missing_codex_binary_is_an_actionable_capability_error(tmp_path: Path) -> None:
    client = CodexAppServerAdapter(tmp_path / "missing-codex")
    with pytest.raises(CapabilityError, match=r"Install Codex.*codex\.path"):
        client.probe()


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


def test_concurrent_distinct_threads_share_transport_and_teardown_receipts(
    tmp_path: Path,
) -> None:
    cancelled = threading.Event()
    client = adapter(tmp_path, "concurrent_stall")
    provider = CodexProvider(adapter=client)
    calls = {
        "cancelled": replace(
            request(
                tmp_path,
                session_id="thread-cancelled",
                timeout=30,
                cancel_event=cancelled,
            ),
            operation_id="concurrent-cancelled",
        ),
        "sibling": replace(
            request(tmp_path, session_id="thread-sibling", timeout=30),
            operation_id="concurrent-sibling",
        ),
    }
    errors: dict[str, BaseException] = {}

    def run(name: str) -> None:
        try:
            provider.run(calls[name])
        except BaseException as exc:
            errors[name] = exc

    workers = [threading.Thread(target=run, args=(name,)) for name in calls]
    for worker in workers:
        worker.start()
    deadline = time.monotonic() + 30
    observed: list[dict] = []
    while time.monotonic() < deadline:
        if (tmp_path / "codex-transcript.jsonl").exists():
            observed = transcript(tmp_path)
            if sum(item.get("method") == "turn/start" for item in observed) == 2:
                break
        time.sleep(0.01)
    assert sum(item.get("method") == "turn/start" for item in observed) == 2

    cancelled.set()
    for worker in workers:
        worker.join(timeout=30)
    try:
        assert all(not worker.is_alive() for worker in workers)
        assert isinstance(errors["cancelled"], ProviderInterruptedError)
        assert isinstance(errors["sibling"], ProviderError)

        recorded = transcript(tmp_path)
        methods = [item.get("method") for item in recorded]
        assert methods.count("initialize") == 1
        assert methods.index("turn/interrupt") > max(
            index for index, method in enumerate(methods) if method == "turn/start"
        )
        assert {
            item["params"]["threadId"]
            for item in recorded
            if item.get("method") == "turn/start"
        } == {"thread-cancelled", "thread-sibling"}
        for call in calls.values():
            receipt = json.loads(receipt_path(call).read_text())
            assert receipt["status"] == "turn_acknowledged"
            assert receipt["cleanup"] == {"status": "completed"}
            assert receipt["enforcement"]["audit"] == "no-tool-calls-observed"
    finally:
        client.close()


def test_start_waits_for_in_progress_transport_teardown(tmp_path: Path) -> None:
    client = adapter(tmp_path)
    client._transport_cleanup_lock.acquire()
    entered = threading.Event()
    errors: list[BaseException] = []

    def start() -> None:
        entered.set()
        try:
            client._start()
        except BaseException as exc:
            errors.append(exc)

    worker = threading.Thread(target=start)
    worker.start()
    assert entered.wait(30)
    time.sleep(0.05)
    assert worker.is_alive()
    assert client._process is None
    with client._lock:
        client._closed = True
    client._transport_cleanup_lock.release()
    worker.join(timeout=30)

    assert not worker.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], RuntimeError)


def test_late_turn_ack_cannot_bind_to_or_kill_replacement_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from botpipe.codex_appserver import CodexProtocolError

    class FakeProcess:
        def __init__(self) -> None:
            self.alive = True

        def poll(self):
            return None if self.alive else 0

    class FakeContainment:
        def __init__(self) -> None:
            self.terminations = 0

        def capture_descendant_groups(self, process):
            pass

        def terminate(self, process, *, grace_seconds):
            self.terminations += 1
            process.alive = False

        def ensure_tree_exited(self, process, *, grace_seconds):
            if process.alive:
                self.terminate(process, grace_seconds=grace_seconds)

    client = adapter(tmp_path)
    old_process, new_process = FakeProcess(), FakeProcess()
    old_containment, new_containment = FakeContainment(), FakeContainment()
    client._process = old_process  # type: ignore[assignment]
    client._containment = old_containment  # type: ignore[assignment]
    monkeypatch.setattr(client, "_start", lambda **_kwargs: None)
    ack_ready = threading.Event()
    release_ack = threading.Event()

    def rpc(
        method, params, timeout, cancel_event=None, *, deadline=None, process=None
    ):
        if method == "thread/resume":
            return {"thread": {"id": "thread-late-ack"}}
        if method == "turn/start":
            assert process is old_process
            ack_ready.set()
            assert release_ack.wait(30)
            return {"turn": {"id": "turn-old", "status": "inProgress"}}
        raise AssertionError(method)

    monkeypatch.setattr(client, "_rpc", rpc)
    checkpoints: list[dict] = []
    call = replace(
        request(tmp_path, session_id="thread-late-ack", timeout=30),
        on_checkpoint=checkpoints.append,
    )
    errors: list[BaseException] = []

    def run() -> None:
        try:
            client.start_turn(call)
        except BaseException as exc:
            errors.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    assert ack_ready.wait(30)
    client._kill_transport(CodexProtocolError("old transport stopped"), cleanup_seconds=0)
    with client._transport_cleanup_lock, client._lock:
        client._process = new_process  # type: ignore[assignment]
        client._containment = new_containment  # type: ignore[assignment]
        client._tearing_down_process = None
    release_ack.set()
    worker.join(timeout=30)

    assert not worker.is_alive()
    assert len(errors) == 1
    assert isinstance(errors[0], CodexProtocolError)
    assert "stopped transport" in str(errors[0])
    assert checkpoints[-1]["status"] == "failed"
    assert checkpoints[-1]["cleanup"] == {"status": "completed"}
    assert new_process.poll() is None
    assert new_containment.terminations == 0
    assert not client._turns


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

    checkpoints = []
    with pytest.raises(ProviderTimeoutError, match="turn start"):
        client.start_turn(
            replace(
                request(tmp_path, timeout=0.2),
                on_checkpoint=checkpoints.append,
            )
        )
    client.close()

    assert pid_file.exists(), "fixture never dispatched its unknown turn"
    assert not any(
        item.get("method") == "turn/interrupt" for item in transcript(tmp_path)
    ), "an unknown turn id must not be guessed"
    time.sleep(1.1)
    assert not marker.exists(), "pre-acknowledgement turn survived RPC timeout"
    assert checkpoints[-1]["status"] == "failed"
    assert checkpoints[-1]["cleanup"] == {"status": "completed"}


def test_pre_ack_cleanup_preserves_orphaned_tool_policy_evidence(
    tmp_path: Path,
) -> None:
    client = adapter(tmp_path, "stall_turn_start_disallowed")
    checkpoints = []

    with pytest.raises(CapabilityError, match="disallowed tool 'shell'"):
        client.start_turn(
            replace(
                request(tmp_path, preset="generate", tools=(), timeout=0.2),
                on_checkpoint=checkpoints.append,
            )
        )
    client.close()

    terminal = checkpoints[-1]
    assert terminal["status"] == "failed"
    assert terminal["cleanup"] == {"status": "completed"}
    assert terminal["policy_error"] is True
    assert terminal["enforcement"]["audit"] == "tool-policy-violation"
    assert terminal["audit"][0]["data"]["item"]["id"] == (
        "pre-ack-forbidden-command"
    )


def test_completed_orphan_wins_lost_turn_start_ack(tmp_path: Path) -> None:
    client = adapter(tmp_path, "stall_turn_start_complete")
    checkpoints = []
    try:
        response = client.start_turn(
            replace(
                request(tmp_path, timeout=0.2),
                on_checkpoint=checkpoints.append,
            )
        )
    finally:
        client.close()

    assert response.text == "completed before acknowledgement"
    assert response.metadata["turn_id"] == "turn-1"
    assert response.metadata["recovered_from_lost_ack"] is True
    assert checkpoints[-1]["status"] == "response_received"


def test_probe_subprocess_uses_remaining_dispatch_budget(monkeypatch) -> None:
    import subprocess
    from botpipe import capabilities

    timeouts = []

    def stall(command, **kwargs):
        timeouts.append(kwargs["timeout"])
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(capabilities.subprocess, "run", stall)
    with pytest.raises(TimeoutError, match="probe timed out"):
        capabilities._run(
            ["codex", "--version"], env={}, timeout=30,
            deadline=time.monotonic() + 0.25,
        )
    assert 0 < timeouts[0] <= 0.25


def test_setup_and_turn_start_share_one_timeout_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import botpipe.codex_appserver as appserver

    client = adapter(tmp_path)
    clock = [100.0]
    calls = []

    monkeypatch.setattr(appserver.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(client, "_start", lambda **_kwargs: None)
    monkeypatch.setattr(client, "_kill_transport", lambda *_args, **_kwargs: None)

    def rpc(
        method, params, timeout, cancel_event=None, *, deadline=None, process=None
    ):
        calls.append((method, timeout, deadline))
        if method == "thread/start":
            clock[0] += 0.18
            return {"thread": {"id": "thread-budget"}}
        if method == "turn/start":
            raise TimeoutError("controlled turn/start timeout")
        raise AssertionError(method)

    monkeypatch.setattr(client, "_rpc", rpc)

    with pytest.raises(ProviderTimeoutError, match="turn start"):
        client.start_turn(request(tmp_path, timeout=0.25))

    assert [call[0] for call in calls] == ["thread/start", "turn/start"]
    assert calls[0][1] == pytest.approx(0.25)
    assert calls[1][1] == pytest.approx(0.07)
    assert calls[1][2] == pytest.approx(100.25)


def test_expired_setup_budget_prevents_thread_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import botpipe.codex_appserver as appserver

    original = appserver._tool_config

    def delayed_setup(*args, **kwargs):
        time.sleep(0.12)
        return original(*args, **kwargs)

    monkeypatch.setattr(appserver, "_tool_config", delayed_setup)
    client = adapter(tmp_path)
    client._start()
    try:
        with pytest.raises(ProviderTimeoutError, match="timed out"):
            client.start_turn(request(tmp_path, timeout=0.05))
    finally:
        client.close()

    assert not any(
        item.get("method") in {"thread/start", "turn/start"}
        for item in transcript(tmp_path)
    )


def test_expired_thread_checkpoint_releases_session_lock(tmp_path: Path) -> None:
    client = adapter(tmp_path)
    client._start()

    def delay_thread_bound(checkpoint: dict) -> None:
        if checkpoint.get("status") == "thread_bound":
            time.sleep(0.08)

    first = replace(
        request(tmp_path, timeout=0.05), on_checkpoint=delay_thread_bound
    )
    responses = []
    errors: list[BaseException] = []

    def resume() -> None:
        try:
            responses.append(
                client.start_turn(
                    request(tmp_path, session_id="thread-fixture", timeout=1)
                )
            )
        except BaseException as exc:
            errors.append(exc)

    worker = threading.Thread(target=resume, daemon=True)
    try:
        with pytest.raises(ProviderTimeoutError):
            client.start_turn(first)
        worker.start()
        worker.join(timeout=2)
    finally:
        client.close()

    assert not worker.is_alive(), "expired request retained the session lock"
    assert not errors
    assert responses[0].text == "fixture answer"


def test_terminal_audit_checkpoint_failure_releases_session_lock(tmp_path: Path) -> None:
    client = adapter(tmp_path)

    def fail_audit(checkpoint: dict) -> None:
        if "audit" in checkpoint:
            raise RuntimeError("receipt audit write failed")

    first = replace(request(tmp_path), on_checkpoint=fail_audit)
    try:
        with pytest.raises(RuntimeError, match="audit write failed"):
            client.start_turn(first)
        second = client.start_turn(
            request(tmp_path, session_id="thread-fixture", timeout=1)
        )
    finally:
        client.close()
    assert second.text == "fixture answer"


def test_cleanup_failure_checkpoints_every_affected_turn(tmp_path: Path) -> None:
    from botpipe.codex_appserver import CodexProtocolError, _Turn

    client = adapter(tmp_path)
    class FakeProcess:
        pid = 123

        def poll(self):
            return None

    process = FakeProcess()

    class BrokenContainment:
        def capture_descendant_groups(self, _process):
            pass

        def terminate(self, _process, *, grace_seconds):
            raise RuntimeError("process inspection unavailable")

        def ensure_tree_exited(self, _process, *, grace_seconds):
            raise RuntimeError("cleanup unverified")

    updates: dict[str, list[dict]] = {"one": [], "two": []}
    for name in updates:
        turn = _Turn(
            f"thread-{name}",
            f"turn-{name}",
            None,
            None,
            updates[name].append,
        )
        client._turns[(turn.thread_id, turn.turn_id)] = turn
    client._process = process
    client._containment = BrokenContainment()  # type: ignore[assignment]

    with pytest.raises(CodexProtocolError, match="cleanup was incomplete"):
        client._kill_transport(
            CodexProtocolError("transport failed"),
            cleanup_seconds=0,
        )

    for recorded in updates.values():
        assert recorded[-1]["cleanup"]["status"] == "incomplete"
        assert "process inspection unavailable" in recorded[-1]["cleanup"]["error"]


@pytest.mark.skipif(os.name != "posix", reason="detached POSIX process groups")
def test_cleanup_started_after_parent_exit_is_not_recorded_as_verified(
    tmp_path: Path,
) -> None:
    from botpipe.codex_appserver import CodexProtocolError, _Turn

    class DeadProcess:
        pid = 123

        def poll(self):
            return 0

    class ApparentlyEmptyContainment:
        def capture_descendant_groups(self, process):
            pass

        def ensure_tree_exited(self, process, *, grace_seconds):
            pass

    client = adapter(tmp_path)
    process = DeadProcess()
    updates: list[dict] = []
    turn = _Turn("thread", "turn", None, None, updates.append, process=process)  # type: ignore[arg-type]
    client._process = process  # type: ignore[assignment]
    client._containment = ApparentlyEmptyContainment()  # type: ignore[assignment]
    client._turns[(turn.thread_id, turn.turn_id)] = turn

    with pytest.raises(CodexProtocolError, match="detached descendants"):
        client._kill_transport(
            CodexProtocolError("parent exited"),
            expected_process=process,  # type: ignore[arg-type]
        )

    assert updates[-1]["cleanup"]["status"] == "incomplete"
    assert "after the app-server exited" in updates[-1]["cleanup"]["error"]


def test_shared_transport_failure_preserves_authoritative_completed_turn(
    tmp_path: Path,
) -> None:
    from botpipe.codex_appserver import CodexProtocolError, _Turn

    client = adapter(tmp_path)
    completed = _Turn("thread-complete", "turn-complete", None, None)
    active = _Turn("thread-active", "turn-active", None, None)
    completed.completed = True
    client._turns[(completed.thread_id, completed.turn_id)] = completed
    client._turns[(active.thread_id, active.turn_id)] = active

    failure = CodexProtocolError("shared transport stopped")
    client._fail_transport(failure)

    assert completed.error is None
    assert active.error is failure


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

    def fake_run(command, *, env, timeout, deadline=None):
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
