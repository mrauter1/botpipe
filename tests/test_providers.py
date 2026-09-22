from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

import botpipe.providers as provider_module

from botpipe.policy import NetworkMode, OperationKind, Policy, SandboxMode
from botpipe.providers import (
    CapabilityError,
    ClaudeProvider,
    CodexProvider,
    FakeProvider,
    PiProvider,
    ProviderError,
    ProviderInterruptedError,
    ProviderPolicyError,
    ProviderRequest,
    ProviderResponse,
    ProviderTimeoutError,
    receipt_path,
)
from botpipe.recovery import Completed


def request(tmp_path: Path, **changes: object) -> ProviderRequest:
    values = dict(
        operation_id="scope/turn:1",
        prompt="hello",
        workspace=tmp_path,
        session_id=None,
        output_schema=None,
        policy=Policy(),
        artifacts={},
        receipt_dir=tmp_path / "receipts",
        timeout=2,
        attempt=1,
    )
    values.update(changes)
    return ProviderRequest(**values)  # type: ignore[arg-type]


def executable(tmp_path: Path, body: str) -> tuple[str, ...]:
    script = tmp_path / "provider.py"
    script.write_text(body, encoding="utf-8")
    return sys.executable, str(script)


def test_native_stream_capture_fails_at_bounded_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(provider_module, "_MAX_NATIVE_STREAM_BYTES", 1024)
    command = executable(
        tmp_path,
        "import sys\nsys.stdout.write('x' * 2048)\nsys.stdout.flush()\n",
    )

    with pytest.raises(ProviderError, match="capture limit"):
        CodexProvider(command).run(request(tmp_path))

    assert json.loads(receipt_path(request(tmp_path)).read_text())["status"] == "failed"


def test_codex_retains_raw_receipt_and_recovers_without_dispatch(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "calls"
    command = executable(
        tmp_path,
        f"""import json, pathlib
p=pathlib.Path({str(marker)!r}); p.write_text((p.read_text() if p.exists() else "")+"x")
print(json.dumps({{"type":"thread.started","thread_id":"thread-7"}}))
print(json.dumps({{"type":"item.completed","item":{{"type":"agent_message","text":"progress"}}}}))
print(json.dumps({{"type":"item.completed","item":{{"type":"agent_message","text":"done"}}}}))
print(json.dumps({{"type":"turn.completed","usage":{{"input_tokens":3,"output_tokens":2}}}}))
""",
    )
    provider = CodexProvider(command)
    req = request(tmp_path, output_schema={"type": "object"})

    response = provider.run(req)
    recovered = provider.recover(req)
    replayed = provider.run(req)

    assert response.text == "done"
    assert response.session_id == "thread-7"
    assert response.usage["input_tokens"] == 3
    assert recovered == Completed(response)
    assert replayed == response
    assert marker.read_text() == "x"
    receipt = json.loads(receipt_path(req).read_text())
    assert receipt["status"] == "completed"
    assert (
        (req.receipt_dir / receipt["raw"]["stdout"]).read_text().startswith('{"type"')
    )
    assert receipt["emission"]["structured_output"] == "native"


def test_claude_emits_settings_and_reports_schema_fallback(tmp_path: Path) -> None:
    command = executable(
        tmp_path,
        """import json
print(json.dumps({"result":"ok","session_id":"session-c","usage":{"input_tokens":4}}))
""",
    )
    req = request(
        tmp_path,
        output_schema={"type": "string"},
        policy=Policy(
            network=NetworkMode.LIMITED,
            network_domains=("api.example.com",),
            allow_write=("generated",),
            deny_read=("secret",),
        ),
    )
    response = ClaudeProvider(command, native_schema=False).run(req)
    receipt = json.loads(receipt_path(req).read_text())
    settings = json.loads(
        (req.receipt_dir / receipt["emission"]["settings"]).read_text()
    )
    assert response == ProviderResponse(
        "ok", "session-c", {"input_tokens": 4}, response.metadata
    )
    assert response.metadata["structured_output"] == "prompt_only"
    assert settings["sandbox"]["network"]["allowedDomains"] == ["api.example.com"]
    assert settings["sandbox"]["network"]["strictAllowlist"] is True
    assert settings["sandbox"]["filesystem"]["denyRead"] == [
        str((tmp_path / "secret").resolve())
    ]


def test_claude_uses_native_schema_and_enforces_read_only(tmp_path: Path) -> None:
    command = executable(
        tmp_path,
        """import json
print(json.dumps({"structured_output":{"ok":True},"session_id":"s"}))
""",
    )
    req = request(
        tmp_path,
        output_schema={"type": "object"},
        policy=Policy(sandbox_mode=SandboxMode.READ_ONLY),
    )
    response = ClaudeProvider(command).run(req)
    receipt = json.loads(receipt_path(req).read_text())
    settings = json.loads(
        (req.receipt_dir / receipt["emission"]["settings"]).read_text()
    )
    assert json.loads(response.text) == {"ok": True}
    assert response.metadata["structured_output"] == "native"
    assert settings["sandbox"]["failIfUnavailable"] is True
    assert settings["sandbox"]["allowUnsandboxedCommands"] is False
    assert str(tmp_path.resolve()) in settings["sandbox"]["filesystem"]["denyWrite"]
    assert "Edit" in settings["permissions"]["deny"]


def test_claude_grants_exact_declared_immutable_read(tmp_path: Path) -> None:
    snapshot = tmp_path.parent / "state" / "snapshot.json"
    command = executable(tmp_path, 'import json\nprint(json.dumps({"result":"ok"}))\n')
    req = request(tmp_path, reads=(snapshot,))
    ClaudeProvider(command).run(req)
    receipt = json.loads(receipt_path(req).read_text())
    settings = json.loads(
        (req.receipt_dir / receipt["emission"]["settings"]).read_text()
    )
    assert settings["sandbox"]["filesystem"]["allowRead"] == [str(snapshot.resolve())]
    assert (
        f"Read(//{str(snapshot.resolve()).lstrip('/')})"
        in settings["permissions"]["allow"]
    )


def test_claude_error_payload_is_a_provider_failure(tmp_path: Path) -> None:
    command = executable(
        tmp_path,
        'import json\nprint(json.dumps({"is_error":True,"result":"denied"}))\n',
    )
    req = request(tmp_path)
    with pytest.raises(ProviderError, match="Claude reported an error"):
        ClaudeProvider(command).run(req)
    assert json.loads(receipt_path(req).read_text())["status"] == "failed"


def test_uncertain_started_attempt_is_never_resent(tmp_path: Path) -> None:
    req = request(tmp_path)
    path = receipt_path(req)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "operation_id": req.operation_id,
                "attempt": 1,
                "status": "running",
                "pid": 99999999,
            }
        )
    )
    provider = CodexProvider(("does-not-matter",))
    with pytest.raises(ProviderInterruptedError, match="refusing to resend") as error:
        provider.run(req)
    assert error.value.process_alive is False


