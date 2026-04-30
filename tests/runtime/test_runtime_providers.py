from __future__ import annotations

import subprocess

import pytest

from core.errors import ProviderExecutionError
from core.prompts import ResolvedPrompt
from core.providers.models import LLMRequest, ProducerRequest, TokenUsage, VerifierRequest
from core.providers.parsing import parse_outcome_json
from core.providers.rendered import RenderedLLMProvider
from core.providers.turns import RenderedProviderTurn
from core.stores.protocols import SessionBinding
from runtime.config import (
    ClaudeProviderConfig,
    CodexProviderConfig,
    ConfigError,
    ProviderConfig,
    ResolvedRuntimeConfig,
    RuntimeConfig,
)
from runtime.providers._common import (
    build_session_binding,
    ensure_session_provider_match,
    format_subprocess_streams,
    require_prompt_text,
)
from runtime.providers.claude import (
    ClaudeTransport,
    claude_permission_args,
    parse_claude_exec_json,
    verify_claude_code_capabilities,
)
import runtime.providers.claude as claude_runtime_provider
from runtime.providers.codex import (
    CodexCLICommand,
    CodexTransport,
    resolve_codex_cli_commands,
    parse_codex_exec_json,
    verify_codex_exec_capabilities,
)
import runtime.providers.codex as codex_runtime_provider


CODEX_START_HELP = "--json\n-m, --model <MODEL>\n--dangerously-bypass-approvals-and-sandbox\n"
CODEX_RESUME_HELP = "--json\n-m, --model <MODEL>\n--dangerously-bypass-approvals-and-sandbox\n"
CLAUDE_HEADLESS_HELP = "--print\n-p\n--output-format\n--resume\n--model\n"
CLAUDE_HELP = "--print\n-p\n--output-format\n--resume\n--model\n--allowedTools\n--dangerously-skip-permissions\n"


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
        prompt=ResolvedPrompt(path="prompt.md", text=prompt_text),
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
        prompt=ResolvedPrompt(path="verify.md", text=prompt_text),
        raw_output=raw_output,
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
) -> RenderedProviderTurn:
    return RenderedProviderTurn(
        step_name=step_name,
        turn_kind=turn_kind,
        prompt_text=prompt_text,
        session=session,
        expected_response=expected_response,
    )


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
    outcome = parse_outcome_json('{"tag":"done","reason":"ok","payload":{"x":1}}')

    assert outcome.tag == "done"
    assert outcome.reason == "ok"
    assert outcome.payload == {"x": 1}
    assert outcome.raw_output == '{"tag":"done","reason":"ok","payload":{"x":1}}'


def test_parse_outcome_json_accepts_fenced_json_block() -> None:
    raw = '```json\n{"tag":"question","reason":"Need user input.","question":"Proceed?"}\n```'

    outcome = parse_outcome_json(raw)

    assert outcome.tag == "question"
    assert outcome.reason == "Need user input."
    assert outcome.question == "Proceed?"
    assert outcome.payload == {}
    assert outcome.raw_output == raw


def test_parse_outcome_json_rejects_invalid_json() -> None:
    with pytest.raises(ProviderExecutionError, match="malformed outcome JSON"):
        parse_outcome_json("{not-json}")


def test_parse_outcome_json_rejects_missing_tag() -> None:
    with pytest.raises(ProviderExecutionError, match="must contain a non-empty string 'tag'"):
        parse_outcome_json('{"reason":"missing"}')


