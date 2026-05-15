from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from botpipe.core.errors import ProviderExecutionError, exception_failure_context, exception_retry_kind
from botpipe.core.provider_policy import (
    PermissionPolicy,
    ProviderPolicy,
    ProviderPolicyValidationConfig,
    SandboxPolicy,
    WorkspaceFilesystemPolicy,
    WorkspacePolicy,
)
from botpipe.core.prompts import ResolvedPrompt
from botpipe.core.providers.models import LLMRequest, ProducerRequest, TokenUsage, VerifierRequest
from botpipe.core.providers.parsing import parse_outcome_json
from botpipe.core.providers.rendered import RenderedLLMProvider
from botpipe.core.providers.turns import RenderedProviderTurn
from botpipe.core.stores.protocols import SessionBinding
from botpipe.runtime.config import (
    ClaudeProviderConfig,
    CodexProviderConfig,
    ConfigError,
    ProviderConfig,
    ResolvedRuntimeConfig,
    RuntimeConfig,
)
from botpipe.runtime.providers._common import (
    build_session_binding,
    communicate_text_subprocess,
    ensure_session_provider_match,
    format_subprocess_streams,
    require_prompt_text,
    terminate_text_subprocess,
)
from botpipe.runtime.providers.claude import (
    ClaudeTransport,
    claude_permission_args,
    parse_claude_exec_json,
    verify_claude_code_capabilities,
)
from botpipe.runtime.providers.claude_policy import ClaudeCapabilities
import botpipe.runtime.providers.claude as claude_runtime_provider
from botpipe.runtime.providers.codex import (
    CodexCLICommand,
    CodexTransport,
    resolve_codex_cli_commands,
    parse_codex_exec_json,
    verify_codex_exec_capabilities,
)
import botpipe.runtime.providers.codex as codex_runtime_provider


CODEX_START_HELP = "--json\n-m, --model <MODEL>\n--dangerously-bypass-approvals-and-sandbox\n"
CODEX_RESUME_HELP = "--json\n-m, --model <MODEL>\n--dangerously-bypass-approvals-and-sandbox\n"
CLAUDE_HEADLESS_HELP = "--print\n-p\n--output-format\n--resume\n--model\n--settings\n--add-dir\n"
CLAUDE_HELP = (
    "--print\n-p\n--output-format\n--resume\n--model\n--settings\n--add-dir\n"
    "--allowedTools\n--dangerously-skip-permissions\n"
)


@pytest.fixture(autouse=True)
def _clear_provider_caches() -> None:
    codex_runtime_provider._probe_codex_exec_surface.cache_clear()
    claude_runtime_provider._probe_claude_help_surface.cache_clear()


def _completed(*, args: list[str], stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=args, returncode=returncode, stdout=stdout, stderr=stderr)


def _config(
    *,
    provider_name: str = "codex",
    codex_effort: str | None = None,
    claude_effort: str | None = None,
    claude_permission_strategy: str = "inherit",
) -> ResolvedRuntimeConfig:
    return ResolvedRuntimeConfig(
        provider=ProviderConfig(
            name=provider_name,
            codex=CodexProviderConfig(model="gpt-test", model_effort=codex_effort),
            claude=ClaudeProviderConfig(
                model="claude-test",
                effort=claude_effort,
                permission_strategy=claude_permission_strategy,
            ),
        ),
        runtime=RuntimeConfig(max_steps=5),
    )


def _placeholder_session() -> SessionBinding:
    return SessionBinding(ref_name="main", scope=None, session_id="main:global:1")


def _provider_session(provider: str, session_id: str = "session-1") -> SessionBinding:
    return SessionBinding(
        ref_name="main",
        scope=None,
        session_id=session_id,
        metadata={
            "provider": provider,
            "mode": "persistent",
            "provider_metadata": {"trace": "resume"},
            "model_override": "model-x",
            "effort_override": None,
        },
    )


def _producer_request(*, prompt_text: str = "prompt", session: SessionBinding | None = None) -> ProducerRequest:
    return ProducerRequest(
        step_name="produce",
        producer_prompt=ResolvedPrompt(path="prompt.md", text=prompt_text),
        context=object(),
        artifacts=object(),
        session=session,
    )


def _verifier_request(
    *,
    prompt_text: str = "verify",
    raw_output: str = "producer output",
    session: SessionBinding | None = None,
) -> VerifierRequest:
    return VerifierRequest(
        step_name="verify",
        verifier_prompt=ResolvedPrompt(path="verify.md", text=prompt_text),
        producer_raw_output=raw_output,
        context=object(),
        artifacts=object(),
        session=session,
    )


def _llm_request(*, prompt_text: str = "ask", session: SessionBinding | None = None) -> LLMRequest:
    return LLMRequest(
        step_name="ask",
        prompt=ResolvedPrompt(path="ask.md", text=prompt_text),
        context=object(),
        artifacts=object(),
        session=session,
    )


def _rendered_turn(
    *,
    step_name: str = "turn",
    turn_kind: str = "producer",
    prompt_text: str = "prompt",
    session: SessionBinding | None = None,
    expected_response: str = "raw_text",
    policy: ProviderPolicy | None = None,
    run_folder: Path | None = None,
    workspace_root: Path | None = None,
    step_execution_id: str | None = None,
    runtime_event_sink=None,
    attempt: int = 1,
) -> RenderedProviderTurn:
    return RenderedProviderTurn(
        step_name=step_name,
        turn_kind=turn_kind,
        prompt_text=prompt_text,
        session=session,
        expected_response=expected_response,
        policy=policy,
        run_folder=run_folder,
        workspace_root=workspace_root,
        step_execution_id=step_execution_id,
        runtime_event_sink=runtime_event_sink,
        attempt=attempt,
    )


class _AsyncProcessStub:
    def __init__(
        self,
        *,
        stdout: str,
        stderr: str = "",
        returncode: int = 0,
        seen_inputs: list[bytes | None] | None = None,
    ) -> None:
        self._stdout = stdout.encode("utf-8")
        self._stderr = stderr.encode("utf-8")
        self.returncode = returncode
        self._seen_inputs = seen_inputs

    async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
        if self._seen_inputs is not None:
            self._seen_inputs.append(input)
        return self._stdout, self._stderr


