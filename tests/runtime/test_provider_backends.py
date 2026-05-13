from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from botpipe.core.outcome_contract import NATIVE_SCHEMA_EXCEEDS_LIMIT
from botpipe.core.providers.rendered import RenderedLLMProvider
from botpipe.core.providers.turns import ProviderTurnResult, RenderedProviderTurn
from botpipe.core.stores.protocols import SessionBinding
from botpipe.runtime import cli
from botpipe.runtime import providers as runtime_providers
from botpipe.runtime.providers.claude import ClaudeProvider, ClaudeTransport, build_claude_provider
import botpipe.runtime.providers.claude as claude_runtime_provider
from botpipe.runtime.providers.codex import CodexCLICommand, CodexProvider, CodexTransport, build_codex_provider
import botpipe.runtime.providers.codex as codex_runtime_provider
from botpipe.runtime.config import (
    ClaudeProviderConfig,
    CodexProviderConfig,
    ConfigError,
    ProviderConfig,
    ResolvedRuntimeConfig,
    RuntimeConfig,
    resolve_runtime_config,
)
import botpipe.runtime.config as runtime_config
from botpipe.runtime.provider_backends import resolve_provider_backend
import botpipe.runtime.provider_backends as provider_backends


CLAUDE_HEADLESS_HELP = "--print\n-p\n--output-format\n--resume\n--model\n--settings\n--add-dir\n"
_NATIVE_RESPONSE_SCHEMA_UNSET = object()


class _StubTransport:
    async def run_turn(self, turn: RenderedProviderTurn) -> ProviderTurnResult:  # pragma: no cover - defensive
        raise AssertionError(f"unexpected turn call: {turn!r}")


class _SyncOnlyTransport:
    def run_turn(self, turn: RenderedProviderTurn) -> ProviderTurnResult:  # pragma: no cover - defensive
        return ProviderTurnResult(raw_text="sync")


def _resolved_config(provider_name: str = "codex") -> ResolvedRuntimeConfig:
    return ResolvedRuntimeConfig(
        provider=ProviderConfig(
            name=provider_name,
            codex=CodexProviderConfig(model="gpt-test", model_effort=None),
            claude=ClaudeProviderConfig(model="claude-test", effort=None),
        ),
        runtime=RuntimeConfig(max_steps=5),
    )


def _runtime_args(**overrides: object) -> argparse.Namespace:
    payload = {
        "provider": None,
        "model": None,
        "model_effort": None,
        "max_steps": None,
        "no_git": False,
        "git_commit_policy": None,
        "no_trace": False,
    }
    payload.update(overrides)
    return argparse.Namespace(**payload)


@pytest.fixture(autouse=True)
def _clear_provider_cli_caches() -> None:
    codex_runtime_provider._probe_codex_exec_surface.cache_clear()
    claude_runtime_provider._probe_claude_help_surface.cache_clear()


def _completed(*, args: list[str], stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=args, returncode=returncode, stdout=stdout, stderr=stderr)


def _closed_empty_object_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }


def _outcome_turn(
    *,
    tmp_path: Path,
    session: SessionBinding | None = None,
    response_schema: dict[str, object] | None = None,
    native_response_schema: dict[str, object] | None | object = _NATIVE_RESPONSE_SCHEMA_UNSET,
    response_schema_native_skip_reason: str | None = None,
) -> RenderedProviderTurn:
    response_schema = response_schema or {
        "type": "object",
        "properties": {
            "outcome": {
                "type": "object",
                "properties": {
                    "tag": {"type": "string", "const": "done"},
                    "payload": _closed_empty_object_schema(),
                    "route_fields": _closed_empty_object_schema(),
                },
                "required": ["tag", "payload", "route_fields"],
                "additionalProperties": False,
            }
        },
        "required": ["outcome"],
        "additionalProperties": False,
    }
    if native_response_schema is _NATIVE_RESPONSE_SCHEMA_UNSET:
        native_response_schema = response_schema
    return RenderedProviderTurn(
        step_name="review",
        turn_kind="step",
        prompt_text="Return a routed outcome.",
        session=session,
        expected_response="outcome_json",
        run_folder=tmp_path,
        response_schema=response_schema,
        native_response_schema=native_response_schema,
        response_schema_native_skip_reason=response_schema_native_skip_reason,
    )


