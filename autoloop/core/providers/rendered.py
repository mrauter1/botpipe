"""Semantic provider wrapper around rendered transport turns."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
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
from .protocols import ProviderTransport, validate_provider_transport
from .rendering import render_provider_turn
from .turns import ProviderTurnResult


class RenderedLLMProvider:
    """Adapt the semantic provider protocol to the rendered transport boundary."""

    def __init__(
        self,
        transport: ProviderTransport,
        *,
        operation_executor: Callable[[RenderedProviderTurn], ProviderTurnResult] | None = None,
    ) -> None:
        self._transport = validate_provider_transport(transport)
        if operation_executor is not None and not callable(operation_executor):
            raise TypeError("operation_executor must be callable when provided")
        self._operation_executor = operation_executor

    async def run_producer(self, request: ProducerRequest) -> ProducerResponse:
        result = await self._run_turn(_producer_context(request))
        return _producer_response(result)

    async def run_verifier(self, request: VerifierRequest) -> OutcomeResponse:
        result = await self._run_turn(_verifier_context(request))
        return _outcome_response(result)

    async def run_llm(self, request: LLMRequest) -> OutcomeResponse:
        result = await self._run_turn(_llm_context(request))
        return _outcome_response(result)

    def run_operation(self, request: OperationRequest) -> OperationResponse:
        result = self._run_operation_turn(_operation_context(request))
        return OperationResponse(
            raw_output=result.raw_text,
            session=result.session,
            metadata=result.metadata,
            usage=result.usage,
        )

    async def _run_turn(self, context: ProviderTurnContext):
        turn = render_provider_turn(context)
        return await self._transport.run_turn(turn)

    def _run_operation_turn(self, context: ProviderTurnContext):
        turn = render_provider_turn(context)
        if self._operation_executor is not None:
            return self._operation_executor(turn)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return run_provider_coro_sync(self._transport.run_turn(turn))
        raise RuntimeError(
            "RenderedLLMProvider requires an explicit operation_executor to support llm()/classify() "
            "inside an active workflow event loop."
        )


def _producer_response(result) -> ProducerResponse:
    return ProducerResponse(
        raw_output=result.raw_text,
        session=result.session,
        metadata=result.metadata,
        usage=result.usage,
    )


def _outcome_response(result) -> OutcomeResponse:
    outcome = parse_outcome_json(result.raw_text)
    return OutcomeResponse(
        outcome=outcome,
        session=result.session,
        metadata=result.metadata,
        usage=result.usage,
    )


def run_provider_coro_sync(awaitable):
    """Synchronously bridge an async provider coroutine for outer sync callers."""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    raise RuntimeError("Synchronous provider execution cannot run inside an active event loop; use the async API.")


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
