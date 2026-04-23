from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

import pytest

from autoloop_v3.runtime import cli
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


class _StubProvider:
    def run_producer(self, request):  # pragma: no cover - defensive
        raise AssertionError(f"unexpected producer call: {request!r}")

    def run_verifier(self, request):  # pragma: no cover - defensive
        raise AssertionError(f"unexpected verifier call: {request!r}")

    def run_llm(self, request):  # pragma: no cover - defensive
        raise AssertionError(f"unexpected llm call: {request!r}")


def _resolved_config(provider_name: str = "codex") -> ResolvedRuntimeConfig:
    return ResolvedRuntimeConfig(
        provider=ProviderConfig(
            name=provider_name,
            codex=CodexProviderConfig(model="gpt-test", model_effort="medium"),
            claude=ClaudeProviderConfig(model="claude-test", effort="high"),
        ),
        runtime=RuntimeConfig(max_steps=5),
    )


def test_resolve_provider_backend_dispatches_by_provider_name(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    codex_provider = _StubProvider()
    claude_provider = _StubProvider()

    monkeypatch.setitem(
        provider_backends._BACKEND_BUILDERS,
        "codex",
        lambda config: seen.append(config.provider.name) or codex_provider,
    )
    monkeypatch.setitem(
        provider_backends._BACKEND_BUILDERS,
        "claude",
        lambda config: seen.append(config.provider.name) or claude_provider,
    )

    assert resolve_provider_backend(config=_resolved_config("codex")) is codex_provider
    assert resolve_provider_backend(config=_resolved_config("claude")) is claude_provider
    assert seen == ["codex", "claude"]


def test_resolve_provider_backend_rejects_module_function_provider_names() -> None:
    config = _resolved_config()
    config = replace(config, provider=replace(config.provider, name="provider_backend:build"))

    with pytest.raises(ConfigError, match="module:function strings"):
        resolve_provider_backend(config=config)


def test_resolve_provider_backend_raises_precise_error_for_unavailable_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider_backends, "_command_on_path", lambda name: None)

    with pytest.raises(
        ConfigError,
        match=r"provider 'claude' is unavailable in this environment: the 'claude' CLI was not found on PATH\.",
    ):
        resolve_provider_backend(config=_resolved_config("claude"))


def test_resolve_provider_backend_raises_precise_error_for_unimplemented_codex_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider_backends, "_command_on_path", lambda name: f"/usr/bin/{name}")

    with pytest.raises(
        ConfigError,
        match=r"provider 'codex' is unavailable in this repository build: the framework-owned Codex adapter "
        r"has not been implemented yet \(detected CLI at /usr/bin/codex\)\.",
    ):
        resolve_provider_backend(config=_resolved_config("codex"))


def test_cli_resolve_provider_uses_builtin_backend_resolver_when_not_injected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = _StubProvider()
    config = _resolved_config("codex")
    args = argparse.Namespace()

    monkeypatch.setattr(cli, "resolve_provider_backend", lambda *, config: sentinel)

    assert cli._resolve_provider(config=config, args=args, provider_factory=None) is sentinel


def test_cli_resolve_provider_preserves_non_public_injection_seam_precedence() -> None:
    sentinel = _StubProvider()
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


def test_resolve_runtime_config_routes_cli_overrides_to_selected_provider(tmp_path: Path) -> None:
    resolved = resolve_runtime_config(
        tmp_path,
        argparse.Namespace(provider="claude", model="claude-opus", model_effort="max", max_steps=None),
    )

    assert resolved.provider.name == "claude"
    assert resolved.provider.claude.model == "claude-opus"
    assert resolved.provider.claude.effort == "max"
    assert resolved.provider.codex.model == "gpt-5.4"
