"""Framework-owned provider backend resolution."""

from __future__ import annotations

import shutil
from typing import Callable

from ..core.providers.protocols import LLMProvider
from .config import ConfigError, ResolvedRuntimeConfig


BackendBuilder = Callable[[ResolvedRuntimeConfig], LLMProvider]


def resolve_provider_backend(*, config: ResolvedRuntimeConfig) -> LLMProvider:
    """Resolve the built-in provider backend for the given runtime config."""

    provider_name = config.provider.name.strip()
    if ":" in provider_name:
        raise ConfigError(
            f"provider.name must select a built-in backend; module:function strings like {provider_name!r} "
            "are not supported."
        )

    builder = _BACKEND_BUILDERS.get(provider_name)
    if builder is None:
        supported = ", ".join(sorted(_BACKEND_BUILDERS))
        raise ConfigError(f"provider.name must be one of the built-in backends: {supported}.")
    return builder(config)


def _build_codex_backend(config: ResolvedRuntimeConfig) -> LLMProvider:
    executable = _command_on_path("codex")
    if executable is None:
        raise ConfigError(
            "provider 'codex' is unavailable in this environment: the 'codex' CLI was not found on PATH."
        )
    raise ConfigError(
        "provider 'codex' is unavailable in this repository build: the framework-owned Codex adapter "
        f"has not been implemented yet (detected CLI at {executable})."
    )


def _build_claude_backend(config: ResolvedRuntimeConfig) -> LLMProvider:
    executable = _command_on_path("claude")
    if executable is None:
        raise ConfigError(
            "provider 'claude' is unavailable in this environment: the 'claude' CLI was not found on PATH."
        )
    raise ConfigError(
        "provider 'claude' is unavailable in this repository build: the framework-owned Claude adapter "
        f"has not been implemented yet (detected CLI at {executable})."
    )


def _command_on_path(name: str) -> str | None:
    return shutil.which(name)


_BACKEND_BUILDERS: dict[str, BackendBuilder] = {
    "claude": _build_claude_backend,
    "codex": _build_codex_backend,
}