def test_parse_outcome_json_rejects_missing_reason() -> None:
    with pytest.raises(ProviderExecutionError, match="must contain a non-empty string 'reason'"):
        parse_outcome_json('{"tag":"done"}')


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

    with pytest.raises(ProviderExecutionError, match="did not return assistant text"):
        parse_codex_exec_json(stdout)


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
    with pytest.raises(ProviderExecutionError, match="must contain a string 'result'"):
        parse_claude_exec_json('{"session_id":"claude-session-1"}')


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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(codex_runtime_provider.shutil, "which", lambda name: "/usr/bin/codex")
    calls: list[list[str]] = []
    prompt_text = "# Step: produce\n\nShared runtime prompt."

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command == ["codex", "exec", "--help"]:
            return _completed(args=command, stdout=CODEX_START_HELP)
        if command == ["codex", "exec", "resume", "--help"]:
            return _completed(args=command, stdout=CODEX_RESUME_HELP)
        assert kwargs["input"] == prompt_text
        return _completed(
            args=command,
            stdout="\n".join(
                (
                    '{"type":"thread.started","thread_id":"codex-session-1"}',
                    '{"type":"item.completed","item":{"type":"agent_message","text":"producer text"}}',
                )
            ),
        )

    monkeypatch.setattr(codex_runtime_provider.subprocess, "run", fake_run)
    transport = CodexTransport(
        commands=resolve_codex_cli_commands(_config(provider_name="codex")),
        model="gpt-test",
        model_effort=None,
    )

    result = transport.run_turn(_rendered_turn(step_name="produce", prompt_text=prompt_text, session=_placeholder_session()))

    assert calls[-1] == [
        "codex",
        "exec",
        "--json",
        "--dangerously-bypass-approvals-and-sandbox",
        "--model",
        "gpt-test",
    ]
    assert result.raw_text == "producer text"
    assert result.session is not None
    assert result.session.session_id == "codex-session-1"
    assert result.metadata["provider_metadata"] == {
        "assistant_message_count": 1,
        "jsonl_event_count": 2,
        "malformed_jsonl_lines": 0,
    }


