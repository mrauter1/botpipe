from __future__ import annotations

import argparse
from dataclasses import replace

import pytest

from autoloop_v3.runtime import cli
from autoloop_v3.runtime.config import (
    ClaudeProviderConfig,
    CodexProviderConfig,
    ConfigError,
    ProviderConfig,
    ResolvedRuntimeConfig,
    RuntimeConfig,
)
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
    args = argparse.Namespace(provider_factory="provider_backend:build")

    monkeypatch.setattr(cli, "resolve_provider_backend", lambda *, config: sentinel)

    assert cli._resolve_provider(config=config, args=args, provider_factory=None) is sentinel