def test_resolve_provider_backend_dispatches_by_provider_name(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    codex_transport = _StubTransport()
    claude_transport = _StubTransport()

    def operation_executor(turn: RenderedProviderTurn) -> ProviderTurnResult:
        return ProviderTurnResult(raw_text="operation")

    monkeypatch.setitem(
        provider_backends._BACKEND_BUILDERS,
        "codex",
        lambda config: seen.append(config.provider.name) or codex_transport,
    )
    monkeypatch.setitem(
        provider_backends._BACKEND_BUILDERS,
        "claude",
        lambda config: seen.append(config.provider.name) or claude_transport,
    )
    monkeypatch.setitem(
        provider_backends._OPERATION_EXECUTOR_BUILDERS,
        "codex",
        lambda config: operation_executor,
    )
    monkeypatch.setitem(
        provider_backends._OPERATION_EXECUTOR_BUILDERS,
        "claude",
        lambda config: operation_executor,
    )

    codex_provider = resolve_provider_backend(config=_resolved_config("codex"))
    claude_provider = resolve_provider_backend(config=_resolved_config("claude"))

    assert isinstance(codex_provider, RenderedLLMProvider)
    assert codex_provider._transport is codex_transport
    assert isinstance(claude_provider, RenderedLLMProvider)
    assert claude_provider._transport is claude_transport
    assert seen == ["codex", "claude"]


def test_codex_backend_delivers_full_response_schema_via_output_schema_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        codex_runtime_provider,
        "_probe_codex_exec_surface",
        lambda: codex_runtime_provider._CodexExecSurface(
            start_help="--json\n--output-schema\n-m, --model <MODEL>\n",
            resume_help="--json\n-m, --model <MODEL>\n",
        ),
    )

    def fake_run_text_subprocess(command: list[str], *, input_text=None, env=None):
        captured["command"] = list(command)
        captured["input_text"] = input_text
        captured["env"] = dict(env or {})
        return (
            '{"type":"thread.started","thread_id":"thread-1"}\n'
            '{"type":"item.completed","item":{"type":"agent_message","text":"{\\"outcome\\":{\\"tag\\":\\"done\\",\\"payload\\":{},\\"route_fields\\":{}}}"}}',
            "",
            0,
        )

    monkeypatch.setattr(codex_runtime_provider, "run_text_subprocess", fake_run_text_subprocess)

    executor = codex_runtime_provider.build_codex_operation_executor(
        _resolved_config("codex"),
        commands=CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
    )
    turn = _outcome_turn(tmp_path=tmp_path)

    result = executor(turn)

    command = captured["command"]
    assert isinstance(command, list)
    assert "--output-schema" in command
    schema_path = Path(command[command.index("--output-schema") + 1])
    assert json.loads(schema_path.read_text(encoding="utf-8")) == turn.response_schema
    assert result.metadata["structured_output"] == {
        "provider": "codex",
        "delivery_mode": "native_full",
        "schema_path": str(schema_path),
    }


def test_codex_backend_writes_native_response_schema_when_it_differs_from_prompt_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    prompt_schema = {
        "type": "object",
        "properties": {
            "outcome": {
                "type": "object",
                "properties": {
                    "tag": {"type": "string", "const": "done"},
                    "payload": _closed_empty_object_schema(),
                    "route_fields": _closed_empty_object_schema(),
                },
                "required": ["tag", "payload", "route_fields"],
                "additionalProperties": False,
            }
        },
        "required": ["outcome"],
        "additionalProperties": False,
        "description": "prompt-only detail",
    }
    native_schema = {
        key: value
        for key, value in prompt_schema.items()
        if key != "description"
    }

    monkeypatch.setattr(
        codex_runtime_provider,
        "_probe_codex_exec_surface",
        lambda: codex_runtime_provider._CodexExecSurface(
            start_help="--json\n--output-schema\n-m, --model <MODEL>\n",
            resume_help="--json\n-m, --model <MODEL>\n",
        ),
    )

    def fake_run_text_subprocess(command: list[str], *, input_text=None, env=None):
        captured["command"] = list(command)
        return (
            '{"type":"thread.started","thread_id":"thread-1"}\n'
            '{"type":"item.completed","item":{"type":"agent_message","text":"{\\"outcome\\":{\\"tag\\":\\"done\\",\\"payload\\":{},\\"route_fields\\":{}}}"}}',
            "",
            0,
        )

    monkeypatch.setattr(codex_runtime_provider, "run_text_subprocess", fake_run_text_subprocess)

    executor = codex_runtime_provider.build_codex_operation_executor(
        _resolved_config("codex"),
        commands=CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
    )
    turn = _outcome_turn(
        tmp_path=tmp_path,
        response_schema=prompt_schema,
        native_response_schema=native_schema,
    )

    executor(turn)

    command = captured["command"]
    assert isinstance(command, list)
    schema_path = Path(command[command.index("--output-schema") + 1])
    assert json.loads(schema_path.read_text(encoding="utf-8")) == native_schema
    assert json.loads(schema_path.read_text(encoding="utf-8")) != turn.response_schema


