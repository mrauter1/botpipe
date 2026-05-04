"""Provider protocols."""

from __future__ import annotations

from typing import Protocol

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


class ProviderTransport(Protocol):
    """Lower-level transport interface for rendered provider turns."""

    def run_turn(self, turn: RenderedProviderTurn) -> ProviderTurnResult:
        """Execute one rendered provider turn."""
