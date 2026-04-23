"""Framework-owned provider backend resolution."""

from __future__ import annotations

from typing import Callable

from ..core.providers.protocols import LLMProvider
from .config import ConfigError, ResolvedRuntimeConfig
from .providers.claude import build_claude_provider
from .providers.codex import build_codex_provider


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


_BACKEND_BUILDERS: dict[str, BackendBuilder] = {
    "claude": build_claude_provider,
    "codex": build_codex_provider,
}