def test_codex_backend_uses_prompt_only_when_response_schema_exceeds_native_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    detailed_schema = {
        "type": "object",
        "properties": {
            "outcome": {
                "anyOf": [
                    {
                        "type": "object",
                        "properties": {
                            "tag": {"type": "string", "const": "done"},
                            "payload": {
                                "type": "object",
                                "properties": {"summary": {"type": "string"}},
                                "required": ["summary"],
                                "additionalProperties": False,
                            },
                            "route_fields": {
                                "type": "object",
                                "properties": {},
                                "required": [],
                                "additionalProperties": False,
                            },
                        },
                        "required": ["tag", "payload", "route_fields"],
                        "additionalProperties": False,
                    }
                ]
            }
        },
        "required": ["outcome"],
        "additionalProperties": False,
    }

    monkeypatch.setattr(
        codex_runtime_provider,
        "_probe_codex_exec_surface",
        lambda: codex_runtime_provider._CodexExecSurface(
            start_help="--json\n--output-schema\n-m, --model <MODEL>\n",
            resume_help="--json\n-m, --model <MODEL>\n",
        ),
    )

    def fake_run_text_subprocess(command: list[str], *, input_text=None, env=None):
        captured["command"] = list(command)
        return (
            '{"type":"thread.started","thread_id":"thread-1"}\n'
            '{"type":"item.completed","item":{"type":"agent_message","text":"{\\"outcome\\":{\\"tag\\":\\"done\\",\\"payload\\":{},\\"route_fields\\":{}}}"}}',
            "",
            0,
        )

    monkeypatch.setattr(codex_runtime_provider, "run_text_subprocess", fake_run_text_subprocess)

    executor = codex_runtime_provider.build_codex_operation_executor(
        _resolved_config("codex"),
        commands=CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
    )
    turn = _outcome_turn(
        tmp_path=tmp_path,
        response_schema=detailed_schema,
        native_response_schema=None,
        response_schema_native_skip_reason=NATIVE_SCHEMA_EXCEEDS_LIMIT,
    )
    result = executor(turn)

    command = captured["command"]
    assert isinstance(command, list)
    assert "--output-schema" not in command
    assert result.metadata["structured_output"] == {
        "provider": "codex",
        "delivery_mode": "prompt_only",
        "reason": "provider_response_schema_exceeds_native_limit",
    }


def test_codex_backend_records_prompt_only_fallback_when_resume_lacks_output_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        codex_runtime_provider,
        "_probe_codex_exec_surface",
        lambda: codex_runtime_provider._CodexExecSurface(
            start_help="--json\n--output-schema\n-m, --model <MODEL>\n",
            resume_help="--json\n-m, --model <MODEL>\n",
        ),
    )

    def fake_run_text_subprocess(command: list[str], *, input_text=None, env=None):
        captured["command"] = list(command)
        return (
            '{"type":"item.completed","item":{"type":"agent_message","text":"{\\"outcome\\":{\\"tag\\":\\"done\\",\\"payload\\":{},\\"route_fields\\":{}}}"}}',
            "",
            0,
        )

    monkeypatch.setattr(codex_runtime_provider, "run_text_subprocess", fake_run_text_subprocess)

    executor = codex_runtime_provider.build_codex_operation_executor(
        _resolved_config("codex"),
        commands=CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
    )
    turn = _outcome_turn(
        tmp_path=tmp_path,
        session=SessionBinding(ref_name="default", session_id="thread-1", provider="codex", metadata={"provider": "codex"}),
    )

    result = executor(turn)

    command = captured["command"]
    assert isinstance(command, list)
    assert "--output-schema" not in command
    assert result.metadata["structured_output"] == {
        "provider": "codex",
        "delivery_mode": "prompt_only",
        "reason": "resume_command_does_not_support_output_schema",
    }


def test_codex_operation_executor_recovers_from_missing_rollout_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run_text_subprocess(command: list[str], *, input_text=None, env=None):
        calls.append(list(command))
        if "resume" in command:
            return (
                "",
                (
                    "Error: thread/resume: thread/resume failed: no rollout found for thread id "
                    "stale-thread (code -32600)"
                ),
                1,
            )
        return (
            '{"type":"thread.started","thread_id":"fresh-thread"}\n'
            '{"type":"item.completed","item":{"type":"agent_message","text":"{\\"outcome\\":{\\"tag\\":\\"done\\",\\"payload\\":{},\\"route_fields\\":{}}}"}}',
            "",
            0,
        )

    monkeypatch.setattr(codex_runtime_provider, "run_text_subprocess", fake_run_text_subprocess)

    executor = codex_runtime_provider.build_codex_operation_executor(
        _resolved_config("codex"),
        commands=CodexCLICommand(
            start_command=("codex", "exec", "--json"),
            resume_command=("codex", "exec", "resume", "--json"),
        ),
    )
    turn = _outcome_turn(
        tmp_path=tmp_path,
        session=SessionBinding(
            ref_name="default",
            session_id="stale-thread",
            provider="codex",
            metadata={"provider": "codex"},
        ),
    )

    result = executor(turn)

    assert calls[0] == ["codex", "exec", "resume", "--json", "--model", "gpt-test", "stale-thread", "-"]
    assert calls[1][:5] == ["codex", "exec", "--json", "--model", "gpt-test"]
    assert "--output-schema" in calls[1]
    assert result.session is not None
    assert result.session.session_id == "fresh-thread"
    assert result.metadata["mode"] == "start"
    assert result.metadata["provider_metadata"]["resume_recovery"]["reason"] == "missing_rollout"


