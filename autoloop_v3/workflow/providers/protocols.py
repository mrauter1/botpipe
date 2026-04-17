"""Provider protocols."""

from __future__ import annotations

from typing import Protocol

from .models import LLMRequest, OutcomeResponse, ProducerRequest, ProducerResponse, VerifierRequest


class LLMProvider(Protocol):
    """Provider interface for all workflow turn kinds."""

    def run_producer(self, request: ProducerRequest) -> ProducerResponse:
        """Execute a producer turn."""

    def run_verifier(self, request: VerifierRequest) -> OutcomeResponse:
        """Execute a verifier turn."""

    def run_llm(self, request: LLMRequest) -> OutcomeResponse:
        """Execute a single LLM turn."""

