"""Provider protocols."""

from __future__ import annotations

import inspect
from typing import Protocol, cast, runtime_checkable

from .models import LLMRequest, OutcomeResponse, ProducerRequest, ProducerResponse, VerifierRequest
from .turns import ProviderTurnResult, RenderedProviderTurn


@runtime_checkable
class LLMProvider(Protocol):
    """Provider interface for all workflow turn kinds."""

    async def run_producer(self, request: ProducerRequest) -> ProducerResponse:
        """Execute a producer turn."""

    async def run_verifier(self, request: VerifierRequest) -> OutcomeResponse:
        """Execute a verifier turn."""

    async def run_llm(self, request: LLMRequest) -> OutcomeResponse:
        """Execute a single LLM turn asynchronously."""


@runtime_checkable
class ProviderTransport(Protocol):
    """Lower-level transport interface for rendered provider turns."""

    async def run_turn(self, turn: RenderedProviderTurn) -> ProviderTurnResult:
        """Execute one rendered provider turn asynchronously."""


def validate_llm_provider(provider: object) -> LLMProvider:
    """Validate and return an async-native provider."""

    _validate_async_methods(
        provider,
        method_names=("run_producer", "run_verifier", "run_llm"),
        subject="provider",
    )
    return cast(LLMProvider, provider)


def validate_provider_transport(transport: object) -> ProviderTransport:
    """Validate and return an async-native transport."""

    _validate_async_methods(
        transport,
        method_names=("run_turn",),
        subject="provider transport",
    )
    return cast(ProviderTransport, transport)


def _validate_async_methods(
    value: object,
    *,
    method_names: tuple[str, ...],
    subject: str,
) -> None:
    missing = [name for name in method_names if not callable(getattr(value, name, None))]
    if missing:
        raise TypeError(
            f"invalid {subject} {type(value).__name__!r}: missing required method(s): {', '.join(missing)}"
        )

    non_async = [name for name in method_names if not inspect.iscoroutinefunction(getattr(value, name))]
    if non_async:
        raise TypeError(
            f"invalid {subject} {type(value).__name__!r}: method(s) must be async coroutine functions: "
            f"{', '.join(non_async)}"
        )