def test_claude_backend_records_prompt_only_fallback_for_response_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(claude_runtime_provider, "verify_claude_code_capabilities", lambda config=None: None)

    def fake_run_text_subprocess(command: list[str], *, input_text=None, env=None, cwd=None):
        captured["command"] = list(command)
        return (
            json.dumps(
                {
                    "result": '{"outcome":{"tag":"done","payload":{},"route_fields":{}}}',
                    "session_id": "session-1",
                }
            ),
            "",
            0,
        )

    monkeypatch.setattr(claude_runtime_provider, "run_text_subprocess", fake_run_text_subprocess)

    executor = claude_runtime_provider.build_claude_operation_executor(_resolved_config("claude"))
    result = executor(_outcome_turn(tmp_path=tmp_path))

    command = captured["command"]
    assert isinstance(command, list)
    assert "--output-schema" not in command
    assert result.metadata["structured_output"] == {
        "provider": "claude",
        "delivery_mode": "prompt_only",
        "reason": "backend_does_not_support_output_schema",
    }


def test_resolve_provider_backend_rejects_sync_transport_builder_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        provider_backends._BACKEND_BUILDERS,
        "codex",
        lambda config: _SyncOnlyTransport(),
    )
    monkeypatch.setitem(
        provider_backends._OPERATION_EXECUTOR_BUILDERS,
        "codex",
        lambda config: (lambda turn: ProviderTurnResult(raw_text="operation")),
    )

    with pytest.raises(TypeError, match="provider transport .* async coroutine functions"):
        resolve_provider_backend(config=_resolved_config("codex"))


def test_resolve_provider_backend_rejects_module_function_provider_names() -> None:
    config = _resolved_config()
    config = replace(config, provider=replace(config.provider, name="provider_backend:build"))

    with pytest.raises(ConfigError, match="module:function strings"):
        resolve_provider_backend(config=config)


def test_resolve_provider_backend_raises_precise_error_for_unavailable_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(claude_runtime_provider.shutil, "which", lambda name: None)

    with pytest.raises(
        ConfigError,
        match=r"provider 'claude' is unavailable in this environment: the 'claude' CLI was not found on PATH\.",
    ):
        resolve_provider_backend(config=_resolved_config("claude"))


def test_resolve_provider_backend_raises_precise_error_for_unavailable_codex_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(codex_runtime_provider.shutil, "which", lambda name: None)

    with pytest.raises(
        ConfigError,
        match=r"provider 'codex' is unavailable in this environment: the 'codex' CLI was not found on PATH\.",
    ):
        resolve_provider_backend(config=_resolved_config("codex"))


def test_resolve_codex_cli_commands_no_longer_bakes_policy_flags_or_model_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(codex_runtime_provider.shutil, "which", lambda name: "/usr/bin/codex")

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if command == ["codex", "exec", "--help"]:
            return _completed(args=command, stdout="--json\n-m, --model <MODEL>\n--model-effort\n--full-auto\n")
        if command == ["codex", "exec", "resume", "--help"]:
            return _completed(args=command, stdout="--json\n-m, --model <MODEL>\n--model-effort\n--full-auto\n")
        raise AssertionError(f"unexpected command: {command!r}")

    monkeypatch.setattr(codex_runtime_provider.subprocess, "run", fake_run)

    commands = codex_runtime_provider.resolve_codex_cli_commands(_resolved_config("codex"))

    assert commands == CodexCLICommand(
        start_command=("codex", "exec", "--json"),
        resume_command=("codex", "exec", "resume", "--json"),
    )


def test_resolve_provider_backend_returns_rendered_codex_provider_when_capabilities_are_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(codex_runtime_provider.shutil, "which", lambda name: "/usr/bin/codex")

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if command == ["codex", "exec", "--help"]:
            return _completed(
                args=command,
                stdout="--json\n-m, --model <MODEL>\n--dangerously-bypass-approvals-and-sandbox\n",
            )
        if command == ["codex", "exec", "resume", "--help"]:
            return _completed(
                args=command,
                stdout="--json\n-m, --model <MODEL>\n--dangerously-bypass-approvals-and-sandbox\n",
            )
        raise AssertionError(f"unexpected command: {command!r}")

    monkeypatch.setattr(codex_runtime_provider.subprocess, "run", fake_run)

    provider = resolve_provider_backend(config=_resolved_config("codex"))

    assert isinstance(provider, RenderedLLMProvider)
    assert isinstance(provider._transport, CodexTransport)