class _AsyncBytesWriterStub:
    def __init__(self, seen_inputs: list[bytes | None] | None = None) -> None:
        self._seen_inputs = seen_inputs
        self._buffer = bytearray()

    def write(self, data: bytes) -> None:
        self._buffer.extend(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        if self._seen_inputs is not None:
            self._seen_inputs.append(bytes(self._buffer) if self._buffer else None)

    async def wait_closed(self) -> None:
        return None


class _BrokenPipeAsyncBytesWriterStub(_AsyncBytesWriterStub):
    async def drain(self) -> None:
        raise BrokenPipeError("stdin closed")


class _AsyncLineReaderStub:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = list(lines)

    async def readline(self) -> bytes:
        if not self._lines:
            return b""
        return self._lines.pop(0)

    async def read(self, n: int = -1) -> bytes:
        if not self._lines:
            return b""
        if n is None or n < 0:
            payload = b"".join(self._lines)
            self._lines.clear()
            return payload
        chunk = self._lines[0]
        if len(chunk) <= n:
            return self._lines.pop(0)
        self._lines[0] = chunk[n:]
        return chunk[:n]


class _AsyncBytesReaderStub:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    async def read(self) -> bytes:
        return self._payload


class _StreamingAsyncProcessStub:
    def __init__(
        self,
        *,
        stdout_lines: list[str],
        stderr: str = "",
        returncode: int = 0,
        seen_inputs: list[bytes | None] | None = None,
    ) -> None:
        self.stdin = _AsyncBytesWriterStub(seen_inputs)
        self.stdout = _AsyncLineReaderStub([line.encode("utf-8") for line in stdout_lines])
        self.stderr = _AsyncBytesReaderStub(stderr.encode("utf-8"))
        self.returncode = returncode

    async def wait(self) -> int:
        return self.returncode


class _TerminableStreamingAsyncProcessStub:
    def __init__(
        self,
        *,
        stdout_lines: list[str],
        stderr: str = "",
        seen_inputs: list[bytes | None] | None = None,
    ) -> None:
        self.stdin = _AsyncBytesWriterStub(seen_inputs)
        self.stdout = _AsyncLineReaderStub([line.encode("utf-8") for line in stdout_lines])
        self.stderr = _AsyncBytesReaderStub(stderr.encode("utf-8"))
        self.returncode: int | None = None
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls = 0

    def terminate(self) -> None:
        self.terminate_calls += 1
        self.returncode = -15

    def kill(self) -> None:
        self.kill_calls += 1
        self.returncode = -9

    async def wait(self) -> int:
        self.wait_calls += 1
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


class _FailingAsyncBytesReaderStub:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def read(self, n: int = -1) -> bytes:
        raise self._exc


class _FailingStdoutAsyncProcessStub:
    def __init__(
        self,
        *,
        stdout_exc: Exception,
        seen_inputs: list[bytes | None] | None = None,
    ) -> None:
        self.stdin = _AsyncBytesWriterStub(seen_inputs)
        self.stdout = _FailingAsyncBytesReaderStub(stdout_exc)
        self.stderr = _AsyncBytesReaderStub(b"")
        self.returncode: int | None = None
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls = 0

    def terminate(self) -> None:
        self.terminate_calls += 1
        self.returncode = -15

    def kill(self) -> None:
        self.kill_calls += 1
        self.returncode = -9

    async def wait(self) -> int:
        self.wait_calls += 1
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


class _CancellableAsyncProcessStub:
    def __init__(self) -> None:
        self.returncode: int | None = None
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls = 0
        self.seen_inputs: list[bytes | None] = []
        self._wait_released = asyncio.Event()

    async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
        self.seen_inputs.append(input)
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            raise

    def terminate(self) -> None:
        self.terminate_calls += 1

    def kill(self) -> None:
        self.kill_calls += 1
        self.returncode = -9
        self._wait_released.set()

    async def wait(self) -> int:
        self.wait_calls += 1
        await self._wait_released.wait()
        if self.returncode is None:
            self.returncode = -15
        return self.returncode


class _LookupRacyProcessStub:
    def __init__(self, *, raise_on_kill: bool = False) -> None:
        self.returncode: int | None = None
        self.raise_on_kill = raise_on_kill
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls = 0

    def terminate(self) -> None:
        self.terminate_calls += 1
        if not self.raise_on_kill:
            raise ProcessLookupError

    def kill(self) -> None:
        self.kill_calls += 1
        if self.raise_on_kill:
            raise ProcessLookupError
        self.returncode = -9

    async def wait(self) -> int:
        self.wait_calls += 1
        if self.raise_on_kill and self.wait_calls == 1:
            raise asyncio.TimeoutError
        self.returncode = 0 if self.returncode is None else self.returncode
        return self.returncode


def test_require_prompt_text_rejects_missing_text() -> None:
    with pytest.raises(ProviderExecutionError, match=r"provider 'codex'.*step 'plan'"):
        require_prompt_text(ResolvedPrompt(path="plan.md", text=None), "codex", "plan")


def test_format_subprocess_streams_renders_empty_streams() -> None:
    assert format_subprocess_streams("", "") == "[empty stdout/stderr]"


def test_ensure_session_provider_match_rejects_cross_provider_resume() -> None:
    with pytest.raises(ProviderExecutionError, match="resuming across providers is forbidden"):
        ensure_session_provider_match("codex", _provider_session("claude"))


def test_build_session_binding_preserves_slot_and_canonical_metadata() -> None:
    binding = build_session_binding(
        _placeholder_session(),
        session_id="provider-session-9",
        provider_name="codex",
        provider_metadata={"trace": "ok", "thread_id": "hidden"},
        model="gpt-test",
        effort="medium",
    )

    assert binding.ref_name == "main"
    assert binding.scope is None
    assert binding.session_id == "provider-session-9"
    assert binding.metadata["provider"] == "codex"
    assert binding.metadata["mode"] == "persistent"
    assert binding.metadata["provider_metadata"] == {"trace": "ok"}
    assert binding.metadata["model_override"] == "gpt-test"
    assert binding.metadata["effort_override"] == "medium"


def test_build_session_binding_omits_per_turn_usage_fields_from_persisted_session_metadata() -> None:
    binding = build_session_binding(
        _placeholder_session(),
        session_id="provider-session-10",
        provider_name="claude",
        provider_metadata={
            "usage": {"input_tokens": 9},
            "token_usage": {"total_tokens": 12},
            "provider_usage": {"output_tokens": 3},
            "stop_reason": "done",
        },
        model="claude-test",
        effort=None,
    )

    assert binding.metadata["provider_metadata"] == {"stop_reason": "done"}
    assert binding.provider_metadata == {"stop_reason": "done"}


def test_parse_outcome_json_accepts_plain_object() -> None:
    outcome = parse_outcome_json('{"tag":"done","payload":{"x":1}}')

    assert outcome.tag == "done"
    assert outcome.reason == ""
    assert outcome.payload == {"x": 1}
    assert outcome.raw_output == '{"tag":"done","payload":{"x":1}}'


def test_parse_outcome_json_accepts_canonical_outcome_envelope() -> None:
    raw = (
        '{"outcome":{"tag":"question","payload":{},"route_fields":{"questions":["Proceed?"],"reason":null}}}'
    )

    outcome = parse_outcome_json(raw)

    assert outcome.tag == "question"
    assert outcome.payload == {}
    assert outcome.route_fields == {"questions": ["Proceed?"], "reason": None}
    assert outcome.question == "Proceed?"
    assert outcome.reason == ""
    assert outcome.raw_output == raw


def test_parse_outcome_json_prefers_canonical_route_fields_over_legacy_top_level_fields() -> None:
    outcome = parse_outcome_json(
        '{"outcome":{"tag":"question","payload":{},"route_fields":{"questions":["Canonical?"],"reason":"canonical"}},"question":"Legacy?","reason":"legacy"}'
    )

    assert outcome.route_fields == {"questions": ["Canonical?"], "reason": "canonical"}
    assert outcome.question == "Canonical?"
    assert outcome.reason == "canonical"


def test_parse_outcome_json_ignores_legacy_reason_when_canonical_reason_is_null() -> None:
    outcome = parse_outcome_json(
        '{"outcome":{"tag":"question","payload":{},"route_fields":{"questions":["Canonical?"],"reason":null}},"reason":"legacy"}'
    )

    assert outcome.route_fields == {"questions": ["Canonical?"], "reason": None}
    assert outcome.question == "Canonical?"
    assert outcome.reason == ""


def test_parse_outcome_json_does_not_project_legacy_question_for_canonical_route_fields() -> None:
    outcome = parse_outcome_json(
        '{"outcome":{"tag":"question","payload":{},"route_fields":{}},"question":"Legacy?"}'
    )

    assert outcome.route_fields == {}
    assert outcome.question is None
    assert outcome.reason == ""


def test_parse_outcome_json_accepts_fenced_json_block() -> None:
    raw = '```json\n{"tag":"question","question":"Proceed?"}\n```'

    outcome = parse_outcome_json(raw)

    assert outcome.tag == "question"
    assert outcome.reason == ""
    assert outcome.question == "Proceed?"
    assert outcome.payload == {}
    assert outcome.raw_output == raw


def test_parse_outcome_json_accepts_last_json_message_after_status_text() -> None:
    raw = 'I updated the files and verified them.\n\n{"outcome":{"tag":"accepted","payload":{},"route_fields":{}}}'

    outcome = parse_outcome_json(raw)

    assert outcome.tag == "accepted"
    assert outcome.payload == {}
    assert outcome.raw_output == raw


def test_parse_outcome_json_rejects_invalid_json() -> None:
    with pytest.raises(ProviderExecutionError, match="malformed outcome JSON"):
        parse_outcome_json("{not-json}")


def test_parse_outcome_json_rejects_missing_tag() -> None:
    with pytest.raises(ProviderExecutionError, match="must contain a non-empty string 'tag'"):
        parse_outcome_json('{"reason":"missing"}')


def test_parse_outcome_json_accepts_missing_reason_for_authored_routes() -> None:
    blocked = parse_outcome_json('{"tag":"blocked"}')
    failed = parse_outcome_json('{"tag":"failed"}')

    assert blocked.reason == ""
    assert failed.reason == ""


def test_parse_outcome_json_rejects_question_without_question_field() -> None:
    with pytest.raises(ProviderExecutionError, match="question route without a non-empty question") as exc_info:
        parse_outcome_json('{"tag":"question"}')

    assert exc_info.value.retry_kind == "invalid_payload"
    assert exc_info.value.failure_context is not None
    assert exc_info.value.failure_context.kind == "invalid_payload"
    assert exc_info.value.failure_context.candidate_route == "question"


def test_parse_outcome_json_rejects_non_object_payload() -> None:
    with pytest.raises(ProviderExecutionError, match="field 'payload' must be an object"):
        parse_outcome_json('{"tag":"done","payload":[]}')


def test_parse_codex_exec_json_ignores_malformed_lines_when_output_is_otherwise_valid() -> None:
    stdout = "\n".join(
        (
            "not-json",
            '{"type":"thread.started","thread_id":"codex-session-1"}',
            '{"type":"item.completed","item":{"type":"agent_message","text":"hello"}}',
        )
    )

    assistant_text, session_id, provider_metadata, usage = parse_codex_exec_json(stdout)

    assert assistant_text == "hello"
    assert session_id == "codex-session-1"
    assert provider_metadata == {
        "assistant_message_count": 1,
        "jsonl_event_count": 2,
        "malformed_jsonl_lines": 1,
    }
    assert usage is None


def test_parse_codex_exec_json_extracts_usage_when_present() -> None:
    stdout = "\n".join(
        (
            '{"type":"thread.started","thread_id":"codex-session-1"}',
            '{"type":"response.completed","response":{"usage":{"input_tokens":21,"output_tokens":13,"total_tokens":34,"reasoning_tokens":5}}}',
            '{"type":"item.completed","item":{"type":"agent_message","text":"hello"}}',
        )
    )

    _, _, _, usage = parse_codex_exec_json(stdout)

    assert usage == TokenUsage(
        input_tokens=21,
        output_tokens=13,
        total_tokens=34,
        cached_input_tokens=None,
        reasoning_tokens=5,
        source="codex",
        provider_raw={
            "input_tokens": 21,
            "output_tokens": 13,
            "total_tokens": 34,
            "reasoning_tokens": 5,
        },
    )


def test_parse_codex_exec_json_rejects_missing_assistant_text() -> None:
    stdout = '{"type":"thread.started","thread_id":"codex-session-1"}\n'

    with pytest.raises(ProviderExecutionError, match="did not return assistant text") as exc_info:
        parse_codex_exec_json(stdout)

    failure_context = exception_failure_context(exc_info.value)
    assert failure_context is not None
    assert failure_context.details["provider_failure_stage"] == "adapter_output"
    assert exception_retry_kind(exc_info.value) == "malformed_provider_output"


def test_parse_claude_exec_json_preserves_provider_metadata() -> None:
    result, session_id, provider_metadata, usage = parse_claude_exec_json(
        '{"result":"hello","session_id":"claude-session-1","stop_reason":"end_turn"}'
    )

    assert result == "hello"
    assert session_id == "claude-session-1"
    assert provider_metadata == {"stop_reason": "end_turn"}
    assert usage is None


def test_parse_claude_exec_json_extracts_usage_when_present() -> None:
    _, _, provider_metadata, usage = parse_claude_exec_json(
        '{"result":"hello","session_id":"claude-session-1","usage":{"input_tokens":9,"output_tokens":4,"total_tokens":13,"cached_input_tokens":2},"stop_reason":"end_turn"}'
    )

    assert provider_metadata == {
        "usage": {
            "input_tokens": 9,
            "output_tokens": 4,
            "total_tokens": 13,
            "cached_input_tokens": 2,
        },
        "stop_reason": "end_turn",
    }
    assert usage == TokenUsage(
        input_tokens=9,
        output_tokens=4,
        total_tokens=13,
        cached_input_tokens=2,
        reasoning_tokens=None,
        source="claude",
        provider_raw={
            "input_tokens": 9,
            "output_tokens": 4,
            "total_tokens": 13,
            "cached_input_tokens": 2,
        },
    )


def test_parse_claude_exec_json_rejects_missing_result() -> None:
    with pytest.raises(ProviderExecutionError, match="must contain a string 'result'") as exc_info:
        parse_claude_exec_json('{"session_id":"claude-session-1"}')

    failure_context = exception_failure_context(exc_info.value)
    assert failure_context is not None
    assert failure_context.details["provider_failure_stage"] == "adapter_output"
    assert exception_retry_kind(exc_info.value) == "malformed_provider_output"


def test_claude_permission_args_maps_supported_strategies() -> None:
    assert claude_permission_args(ClaudeProviderConfig(permission_strategy="inherit")) == []
    assert claude_permission_args(ClaudeProviderConfig(permission_strategy="allow_core_tools")) == [
        "--allowedTools",
        "Read,Write,Edit,Glob,Grep,Bash",
    ]
    assert claude_permission_args(ClaudeProviderConfig(permission_strategy="bypass")) == [
        "--dangerously-skip-permissions"
    ]


def test_claude_permission_args_rejects_unknown_strategy() -> None:
    with pytest.raises(ConfigError, match="permission_strategy"):
        claude_permission_args(ClaudeProviderConfig(permission_strategy="unknown"))


def test_verify_codex_exec_capabilities_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(codex_runtime_provider.shutil, "which", lambda name: "/usr/bin/codex")

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if command == ["codex", "exec", "--help"]:
            return _completed(args=command, stdout=CODEX_START_HELP)
        if command == ["codex", "exec", "resume", "--help"]:
            return _completed(args=command, stdout=CODEX_RESUME_HELP)
        raise AssertionError(f"unexpected command: {command!r}")

    monkeypatch.setattr(codex_runtime_provider.subprocess, "run", fake_run)

    verify_codex_exec_capabilities()


def test_verify_codex_exec_capabilities_rejects_missing_required_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(codex_runtime_provider.shutil, "which", lambda name: "/usr/bin/codex")

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if command == ["codex", "exec", "--help"]:
            return _completed(args=command, stdout="--full-auto\n-m, --model <MODEL>\n")
        if command == ["codex", "exec", "resume", "--help"]:
            return _completed(args=command, stdout=CODEX_RESUME_HELP)
        raise AssertionError(f"unexpected command: {command!r}")

    monkeypatch.setattr(codex_runtime_provider.subprocess, "run", fake_run)

    with pytest.raises(ConfigError, match=r"provider 'codex' requires 'codex exec --json' support"):
        verify_codex_exec_capabilities()


def test_verify_claude_code_capabilities_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(claude_runtime_provider.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(
        claude_runtime_provider.subprocess,
        "run",
        lambda command, **_: _completed(args=command, stdout=CLAUDE_HEADLESS_HELP),
    )

    verify_claude_code_capabilities()


def test_verify_claude_code_capabilities_rejects_missing_required_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(claude_runtime_provider.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(
        claude_runtime_provider.subprocess,
        "run",
        lambda command, **_: _completed(args=command, stdout="--print\n-p\n--resume\n--model\n"),
    )

    with pytest.raises(ConfigError, match=r"provider 'claude' requires '--output-format' support"):
        verify_claude_code_capabilities()


def test_verify_claude_code_capabilities_rejects_missing_settings_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(claude_runtime_provider.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(
        claude_runtime_provider.subprocess,
        "run",
        lambda command, **_: _completed(args=command, stdout="--print\n-p\n--output-format\n--resume\n--model\n"),
    )

    with pytest.raises(ConfigError, match=r"provider 'claude' requires '--settings' support"):
        verify_claude_code_capabilities()


def test_verify_claude_code_capabilities_rejects_missing_add_dir_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(claude_runtime_provider.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(
        claude_runtime_provider.subprocess,
        "run",
        lambda command, **_: _completed(
            args=command,
            stdout="--print\n-p\n--output-format\n--resume\n--model\n--settings\n",
        ),
    )

    with pytest.raises(ConfigError, match=r"provider 'claude' requires '--add-dir' support"):
        verify_claude_code_capabilities()


def test_verify_claude_code_capabilities_rejects_missing_allowed_tools_when_strategy_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(claude_runtime_provider.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(
        claude_runtime_provider.subprocess,
        "run",
        lambda command, **_: _completed(args=command, stdout=CLAUDE_HEADLESS_HELP),
    )

    with pytest.raises(ConfigError, match=r"--allowedTools"):
        verify_claude_code_capabilities(ClaudeProviderConfig(permission_strategy="allow_core_tools"))


def test_codex_transport_sends_rendered_prompt_text_to_cli_stdin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []
    prompt_text = "# Step: produce\n\nShared runtime prompt."
    seen_inputs: list[bytes | None] = []
    seen_cwds: list[str | None] = []

    async def fake_create_subprocess_exec(*command: str, **kwargs: object) -> _AsyncProcessStub:
        calls.append(tuple(command))
        cwd = kwargs.get("cwd")
        seen_cwds.append(None if cwd is None else str(cwd))
        return _AsyncProcessStub(
            stdout="\n".join(
                (
                    '{"type":"thread.started","thread_id":"codex-session-1"}',
                    '{"type":"item.completed","item":{"type":"agent_message","text":"producer text"}}',
                )
            ),
            seen_inputs=seen_inputs,
        )

    monkeypatch.setattr(codex_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    transport = CodexTransport(
        commands=CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
        model="gpt-test",
        model_effort=None,
    )

    result = asyncio.run(
        transport.run_turn(
            _rendered_turn(
                step_name="produce",
                prompt_text=prompt_text,
                session=_placeholder_session(),
                workspace_root=tmp_path,
            )
        )
    )

    assert calls == [("codex", "exec", "--json", "--model", "gpt-test")]
    assert seen_inputs == [prompt_text.encode("utf-8")]
    assert seen_cwds == [str(tmp_path)]
    assert result.raw_text == "producer text"
    assert result.session is not None
    assert result.session.session_id == "codex-session-1"
    assert result.metadata["provider_metadata"] == {
        "assistant_message_count": 1,
        "jsonl_event_count": 2,
        "malformed_jsonl_lines": 0,
    }


def test_codex_transport_supports_async_subprocess_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompt_text = "# Step: produce\n\nShared runtime prompt."
    calls: list[tuple[str, ...]] = []
    seen_inputs: list[bytes | None] = []

    async def fake_create_subprocess_exec(*command: str, **_: object) -> _AsyncProcessStub:
        calls.append(tuple(command))
        return _AsyncProcessStub(
            stdout="\n".join(
                (
                    '{"type":"thread.started","thread_id":"codex-session-async"}',
                    '{"type":"item.completed","item":{"type":"agent_message","text":"producer text"}}',
                )
            ),
            seen_inputs=seen_inputs,
        )

    monkeypatch.setattr(codex_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    transport = CodexTransport(
        commands=CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
        model="gpt-test",
        model_effort=None,
    )

    result = asyncio.run(
        transport.run_turn(_rendered_turn(step_name="produce", prompt_text=prompt_text, session=_placeholder_session()))
    )

    assert calls == [("codex", "exec", "--json", "--model", "gpt-test")]
    assert seen_inputs == [prompt_text.encode("utf-8")]
    assert result.raw_text == "producer text"
    assert result.session is not None
    assert result.session.session_id == "codex-session-async"


def test_codex_transport_prefers_native_no_prompt_resume_for_interrupted_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_folder = tmp_path / "run"
    run_folder.mkdir()
    events_file = run_folder / "events.jsonl"
    prompt_text = "# Step: produce\n\nShared runtime prompt."
    prompt_fingerprint = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()
    seq = 0

    def append_event(event_type: str, payload: dict[str, object]) -> None:
        nonlocal seq
        seq += 1
        event = {
            "schema": "botpipe.runtime_event/v1",
            "ts": "2026-05-13T00:00:00+00:00",
            "run_id": "run-test",
            "seq": seq,
            "event_type": event_type,
            **payload,
        }
        with events_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")

    base_payload = {
        "step_name": "produce",
        "step_execution_id": "produce:1",
        "turn_kind": "producer",
        "attempt": 1,
    }
    append_event("provider_attempt_started", dict(base_payload))
    append_event("provider_turn_started", {**base_payload, "prompt_fingerprint": prompt_fingerprint})
    append_event("provider_session_known", {**base_payload, "session_id": "interrupted-session"})

    calls: list[tuple[str, ...]] = []
    seen_inputs: list[bytes | None] = []

    async def fake_create_subprocess_exec(*command: str, **_: object) -> _AsyncProcessStub:
        calls.append(tuple(command))
        return _AsyncProcessStub(
            stdout="\n".join(
                (
                    '{"type":"thread.started","thread_id":"interrupted-session"}',
                    '{"type":"item.completed","item":{"type":"agent_message","text":"resumed text"}}',
                )
            ),
            seen_inputs=seen_inputs,
        )

    monkeypatch.setattr(codex_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    transport = CodexTransport(
        commands=CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
        model="gpt-test",
        model_effort=None,
    )

    result = asyncio.run(
        transport.run_turn(
            _rendered_turn(
                step_name="produce",
                prompt_text=prompt_text,
                session=_placeholder_session(),
                run_folder=run_folder,
                step_execution_id="produce:1",
                runtime_event_sink=lambda event_type, payload: append_event(event_type, dict(payload)),
            )
        )
    )

    assert calls == [("codex", "exec", "resume", "--json", "--model", "gpt-test", "interrupted-session")]
    assert seen_inputs == [None]
    assert result.raw_text == "resumed text"
    assert result.metadata["provider_metadata"]["interrupted_turn_resume"]["mode"] == "provider_native_no_prompt"


def test_codex_transport_streams_session_known_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_events: list[tuple[str, dict[str, object]]] = []
    seen_inputs: list[bytes | None] = []

    async def fake_create_subprocess_exec(*_: str, **__: object) -> _StreamingAsyncProcessStub:
        return _StreamingAsyncProcessStub(
            stdout_lines=[
                '{"type":"thread.started","thread_id":"streamed-session"}\n',
                '{"type":"item.completed","item":{"type":"agent_message","text":"producer text"}}\n',
            ],
            seen_inputs=seen_inputs,
        )

    monkeypatch.setattr(codex_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    transport = CodexTransport(
        commands=CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
        model="gpt-test",
        model_effort=None,
    )

    result = asyncio.run(
        transport.run_turn(
            _rendered_turn(
                step_name="produce",
                prompt_text="prompt",
                session=_placeholder_session(),
                runtime_event_sink=lambda event_type, payload: seen_events.append((event_type, dict(payload))),
            )
        )
    )

    assert seen_inputs == [b"prompt"]
    assert result.session is not None
    assert result.session.session_id == "streamed-session"
    assert any(
        event_type == "provider_session_known" and payload["session_id"] == "streamed-session"
        for event_type, payload in seen_events
    )


def test_codex_transport_accepts_large_jsonl_line_without_stream_limit_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_events: list[tuple[str, dict[str, object]]] = []
    padding = "x" * (codex_runtime_provider._CODEX_STDOUT_CHUNK_SIZE + 1024)
    session_line = json.dumps(
        {
            "type": "thread.started",
            "thread_id": "large-streamed-session",
            "padding": padding,
        }
    )

    async def fake_create_subprocess_exec(*_: str, **__: object) -> _StreamingAsyncProcessStub:
        return _StreamingAsyncProcessStub(
            stdout_lines=[
                f"{session_line}\n",
                '{"type":"item.completed","item":{"type":"agent_message","text":"producer text"}}\n',
            ],
        )

    monkeypatch.setattr(codex_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    transport = CodexTransport(
        commands=CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
        model="gpt-test",
        model_effort=None,
    )

    result = asyncio.run(
        transport.run_turn(
            _rendered_turn(
                step_name="produce",
                prompt_text="prompt",
                session=_placeholder_session(),
                runtime_event_sink=lambda event_type, payload: seen_events.append((event_type, dict(payload))),
            )
        )
    )

    assert result.raw_text == "producer text"
    assert result.session is not None
    assert result.session.session_id == "large-streamed-session"
    assert any(
        event_type == "provider_session_known" and payload["session_id"] == "large-streamed-session"
        for event_type, payload in seen_events
    )


def test_codex_transport_does_not_wrap_runtime_event_sink_failures_as_transport_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process: _TerminableStreamingAsyncProcessStub | None = None
    seen_inputs: list[bytes | None] = []

    async def fake_create_subprocess_exec(*_: str, **__: object) -> _TerminableStreamingAsyncProcessStub:
        nonlocal process
        process = _TerminableStreamingAsyncProcessStub(
            stdout_lines=[
                '{"type":"thread.started","thread_id":"streamed-session"}\n',
                '{"type":"item.completed","item":{"type":"agent_message","text":"producer text"}}\n',
            ],
            seen_inputs=seen_inputs,
        )
        return process

    def failing_event_sink(event_type: str, payload: dict[str, object]) -> None:
        if event_type == "provider_session_known":
            raise RuntimeError("event sink failed")

    monkeypatch.setattr(codex_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    transport = CodexTransport(
        commands=CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
        model="gpt-test",
        model_effort=None,
    )

    with pytest.raises(RuntimeError, match="event sink failed"):
        asyncio.run(
            transport.run_turn(
                _rendered_turn(
                    step_name="produce",
                    prompt_text="prompt",
                    session=_placeholder_session(),
                    runtime_event_sink=failing_event_sink,
                )
            )
        )

    assert process is not None
    assert process.terminate_calls == 1
    assert process.kill_calls == 0
    assert process.wait_calls == 1
    assert seen_inputs == [b"prompt"]


def test_codex_transport_native_resume_missing_rollout_falls_back_to_fresh_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_folder = tmp_path / "run"
    run_folder.mkdir()
    events_file = run_folder / "events.jsonl"
    prompt_text = "# Step: produce\n\nShared runtime prompt."
    prompt_fingerprint = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()

    base_payload = {
        "schema": "botpipe.runtime_event/v1",
        "ts": "2026-05-13T00:00:00+00:00",
        "run_id": "run-test",
        "step_name": "produce",
        "step_execution_id": "produce:1",
        "turn_kind": "producer",
        "attempt": 1,
    }
    events = [
        {"seq": 1, "event_type": "provider_attempt_started"},
        {"seq": 2, "event_type": "provider_turn_started", "prompt_fingerprint": prompt_fingerprint},
        {"seq": 3, "event_type": "provider_session_known", "session_id": "interrupted-session"},
    ]
    with events_file.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps({**base_payload, **event}) + "\n")

    calls: list[tuple[str, ...]] = []
    seen_inputs: list[bytes | None] = []
    responses = [
        _AsyncProcessStub(
            stdout="",
            stderr=(
                "Error: thread/resume: thread/resume failed: no rollout found for thread id "
                "interrupted-session (code -32600)"
            ),
            returncode=1,
            seen_inputs=seen_inputs,
        ),
        _AsyncProcessStub(
            stdout="\n".join(
                (
                    '{"type":"thread.started","thread_id":"fresh-session"}',
                    '{"type":"item.completed","item":{"type":"agent_message","text":"fresh text"}}',
                )
            ),
            seen_inputs=seen_inputs,
        ),
    ]

    async def fake_create_subprocess_exec(*command: str, **_: object) -> _AsyncProcessStub:
        calls.append(tuple(command))
        return responses.pop(0)

    monkeypatch.setattr(codex_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    transport = CodexTransport(
        commands=CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
        model="gpt-test",
        model_effort=None,
    )

    result = asyncio.run(
        transport.run_turn(
            _rendered_turn(
                step_name="produce",
                prompt_text=prompt_text,
                session=_provider_session("codex", "previous-session"),
                run_folder=run_folder,
                step_execution_id="produce:1",
            )
        )
    )

    assert calls == [
        ("codex", "exec", "resume", "--json", "--model", "gpt-test", "interrupted-session"),
        ("codex", "exec", "--json", "--model", "gpt-test"),
    ]
    assert seen_inputs == [None, prompt_text.encode("utf-8")]
    assert result.raw_text == "fresh text"
    assert result.metadata["mode"] == "start"


def test_codex_interrupted_attempt_scan_disqualifies_failed_native_resume(tmp_path: Path) -> None:
    run_folder = tmp_path / "run"
    run_folder.mkdir()
    events_file = run_folder / "events.jsonl"
    prompt_text = "# Step: produce\n\nShared runtime prompt."
    prompt_fingerprint = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()
    base_payload = {
        "schema": "botpipe.runtime_event/v1",
        "ts": "2026-05-13T00:00:00+00:00",
        "run_id": "run-test",
        "step_name": "produce",
        "step_execution_id": "produce:1",
        "turn_kind": "producer",
        "attempt": 1,
    }
    events = [
        {"seq": 1, "event_type": "provider_attempt_started"},
        {"seq": 2, "event_type": "provider_turn_started", "prompt_fingerprint": prompt_fingerprint},
        {"seq": 3, "event_type": "provider_session_known", "session_id": "interrupted-session"},
        {"seq": 4, "event_type": "provider_attempt_started"},
        {"seq": 5, "event_type": "provider_turn_started", "prompt_fingerprint": prompt_fingerprint},
        {"seq": 6, "event_type": "provider_attempt_resume_started", "session_id": "interrupted-session"},
        {
            "seq": 7,
            "event_type": "provider_attempt_resume_failed",
            "session_id": "interrupted-session",
            "prompt_fingerprint": prompt_fingerprint,
        },
    ]
    with events_file.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps({**base_payload, **event}) + "\n")

    interrupted = codex_runtime_provider._find_interrupted_codex_attempt(
        _rendered_turn(
            step_name="produce",
            prompt_text=prompt_text,
            run_folder=run_folder,
            step_execution_id="produce:1",
        ),
        prompt_fingerprint=prompt_fingerprint,
    )

    assert interrupted is None


def test_codex_transport_run_turn_does_not_fall_back_to_subprocess_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_create_subprocess_exec(*command: str, **_: object) -> _AsyncProcessStub:
        return _AsyncProcessStub(
            stdout="\n".join(
                (
                    '{"type":"thread.started","thread_id":"codex-session-async"}',
                    '{"type":"item.completed","item":{"type":"agent_message","text":"producer text"}}',
                )
            ),
        )

    def fail_subprocess_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("provider turn execution must not use subprocess.run")

    monkeypatch.setattr(codex_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(codex_runtime_provider.subprocess, "run", fail_subprocess_run)
    transport = CodexTransport(
        commands=CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
        model="gpt-test",
        model_effort=None,
    )

    result = asyncio.run(transport.run_turn(_rendered_turn(session=_placeholder_session())))

    assert result.raw_text == "producer text"
    assert result.session is not None
    assert result.session.session_id == "codex-session-async"


def test_communicate_text_subprocess_terminates_then_kills_on_cancellation() -> None:
    process = _CancellableAsyncProcessStub()

    async def cancel_mid_communicate() -> None:
        task = asyncio.create_task(communicate_text_subprocess(process, input_text="payload"))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel_mid_communicate())

    assert process.seen_inputs == [b"payload"]
    assert process.terminate_calls == 1
    assert process.kill_calls == 1
    assert process.wait_calls >= 1


def test_terminate_text_subprocess_ignores_process_lookup_race_during_terminate() -> None:
    process = _LookupRacyProcessStub()

    asyncio.run(terminate_text_subprocess(process))

    assert process.terminate_calls == 1
    assert process.kill_calls == 0
    assert process.wait_calls == 1
    assert process.returncode == 0


def test_terminate_text_subprocess_ignores_process_lookup_race_during_kill() -> None:
    process = _LookupRacyProcessStub(raise_on_kill=True)

    asyncio.run(terminate_text_subprocess(process))

    assert process.terminate_calls == 1
    assert process.kill_calls == 1
    assert process.wait_calls == 1


def test_codex_transport_does_not_parse_workflow_outcome_json(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = CodexTransport(
        commands=CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
        model="gpt-test",
        model_effort=None,
    )
    async def fake_create_subprocess_exec(*command: str, **_: object) -> _AsyncProcessStub:
        return _AsyncProcessStub(
            stdout='{"type":"item.completed","item":{"type":"agent_message","text":"{\\"tag\\":\\"done\\"}"}}',
        )

    monkeypatch.setattr(codex_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = asyncio.run(
        transport.run_turn(_rendered_turn(step_name="verify", turn_kind="verifier", expected_response="outcome_json"))
    )

    assert result.raw_text == '{"tag":"done"}'


def test_rendered_llm_provider_returns_producer_response_with_codex_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = CodexTransport(
        commands=CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
        model="gpt-test",
        model_effort=None,
    )
    async def fake_create_subprocess_exec(*command: str, **_: object) -> _AsyncProcessStub:
        return _AsyncProcessStub(
            stdout="\n".join(
                (
                    '{"type":"thread.started","thread_id":"codex-session-2"}',
                    '{"type":"response.completed","response":{"usage":{"input_tokens":15,"output_tokens":6,"total_tokens":21}}}',
                    '{"type":"item.completed","item":{"type":"agent_message","text":"producer text"}}',
                )
            ),
        )

    monkeypatch.setattr(codex_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    provider = RenderedLLMProvider(transport)

    response = asyncio.run(provider.run_producer(_producer_request(session=_placeholder_session())))

    assert response.raw_output == "producer text"
    assert response.session is not None
    assert response.session.session_id == "codex-session-2"
    assert response.metadata["mode"] == "start"
    assert response.usage == TokenUsage(
        input_tokens=15,
        output_tokens=6,
        total_tokens=21,
        cached_input_tokens=None,
        reasoning_tokens=None,
        source="codex",
        provider_raw={"input_tokens": 15, "output_tokens": 6, "total_tokens": 21},
    )


def test_rendered_llm_provider_parses_codex_verifier_outcome_in_core(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_inputs: list[bytes | None] = []

    async def fake_create_subprocess_exec(*command: str, **_: object) -> _AsyncProcessStub:
        return _AsyncProcessStub(
            stdout="\n".join(
                (
                    '{"type":"thread.started","thread_id":"codex-session-3"}',
                    '{"type":"item.completed","item":{"type":"agent_message","text":"{\\"tag\\":\\"pair_ok\\",\\"reason\\":\\"accepted\\",\\"payload\\":{\\"summary\\":\\"ok\\"}}"}}',
                )
            ),
            seen_inputs=seen_inputs,
        )

    monkeypatch.setattr(codex_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    provider = RenderedLLMProvider(
        CodexTransport(
            commands=CodexCLICommand(
                start_command=("codex", "exec", "--json"),
                resume_command=("codex", "exec", "resume", "--json"),
            ),
            model="gpt-test",
            model_effort=None,
        )
    )

    response = asyncio.run(provider.run_verifier(_verifier_request(session=_placeholder_session())))

    rendered_prompt = (seen_inputs[0] or b"").decode("utf-8")
    assert "# Step: verify" in rendered_prompt
    assert "## Runtime Step Contract" in rendered_prompt
    assert "### Required inputs" in rendered_prompt
    assert "### Control response" in rendered_prompt
    assert "<producer_raw_output>" not in rendered_prompt
    assert "producer output" not in rendered_prompt
    assert response.outcome.tag == "pair_ok"
    assert response.outcome.reason == "accepted"
    assert response.outcome.payload == {"summary": "ok"}
    assert response.session is not None
    assert response.session.session_id == "codex-session-3"


def test_codex_transport_rejects_unusable_jsonl(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = CodexTransport(
        commands=CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
        model="gpt-test",
        model_effort=None,
    )
    async def fake_create_subprocess_exec(*command: str, **_: object) -> _AsyncProcessStub:
        return _AsyncProcessStub(stdout="not-json\n")

    monkeypatch.setattr(codex_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    with pytest.raises(ProviderExecutionError, match="unusable JSONL output") as exc_info:
        asyncio.run(transport.run_turn(_rendered_turn(session=_placeholder_session())))

    failure_context = exception_failure_context(exc_info.value)
    assert failure_context is not None
    assert failure_context.details["provider_failure_stage"] == "adapter_output"
    assert exception_retry_kind(exc_info.value) == "malformed_provider_output"


def test_codex_transport_rejects_missing_resumable_session_id(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = CodexTransport(
        commands=CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
        model="gpt-test",
        model_effort=None,
    )

    async def fake_create_subprocess_exec(*command: str, **_: object) -> _AsyncProcessStub:
        return _AsyncProcessStub(
            stdout='{"type":"item.completed","item":{"type":"agent_message","text":"producer text"}}'
        )

    monkeypatch.setattr(codex_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    with pytest.raises(ProviderExecutionError, match="did not return a resumable session_id") as exc_info:
        asyncio.run(transport.run_turn(_rendered_turn(step_name="produce", session=_placeholder_session())))

    failure_context = exception_failure_context(exc_info.value)
    assert failure_context is not None
    assert failure_context.step_name == "produce"
    assert failure_context.details["provider_failure_stage"] == "adapter_output"
    assert exception_retry_kind(exc_info.value) == "provider_transport_failure"


def test_codex_transport_raises_on_non_zero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = CodexTransport(
        commands=CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
        model="gpt-test",
        model_effort=None,
    )
    async def fake_create_subprocess_exec(*command: str, **_: object) -> _AsyncProcessStub:
        return _AsyncProcessStub(stdout="oops", stderr="bad", returncode=7)

    monkeypatch.setattr(codex_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    with pytest.raises(ProviderExecutionError, match=r"exit code 7") as exc_info:
        asyncio.run(transport.run_turn(_rendered_turn(session=_placeholder_session())))

    failure_context = exception_failure_context(exc_info.value)
    assert failure_context is not None
    assert failure_context.details["provider_failure_stage"] == "transport"
    assert exception_retry_kind(exc_info.value) == "provider_transport_failure"


def test_codex_transport_wraps_stdout_read_failures_as_retryable_transport_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = CodexTransport(
        commands=CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
        model="gpt-test",
        model_effort=None,
    )
    process: _FailingStdoutAsyncProcessStub | None = None
    seen_inputs: list[bytes | None] = []

    async def fake_create_subprocess_exec(*command: str, **_: object) -> _FailingStdoutAsyncProcessStub:
        nonlocal process
        process = _FailingStdoutAsyncProcessStub(
            stdout_exc=asyncio.LimitOverrunError("Separator is found, but chunk is longer than limit", 65536),
            seen_inputs=seen_inputs,
        )
        return process

    monkeypatch.setattr(codex_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    with pytest.raises(ProviderExecutionError, match="failed while communicating with the CLI") as exc_info:
        asyncio.run(
            transport.run_turn(_rendered_turn(step_name="produce", prompt_text="prompt", session=_placeholder_session()))
        )

    failure_context = exception_failure_context(exc_info.value)
    assert failure_context is not None
    assert failure_context.step_name == "produce"
    assert failure_context.details["provider_failure_stage"] == "transport"
    assert exception_retry_kind(exc_info.value) == "provider_transport_failure"
    assert process is not None
    assert process.terminate_calls == 1
    assert process.kill_calls == 0
    assert process.wait_calls == 1
    assert seen_inputs == [b"prompt"]


def test_codex_transport_reports_subprocess_failure_when_stdin_pipe_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = CodexTransport(
        commands=CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
        model="gpt-test",
        model_effort=None,
    )

    async def fake_create_subprocess_exec(*command: str, **_: object) -> _StreamingAsyncProcessStub:
        process = _StreamingAsyncProcessStub(stdout_lines=[], stderr="bad", returncode=7)
        process.stdin = _BrokenPipeAsyncBytesWriterStub()
        return process

    monkeypatch.setattr(codex_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    with pytest.raises(ProviderExecutionError, match=r"exit code 7"):
        asyncio.run(transport.run_turn(_rendered_turn(session=_placeholder_session())))


def test_codex_transport_recovers_from_missing_rollout_resume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []
    seen_inputs: list[bytes | None] = []
    responses = [
        _AsyncProcessStub(
            stdout="",
            stderr=(
                "Error: thread/resume: thread/resume failed: no rollout found for thread id "
                "stale-thread (code -32600)"
            ),
            returncode=1,
            seen_inputs=seen_inputs,
        ),
        _AsyncProcessStub(
            stdout="\n".join(
                (
                    '{"type":"thread.started","thread_id":"fresh-thread"}',
                    '{"type":"item.completed","item":{"type":"agent_message","text":"producer text"}}',
                )
            ),
            seen_inputs=seen_inputs,
        ),
    ]

    async def fake_create_subprocess_exec(*command: str, **_: object) -> _AsyncProcessStub:
        calls.append(tuple(command))
        return responses.pop(0)

    monkeypatch.setattr(codex_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    transport = CodexTransport(
        commands=CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
        model="gpt-test",
        model_effort=None,
    )

    result = asyncio.run(transport.run_turn(_rendered_turn(session=_provider_session("codex", "stale-thread"))))

    assert calls == [
        ("codex", "exec", "resume", "--json", "--model", "gpt-test", "stale-thread", "-"),
        ("codex", "exec", "--json", "--model", "gpt-test"),
    ]
    assert seen_inputs == [b"prompt", b"prompt"]
    assert result.raw_text == "producer text"
    assert result.session is not None
    assert result.session.session_id == "fresh-thread"
    assert result.metadata["mode"] == "start"
    assert result.metadata["provider_metadata"]["resume_recovery"] == {
        "reason": "missing_rollout",
        "discarded_session_id": "stale-thread",
    }


def test_codex_transport_rejects_cross_provider_resume() -> None:
    transport = CodexTransport(
        commands=CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
        model="gpt-test",
        model_effort=None,
    )

    with pytest.raises(ProviderExecutionError, match="resuming across providers is forbidden"):
        asyncio.run(transport.run_turn(_rendered_turn(session=_provider_session("claude"))))


def test_codex_transport_emits_run_scoped_policy_artifacts_and_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompt_text = "# Step: produce\n\nShared runtime prompt."
    calls: list[tuple[str, ...]] = []
    seen_envs: list[dict[str, str] | None] = []
    seen_events: list[tuple[str, dict[str, object]]] = []

    async def fake_create_subprocess_exec(*command: str, **kwargs: object) -> _AsyncProcessStub:
        calls.append(tuple(command))
        env = kwargs.get("env")
        seen_envs.append(dict(env) if isinstance(env, dict) else None)
        return _AsyncProcessStub(
            stdout="\n".join(
                (
                    '{"type":"thread.started","thread_id":"codex-session-policy"}',
                    '{"type":"item.completed","item":{"type":"agent_message","text":"producer text"}}',
                )
            ),
        )

    monkeypatch.setattr(codex_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    transport = CodexTransport(
        commands=CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
        model="gpt-test",
        model_effort=None,
    )
    policy = ProviderPolicy(
        permissions=PermissionPolicy(mode="full_auto_sandboxed"),
        sandbox=SandboxPolicy(
            mode="workspace_write",
            workspace=WorkspacePolicy(
                filesystem=WorkspaceFilesystemPolicy(allow_write=(".", "./build")),
            ),
        ),
    )

    result = asyncio.run(
        transport.run_turn(
            _rendered_turn(
                step_name="produce",
                prompt_text=prompt_text,
                session=_placeholder_session(),
                policy=policy,
                run_folder=tmp_path,
                step_execution_id="produce:1",
                runtime_event_sink=lambda event_type, payload: seen_events.append((event_type, dict(payload))),
            )
        )
    )

    assert calls == [
        (
            "codex",
            "exec",
            "--json",
            '--config=approval_policy="never"',
            '--config=sandbox_mode="workspace-write"',
            '--config=sandbox_workspace_write.writable_roots=[".", "./build"]',
            "--config=sandbox_workspace_write.network_access=true",
            '--config=shell_environment_policy.inherit="core"',
            "--config=shell_environment_policy.ignore_default_excludes=false",
            '--config=shell_environment_policy.exclude=["*TOKEN*", "*SECRET*", "*KEY*"]',
            "--model",
            "gpt-test",
        )
    ]
    assert seen_envs and seen_envs[0] is not None
    assert "CODEX_HOME" not in seen_envs[0]
    policy_root = tmp_path / "provider_policy" / "produce__visit-1" / "codex"
    assert not (policy_root / "config.toml").exists()
    assert result.metadata["provider_metadata"]["policy"]["effective_policy_file"] == str(policy_root / "effective_policy.json")
    assert result.metadata["provider_metadata"]["policy"]["capability_report_file"] == str(policy_root / "capability_report.json")
    assert "policy_fingerprint" in result.metadata["provider_metadata"]["policy"]
    assert [
        event
        for event, _payload in seen_events
        if event in {"provider_policy_emitted", "provider_policy_capability_report"}
    ] == [
        "provider_policy_emitted",
        "provider_policy_capability_report",
    ]


def test_codex_transport_capability_report_keeps_narrowed_read_roots_unenforced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_create_subprocess_exec(*_command: str, **_kwargs: object) -> _AsyncProcessStub:
        return _AsyncProcessStub(
            stdout="\n".join(
                (
                    '{"type":"thread.started","thread_id":"codex-session-policy"}',
                    '{"type":"item.completed","item":{"type":"agent_message","text":"producer text"}}',
                )
            ),
        )

    monkeypatch.setattr(codex_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    transport = CodexTransport(
        commands=CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
        model="gpt-test",
        model_effort=None,
        validation=ProviderPolicyValidationConfig(unsafe_expansion="warn"),
    )
    policy = ProviderPolicy(
        sandbox=SandboxPolicy(
            workspace=WorkspacePolicy(
                filesystem=WorkspaceFilesystemPolicy(allow_read=("./src",)),
            ),
        ),
    )

    result = asyncio.run(
        transport.run_turn(
            _rendered_turn(
                step_name="produce",
                prompt_text="# Step: produce\n\nShared runtime prompt.",
                session=_placeholder_session(),
                policy=policy,
                run_folder=tmp_path,
                step_execution_id="produce:1",
            )
        )
    )

    report_path = Path(result.metadata["provider_metadata"]["policy"]["capability_report_file"])
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["decision"] == "warn"
    assert report["unsafe_expansions"] == [
        "sandbox.workspace.filesystem.allow_read cannot be narrowed by Codex",
    ]
    assert report["effective_enforcement"]["read_roots"] == []


def test_codex_operation_executor_uses_policy_env_and_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[tuple[str, ...], dict[str, str] | None, str | None]] = []
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    def fake_run_text_subprocess(
        command: list[str],
        *,
        input_text: str | None = None,
        env=None,
        cwd: str | None = None,
    ) -> tuple[str, str, int]:
        seen.append((tuple(command), None if env is None else dict(env), None if cwd is None else str(cwd)))
        return (
            "\n".join(
                (
                    '{"type":"thread.started","thread_id":"codex-session-op"}',
                    '{"type":"item.completed","item":{"type":"agent_message","text":"operation text"}}',
                )
            ),
            "",
            0,
        )

    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setattr(codex_runtime_provider, "run_text_subprocess", fake_run_text_subprocess)
    executor = codex_runtime_provider.build_codex_operation_executor(
        _config(),
        commands=CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
    )
    policy = ProviderPolicy(
        permissions=PermissionPolicy(mode="full_auto_sandboxed"),
        sandbox=SandboxPolicy(
            workspace=WorkspacePolicy(
                filesystem=WorkspaceFilesystemPolicy(allow_write=(".", "./dist")),
            )
        ),
    )

    result = executor(
        _rendered_turn(
            step_name="operate",
            turn_kind="operation",
            policy=policy,
            run_folder=tmp_path,
            workspace_root=workspace_root,
            step_execution_id="operate:1",
        )
    )

    assert seen and seen[0][0] == (
        "codex",
        "exec",
        "--json",
        '--config=approval_policy="never"',
        '--config=sandbox_mode="workspace-write"',
        '--config=sandbox_workspace_write.writable_roots=[".", "./dist"]',
        "--config=sandbox_workspace_write.network_access=true",
        '--config=shell_environment_policy.inherit="core"',
        "--config=shell_environment_policy.ignore_default_excludes=false",
        '--config=shell_environment_policy.exclude=["*TOKEN*", "*SECRET*", "*KEY*"]',
        "--model",
        "gpt-test",
    )
    assert seen[0][1] is not None
    assert "CODEX_HOME" not in seen[0][1]
    assert seen[0][2] == str(workspace_root)
    assert result.metadata["provider_metadata"]["policy"]["capability_report_file"].endswith("capability_report.json")


def test_claude_transport_emits_run_scoped_policy_artifacts_and_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompt_text = "# Step: produce\n\nShared runtime prompt."
    calls: list[tuple[str, ...]] = []
    seen_envs: list[dict[str, str] | None] = []
    seen_cwds: list[str | None] = []
    seen_events: list[tuple[str, dict[str, object]]] = []
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    async def fake_create_subprocess_exec(*command: str, **kwargs: object) -> _AsyncProcessStub:
        calls.append(tuple(command))
        env = kwargs.get("env")
        seen_envs.append(dict(env) if isinstance(env, dict) else None)
        cwd = kwargs.get("cwd")
        seen_cwds.append(None if cwd is None else str(cwd))
        return _AsyncProcessStub(
            stdout='{"result":"producer text","session_id":"claude-session-policy","stop_reason":"end_turn"}',
        )

    monkeypatch.setattr(claude_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    transport = ClaudeTransport(config=_config(provider_name="claude").provider.claude)
    policy = ProviderPolicy(
        permissions=PermissionPolicy(mode="full_auto_sandboxed"),
        sandbox=SandboxPolicy(
            mode="workspace_write",
            workspace=WorkspacePolicy(
                filesystem=WorkspaceFilesystemPolicy(allow_write=(".", "./build")),
            ),
        ),
    )

    result = asyncio.run(
        transport.run_turn(
            _rendered_turn(
                step_name="produce",
                prompt_text=prompt_text,
                session=_placeholder_session(),
                policy=policy,
                run_folder=tmp_path,
                workspace_root=workspace_root,
                step_execution_id="produce:1",
                runtime_event_sink=lambda event_type, payload: seen_events.append((event_type, dict(payload))),
            )
        )
    )

    settings_path = tmp_path / "provider_policy" / "produce__visit-1" / "claude" / "settings.json"
    assert settings_path.exists()
    assert calls == [
        (
            "claude",
            "-p",
            prompt_text,
            "--output-format",
            "json",
            "--settings",
            str(settings_path),
            "--add-dir",
            str(workspace_root.resolve()),
            "--model",
            "claude-test",
        )
    ]
    assert seen_envs and seen_envs[0] is not None
    assert "CLAUDE_CONFIG_DIR" not in seen_envs[0]
    assert seen_envs[0]["CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD"] == "1"
    assert seen_cwds == [None]
    assert result.metadata["provider_metadata"]["policy"]["effective_policy_file"] == str(
        settings_path.parent / "effective_policy.json"
    )
    assert result.metadata["provider_metadata"]["policy"]["capability_report_file"] == str(
        settings_path.parent / "capability_report.json"
    )
    assert [event for event, _payload in seen_events] == [
        "provider_policy_emitted",
        "provider_policy_capability_report",
    ]


def test_claude_transport_marks_capability_loss_when_native_filesystem_support_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    async def fake_create_subprocess_exec(*_command: str, **_kwargs: object) -> _AsyncProcessStub:
        return _AsyncProcessStub(
            stdout='{"result":"producer text","session_id":"claude-session-policy","stop_reason":"end_turn"}',
        )

    monkeypatch.setattr(claude_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    transport = ClaudeTransport(
        config=_config(provider_name="claude").provider.claude,
        validation=ProviderPolicyValidationConfig(lossy_mapping="warn"),
        capabilities=ClaudeCapabilities(supports_sandbox_filesystem=False),
    )
    policy = ProviderPolicy(
        sandbox=SandboxPolicy(
            workspace=WorkspacePolicy(
                filesystem=WorkspaceFilesystemPolicy(allow_write=(".", "./dist")),
            ),
        ),
    )

    result = asyncio.run(
        transport.run_turn(
            _rendered_turn(
                step_name="produce",
                prompt_text="# Step: produce\n\nShared runtime prompt.",
                session=_placeholder_session(),
                policy=policy,
                run_folder=tmp_path,
                workspace_root=workspace_root,
                step_execution_id="produce:1",
            )
        )
    )

    report_path = Path(result.metadata["provider_metadata"]["policy"]["capability_report_file"])
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["decision"] == "warn"
    assert report["lossy"] == [
        "sandbox.filesystem native enforcement unavailable; emitted Read/Edit permission rules only",
    ]
    assert report["effective_enforcement"]["write_roots"] == []


def test_claude_transport_preserves_legacy_bypass_for_policy_backed_turns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    async def fake_create_subprocess_exec(*command: str, **_: object) -> _AsyncProcessStub:
        calls.append(tuple(command))
        return _AsyncProcessStub(
            stdout='{"result":"producer text","session_id":"claude-session-bypass","stop_reason":"end_turn"}',
        )

    monkeypatch.setattr(claude_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    transport = ClaudeTransport(config=_config(provider_name="claude", claude_permission_strategy="bypass").provider.claude)
    policy = ProviderPolicy(
        permissions=PermissionPolicy(
            mode="full_auto_unsandboxed",
            allow_dangerous_bypass=True,
            disable_dangerous_bypass=False,
        ),
        sandbox=SandboxPolicy(
            enabled=False,
            required=False,
            mode="danger_full_access",
        ),
    )

    asyncio.run(
        transport.run_turn(
            _rendered_turn(
                step_name="produce",
                prompt_text="# Step: produce\n\nShared runtime prompt.",
                session=_placeholder_session(),
                policy=policy,
                run_folder=tmp_path,
                workspace_root=workspace_root,
                step_execution_id="produce:1",
            )
        )
    )

    assert calls == [
        (
            "claude",
            "-p",
            "# Step: produce\n\nShared runtime prompt.",
            "--output-format",
            "json",
            "--settings",
            str(tmp_path / "provider_policy" / "produce__visit-1" / "claude" / "settings.json"),
            "--add-dir",
            str(workspace_root.resolve()),
            "--dangerously-skip-permissions",
            "--model",
            "claude-test",
        )
    ]


def test_claude_transport_does_not_reapply_legacy_bypass_when_explicit_policy_is_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    async def fake_create_subprocess_exec(*command: str, **_: object) -> _AsyncProcessStub:
        calls.append(tuple(command))
        return _AsyncProcessStub(
            stdout='{"result":"producer text","session_id":"claude-session-safe","stop_reason":"end_turn"}',
        )

    monkeypatch.setattr(claude_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    transport = ClaudeTransport(config=_config(provider_name="claude", claude_permission_strategy="bypass").provider.claude)
    policy = ProviderPolicy(
        permissions=PermissionPolicy(mode="ask"),
        sandbox=SandboxPolicy(
            enabled=True,
            required=True,
            mode="workspace_write",
        ),
    )

    asyncio.run(
        transport.run_turn(
            _rendered_turn(
                step_name="produce",
                prompt_text="# Step: produce\n\nShared runtime prompt.",
                session=_placeholder_session(),
                policy=policy,
                run_folder=tmp_path,
                workspace_root=workspace_root,
                step_execution_id="produce:1",
            )
        )
    )

    assert calls == [
        (
            "claude",
            "-p",
            "# Step: produce\n\nShared runtime prompt.",
            "--output-format",
            "json",
            "--settings",
            str(tmp_path / "provider_policy" / "produce__visit-1" / "claude" / "settings.json"),
            "--add-dir",
            str(workspace_root.resolve()),
            "--model",
            "claude-test",
        )
    ]


def test_claude_operation_executor_uses_policy_settings_and_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[tuple[str, ...], dict[str, str] | None, str | None]] = []
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    def fake_run_text_subprocess(
        command: list[str],
        *,
        input_text: str | None = None,
        env=None,
        cwd: Path | None = None,
    ) -> tuple[str, str, int]:
        seen.append((tuple(command), None if env is None else dict(env), None if cwd is None else str(cwd)))
        return ('{"result":"operation text","session_id":"claude-session-op","stop_reason":"done"}', "", 0)

    monkeypatch.setattr(claude_runtime_provider.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(
        claude_runtime_provider.subprocess,
        "run",
        lambda command, **_: _completed(args=command, stdout=CLAUDE_HEADLESS_HELP),
    )
    monkeypatch.setattr(claude_runtime_provider, "run_text_subprocess", fake_run_text_subprocess)
    executor = claude_runtime_provider.build_claude_operation_executor(_config(provider_name="claude"))
    policy = ProviderPolicy(
        permissions=PermissionPolicy(mode="full_auto_sandboxed"),
        sandbox=SandboxPolicy(
            workspace=WorkspacePolicy(
                filesystem=WorkspaceFilesystemPolicy(allow_write=(".", "./dist")),
            )
        ),
    )

    result = executor(
        _rendered_turn(
            step_name="operate",
            turn_kind="operation",
            policy=policy,
            run_folder=tmp_path,
            workspace_root=workspace_root,
            step_execution_id="operate:1",
        )
    )

    settings_path = tmp_path / "provider_policy" / "operate__visit-1" / "claude" / "settings.json"
    assert seen and seen[0][0] == (
        "claude",
        "-p",
        "prompt",
        "--output-format",
        "json",
        "--settings",
        str(settings_path),
        "--add-dir",
        str(workspace_root.resolve()),
        "--model",
        "claude-test",
    )
    assert seen[0][1] is not None
    assert "CLAUDE_CONFIG_DIR" not in seen[0][1]
    assert seen[0][1]["CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD"] == "1"
    assert seen[0][2] is None
    assert result.metadata["provider_metadata"]["policy"]["capability_report_file"].endswith("capability_report.json")


def test_claude_transport_sends_rendered_prompt_text_to_cli_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    prompt_text = "# Step: produce\n\nShared runtime prompt."
    calls: list[tuple[str, ...]] = []

    async def fake_create_subprocess_exec(*command: str, **_: object) -> _AsyncProcessStub:
        calls.append(tuple(command))
        return _AsyncProcessStub(
            stdout='{"result":"producer text","session_id":"claude-session-1","stop_reason":"end_turn"}',
        )

    monkeypatch.setattr(claude_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    transport = ClaudeTransport(config=_config(provider_name="claude").provider.claude)

    result = asyncio.run(
        transport.run_turn(_rendered_turn(step_name="produce", prompt_text=prompt_text, session=_placeholder_session()))
    )

    assert calls == [("claude", "-p", prompt_text, "--output-format", "json", "--model", "claude-test")]
    assert result.raw_text == "producer text"
    assert result.session is not None
    assert result.session.session_id == "claude-session-1"
    assert result.session.metadata["provider_metadata"] == {"stop_reason": "end_turn"}


def test_claude_transport_supports_async_subprocess_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    prompt_text = "# Step: produce\n\nShared runtime prompt."
    calls: list[tuple[str, ...]] = []

    async def fake_create_subprocess_exec(*command: str, **_: object) -> _AsyncProcessStub:
        calls.append(tuple(command))
        return _AsyncProcessStub(
            stdout='{"result":"producer text","session_id":"claude-session-async","stop_reason":"end_turn"}'
        )

    monkeypatch.setattr(claude_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    transport = ClaudeTransport(config=_config(provider_name="claude").provider.claude)

    result = asyncio.run(
        transport.run_turn(_rendered_turn(step_name="produce", prompt_text=prompt_text, session=_placeholder_session()))
    )

    assert calls == [("claude", "-p", prompt_text, "--output-format", "json", "--model", "claude-test")]
    assert result.raw_text == "producer text"
    assert result.session is not None
    assert result.session.session_id == "claude-session-async"


def test_claude_transport_run_turn_does_not_fall_back_to_subprocess_run(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_create_subprocess_exec(*command: str, **_: object) -> _AsyncProcessStub:
        return _AsyncProcessStub(
            stdout='{"result":"producer text","session_id":"claude-session-async","stop_reason":"end_turn"}'
        )

    def fail_subprocess_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("provider turn execution must not use subprocess.run")

    monkeypatch.setattr(claude_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(claude_runtime_provider.subprocess, "run", fail_subprocess_run)
    transport = ClaudeTransport(config=_config(provider_name="claude").provider.claude)

    result = asyncio.run(transport.run_turn(_rendered_turn(session=_placeholder_session())))

    assert result.raw_text == "producer text"
    assert result.session is not None
    assert result.session.session_id == "claude-session-async"


def test_claude_transport_does_not_parse_workflow_outcome_json(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_create_subprocess_exec(*command: str, **_: object) -> _AsyncProcessStub:
        return _AsyncProcessStub(stdout='{"result":"{\\"tag\\":\\"done\\"}"}')

    monkeypatch.setattr(claude_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    transport = ClaudeTransport(config=_config(provider_name="claude").provider.claude)

    result = asyncio.run(
        transport.run_turn(_rendered_turn(step_name="ask", turn_kind="llm", expected_response="outcome_json"))
    )

    assert result.raw_text == '{"tag":"done"}'


def test_rendered_llm_provider_parses_claude_llm_outcome_in_core(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resumable = _provider_session("claude", session_id="claude-session-existing")
    calls: list[tuple[str, ...]] = []

    async def fake_create_subprocess_exec(*command: str, **_: object) -> _AsyncProcessStub:
        calls.append(tuple(command))
        return _AsyncProcessStub(
            stdout='{"result":"{\\"tag\\":\\"done\\",\\"reason\\":\\"completed\\"}","usage":{"prompt_tokens":8,"completion_tokens":3,"total_tokens":11},"stop_reason":"done"}',
        )

    monkeypatch.setattr(claude_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    provider = RenderedLLMProvider(
        ClaudeTransport(config=_config(provider_name="claude", claude_permission_strategy="allow_core_tools").provider.claude)
    )

    response = asyncio.run(provider.run_llm(_llm_request(session=resumable)))

    assert calls[-1][:4] == ("claude", "--resume", "claude-session-existing", "-p")
    rendered_prompt = calls[-1][4]
    assert "# Step: ask" in rendered_prompt
    assert "## Runtime Step Contract" in rendered_prompt
    assert "<producer_raw_output>" not in rendered_prompt
    assert calls[-1][5:] == (
        "--output-format",
        "json",
        "--model",
        "claude-test",
        "--allowedTools",
        "Read,Write,Edit,Glob,Grep,Bash",
    )
    assert response.outcome.tag == "done"
    assert response.outcome.reason == "completed"
    assert response.session is not None
    assert response.session.session_id == "claude-session-existing"
    assert response.session.metadata["provider_metadata"] == {"stop_reason": "done"}
    assert response.usage == TokenUsage(
        input_tokens=8,
        output_tokens=3,
        total_tokens=11,
        cached_input_tokens=None,
        reasoning_tokens=None,
        source="claude",
        provider_raw={"prompt_tokens": 8, "completion_tokens": 3, "total_tokens": 11},
    )


def test_claude_transport_rejects_malformed_json(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_create_subprocess_exec(*command: str, **_: object) -> _AsyncProcessStub:
        return _AsyncProcessStub(stdout="{bad-json}")

    monkeypatch.setattr(claude_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    transport = ClaudeTransport(config=_config(provider_name="claude").provider.claude)

    with pytest.raises(ProviderExecutionError, match="malformed JSON output") as exc_info:
        asyncio.run(transport.run_turn(_rendered_turn(session=_placeholder_session())))

    failure_context = exception_failure_context(exc_info.value)
    assert failure_context is not None
    assert failure_context.details["provider_failure_stage"] == "adapter_output"
    assert exception_retry_kind(exc_info.value) == "malformed_provider_output"


def test_claude_transport_rejects_missing_resumable_session_id(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_create_subprocess_exec(*command: str, **_: object) -> _AsyncProcessStub:
        return _AsyncProcessStub(stdout='{"result":"producer text","stop_reason":"end_turn"}')

    monkeypatch.setattr(claude_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    transport = ClaudeTransport(config=_config(provider_name="claude").provider.claude)

    with pytest.raises(ProviderExecutionError, match="did not return a resumable session_id") as exc_info:
        asyncio.run(transport.run_turn(_rendered_turn(step_name="produce", session=_placeholder_session())))

    failure_context = exception_failure_context(exc_info.value)
    assert failure_context is not None
    assert failure_context.step_name == "produce"
    assert failure_context.details["provider_failure_stage"] == "adapter_output"
    assert exception_retry_kind(exc_info.value) == "provider_transport_failure"


def test_claude_transport_raises_on_non_zero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_create_subprocess_exec(*command: str, **_: object) -> _AsyncProcessStub:
        return _AsyncProcessStub(stdout="oops", stderr="bad", returncode=3)

    monkeypatch.setattr(claude_runtime_provider.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    transport = ClaudeTransport(config=_config(provider_name="claude").provider.claude)

    with pytest.raises(ProviderExecutionError, match=r"exit code 3") as exc_info:
        asyncio.run(transport.run_turn(_rendered_turn(session=_placeholder_session())))

    failure_context = exception_failure_context(exc_info.value)
    assert failure_context is not None
    assert failure_context.details["provider_failure_stage"] == "transport"
    assert exception_retry_kind(exc_info.value) == "provider_transport_failure"


def test_claude_transport_rejects_cross_provider_resume() -> None:
    transport = ClaudeTransport(config=_config(provider_name="claude").provider.claude)

    with pytest.raises(ProviderExecutionError, match="resuming across providers is forbidden"):
        asyncio.run(transport.run_turn(_rendered_turn(session=_provider_session("codex"))))
