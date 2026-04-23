from __future__ import annotations

import subprocess

import pytest

from autoloop_v3.core.errors import ProviderExecutionError
from autoloop_v3.core.prompts import ResolvedPrompt
from autoloop_v3.core.providers.models import LLMRequest, ProducerRequest, VerifierRequest
from autoloop_v3.core.stores.protocols import SessionBinding
from autoloop_v3.runtime.config import (
    ClaudeProviderConfig,
    CodexProviderConfig,
    ConfigError,
    ProviderConfig,
    ResolvedRuntimeConfig,
    RuntimeConfig,
)
from autoloop_v3.runtime.providers._common import (
    build_session_binding,
    ensure_session_provider_match,
    format_subprocess_streams,
    parse_outcome_json,
    render_verifier_input,
    require_prompt_text,
)
from autoloop_v3.runtime.providers.claude import (
    ClaudeProvider,
    claude_permission_args,
    parse_claude_exec_json,
    verify_claude_code_capabilities,
)
import autoloop_v3.runtime.providers.claude as claude_runtime_provider
from autoloop_v3.runtime.providers.codex import (
    CodexProvider,
    resolve_codex_cli_commands,
    parse_codex_exec_json,
    verify_codex_exec_capabilities,
)
import autoloop_v3.runtime.providers.codex as codex_runtime_provider


CODEX_START_HELP = "--json\n-m, --model <MODEL>\n--dangerously-bypass-approvals-and-sandbox\n"
CODEX_RESUME_HELP = "--json\n-m, --model <MODEL>\n--dangerously-bypass-approvals-and-sandbox\n"
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


def test_require_prompt_text_rejects_missing_text() -> None:
    with pytest.raises(ProviderExecutionError, match=r"provider 'codex'.*step 'plan'"):
        require_prompt_text(ResolvedPrompt(path="plan.md", text=None), "codex", "plan")


def test_format_subprocess_streams_renders_empty_streams() -> None:
    assert format_subprocess_streams("", "") == "[empty stdout/stderr]"


def test_ensure_session_provider_match_rejects_cross_provider_resume() -> None:
    with pytest.raises(ProviderExecutionError, match="resuming across providers is forbidden"):
        ensure_session_provider_match("codex", _provider_session("claude"))


def test_render_verifier_input_is_explicit_and_deterministic() -> None:
    rendered = render_verifier_input("Check it", "raw body")

    assert rendered == (
        "<verifier_prompt>\nCheck it\n</verifier_prompt>\n\n"
        "<producer_raw_output>\nraw body\n</producer_raw_output>\n"
    )


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


def test_parse_outcome_json_accepts_plain_object() -> None:
    outcome = parse_outcome_json('{"tag":"done","reason":"ok","payload":{"x":1}}')

    assert outcome.tag == "done"
    assert outcome.reason == "ok"
    assert outcome.payload == {"x": 1}
    assert outcome.raw_output == '{"tag":"done","reason":"ok","payload":{"x":1}}'


def test_parse_outcome_json_accepts_fenced_json_block() -> None:
    raw = '```json\n{"tag":"question","question":"Proceed?"}\n```'

    outcome = parse_outcome_json(raw)

    assert outcome.tag == "question"
    assert outcome.question == "Proceed?"
    assert outcome.payload == {}
    assert outcome.raw_output == raw


def test_parse_outcome_json_rejects_invalid_json() -> None:
    with pytest.raises(ProviderExecutionError, match="malformed outcome JSON"):
        parse_outcome_json("{not-json}")


def test_parse_outcome_json_rejects_missing_tag() -> None:
    with pytest.raises(ProviderExecutionError, match="must contain a non-empty string 'tag'"):
        parse_outcome_json('{"reason":"missing"}')


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

    assistant_text, session_id, provider_metadata = parse_codex_exec_json(stdout)

    assert assistant_text == "hello"
    assert session_id == "codex-session-1"
    assert provider_metadata == {
        "assistant_message_count": 1,
        "jsonl_event_count": 2,
        "malformed_jsonl_lines": 1,
    }


def test_parse_codex_exec_json_rejects_missing_assistant_text() -> None:
    stdout = '{"type":"thread.started","thread_id":"codex-session-1"}\n'

    with pytest.raises(ProviderExecutionError, match="did not return assistant text"):
        parse_codex_exec_json(stdout)


def test_parse_claude_exec_json_preserves_provider_metadata() -> None:
    result, session_id, provider_metadata = parse_claude_exec_json(
        '{"result":"hello","session_id":"claude-session-1","stop_reason":"end_turn"}'
    )

    assert result == "hello"
    assert session_id == "claude-session-1"
    assert provider_metadata == {"stop_reason": "end_turn"}


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
        lambda command, **_: _completed(args=command, stdout=CLAUDE_HELP),
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


