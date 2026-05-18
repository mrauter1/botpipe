"""Semantic provider wrapper around rendered transport turns."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from typing import Literal

from ..errors import FailureContext, WorkflowExecutionError, exception_failure_context, replace_execution_error
from ..prompts import ResolvedPrompt
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
        result = await self._run_turn(_step_context(request, turn_kind="producer", prompt=request.producer_prompt))
        return _producer_response(result)

    async def run_verifier(self, request: VerifierRequest) -> OutcomeResponse:
        result = await self._run_turn(_step_context(request, turn_kind="verifier", prompt=request.verifier_prompt))
        return _outcome_response(result)

    async def run_llm(self, request: LLMRequest) -> OutcomeResponse:
        result = await self._run_turn(_step_context(request, turn_kind=request.turn_kind, prompt=request.prompt))
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
        checkpoint_provider_attempt = getattr(context.context, "_checkpoint_provider_attempt", None)
        if callable(checkpoint_provider_attempt):
            checkpoint_provider_attempt(turn)
        return await self._transport.run_turn(turn)

    def _run_operation_turn(self, context: ProviderTurnContext):
        turn = render_provider_turn(context)
        checkpoint_provider_attempt = getattr(context.context, "_checkpoint_provider_attempt", None)
        if callable(checkpoint_provider_attempt):
            checkpoint_provider_attempt(turn)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return run_provider_coro_sync(self._transport.run_turn(turn))
        # Temporary compatibility exception for the existing public non-parallel
        # operation helpers only. Provider-backed branch steps, produce/verify
        # steps, prompt steps, and provider-backed fan-in execution stay on the
        # async transport path and must not route through this sync bridge.
        if self._operation_executor is not None:
            return self._operation_executor(turn)
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
    try:
        outcome = parse_outcome_json(result.raw_text)
    except WorkflowExecutionError as exc:
        raise _with_failed_turn_snapshot(exc, result) from exc
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


def _step_context(
    request: ProducerRequest | VerifierRequest | LLMRequest,
    *,
    turn_kind: Literal["producer", "verifier", "step", "outcome_repair"],
    prompt: ResolvedPrompt,
) -> ProviderTurnContext:
    return ProviderTurnContext(
        step_name=request.step_name,
        turn_kind=turn_kind,
        prompt=prompt,
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
        response_schema=request.response_schema,
        native_response_schema=request.native_response_schema,
        response_schema_native_skip_reason=request.response_schema_native_skip_reason,
        retry_feedback=request.retry_feedback,
        route_handoff=request.route_handoff,
        policy=request.policy,
        attempt=request.attempt,
        max_attempts=request.max_attempts,
        rendered_prompt_text=_resume_rendered_prompt_text(
            request.context,
            turn_kind=turn_kind,
            attempt=request.attempt,
        ),
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
        response_schema=None,
        native_response_schema=None,
        response_schema_native_skip_reason=None,
        retry_feedback=request.retry_feedback,
        route_handoff=None,
        policy=request.policy,
        attempt=request.attempt,
        max_attempts=request.max_attempts,
        rendered_prompt_text=_resume_rendered_prompt_text(
            request.context,
            turn_kind="operation",
            attempt=request.attempt,
        ),
    )


def _resume_rendered_prompt_text(context: object, *, turn_kind: str, attempt: int) -> str | None:
    cursor = getattr(context, "_provider_attempt_resume_cursor", None)
    if not isinstance(cursor, dict):
        return None
    if cursor.get("phase") != "provider_attempt":
        return None
    cursor_kind = cursor.get("turn_kind")
    expected_kind = "llm" if turn_kind == "step" else turn_kind
    if cursor_kind != expected_kind:
        return None
    if cursor.get("attempt") != attempt:
        return None
    prompt_text = cursor.get("prompt_text")
    return prompt_text if isinstance(prompt_text, str) else None


def _with_failed_turn_snapshot(exc: WorkflowExecutionError, result: ProviderTurnResult) -> WorkflowExecutionError:
    failure_context = exception_failure_context(exc)
    if failure_context is None:
        return exc
    if failure_context.kind != "malformed_provider_output":
        return exc
    if failure_context.details.get("provider_failure_stage") != "outcome_contract":
        return exc
    details = dict(failure_context.details)
    details.setdefault("provider_raw_output_sha256", hashlib.sha256(result.raw_text.encode("utf-8")).hexdigest())
    details.setdefault("provider_raw_output_excerpt", _bounded_output_excerpt(result.raw_text))
    session_payload = _session_payload(result.session)
    if session_payload is not None:
        details.setdefault("failed_provider_session", session_payload)
    usage_payload = _usage_payload(result.usage)
    if usage_payload is not None:
        details.setdefault("failed_provider_usage", usage_payload)
    return replace_execution_error(
        exc,
        failure_context=FailureContext(
            kind=failure_context.kind,
            step_name=failure_context.step_name,
            candidate_route=failure_context.candidate_route,
            final_route=failure_context.final_route,
            runtime_control=failure_context.runtime_control,
            provider_attributable=failure_context.provider_attributable,
            source_hook=failure_context.source_hook,
            source_phase=failure_context.source_phase,
            target_step=failure_context.target_step,
            pending_input_id=failure_context.pending_input_id,
            details=details,
        ),
    )


def _bounded_output_excerpt(text: str, *, limit: int = 2_000) -> str:
    if len(text) <= limit:
        return text
    half = max((limit - 5) // 2, 0)
    return f"{text[:half]} ... {text[-half:]}"


def _session_payload(session: object) -> dict[str, object] | None:
    key = getattr(session, "key", None)
    slot = getattr(key, "slot", None)
    domain = getattr(key, "domain", None)
    value = getattr(key, "value", None)
    ref_name = getattr(session, "ref_name", None)
    if not isinstance(ref_name, str) and not (
        isinstance(slot, str) and isinstance(domain, str) and isinstance(value, str)
    ):
        return None
    payload: dict[str, object] = {
        "ref_name": ref_name,
        "scope": getattr(session, "scope", None),
        "session_id": getattr(session, "session_id", None),
        "provider": getattr(session, "provider", None),
        "provider_metadata": deepcopy(getattr(session, "provider_metadata", {}) or {}),
        "metadata": deepcopy(getattr(session, "metadata", {}) or {}),
    }
    if isinstance(slot, str) and isinstance(domain, str) and isinstance(value, str):
        payload["key"] = {"slot": slot, "domain": domain, "value": value}
    return payload


def _usage_payload(usage: object) -> dict[str, object] | None:
    if usage is None:
        return None
    if is_dataclass(usage):
        return {key: value for key, value in asdict(usage).items() if value is not None}
    if isinstance(usage, dict):
        return dict(usage)
    return None