def test_codex_transport_does_not_parse_workflow_outcome_json(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = CodexTransport(
        commands=CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
        model="gpt-test",
        model_effort=None,
    )
    monkeypatch.setattr(
        codex_runtime_provider.subprocess,
        "run",
        lambda command, **_: _completed(
            args=command,
            stdout='{"type":"item.completed","item":{"type":"agent_message","text":"{\\"tag\\":\\"done\\"}"}}',
        ),
    )

    result = transport.run_turn(
        _rendered_turn(step_name="verify", turn_kind="verifier", expected_response="outcome_json")
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
    monkeypatch.setattr(
        codex_runtime_provider.subprocess,
        "run",
        lambda command, **_: _completed(
            args=command,
            stdout="\n".join(
                (
                    '{"type":"thread.started","thread_id":"codex-session-2"}',
                    '{"type":"response.completed","response":{"usage":{"input_tokens":15,"output_tokens":6,"total_tokens":21}}}',
                    '{"type":"item.completed","item":{"type":"agent_message","text":"producer text"}}',
                )
            ),
        ),
    )
    provider = RenderedLLMProvider(transport)

    response = provider.run_producer(_producer_request(session=_placeholder_session()))

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
    monkeypatch.setattr(codex_runtime_provider.shutil, "which", lambda name: "/usr/bin/codex")

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if command == ["codex", "exec", "--help"]:
            return _completed(args=command, stdout=CODEX_START_HELP)
        if command == ["codex", "exec", "resume", "--help"]:
            return _completed(args=command, stdout=CODEX_RESUME_HELP)
        rendered_prompt = str(kwargs["input"])
        assert "# Step: verify" in rendered_prompt
        assert "## Runtime Step Contract" in rendered_prompt
        assert "### Required inputs" in rendered_prompt
        assert "### Control response" in rendered_prompt
        assert "<producer_raw_output>" not in rendered_prompt
        assert "producer output" not in rendered_prompt
        return _completed(
            args=command,
            stdout="\n".join(
                (
                    '{"type":"thread.started","thread_id":"codex-session-3"}',
                    '{"type":"item.completed","item":{"type":"agent_message","text":"{\\"tag\\":\\"pair_ok\\",\\"reason\\":\\"accepted\\",\\"payload\\":{\\"summary\\":\\"ok\\"}}"}}',
                )
            ),
        )

    monkeypatch.setattr(codex_runtime_provider.subprocess, "run", fake_run)
    provider = RenderedLLMProvider(
        CodexTransport(
            commands=resolve_codex_cli_commands(_config(provider_name="codex")),
            model="gpt-test",
            model_effort=None,
        )
    )

    response = provider.run_verifier(_verifier_request(session=_placeholder_session()))

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
    monkeypatch.setattr(
        codex_runtime_provider.subprocess,
        "run",
        lambda command, **_: _completed(args=command, stdout="not-json\n"),
    )

    with pytest.raises(ProviderExecutionError, match="unusable JSONL output"):
        transport.run_turn(_rendered_turn(session=_placeholder_session()))


def test_codex_transport_raises_on_non_zero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = CodexTransport(
        commands=CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
        model="gpt-test",
        model_effort=None,
    )
    monkeypatch.setattr(
        codex_runtime_provider.subprocess,
        "run",
        lambda command, **_: _completed(args=command, stdout="oops", stderr="bad", returncode=7),
    )

    with pytest.raises(ProviderExecutionError, match=r"exit code 7"):
        transport.run_turn(_rendered_turn(session=_placeholder_session()))


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
        transport.run_turn(_rendered_turn(session=_provider_session("claude")))


def test_claude_transport_sends_rendered_prompt_text_to_cli_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    prompt_text = "# Step: produce\n\nShared runtime prompt."
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return _completed(
            args=command,
            stdout='{"result":"producer text","session_id":"claude-session-1","stop_reason":"end_turn"}',
        )

    monkeypatch.setattr(claude_runtime_provider.subprocess, "run", fake_run)
    transport = ClaudeTransport(config=_config(provider_name="claude").provider.claude)

    result = transport.run_turn(_rendered_turn(step_name="produce", prompt_text=prompt_text, session=_placeholder_session()))

    assert calls[-1] == ["claude", "-p", prompt_text, "--output-format", "json", "--model", "claude-test"]
    assert result.raw_text == "producer text"
    assert result.session is not None
    assert result.session.session_id == "claude-session-1"
    assert result.session.metadata["provider_metadata"] == {"stop_reason": "end_turn"}


def test_claude_transport_does_not_parse_workflow_outcome_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        claude_runtime_provider.subprocess,
        "run",
        lambda command, **_: _completed(args=command, stdout='{"result":"{\\"tag\\":\\"done\\"}"}'),
    )
    transport = ClaudeTransport(config=_config(provider_name="claude").provider.claude)

    result = transport.run_turn(
        _rendered_turn(step_name="ask", turn_kind="llm", expected_response="outcome_json")
    )

    assert result.raw_text == '{"tag":"done"}'


def test_rendered_llm_provider_parses_claude_llm_outcome_in_core(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resumable = _provider_session("claude", session_id="claude-session-existing")
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return _completed(
            args=command,
            stdout='{"result":"{\\"tag\\":\\"done\\",\\"reason\\":\\"completed\\"}","usage":{"prompt_tokens":8,"completion_tokens":3,"total_tokens":11},"stop_reason":"done"}',
        )

    monkeypatch.setattr(claude_runtime_provider.subprocess, "run", fake_run)
    provider = RenderedLLMProvider(
        ClaudeTransport(config=_config(provider_name="claude", claude_permission_strategy="allow_core_tools").provider.claude)
    )

    response = provider.run_llm(_llm_request(session=resumable))

    assert calls[-1][:4] == ["claude", "--resume", "claude-session-existing", "-p"]
    rendered_prompt = calls[-1][4]
    assert "# Step: ask" in rendered_prompt
    assert "## Runtime Step Contract" in rendered_prompt
    assert "<producer_raw_output>" not in rendered_prompt
    assert calls[-1][5:] == [
        "--output-format",
        "json",
        "--model",
        "claude-test",
        "--allowedTools",
        "Read,Write,Edit,Glob,Grep,Bash",
    ]
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
    monkeypatch.setattr(
        claude_runtime_provider.subprocess,
        "run",
        lambda command, **_: _completed(args=command, stdout="{bad-json}"),
    )
    transport = ClaudeTransport(config=_config(provider_name="claude").provider.claude)

    with pytest.raises(ProviderExecutionError, match="malformed JSON output"):
        transport.run_turn(_rendered_turn(session=_placeholder_session()))


def test_claude_transport_raises_on_non_zero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        claude_runtime_provider.subprocess,
        "run",
        lambda command, **_: _completed(args=command, stdout="oops", stderr="bad", returncode=3),
    )
    transport = ClaudeTransport(config=_config(provider_name="claude").provider.claude)

    with pytest.raises(ProviderExecutionError, match=r"exit code 3"):
        transport.run_turn(_rendered_turn(session=_placeholder_session()))


def test_claude_transport_rejects_cross_provider_resume() -> None:
    transport = ClaudeTransport(config=_config(provider_name="claude").provider.claude)

    with pytest.raises(ProviderExecutionError, match="resuming across providers is forbidden"):
        transport.run_turn(_rendered_turn(session=_provider_session("codex")))