def test_codex_provider_run_producer_uses_start_command_for_placeholder_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(codex_runtime_provider.shutil, "which", lambda name: "/usr/bin/codex")
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command == ["codex", "exec", "--help"]:
            return _completed(args=command, stdout=CODEX_START_HELP)
        if command == ["codex", "exec", "resume", "--help"]:
            return _completed(args=command, stdout=CODEX_RESUME_HELP)
        assert kwargs["input"] == "prompt"
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
    provider = CodexProvider(_config(provider_name="codex"), resolve_codex_cli_commands(_config(provider_name="codex")))

    response = provider.run_producer(_producer_request(session=_placeholder_session()))

    assert calls[-1] == [
        "codex",
        "exec",
        "--json",
        "--dangerously-bypass-approvals-and-sandbox",
        "--model",
        "gpt-test",
    ]
    assert response.raw_output == "producer text"
    assert response.session is not None
    assert response.session.session_id == "codex-session-1"
    assert response.session.metadata["provider"] == "codex"
    assert response.session.metadata["provider_metadata"] == {
        "assistant_message_count": 1,
        "jsonl_event_count": 2,
        "malformed_jsonl_lines": 0,
    }
    assert "thread_id" not in response.session.metadata["provider_metadata"]
    assert response.metadata["provider_metadata"] == response.session.metadata["provider_metadata"]


def test_codex_provider_run_verifier_parses_strict_json_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(codex_runtime_provider.shutil, "which", lambda name: "/usr/bin/codex")

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if command == ["codex", "exec", "--help"]:
            return _completed(args=command, stdout=CODEX_START_HELP)
        if command == ["codex", "exec", "resume", "--help"]:
            return _completed(args=command, stdout=CODEX_RESUME_HELP)
        assert "<verifier_prompt>" in str(kwargs["input"])
        assert "<producer_raw_output>" in str(kwargs["input"])
        return _completed(
            args=command,
            stdout="\n".join(
                (
                    '{"type":"thread.started","thread_id":"codex-session-2"}',
                    '{"type":"item.completed","item":{"type":"agent_message","text":"{\\"tag\\":\\"pair_ok\\",\\"payload\\":{\\"summary\\":\\"ok\\"}}"}}',
                )
            ),
        )

    monkeypatch.setattr(codex_runtime_provider.subprocess, "run", fake_run)
    provider = CodexProvider(_config(provider_name="codex"), resolve_codex_cli_commands(_config(provider_name="codex")))

    response = provider.run_verifier(_verifier_request(session=_placeholder_session()))

    assert response.outcome.tag == "pair_ok"
    assert response.outcome.payload == {"summary": "ok"}
    assert response.session is not None
    assert response.session.session_id == "codex-session-2"


def test_codex_provider_run_llm_resumes_existing_provider_session_and_preserves_session_id_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(codex_runtime_provider.shutil, "which", lambda name: "/usr/bin/codex")
    resumable = _provider_session("codex", session_id="codex-session-existing")
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command == ["codex", "exec", "--help"]:
            return _completed(args=command, stdout=CODEX_START_HELP)
        if command == ["codex", "exec", "resume", "--help"]:
            return _completed(args=command, stdout=CODEX_RESUME_HELP)
        return _completed(
            args=command,
            stdout='{"type":"item.completed","item":{"type":"agent_message","text":"{\\"tag\\":\\"done\\"}"}}',
        )

    monkeypatch.setattr(codex_runtime_provider.subprocess, "run", fake_run)
    provider = CodexProvider(_config(provider_name="codex"), resolve_codex_cli_commands(_config(provider_name="codex")))

    response = provider.run_llm(_llm_request(session=resumable))

    assert calls[-1] == [
        "codex",
        "exec",
        "resume",
        "--json",
        "--dangerously-bypass-approvals-and-sandbox",
        "--model",
        "gpt-test",
        "codex-session-existing",
        "-",
    ]
    assert response.outcome.tag == "done"
    assert response.session is not None
    assert response.session.session_id == "codex-session-existing"


