"""Framework-owned provider backend resolution."""

from __future__ import annotations

from collections.abc import Callable

from ..core.providers.protocols import LLMProvider, ProviderTransport
from ..core.providers.rendered import RenderedLLMProvider
from ..core.providers.turns import ProviderTurnResult, RenderedProviderTurn
from .config import ConfigError, ResolvedRuntimeConfig
from .providers.claude import build_claude_operation_executor, build_claude_transport
from .providers.codex import build_codex_operation_executor, build_codex_transport


BackendBuilder = Callable[[ResolvedRuntimeConfig], ProviderTransport]
OperationExecutorBuilder = Callable[[ResolvedRuntimeConfig], Callable[[RenderedProviderTurn], ProviderTurnResult]]


def resolve_provider_backend(*, config: ResolvedRuntimeConfig) -> LLMProvider:
    """Resolve the built-in provider backend for the given runtime config."""

    provider_name = config.provider.name.strip()
    if ":" in provider_name:
        raise ConfigError(
            f"provider.name must select a built-in backend; module:function strings like {provider_name!r} "
            "are not supported."
        )

    builder = _BACKEND_BUILDERS.get(provider_name)
    operation_builder = _OPERATION_EXECUTOR_BUILDERS.get(provider_name)
    if builder is None or operation_builder is None:
        supported = ", ".join(sorted(_BACKEND_BUILDERS))
        raise ConfigError(f"provider.name must be one of the built-in backends: {supported}.")
    return RenderedLLMProvider(
        builder(config),
        operation_executor=operation_builder(config),
    )


_BACKEND_BUILDERS: dict[str, BackendBuilder] = {
    "claude": build_claude_transport,
    "codex": build_codex_transport,
}

_OPERATION_EXECUTOR_BUILDERS = {
    "claude": build_claude_operation_executor,
    "codex": build_codex_operation_executor,
}
