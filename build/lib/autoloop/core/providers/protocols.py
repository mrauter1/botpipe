"""Provider protocols."""

from __future__ import annotations

from typing import Protocol, TypeGuard, runtime_checkable

from .models import LLMRequest, OperationRequest, OperationResponse, OutcomeResponse, ProducerRequest, ProducerResponse, VerifierRequest
from .turns import ProviderTurnResult, RenderedProviderTurn


class LLMProvider(Protocol):
    """Provider interface for all workflow turn kinds."""

    def run_producer(self, request: ProducerRequest) -> ProducerResponse:
        """Execute a producer turn."""

    def run_verifier(self, request: VerifierRequest) -> OutcomeResponse:
        """Execute a verifier turn."""

    def run_llm(self, request: LLMRequest) -> OutcomeResponse:
        """Execute a single LLM turn."""

    def run_operation(self, request: OperationRequest) -> OperationResponse:
        """Execute a value-returning operation turn."""


@runtime_checkable
class AsyncLLMProvider(Protocol):
    """Async provider interface for provider-backed branch execution."""

    async def run_producer_async(self, request: ProducerRequest) -> ProducerResponse:
        """Execute a producer turn asynchronously."""

    async def run_verifier_async(self, request: VerifierRequest) -> OutcomeResponse:
        """Execute a verifier turn asynchronously."""

    async def run_llm_async(self, request: LLMRequest) -> OutcomeResponse:
        """Execute a single LLM turn asynchronously."""


class ProviderTransport(Protocol):
    """Lower-level transport interface for rendered provider turns."""

    def run_turn(self, turn: RenderedProviderTurn) -> ProviderTurnResult:
        """Execute one rendered provider turn."""


@runtime_checkable
class AsyncProviderTransport(Protocol):
    """Async lower-level transport interface for rendered provider turns."""

    async def run_turn_async(self, turn: RenderedProviderTurn) -> ProviderTurnResult:
        """Execute one rendered provider turn asynchronously."""


def supports_async_llm_provider(provider: object) -> TypeGuard[AsyncLLMProvider]:
    """Return True when the provider exposes the async turn surface."""

    return all(
        callable(getattr(provider, attr, None))
        for attr in ("run_producer_async", "run_verifier_async", "run_llm_async")
    )


def supports_async_provider_transport(transport: object) -> TypeGuard[AsyncProviderTransport]:
    """Return True when the transport exposes the async turn surface."""

    return callable(getattr(transport, "run_turn_async", None))
