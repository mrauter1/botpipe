"""Semantic provider wrapper around rendered transport turns."""

from __future__ import annotations

from .models import (
    LLMRequest,
    OperationRequest,
    OperationResponse,
    OutcomeResponse,
    ProducerRequest,
    ProducerResponse,
    ProviderTurnContext,
    VerifierRequest,
)
from .parsing import parse_outcome_json
from .protocols import ProviderTransport
from .rendering import render_provider_turn


class RenderedLLMProvider:
    """Adapt the semantic provider protocol to the rendered transport boundary."""

    def __init__(self, transport: ProviderTransport) -> None:
        self._transport = transport

    def run_producer(self, request: ProducerRequest) -> ProducerResponse:
        context = _producer_context(request)
        turn = render_provider_turn(context)
        result = self._transport.run_turn(turn)
        return ProducerResponse(
            raw_output=result.raw_text,
            session=result.session,
            metadata=result.metadata,
            usage=result.usage,
        )

    def run_verifier(self, request: VerifierRequest) -> OutcomeResponse:
        context = _verifier_context(request)
        turn = render_provider_turn(context)
        result = self._transport.run_turn(turn)
        outcome = parse_outcome_json(result.raw_text)
        return OutcomeResponse(
            outcome=outcome,
            session=result.session,
            metadata=result.metadata,
            usage=result.usage,
        )

    def run_llm(self, request: LLMRequest) -> OutcomeResponse:
        context = _llm_context(request)
        turn = render_provider_turn(context)
        result = self._transport.run_turn(turn)
        outcome = parse_outcome_json(result.raw_text)
        return OutcomeResponse(
            outcome=outcome,
            session=result.session,
            metadata=result.metadata,
            usage=result.usage,
        )

    def run_operation(self, request: OperationRequest) -> OperationResponse:
        context = _operation_context(request)
        turn = render_provider_turn(context)
        result = self._transport.run_turn(turn)
        return OperationResponse(
            raw_output=result.raw_text,
            session=result.session,
            metadata=result.metadata,
            usage=result.usage,
        )


def _producer_context(request: ProducerRequest) -> ProviderTurnContext:
    return ProviderTurnContext(
        step_name=request.step_name,
        turn_kind="producer",
        prompt=request.producer_prompt,
        context=request.context,
        artifacts=request.artifacts,
        session=request.session,
        expected_output_schema=request.expected_output_schema,
        available_routes=request.available_routes,
        routes=request.routes,
        readable_artifacts=request.readable_artifacts,
        required_artifacts=request.required_artifacts,
        writable_artifacts=request.writable_artifacts,
        route_required_writes=request.route_required_writes,
        retry_feedback=request.retry_feedback,
        route_handoff=request.route_handoff,
        attempt=request.attempt,
        max_attempts=request.max_attempts,
    )


def _verifier_context(request: VerifierRequest) -> ProviderTurnContext:
    return ProviderTurnContext(
        step_name=request.step_name,
        turn_kind="verifier",
        prompt=request.verifier_prompt,
        context=request.context,
        artifacts=request.artifacts,
        session=request.session,
        expected_output_schema=request.expected_output_schema,
        available_routes=request.available_routes,
        routes=request.routes,
        readable_artifacts=request.readable_artifacts,
        required_artifacts=request.required_artifacts,
        writable_artifacts=request.writable_artifacts,
        route_required_writes=request.route_required_writes,
        retry_feedback=request.retry_feedback,
        route_handoff=request.route_handoff,
        attempt=request.attempt,
        max_attempts=request.max_attempts,
    )


def _llm_context(request: LLMRequest) -> ProviderTurnContext:
    return ProviderTurnContext(
        step_name=request.step_name,
        turn_kind="step",
        prompt=request.prompt,
        context=request.context,
        artifacts=request.artifacts,
        session=request.session,
        expected_output_schema=request.expected_output_schema,
        available_routes=request.available_routes,
        routes=request.routes,
        readable_artifacts=request.readable_artifacts,
        required_artifacts=request.required_artifacts,
        writable_artifacts=request.writable_artifacts,
        route_required_writes=request.route_required_writes,
        retry_feedback=request.retry_feedback,
        route_handoff=request.route_handoff,
        attempt=request.attempt,
        max_attempts=request.max_attempts,
    )


def _operation_context(request: OperationRequest) -> ProviderTurnContext:
    return ProviderTurnContext(
        step_name=request.step_name,
        turn_kind="operation",
        prompt=request.prompt,
        context=object() if request.context is None else request.context,
        artifacts=object(),
        session=request.session,
        expected_output_schema=request.return_schema,
        available_routes=request.choices,
        routes={},
        readable_artifacts=(),
        required_artifacts=(),
        writable_artifacts=(),
        route_required_writes={},
        retry_feedback=request.retry_feedback,
        route_handoff=None,
        attempt=request.attempt,
        max_attempts=request.max_attempts,
    )