def test_codex_provider_rejects_unusable_jsonl(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = CodexProvider(_config(provider_name="codex"), codex_runtime_provider.CodexCLICommand(
        start_command=("codex", "exec", "--json"),
        resume_command=("codex", "exec", "resume", "--json"),
    ))
    monkeypatch.setattr(
        codex_runtime_provider.subprocess,
        "run",
        lambda command, **_: _completed(args=command, stdout="not-json\n"),
    )

    with pytest.raises(ProviderExecutionError, match="unusable JSONL output"):
        provider.run_producer(_producer_request(session=_placeholder_session()))


def test_codex_provider_raises_on_non_zero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = CodexProvider(_config(provider_name="codex"), codex_runtime_provider.CodexCLICommand(
        start_command=("codex", "exec", "--json"),
        resume_command=("codex", "exec", "resume", "--json"),
    ))
    monkeypatch.setattr(
        codex_runtime_provider.subprocess,
        "run",
        lambda command, **_: _completed(args=command, stdout="oops", stderr="bad", returncode=7),
    )

    with pytest.raises(ProviderExecutionError, match=r"exit code 7"):
        provider.run_producer(_producer_request(session=_placeholder_session()))


def test_codex_provider_rejects_cross_provider_resume() -> None:
    provider = CodexProvider(
        _config(provider_name="codex"),
        codex_runtime_provider.CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
    )

    with pytest.raises(ProviderExecutionError, match="resuming across providers is forbidden"):
        provider.run_producer(_producer_request(session=_provider_session("claude")))


def test_claude_provider_run_producer_parses_json_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(claude_runtime_provider.shutil, "which", lambda name: "/usr/bin/claude")
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command == ["claude", "--help"]:
            return _completed(args=command, stdout=CLAUDE_HELP)
        return _completed(
            args=command,
            stdout='{"result":"producer text","session_id":"claude-session-1","stop_reason":"end_turn"}',
        )

    monkeypatch.setattr(claude_runtime_provider.subprocess, "run", fake_run)
    provider = ClaudeProvider(_config(provider_name="claude"))

    response = provider.run_producer(_producer_request(session=_placeholder_session()))

    assert calls[-1] == ["claude", "-p", "prompt", "--output-format", "json", "--model", "claude-test"]
    assert response.raw_output == "producer text"
    assert response.session is not None
    assert response.session.session_id == "claude-session-1"
    assert response.session.metadata["provider"] == "claude"
    assert response.session.metadata["provider_metadata"] == {"stop_reason": "end_turn"}
    assert "thread_id" not in response.session.metadata["provider_metadata"]


def test_claude_provider_run_verifier_parses_strict_json_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(claude_runtime_provider.shutil, "which", lambda name: "/usr/bin/claude")

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if command == ["claude", "--help"]:
            return _completed(args=command, stdout=CLAUDE_HELP)
        return _completed(
            args=command,
            stdout='{"result":"{\\"tag\\":\\"pair_ok\\",\\"payload\\":{\\"summary\\":\\"ok\\"}}","session_id":"claude-session-2"}',
        )

    monkeypatch.setattr(claude_runtime_provider.subprocess, "run", fake_run)
    provider = ClaudeProvider(_config(provider_name="claude"))

    response = provider.run_verifier(_verifier_request(session=_placeholder_session()))

    assert response.outcome.tag == "pair_ok"
    assert response.outcome.payload == {"summary": "ok"}
    assert response.session is not None
    assert response.session.session_id == "claude-session-2"


def test_claude_provider_run_llm_resumes_existing_provider_session_and_preserves_session_id_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(claude_runtime_provider.shutil, "which", lambda name: "/usr/bin/claude")
    resumable = _provider_session("claude", session_id="claude-session-existing")
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command == ["claude", "--help"]:
            return _completed(args=command, stdout=CLAUDE_HELP)
        return _completed(args=command, stdout='{"result":"{\\"tag\\":\\"done\\"}","stop_reason":"done"}')

    monkeypatch.setattr(claude_runtime_provider.subprocess, "run", fake_run)
    provider = ClaudeProvider(_config(provider_name="claude", claude_permission_strategy="allow_core_tools"))

    response = provider.run_llm(_llm_request(session=resumable))

    assert calls[-1] == [
        "claude",
        "--resume",
        "claude-session-existing",
        "-p",
        "ask",
        "--output-format",
        "json",
        "--model",
        "claude-test",
        "--allowedTools",
        "Read,Write,Edit,Glob,Grep,Bash",
    ]
    assert response.outcome.tag == "done"
    assert response.session is not None
    assert response.session.session_id == "claude-session-existing"
    assert response.session.metadata["provider_metadata"] == {"stop_reason": "done"}


def test_claude_provider_rejects_malformed_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(claude_runtime_provider.shutil, "which", lambda name: "/usr/bin/claude")

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if command == ["claude", "--help"]:
            return _completed(args=command, stdout=CLAUDE_HELP)
        return _completed(args=command, stdout="{bad-json}")

    monkeypatch.setattr(claude_runtime_provider.subprocess, "run", fake_run)
    provider = ClaudeProvider(_config(provider_name="claude"))

    with pytest.raises(ProviderExecutionError, match="malformed JSON output"):
        provider.run_producer(_producer_request(session=_placeholder_session()))


def test_claude_provider_raises_on_non_zero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(claude_runtime_provider.shutil, "which", lambda name: "/usr/bin/claude")

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if command == ["claude", "--help"]:
            return _completed(args=command, stdout=CLAUDE_HELP)
        return _completed(args=command, stdout="oops", stderr="bad", returncode=3)

    monkeypatch.setattr(claude_runtime_provider.subprocess, "run", fake_run)
    provider = ClaudeProvider(_config(provider_name="claude"))

    with pytest.raises(ProviderExecutionError, match=r"exit code 3"):
        provider.run_producer(_producer_request(session=_placeholder_session()))


def test_claude_provider_rejects_cross_provider_resume(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(claude_runtime_provider.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(
        claude_runtime_provider.subprocess,
        "run",
        lambda command, **_: _completed(args=command, stdout=CLAUDE_HELP),
    )
    provider = ClaudeProvider(_config(provider_name="claude"))

    with pytest.raises(ProviderExecutionError, match="resuming across providers is forbidden"):
        provider.run_producer(_producer_request(session=_provider_session("codex")))