def test_new_attempt_refuses_unverifiable_prior_and_reuses_prior_completion(
    tmp_path: Path,
) -> None:
    first = request(tmp_path)
    first_path = receipt_path(first)
    first_path.parent.mkdir(parents=True)
    first_path.write_text(
        json.dumps(
            {"operation_id": first.operation_id, "attempt": 1, "status": "starting"}
        )
    )
    second = request(tmp_path, attempt=2)
    provider = CodexProvider(("does-not-matter",))
    with pytest.raises(ProviderInterruptedError, match="no verifiable process id"):
        provider.run(second)

    expected = ProviderResponse("already done", "session-1", {"input_tokens": 2}, {})
    first_path.write_text(
        json.dumps(
            {
                "operation_id": first.operation_id,
                "attempt": 1,
                "status": "completed",
                "response": {
                    "text": expected.text,
                    "session_id": expected.session_id,
                    "usage": expected.usage,
                    "metadata": {},
                },
            }
        )
    )
    assert provider.run(second) == expected
    assert not receipt_path(second).exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group recovery fence")
def test_retry_fence_detects_live_descendant_after_group_leader_exits(
    tmp_path: Path,
) -> None:
    child_pid_file = tmp_path / "orphan.pid"
    child_code = (
        "import os, pathlib, signal, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"pathlib.Path({str(child_pid_file)!r}).write_text(str(os.getpid())); "
        "time.sleep(30)"
    )
    command = executable(
        tmp_path,
        f"""import pathlib, subprocess, sys, time
subprocess.Popen([sys.executable, "-c", {child_code!r}])
marker = pathlib.Path({str(child_pid_file)!r})
deadline = time.monotonic() + 2
while not marker.exists() and time.monotonic() < deadline:
    time.sleep(.01)
""",
    )
    leader = subprocess.Popen(command, start_new_session=True)
    leader.wait(timeout=3)
    assert child_pid_file.exists()
    try:
        first = request(tmp_path)
        path = receipt_path(first)
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps(
                {
                    "operation_id": first.operation_id,
                    "attempt": 1,
                    "status": "running",
                    "pid": leader.pid,
                    "process_group": leader.pid,
                }
            )
        )
        second = request(tmp_path, attempt=2)
        with pytest.raises(ProviderInterruptedError, match="still running") as error:
            CodexProvider(("does-not-matter",)).run(second)
        assert error.value.process_alive is True
    finally:
        try:
            os.killpg(leader.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def test_codex_fails_closed_for_unenforceable_read_denial(tmp_path: Path) -> None:
    req = request(tmp_path, policy=Policy(deny_read=("secret",)))
    with pytest.raises(ProviderPolicyError, match="deny_read"):
        CodexProvider(("does-not-matter",)).run(req)
    assert not receipt_path(req).exists()


def test_codex_resume_uses_prompt_schema_fallback_and_correct_order(
    tmp_path: Path,
) -> None:
    provider = CodexProvider(("codex", "exec"))
    req = request(tmp_path, session_id="thread-1", output_schema={"type": "string"})
    command, _, emission = provider._build(req, req.policy.effective())
    assert command[:3] == ["codex", "exec", "resume"]
    assert command[-2:] == ["thread-1", "-"]
    assert "--output-schema" not in command
    assert emission["structured_output"] == "prompt_only"


def test_codex_rejects_narrow_write_roots_it_cannot_enforce(tmp_path: Path) -> None:
    req = request(tmp_path, policy=Policy(allow_write=("generated",)))
    with pytest.raises(ProviderPolicyError, match="cannot narrow"):
        CodexProvider(("does-not-matter",)).run(req)


def test_declared_artifact_parent_is_added_to_codex_writable_roots(
    tmp_path: Path,
) -> None:
    destination = tmp_path.parent / "run-state" / "artifacts" / "report.md"
    provider = CodexProvider(("codex", "exec"))
    req = request(tmp_path, artifacts={"report": destination})
    command, _, _ = provider._build(req, req.policy.effective())
    roots_arg = next(arg for arg in command if "writable_roots=" in arg)
    assert str(destination.parent.resolve()) in roots_arg


@pytest.mark.parametrize(
    "provider", [CodexProvider(("codex", "exec")), ClaudeProvider(("claude",))]
)
def test_read_only_rejects_declared_artifact_writes(
    tmp_path: Path, provider: object
) -> None:
    req = request(
        tmp_path,
        policy=Policy(sandbox_mode=SandboxMode.READ_ONLY),
        artifacts={"report": tmp_path.parent / "state" / "report.md"},
    )
    with pytest.raises(ProviderPolicyError, match="artifact"):
        provider.run(req)  # type: ignore[attr-defined]


def test_timeout_kills_process_and_records_failure(tmp_path: Path) -> None:
    command = executable(tmp_path, "import time\ntime.sleep(10)\n")
    req = request(tmp_path, timeout=0.05)
    with pytest.raises(ProviderTimeoutError):
        ClaudeProvider(command).run(req)
    receipt = json.loads(receipt_path(req).read_text())
    assert receipt["status"] == "failed"
    assert "timed out" in receipt["error"]


def test_codex_persists_session_before_timed_out_process_finishes(
    tmp_path: Path,
) -> None:
    command = executable(
        tmp_path,
        """import json, time
print(json.dumps({"type":"thread.started","thread_id":"early-session"}), flush=True)
time.sleep(10)
""",
    )
    req = request(tmp_path, timeout=0.05)
    with pytest.raises(ProviderTimeoutError):
        CodexProvider(command).run(req)
    receipt = json.loads(receipt_path(req).read_text())
    assert receipt["session_id"] == "early-session"
    assert "session_known_at" in receipt
    raw = (req.receipt_dir / receipt["raw"]["stdout"]).read_text()
    assert "early-session" in raw


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group cleanup")
def test_timeout_kills_child_that_ignores_term_after_parent_exits(
    tmp_path: Path,
) -> None:
    child_pid_file = tmp_path / "child.pid"
    child_code = (
        "import os, pathlib, signal, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"pathlib.Path({str(child_pid_file)!r}).write_text(str(os.getpid())); "
        "time.sleep(30)"
    )
    command = executable(
        tmp_path,
        f"""import pathlib, subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", {child_code!r}])
deadline = time.monotonic() + 2
marker = pathlib.Path({str(child_pid_file)!r})
while not marker.exists() and time.monotonic() < deadline:
    time.sleep(.01)
time.sleep(30)
""",
    )
    req = request(tmp_path, timeout=0.3)
    child_pid: int | None = None
    try:
        with pytest.raises(ProviderTimeoutError):
            ClaudeProvider(command).run(req)
        assert child_pid_file.exists(), (
            "child did not install its SIGTERM handler before timeout"
        )
        child_pid = int(child_pid_file.read_text())

        def child_is_running() -> bool:
            stat = Path(f"/proc/{child_pid}/stat")
            if stat.exists():
                # A zombie has terminated and cannot execute effects; its
                # init-owned process entry can briefly remain visible.
                return stat.read_text().split()[2] != "Z"
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                return False
            return True

        deadline = time.monotonic() + 2
        while child_is_running() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not child_is_running()
    finally:
        if child_pid is not None:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_fake_provider_supports_values_and_artifact_callbacks(tmp_path: Path) -> None:
    def callback(req: ProviderRequest) -> dict[str, bool]:
        req.artifacts["report"].write_text("created")
        return {"ok": True}

    fake = FakeProvider(["first", callback])
    first = fake.run(request(tmp_path))
    target = tmp_path / "report.md"
    second = fake.run(
        request(tmp_path, operation_id="two", artifacts={"report": target})
    )
    assert first.text == "first"
    assert json.loads(second.text) == {"ok": True}
    assert target.read_text() == "created"
    assert len(fake.calls) == 2


@pytest.mark.parametrize(
    "provider",
    [CodexProvider(("missing",)), ClaudeProvider(("missing",)), PiProvider(("missing",))],
)
def test_unproved_query_profile_fails_before_dispatch(
    tmp_path: Path, provider: object
) -> None:
    req = request(tmp_path, operation=OperationKind.QUERY)
    with pytest.raises(CapabilityError, match="query"):
        provider.run(req)  # type: ignore[attr-defined]
    assert not req.receipt_dir.exists()


@pytest.mark.parametrize(
    "provider", [CodexProvider(("missing",)), ClaudeProvider(("missing",)), PiProvider(("missing",))]
)
def test_exact_command_grant_requires_native_mediator(
    tmp_path: Path, provider: object
) -> None:
    req = request(
        tmp_path,
        operation=OperationKind.GENERATE,
        allow_commands=(("git", "status", "--short"),),
    )
    with pytest.raises(CapabilityError, match="exact-argv|operation='generate'"):
        provider.run(req)  # type: ignore[attr-defined]
    assert not req.receipt_dir.exists()


def test_claude_tool_free_generation_closes_ambient_surfaces(tmp_path: Path) -> None:
    provider = ClaudeProvider(("claude",))
    req = request(tmp_path, operation=OperationKind.GENERATE)
    provider.validate_request(req)
    command, _, emission = provider._build(req, req.policy.effective())
    settings = json.loads((req.receipt_dir / emission["settings"]).read_text())
    assert "--bare" in command
    assert "--restricted" in command
    assert "--strict-mcp-config" in command
    assert command[command.index("--tools") + 1] == ""
    assert command[command.index("--permission-mode") + 1] == "dontAsk"
    assert "*" in settings["permissions"]["deny"]


def test_pi_tool_free_generation_disables_all_resource_discovery(tmp_path: Path) -> None:
    provider = PiProvider(("pi",))
    req = request(tmp_path, operation="generate", instructions="Answer concisely.")
    provider.validate_request(req)
    command, env, emission = provider._build(req, req.policy.effective())
    assert req.operation is OperationKind.GENERATE
    for flag in (
        "--no-tools",
        "--no-extensions",
        "--no-skills",
        "--no-prompt-templates",
        "--no-themes",
        "--no-context-files",
        "--no-approve",
    ):
        assert flag in command
    assert env["PI_OFFLINE"] == "1"
    assert emission["tool_profile"] == "none"


def test_request_rejects_shell_strings_and_freezes_settings(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="argv sequences"):
        request(tmp_path, allow_commands=("git status",))
    req = request(tmp_path, settings={"profile": "x"})
    with pytest.raises(TypeError):
        req.settings["profile"] = "y"  # type: ignore[index]


def test_request_rejects_nonfinite_or_oversized_output_schema_before_dispatch(
    tmp_path: Path,
) -> None:
    with pytest.raises(TypeError, match="finite plain JSON"):
        request(tmp_path, output_schema={"minimum": float("nan")})
    with pytest.raises(TypeError, match="finite plain JSON"):
        request(tmp_path, output_schema={"type": object()})
    with pytest.raises(ValueError, match="1 MB"):
        request(tmp_path, output_schema={"description": "x" * 1_000_001})
    assert not (tmp_path / "receipts").exists()
