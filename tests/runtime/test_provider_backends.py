from __future__ import annotations

import argparse
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from autoloop_v3.core.providers.rendered import RenderedLLMProvider
from autoloop_v3.core.providers.turns import ProviderTurnResult, RenderedProviderTurn
from autoloop_v3.runtime import cli
from autoloop_v3.runtime import providers as runtime_providers
from autoloop_v3.runtime.providers.claude import ClaudeProvider, ClaudeTransport, build_claude_provider
import autoloop_v3.runtime.providers.claude as claude_runtime_provider
from autoloop_v3.runtime.providers.codex import CodexProvider, CodexTransport, build_codex_provider
import autoloop_v3.runtime.providers.codex as codex_runtime_provider
from autoloop_v3.runtime.config import (
    ClaudeProviderConfig,
    CodexProviderConfig,
    ConfigError,
    ProviderConfig,
    ResolvedRuntimeConfig,
    RuntimeConfig,
    resolve_runtime_config,
)
import autoloop_v3.runtime.config as runtime_config
from autoloop_v3.runtime.provider_backends import resolve_provider_backend
import autoloop_v3.runtime.provider_backends as provider_backends


CLAUDE_HEADLESS_HELP = "--print\n-p\n--output-format\n--resume\n--model\n"


class _StubTransport:
    def run_turn(self, turn: RenderedProviderTurn) -> ProviderTurnResult:  # pragma: no cover - defensive
        raise AssertionError(f"unexpected turn call: {turn!r}")


def _resolved_config(provider_name: str = "codex") -> ResolvedRuntimeConfig:
    return ResolvedRuntimeConfig(
        provider=ProviderConfig(
            name=provider_name,
            codex=CodexProviderConfig(model="gpt-test", model_effort=None),
            claude=ClaudeProviderConfig(model="claude-test", effort=None),
        ),
        runtime=RuntimeConfig(max_steps=5),
    )


@pytest.fixture(autouse=True)
def _clear_provider_cli_caches() -> None:
    codex_runtime_provider._probe_codex_exec_surface.cache_clear()
    claude_runtime_provider._probe_claude_help_surface.cache_clear()


def _completed(*, args: list[str], stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=args, returncode=returncode, stdout=stdout, stderr=stderr)


def test_resolve_provider_backend_dispatches_by_provider_name(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    codex_transport = _StubTransport()
    claude_transport = _StubTransport()

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

    codex_provider = resolve_provider_backend(config=_resolved_config("codex"))
    claude_provider = resolve_provider_backend(config=_resolved_config("claude"))

    assert isinstance(codex_provider, RenderedLLMProvider)
    assert codex_provider._transport is codex_transport
    assert isinstance(claude_provider, RenderedLLMProvider)
    assert claude_provider._transport is claude_transport
    assert seen == ["codex", "claude"]


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
                "route_contracts",
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
                "route_contracts",
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
            stdout="--print\n-p\n--output-format\n--resume\n--model\n--allowedTools\n--dangerously-skip-permissions\n",
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


def test_resolve_runtime_config_routes_generic_file_overrides_to_selected_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    global_config_dir = tmp_path / "global-config"
    local_config_path = tmp_path / "autoloop.yaml"
    global_config_path = global_config_dir / "autoloop.yaml"
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
        argparse.Namespace(provider=None, model=None, model_effort=None, max_steps=None),
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
    local_config_path = tmp_path / "autoloop.yaml"
    global_config_path = global_config_dir / "autoloop.yaml"
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
        argparse.Namespace(provider=None, model=None, model_effort=None, max_steps=None),
    )

    assert resolved.provider.name == "claude"
    assert resolved.provider.claude.model == "repo-specific"
    assert resolved.provider.claude.effort == "high"


def test_resolve_runtime_config_applies_generic_file_override_to_cli_selected_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    global_config_dir = tmp_path / "global-config"
    global_config_path = global_config_dir / "autoloop.yaml"
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
        argparse.Namespace(provider="claude", model=None, model_effort=None, max_steps=None),
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
    local_config_path = tmp_path / "autoloop.yaml"
    global_config_path = global_config_dir / "autoloop.yaml"
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
        argparse.Namespace(provider="claude", model="cli-model", model_effort="max", max_steps=None),
    )

    assert resolved.provider.name == "claude"
    assert resolved.provider.claude.model == "cli-model"
    assert resolved.provider.claude.effort == "max"


def test_resolve_runtime_config_routes_cli_overrides_to_selected_provider(tmp_path: Path) -> None:
    resolved = resolve_runtime_config(
        tmp_path,
        argparse.Namespace(provider="claude", model="claude-opus", model_effort="max", max_steps=None),
    )

    assert resolved.provider.name == "claude"
    assert resolved.provider.claude.model == "claude-opus"
    assert resolved.provider.claude.effort == "max"
    assert resolved.provider.codex.model == "gpt-5.4"