def test_resolve_provider_backend_returns_rendered_claude_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(claude_runtime_provider.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(
        claude_runtime_provider.subprocess,
        "run",
        lambda command, **_: _completed(
            args=command,
            stdout=CLAUDE_HEADLESS_HELP,
        ),
    )

    provider = resolve_provider_backend(config=_resolved_config("claude"))

    assert isinstance(provider, RenderedLLMProvider)
    assert isinstance(provider._transport, ClaudeTransport)


def test_resolve_runtime_config_reads_full_auto_runtime_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / "repo"
    config_root.mkdir()
    (config_root / "botpipe.yaml").write_text("runtime:\n  full_auto: true\n", encoding="utf-8")
    monkeypatch.setattr(runtime_config, "user_config_dir", lambda: tmp_path / "missing-user-config")

    resolved = resolve_runtime_config(config_root, _runtime_args())

    assert resolved.runtime.full_auto is True


def test_resolve_runtime_config_reads_valid_nested_runtime_policy_without_pyyaml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / "repo"
    config_root.mkdir()
    (config_root / "botpipe.yaml").write_text(
        "runtime:\n  full_auto: true\n  tracing:\n    include_state_snapshots: false\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime_config, "user_config_dir", lambda: tmp_path / "missing-user-config")
    monkeypatch.setattr(runtime_config, "yaml", None)

    resolved = resolve_runtime_config(config_root, _runtime_args())

    assert resolved.runtime.full_auto is True
    assert resolved.runtime.tracing.include_state_snapshots is False


def test_load_runtime_config_file_without_pyyaml_rejects_indented_child_under_scalar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "botpipe.yaml"
    config_path.write_text("runtime: true\n  full_auto: false\n", encoding="utf-8")
    monkeypatch.setattr(runtime_config, "yaml", None)

    with pytest.raises(ConfigError, match="top-level entries must not be indented"):
        runtime_config.load_runtime_config_file(config_path)


def test_load_runtime_config_file_without_pyyaml_rejects_overindented_sibling_mapping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "botpipe.yaml"
    config_path.write_text("provider:\n  name: codex\n    model: gpt-5\n", encoding="utf-8")
    monkeypatch.setattr(runtime_config, "yaml", None)

    with pytest.raises(ConfigError, match="indentation increase is only allowed"):
        runtime_config.load_runtime_config_file(config_path)


def test_runtime_provider_package_reexports_compatibility_names() -> None:
    assert runtime_providers.CodexProvider is CodexProvider
    assert runtime_providers.ClaudeProvider is ClaudeProvider
    assert runtime_providers.build_codex_provider is build_codex_provider
    assert runtime_providers.build_claude_provider is build_claude_provider


def test_compatibility_build_codex_provider_returns_rendered_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(codex_runtime_provider.shutil, "which", lambda name: "/usr/bin/codex")

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if command == ["codex", "exec", "--help"]:
            return _completed(
                args=command,
                stdout="--json\n-m, --model <MODEL>\n--dangerously-bypass-approvals-and-sandbox\n",
            )
        if command == ["codex", "exec", "resume", "--help"]:
            return _completed(
                args=command,
                stdout="--json\n-m, --model <MODEL>\n--dangerously-bypass-approvals-and-sandbox\n",
            )
        raise AssertionError(f"unexpected command: {command!r}")

    monkeypatch.setattr(codex_runtime_provider.subprocess, "run", fake_run)

    provider = build_codex_provider(_resolved_config("codex"))

    assert isinstance(provider, RenderedLLMProvider)
    assert isinstance(provider._transport, CodexTransport)


def test_compatibility_codex_provider_preserves_legacy_constructor_shape() -> None:
    commands = codex_runtime_provider.CodexCLICommand(
        start_command=("codex", "exec", "--json"),
        resume_command=("codex", "exec", "resume", "--json"),
    )

    provider = CodexProvider(_resolved_config("codex"), commands)

    assert isinstance(provider, RenderedLLMProvider)
    assert isinstance(provider._transport, CodexTransport)
    assert provider._transport._commands == commands


def test_compatibility_build_claude_provider_returns_rendered_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(claude_runtime_provider.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(
        claude_runtime_provider.subprocess,
        "run",
        lambda command, **_: _completed(args=command, stdout=CLAUDE_HEADLESS_HELP),
    )

    provider = build_claude_provider(_resolved_config("claude"))

    assert isinstance(provider, RenderedLLMProvider)
    assert isinstance(provider._transport, ClaudeTransport)


def test_compatibility_claude_provider_constructor_returns_rendered_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(claude_runtime_provider.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(
        claude_runtime_provider.subprocess,
        "run",
        lambda command, **_: _completed(args=command, stdout=CLAUDE_HEADLESS_HELP),
    )

    provider = ClaudeProvider(_resolved_config("claude"))

    assert isinstance(provider, RenderedLLMProvider)
    assert isinstance(provider._transport, ClaudeTransport)


@pytest.mark.parametrize(
    ("module", "banned_tokens"),
    (
        (
            codex_runtime_provider,
            (
                "ProducerRequest",
                "VerifierRequest",
                "LLMRequest",
                "ProducerResponse",
                "OutcomeResponse",
                "parse_outcome_json",
                "render_verifier_input",
                "render_provider_turn",
                "route_" + "infos",
                "route_required_writes",
                "available_routes",
                "required_artifacts",
                "retry_feedback",
                "route_handoff",
                "producer_raw_output",
                "<producer_raw_output>",
                "request.raw_output",
            ),
        ),
        (
            claude_runtime_provider,
            (
                "ProducerRequest",
                "VerifierRequest",
                "LLMRequest",
                "ProducerResponse",
                "OutcomeResponse",
                "parse_outcome_json",
                "render_verifier_input",
                "render_provider_turn",
                "route_" + "infos",
                "route_required_writes",
                "available_routes",
                "required_artifacts",
                "retry_feedback",
                "route_handoff",
                "producer_raw_output",
                "<producer_raw_output>",
                "request.raw_output",
            ),
        ),
    ),
)
def test_runtime_cli_transport_files_stay_transport_only(module: object, banned_tokens: tuple[str, ...]) -> None:
    source = Path(module.__file__).read_text(encoding="utf-8")  # type: ignore[attr-defined]

    for token in banned_tokens:
        assert token not in source, f"{module.__name__} unexpectedly contains {token!r}"


def test_resolve_provider_backend_raises_precise_error_for_unsupported_codex_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(codex_runtime_provider.shutil, "which", lambda name: "/usr/bin/codex")

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if command == ["codex", "exec", "--help"]:
            return _completed(args=command, stdout="--full-auto\n-m, --model <MODEL>\n")
        if command == ["codex", "exec", "resume", "--help"]:
            return _completed(args=command, stdout="--json\n-m, --model <MODEL>\n--full-auto\n")
        raise AssertionError(f"unexpected command: {command!r}")

    monkeypatch.setattr(codex_runtime_provider.subprocess, "run", fake_run)

    with pytest.raises(ConfigError, match=r"provider 'codex' requires 'codex exec --json' support"):
        resolve_provider_backend(config=_resolved_config("codex"))


def test_resolve_provider_backend_rejects_codex_model_effort_when_cli_does_not_support_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(codex_runtime_provider.shutil, "which", lambda name: "/usr/bin/codex")

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if command == ["codex", "exec", "--help"]:
            return _completed(
                args=command,
                stdout="--json\n-m, --model <MODEL>\n--dangerously-bypass-approvals-and-sandbox\n",
            )
        if command == ["codex", "exec", "resume", "--help"]:
            return _completed(
                args=command,
                stdout="--json\n-m, --model <MODEL>\n--dangerously-bypass-approvals-and-sandbox\n",
            )
        raise AssertionError(f"unexpected command: {command!r}")

    monkeypatch.setattr(codex_runtime_provider.subprocess, "run", fake_run)
    config = replace(
        _resolved_config("codex"),
        provider=replace(
            _resolved_config("codex").provider,
            codex=CodexProviderConfig(model="gpt-test", model_effort="medium"),
        ),
    )

    with pytest.raises(ConfigError, match=r"provider\.codex\.model_effort"):
        resolve_provider_backend(config=config)


def test_resolve_provider_backend_rejects_claude_effort_when_cli_does_not_support_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(claude_runtime_provider.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(
        claude_runtime_provider.subprocess,
        "run",
        lambda command, **_: _completed(
            args=command,
            stdout="--print\n-p\n--output-format\n--resume\n--model\n--settings\n--add-dir\n--allowedTools\n--dangerously-skip-permissions\n",
        ),
    )
    config = replace(
        _resolved_config("claude"),
        provider=replace(
            _resolved_config("claude").provider,
            claude=ClaudeProviderConfig(model="claude-test", effort="high"),
        ),
    )

    with pytest.raises(ConfigError, match=r"provider\.claude\.effort"):
        resolve_provider_backend(config=config)


def test_resolve_provider_backend_rejects_allow_core_tools_when_claude_cli_lacks_allowed_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(claude_runtime_provider.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(
        claude_runtime_provider.subprocess,
        "run",
        lambda command, **_: _completed(args=command, stdout=CLAUDE_HEADLESS_HELP),
    )
    config = replace(
        _resolved_config("claude"),
        provider=replace(
            _resolved_config("claude").provider,
            claude=ClaudeProviderConfig(
                model="claude-test",
                effort=None,
                permission_strategy="allow_core_tools",
            ),
        ),
    )

    with pytest.raises(ConfigError, match=r"--allowedTools"):
        resolve_provider_backend(config=config)


def test_cli_resolve_provider_uses_builtin_backend_resolver_when_not_injected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = object()
    config = _resolved_config("codex")
    args = argparse.Namespace()

    monkeypatch.setattr(cli, "resolve_provider_backend", lambda *, config: sentinel)

    assert cli._resolve_provider(config=config, args=args, provider_factory=None) is sentinel


def test_cli_resolve_provider_preserves_non_public_injection_seam_precedence() -> None:
    sentinel = object()
    config = _resolved_config("codex")
    args = argparse.Namespace(provider="claude")

    provider = cli._resolve_provider(
        config=config,
        args=args,
        provider_factory=lambda **_: sentinel,
    )

    assert provider is sentinel


def test_resolve_runtime_config_defaults_enable_git_tracking_and_tracing(tmp_path: Path) -> None:
    resolved = resolve_runtime_config(tmp_path, _runtime_args())

    assert resolved.runtime.max_steps == 100
    assert resolved.runtime.git_tracking.enabled is True
    assert resolved.runtime.git_tracking.commit_policy == "step"
    assert resolved.runtime.git_tracking.failure_policy == "propagate"
    assert resolved.runtime.tracing.enabled is True
    assert resolved.runtime.tracing.path == "trace.jsonl"
    assert resolved.runtime.tracing.failure_policy == "propagate"
    assert resolved.runtime.tracing.include_state_snapshots is True
    assert resolved.runtime.resume_topology_mismatch_behavior == "warn"


def test_parse_runtime_config_rejects_invalid_git_commit_policy(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"runtime\.git_tracking\.commit_policy"):
        runtime_config.parse_runtime_config(
            {"runtime": {"git_tracking": {"commit_policy": "invalid"}}},
            tmp_path / "botpipe.yaml",
        )


def test_parse_runtime_config_rejects_non_mapping_git_tracking_section(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"runtime\.git_tracking must be a mapping"):
        runtime_config.parse_runtime_config(
            {"runtime": {"git_tracking": False}},
            tmp_path / "botpipe.yaml",
        )


def test_parse_runtime_config_rejects_non_mapping_tracing_section(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"runtime\.tracing must be a mapping"):
        runtime_config.parse_runtime_config(
            {"runtime": {"tracing": False}},
            tmp_path / "botpipe.yaml",
        )


def test_resolve_runtime_config_no_git_disables_git_tracking(tmp_path: Path) -> None:
    resolved = resolve_runtime_config(tmp_path, _runtime_args(no_git=True))

    assert resolved.runtime.git_tracking.enabled is False
    assert resolved.runtime.git_tracking.commit_policy == "step"


def test_resolve_runtime_config_git_commit_policy_off_disables_git_tracking(tmp_path: Path) -> None:
    resolved = resolve_runtime_config(tmp_path, _runtime_args(git_commit_policy="off"))

    assert resolved.runtime.git_tracking.enabled is False
    assert resolved.runtime.git_tracking.commit_policy == "off"


def test_resolve_runtime_config_git_commit_policy_run_enables_run_policy(tmp_path: Path) -> None:
    resolved = resolve_runtime_config(tmp_path, _runtime_args(git_commit_policy="run"))

    assert resolved.runtime.git_tracking.enabled is True
    assert resolved.runtime.git_tracking.commit_policy == "run"


def test_resolve_runtime_config_git_commit_policy_step_enables_step_policy(tmp_path: Path) -> None:
    resolved = resolve_runtime_config(tmp_path, _runtime_args(git_commit_policy="step", no_git=True))

    assert resolved.runtime.git_tracking.enabled is True
    assert resolved.runtime.git_tracking.commit_policy == "step"


def test_resolve_runtime_config_no_trace_disables_tracing(tmp_path: Path) -> None:
    resolved = resolve_runtime_config(tmp_path, _runtime_args(no_trace=True))

    assert resolved.runtime.tracing.enabled is False
    assert resolved.runtime.tracing.path == "trace.jsonl"


def test_resolve_runtime_config_merges_runtime_file_overrides_and_preserves_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    global_config_dir = tmp_path / "global-config"
    local_config_path = tmp_path / "botpipe.yaml"
    global_config_path = global_config_dir / "botpipe.yaml"
    global_config_dir.mkdir(parents=True)
    global_config_path.write_text("", encoding="utf-8")
    local_config_path.write_text("", encoding="utf-8")

    payloads = {
        global_config_path: {
            "runtime": {
                "git_tracking": {"failure_policy": "record_and_continue"},
                "tracing": {"path": "custom-trace.jsonl"},
            }
        },
        local_config_path: {
            "runtime": {
                "git_tracking": {"commit_policy": "run"},
                "tracing": {"include_state_snapshots": False},
            }
        },
    }
    monkeypatch.setattr(runtime_config, "user_config_dir", lambda: global_config_dir)
    monkeypatch.setattr(runtime_config, "load_runtime_config_file", lambda path: payloads[path])

    resolved = resolve_runtime_config(tmp_path, _runtime_args())

    assert resolved.runtime.max_steps == 100
    assert resolved.runtime.git_tracking.enabled is True
    assert resolved.runtime.git_tracking.commit_policy == "run"
    assert resolved.runtime.git_tracking.failure_policy == "record_and_continue"
    assert resolved.runtime.tracing.enabled is True
    assert resolved.runtime.tracing.path == "custom-trace.jsonl"
    assert resolved.runtime.tracing.failure_policy == "propagate"
    assert resolved.runtime.tracing.include_state_snapshots is False


def test_resolve_runtime_config_routes_generic_file_overrides_to_selected_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    global_config_dir = tmp_path / "global-config"
    local_config_path = tmp_path / "botpipe.yaml"
    global_config_path = global_config_dir / "botpipe.yaml"
    global_config_dir.mkdir(parents=True)
    global_config_path.write_text("", encoding="utf-8")
    local_config_path.write_text("", encoding="utf-8")

    payloads = {
        global_config_path: {
            "provider": {
                "name": "claude",
                "model": "claude-sonnet",
                "model_effort": "high",
                "codex": {"model": "gpt-explicit"},
            }
        },
        local_config_path: {
            "provider": {
                "claude": {"permission_strategy": "bypass"},
            }
        },
    }
    monkeypatch.setattr(runtime_config, "user_config_dir", lambda: global_config_dir)
    monkeypatch.setattr(runtime_config, "load_runtime_config_file", lambda path: payloads[path])

    resolved = resolve_runtime_config(
        tmp_path,
        _runtime_args(),
    )

    assert resolved.provider.name == "claude"
    assert resolved.provider.claude.model == "claude-sonnet"
    assert resolved.provider.claude.effort == "high"
    assert resolved.provider.claude.permission_strategy == "bypass"
    assert resolved.provider.codex.model == "gpt-explicit"


def test_resolve_runtime_config_preserves_later_provider_specific_override_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    global_config_dir = tmp_path / "global-config"
    local_config_path = tmp_path / "botpipe.yaml"
    global_config_path = global_config_dir / "botpipe.yaml"
    global_config_dir.mkdir(parents=True)
    global_config_path.write_text("", encoding="utf-8")
    local_config_path.write_text("", encoding="utf-8")

    payloads = {
        global_config_path: {
            "provider": {
                "model": "global-model",
                "model_effort": "medium",
            }
        },
        local_config_path: {
            "provider": {
                "name": "claude",
                "claude": {
                    "model": "repo-specific",
                    "effort": "high",
                },
            }
        },
    }
    monkeypatch.setattr(runtime_config, "user_config_dir", lambda: global_config_dir)
    monkeypatch.setattr(runtime_config, "load_runtime_config_file", lambda path: payloads[path])

    resolved = resolve_runtime_config(
        tmp_path,
        _runtime_args(),
    )

    assert resolved.provider.name == "claude"
    assert resolved.provider.claude.model == "repo-specific"
    assert resolved.provider.claude.effort == "high"


def test_resolve_runtime_config_applies_generic_file_override_to_cli_selected_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    global_config_dir = tmp_path / "global-config"
    global_config_path = global_config_dir / "botpipe.yaml"
    global_config_dir.mkdir(parents=True)
    global_config_path.write_text("", encoding="utf-8")

    payloads = {
        global_config_path: {
            "provider": {
                "model": "shared-model",
                "model_effort": "high",
            }
        }
    }
    monkeypatch.setattr(runtime_config, "user_config_dir", lambda: global_config_dir)
    monkeypatch.setattr(runtime_config, "load_runtime_config_file", lambda path: payloads[path])

    resolved = resolve_runtime_config(
        tmp_path,
        _runtime_args(provider="claude"),
    )

    assert resolved.provider.name == "claude"
    assert resolved.provider.claude.model == "shared-model"
    assert resolved.provider.claude.effort == "high"
    assert resolved.provider.codex.model == "gpt-5.4"


def test_resolve_runtime_config_applies_cli_override_after_provider_specific_file_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    global_config_dir = tmp_path / "global-config"
    local_config_path = tmp_path / "botpipe.yaml"
    global_config_path = global_config_dir / "botpipe.yaml"
    global_config_dir.mkdir(parents=True)
    global_config_path.write_text("", encoding="utf-8")
    local_config_path.write_text("", encoding="utf-8")

    payloads = {
        global_config_path: {},
        local_config_path: {
            "provider": {
                "name": "claude",
                "claude": {
                    "model": "repo-specific",
                    "effort": "high",
                },
            }
        },
    }
    monkeypatch.setattr(runtime_config, "user_config_dir", lambda: global_config_dir)
    monkeypatch.setattr(runtime_config, "load_runtime_config_file", lambda path: payloads[path])

    resolved = resolve_runtime_config(
        tmp_path,
        _runtime_args(provider="claude", model="cli-model", model_effort="max"),
    )

    assert resolved.provider.name == "claude"
    assert resolved.provider.claude.model == "cli-model"
    assert resolved.provider.claude.effort == "max"


def test_resolve_runtime_config_routes_cli_overrides_to_selected_provider(tmp_path: Path) -> None:
    resolved = resolve_runtime_config(
        tmp_path,
        _runtime_args(provider="claude", model="claude-opus", model_effort="max"),
    )

    assert resolved.provider.name == "claude"
    assert resolved.provider.claude.model == "claude-opus"
    assert resolved.provider.claude.effort == "max"
    assert resolved.provider.codex.model == "gpt-5.4"
