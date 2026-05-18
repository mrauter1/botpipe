"""Focused engine collaborators extracted from the monolithic engine."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal, TypeVar, cast

from pydantic import BaseModel

from .artifacts import ResolvedArtifacts
from .effects import Effects, WorklistEffect
from .errors import FailureContext, ProviderExecutionError, WorkflowExecutionError, replace_execution_error
from .execution_services import ExecutionServices
from .execution_runtime_services import StateRuntimeService
from .extensions import HookRouteRedirect
from .identifiers import ArtifactId
from .operations import OperationRuntime, bind_operation_runtime, provider_configuration
from .outcome_contract import (
    build_provider_outcome_contract,
    payload_schema_for_route,
    route_fields_schema_for_route,
)
from .provider_policy import ProviderPolicyError, policy_fingerprint
from .primitives import AWAIT_INPUT, FAIL, FINISH, Event, Fail, Goto, Outcome, RequestInput
from .prompts import ResolvedPrompt
from .providers.models import (
    LLMRequest,
    OutcomeResponse,
    ProducerRequest,
    ProviderArtifactRef,
    ProviderReadableRef,
    ProviderRoute,
    StepProviderUsage,
    TokenUsage,
    VerifierRequest,
)
from .providers.outcome_repair import (
    OutcomeRepairConstraints,
    extract_outcome_repair_constraints,
    outcome_preserves_repair_constraints,
    repair_incomplete_outcome_json,
)
from .route_required_writes import effective_route_required_writes_for_step, explicit_route_required_writes
from .route_contracts import (
    AwaitInput as AwaitInputAction,
    Continue,
    FailAction,
    Finish as FinishAction,
    RouteContract,
    RouteAction,
    RouteDecision,
    provider_visible_route_tags,
    route_action_for_contract,
    route_target_value,
)
from .step_plans import FanInRead, ProduceVerifyStepPlan, PromptStepPlan, ProviderTurnPlan, ReadRef, RequireRef, StepPlan, WriteRef
from .sessions import SessionKey
from .stores.protocols import PendingHandoff, PendingInput, SessionBinding

if TYPE_CHECKING:
    from pathlib import Path

    from .context import Context
    from .engine import StepFinalizationRecord
    from .worklists import Selection, SelectionSnapshot


HookTerminalControl = Literal["FINISH", "FAIL"]


@dataclass(frozen=True, slots=True)
class HookResult:
    event: Event | None = None
    control: RequestInput | Goto | Fail | HookTerminalControl | None = None


@dataclass(frozen=True, slots=True)
class HookExecutionResult:
    state: BaseModel
    event: Event | None = None
    control: RequestInput | Goto | Fail | HookTerminalControl | None = None
    explicit_event_override: bool = False
    redirect: HookRouteRedirect | None = None


@dataclass(frozen=True, slots=True)
class StepFinalizationRequest:
    step: StepPlan
    context: "Context"
    state: BaseModel
    artifacts: ResolvedArtifacts
    candidate_event: Event
    after_subject: Any
    pending_handoffs: tuple[PendingHandoff, ...]
    error_cls: type[WorkflowExecutionError]
    provider_attributable: bool
    candidate_route: str | None = None
    candidate_route_present: bool = False
    after_hook: Callable[..., Any] | None = None
    after_hook_phase: str = "after"
    source_hook: str | None = None
    source_phase: str | None = None


@dataclass(frozen=True, slots=True)
class _StepRouteResult:
    state: BaseModel
    destination: str
    finalized_event: Event | None
    candidate_route: str | None
    final_route: str | None
    runtime_control: str | None
    target_step: str | None
    terminal: str | None
    pending_input: PendingInput | None
    source_hook: str | None
    source_phase: str | None
    provider_attributable: bool
    hook_route_override_from: str | None
    hook_route_override_to: str | None
    hook_route_redirects: tuple[HookRouteRedirect, ...]
    scheduled_handoffs: tuple[PendingHandoff, ...]
    decision: RouteDecision | None = None


@dataclass(frozen=True, slots=True)
class StepExecutionResult:
    state: BaseModel
    destination: str
    event: Event | None
    outcome: Any | None
    pending_handoffs: tuple[PendingHandoff, ...]
    route_decision: RouteDecision | None = None
    action: RouteAction | None = None
    producer_raw_output: str | None = None
    verifier_raw_output: str | None = None
    provider_usage: StepProviderUsage | None = None
    transition: "StepFinalizationRecord | None" = None
    pending_input: PendingInput | None = None


RouteMode = Literal["capture", "finalize"]


def _provider_attempt_flags(
    *,
    step_kind: str,
    provider_usage: StepProviderUsage | None,
    outcome: Outcome | None,
    producer_raw_output: str | None,
    verifier_raw_output: str | None,
) -> tuple[bool, bool | None, bool | None]:
    if step_kind == "produce_verify":
        producer_attempted = (
            producer_raw_output is not None
            or (provider_usage is not None and provider_usage.producer is not None)
        )
        verifier_attempted = (
            verifier_raw_output is not None
            or (provider_usage is not None and provider_usage.verifier is not None)
        )
        return producer_attempted or verifier_attempted, producer_attempted, verifier_attempted
    provider_attempted = (
        outcome is not None
        or producer_raw_output is not None
        or (provider_usage is not None and provider_usage.llm is not None)
    )
    return provider_attempted, None, None


def _build_step_finalization_record(
    *,
    step: StepPlan,
    outcome: Outcome | None,
    producer_raw_output: str | None,
    verifier_raw_output: str | None,
    provider_usage: StepProviderUsage | None,
    candidate_route: str | None,
    final_route: str | None,
    runtime_control: str | None,
    pending_input: PendingInput | None,
    target_step: str | None,
    terminal: str | None,
    provider_attributable: bool,
    source_hook: str | None,
    source_phase: str | None,
    hook_route_redirects: tuple[HookRouteRedirect, ...],
) -> "StepFinalizationRecord":
    from .engine import StepFinalizationRecord

    provider_attempted, producer_attempted, verifier_attempted = _provider_attempt_flags(
        step_kind=step.kind,
        provider_usage=provider_usage,
        outcome=outcome,
        producer_raw_output=producer_raw_output,
        verifier_raw_output=verifier_raw_output,
    )
    pending_input_id = pending_input.pending_input_id if pending_input is not None else None
    return StepFinalizationRecord(
        candidate_route=candidate_route,
        final_route=final_route,
        runtime_control=runtime_control,
        pending_input_id=pending_input_id,
        target_step=target_step,
        terminal=terminal,
        provider_attributable=provider_attributable,
        provider_attempted=provider_attempted,
        producer_attempted=producer_attempted,
        verifier_attempted=verifier_attempted,
        source_hook=source_hook,
        source_phase=source_phase,
        hook_route_redirects=hook_route_redirects,
    )


def step_result_from_direct_control(
    *,
    step: StepPlan,
    state: BaseModel,
    control: Any,
    pending_handoffs: tuple[PendingHandoff, ...],
    producer_raw_output: str | None = None,
    verifier_raw_output: str | None = None,
    provider_usage: StepProviderUsage | None = None,
) -> StepExecutionResult:
    pending_input = control.pending_input
    finalization = _build_step_finalization_record(
        step=step,
        outcome=None,
        producer_raw_output=producer_raw_output,
        verifier_raw_output=verifier_raw_output,
        provider_usage=provider_usage,
        candidate_route=None,
        final_route=None,
        runtime_control=control.control,
        pending_input=pending_input,
        target_step=control.target_step,
        terminal=control.terminal,
        provider_attributable=False,
        source_hook=control.source_hook,
        source_phase=control.source_phase,
        hook_route_redirects=(),
    )
    action = (
        FinishAction(reason=control.control or "finish")
        if control.destination == FINISH
        else AwaitInputAction(pending_input=pending_input)
        if control.destination == AWAIT_INPUT
        else FailAction(reason=control.control)
        if control.destination == FAIL
        else Continue(
            target_step=control.target_step or control.destination,
            reason=control.control or "route",
        )
    )
    return StepExecutionResult(
        state=state,
        destination=control.destination,
        event=None,
        outcome=None,
        pending_handoffs=pending_handoffs,
        route_decision=RouteDecision(
            final_route=None,
            contract=None,
            action=action,
            runtime_control=control.control,
            provider_attributable=False,
            source_hook=control.source_hook,
            source_phase=control.source_phase,
        ),
        action=action,
        producer_raw_output=producer_raw_output,
        verifier_raw_output=verifier_raw_output,
        provider_usage=provider_usage,
        transition=finalization,
        pending_input=pending_input,
    )


def step_result_from_route_finalization(
    *,
    step: StepPlan,
    route_finalization: _StepRouteResult,
    outcome: Outcome | None = None,
    producer_raw_output: str | None = None,
    verifier_raw_output: str | None = None,
    provider_usage: StepProviderUsage | None = None,
) -> StepExecutionResult:
    finalization = _build_step_finalization_record(
        step=step,
        outcome=outcome,
        producer_raw_output=producer_raw_output,
        verifier_raw_output=verifier_raw_output,
        provider_usage=provider_usage,
        candidate_route=route_finalization.candidate_route,
        final_route=route_finalization.final_route,
        runtime_control=route_finalization.runtime_control,
        pending_input=route_finalization.pending_input,
        target_step=route_finalization.target_step,
        terminal=route_finalization.terminal,
        provider_attributable=route_finalization.provider_attributable,
        source_hook=route_finalization.source_hook,
        source_phase=route_finalization.source_phase,
        hook_route_redirects=route_finalization.hook_route_redirects,
    )
    return StepExecutionResult(
        state=route_finalization.state,
        destination=route_finalization.destination,
        event=route_finalization.finalized_event,
        outcome=outcome,
        pending_handoffs=route_finalization.scheduled_handoffs,
        producer_raw_output=producer_raw_output,
        verifier_raw_output=verifier_raw_output,
        provider_usage=provider_usage,
        transition=finalization,
        pending_input=route_finalization.pending_input,
        route_decision=route_finalization.decision,
        action=None if route_finalization.decision is None else route_finalization.decision.action,
    )


def provider_exec_result(response: Any, *, text: str) -> ProviderExecResult:
    session = getattr(response, "session", None)
    session_id = getattr(session, "session_id", None)
    metadata = getattr(response, "metadata", {}) or {}
    return ProviderExecResult(
        text=text,
        session_id=session_id if isinstance(session_id, str) else None,
        provider_metadata=deepcopy(dict(metadata)),
        usage=getattr(response, "usage", None),
        session=session if isinstance(session, SessionBinding) else None,
    )


@dataclass(frozen=True, slots=True)
class PairProviderResult:
    producer_raw_output: str | None
    verifier_raw_output: str | None
    outcome: Any | None
    producer_session: "SessionBinding | None"
    verifier_session: "SessionBinding | None"
    usage: StepProviderUsage
    direct_control: object | None = None
    short_circuit_event: Event | None = None
    state: BaseModel | None = None
    source_hook: str | None = None
    source_phase: str | None = None


@dataclass(frozen=True, slots=True)
class PairProducerPhaseResult:
    producer_raw_output: str | None
    producer_session: "SessionBinding | None"
    producer_usage: TokenUsage | None
    state: BaseModel
    direct_control: object | None = None
    short_circuit_event: Event | None = None
    source_hook: str | None = None
    source_phase: str | None = None


@dataclass(frozen=True, slots=True)
class PairVerifierPhase:
    producer_raw_output: str
    producer_session: "SessionBinding | None"
    producer_usage: TokenUsage | None
    state: BaseModel


@dataclass(slots=True)
class _PairAttemptPhaseTracker:
    verifier_phase: PairVerifierPhase | None = None


@dataclass(frozen=True, slots=True)
class ProviderExecResult:
    text: str
    session_id: str | None
    provider_metadata: dict[str, object]
    usage: TokenUsage | None = None
    session: "SessionBinding | None" = None
    outcome: Outcome | None = None


def _provider_resume_cursor_for_step(context: "Context", step: StepPlan) -> dict[str, Any] | None:
    cursor = getattr(context, "_provider_attempt_resume_cursor", None)
    if not isinstance(cursor, dict):
        return None
    if cursor.get("phase") != "provider_attempt":
        return None
    if cursor.get("step_name") != step.name:
        return None
    return dict(cursor)


def _resume_cursor_attempt(cursor: dict[str, Any] | None) -> int | None:
    if cursor is None:
        return None
    attempt = cursor.get("attempt")
    return attempt if isinstance(attempt, int) and attempt > 0 else None


def _resume_cursor_turn_kind(cursor: dict[str, Any] | None) -> str | None:
    if cursor is None:
        return None
    turn_kind = cursor.get("turn_kind")
    return turn_kind if isinstance(turn_kind, str) else None


def _same_resume_attempt(cursor: dict[str, Any] | None, attempt: int, *, turn_kind: str | None = None) -> bool:
    if _resume_cursor_attempt(cursor) != attempt:
        return False
    if turn_kind is not None and _resume_cursor_turn_kind(cursor) != turn_kind:
        return False
    return True


def _checkpoint_provider_attempt(context: "Context") -> None:
    checkpoint = getattr(context, "_checkpoint_provider_attempt", None)
    if callable(checkpoint):
        checkpoint(None)


def _provider_checkpoint_data(
    *,
    step: StepPlan,
    context: "Context",
    turn_kind: str,
    attempt: int,
    max_attempts: int,
    producer_raw_output: str | None = None,
    producer_session: SessionBinding | None = None,
    producer_usage: TokenUsage | None = None,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "phase": "provider_attempt",
        "step_name": step.name,
        "step_execution_id": getattr(context, "_step_execution_id", None),
        "turn_kind": turn_kind,
        "attempt": attempt,
        "max_attempts": max_attempts,
    }
    step_meta = getattr(context, "_meta", None)
    visits = None
    if isinstance(step_meta, dict):
        step_payload = step_meta.get("step")
        if isinstance(step_payload, dict):
            visits = step_payload.get("visits")
    if isinstance(visits, int):
        payload["step_visit"] = visits
    if producer_raw_output is not None:
        payload["producer_raw_output"] = producer_raw_output
    producer_session_payload = _session_binding_cursor_payload(producer_session)
    if producer_session_payload is not None:
        payload["producer_session"] = producer_session_payload
    producer_usage_payload = _token_usage_cursor_payload(producer_usage)
    if producer_usage_payload is not None:
        payload["producer_usage"] = producer_usage_payload
    payload.update({key: deepcopy(value) for key, value in extra.items() if value is not None})
    return payload


def _session_binding_cursor_payload(binding: SessionBinding | None) -> dict[str, Any] | None:
    if binding is None:
        return None
    return {
        "key": {
            "slot": binding.key.slot,
            "domain": binding.key.domain,
            "value": binding.key.value,
        },
        "ref_name": binding.ref_name,
        "scope": binding.scope,
        "session_id": binding.session_id,
        "provider": binding.provider,
        "provider_metadata": deepcopy(binding.provider_metadata),
        "metadata": deepcopy(binding.metadata),
    }


def _session_binding_from_cursor(payload: Any) -> SessionBinding | None:
    if not isinstance(payload, dict):
        return None
    key_payload = payload.get("key")
    key: SessionKey | None = None
    if isinstance(key_payload, dict):
        slot = key_payload.get("slot")
        domain = key_payload.get("domain")
        value = key_payload.get("value")
        if isinstance(slot, str) and isinstance(domain, str) and isinstance(value, str):
            key = SessionKey(slot=slot, domain=domain, value=value)
    ref_name = payload.get("ref_name")
    if key is None and not isinstance(ref_name, str):
        return None
    provider_metadata = payload.get("provider_metadata")
    metadata = payload.get("metadata")
    return SessionBinding(
        key=key,
        ref_name=ref_name if isinstance(ref_name, str) else None,
        scope=payload.get("scope") if isinstance(payload.get("scope"), str) else None,
        session_id=payload.get("session_id") if isinstance(payload.get("session_id"), str) else None,
        provider=payload.get("provider") if isinstance(payload.get("provider"), str) else None,
        provider_metadata=provider_metadata if isinstance(provider_metadata, dict) else None,
        metadata=metadata if isinstance(metadata, dict) else None,
    )


def _token_usage_cursor_payload(usage: TokenUsage | None) -> dict[str, Any] | None:
    if usage is None:
        return None
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
        "cached_input_tokens": usage.cached_input_tokens,
        "reasoning_tokens": usage.reasoning_tokens,
        "source": usage.source,
        "provider_raw": deepcopy(usage.provider_raw),
    }


def _token_usage_from_cursor(payload: Any) -> TokenUsage | None:
    if not isinstance(payload, dict):
        return None
    provider_raw = payload.get("provider_raw")
    return TokenUsage(
        input_tokens=payload.get("input_tokens") if isinstance(payload.get("input_tokens"), int) else None,
        output_tokens=payload.get("output_tokens") if isinstance(payload.get("output_tokens"), int) else None,
        total_tokens=payload.get("total_tokens") if isinstance(payload.get("total_tokens"), int) else None,
        cached_input_tokens=payload.get("cached_input_tokens") if isinstance(payload.get("cached_input_tokens"), int) else None,
        reasoning_tokens=payload.get("reasoning_tokens") if isinstance(payload.get("reasoning_tokens"), int) else None,
        source=payload.get("source") if isinstance(payload.get("source"), str) else "unavailable",
        provider_raw=deepcopy(provider_raw) if isinstance(provider_raw, dict) else {},
    )


def _failure_details(exc: Exception, events: Any) -> dict[str, object]:
    failure_context = events.failure_context_for_exception(exc)
    if failure_context is None:
        return {}
    return dict(failure_context.details)


def _exact_outcome_candidate(details: Mapping[str, object]) -> str | None:
    if details.get("outcome_json_candidate_truncated") is True:
        return None
    candidate = details.get("outcome_json_candidate")
    return candidate if isinstance(candidate, str) and candidate.strip() else None


def _failed_provider_session(details: Mapping[str, object]) -> SessionBinding | None:
    return _session_binding_from_cursor(details.get("failed_provider_session"))


def _failed_provider_usage(details: Mapping[str, object]) -> TokenUsage | None:
    return _token_usage_from_cursor(details.get("failed_provider_usage"))


def _outcome_repair_constraints_cursor_payload(constraints: OutcomeRepairConstraints) -> dict[str, object]:
    return {"route_tag": constraints.route_tag}


def _outcome_repair_constraints_from_cursor(cursor: Mapping[str, Any]) -> OutcomeRepairConstraints | None:
    payload = cursor.get("outcome_repair_constraints")
    if not isinstance(payload, Mapping):
        return None
    route_tag = payload.get("route_tag")
    if not isinstance(route_tag, str) or not route_tag:
        return None
    return OutcomeRepairConstraints(route_tag=route_tag)


def _outcome_repair_original_exception(cursor: Mapping[str, Any], *, step_name: str) -> ProviderExecutionError:
    payload = cursor.get("outcome_repair_failure_context")
    if isinstance(payload, dict):
        failure_context = FailureContext.from_payload(payload)
        details = dict(failure_context.details)
        if "failed_provider_session" not in details and isinstance(cursor.get("failed_provider_session"), Mapping):
            details["failed_provider_session"] = dict(cursor["failed_provider_session"])
        if "failed_provider_usage" not in details and isinstance(cursor.get("failed_provider_usage"), Mapping):
            details["failed_provider_usage"] = dict(cursor["failed_provider_usage"])
        if details != failure_context.details:
            failure_context = FailureContext(
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
            )
    else:
        details: dict[str, object] = {"provider_failure_stage": "outcome_contract"}
        candidate = cursor.get("outcome_repair_candidate")
        if isinstance(candidate, str) and candidate:
            details["outcome_json_candidate"] = candidate
            details["outcome_json_candidate_truncated"] = False
        failed_turn_kind = cursor.get("outcome_repair_failed_turn_kind")
        if isinstance(failed_turn_kind, str) and failed_turn_kind:
            details["provider_turn_kind"] = failed_turn_kind
        failure_context = FailureContext(
            kind="malformed_provider_output",
            step_name=step_name,
            provider_attributable=True,
            details=details,
        )
    message = str(failure_context.details.get("error") or "provider returned malformed outcome JSON")
    return ProviderExecutionError(
        message,
        failure_context=failure_context,
        retry_kind="malformed_provider_output",
    )


def _outcome_repair_candidate_from_cursor(cursor: Mapping[str, Any]) -> str | None:
    candidate = cursor.get("outcome_repair_candidate")
    return candidate if isinstance(candidate, str) and candidate.strip() else None


def _filter_outcome_schema_to_route(schema: Mapping[str, Any] | None, route_tag: str) -> dict[str, Any] | None:
    if not isinstance(schema, Mapping):
        return None
    filtered = deepcopy(dict(schema))
    outcome = filtered.get("properties", {}).get("outcome") if isinstance(filtered.get("properties"), Mapping) else None
    if not isinstance(outcome, dict):
        return filtered
    branches = outcome.get("anyOf")
    if not isinstance(branches, list):
        return filtered
    matching = [
        deepcopy(branch)
        for branch in branches
        if isinstance(branch, Mapping)
        and isinstance(branch.get("properties"), Mapping)
        and isinstance(branch["properties"].get("tag"), Mapping)
        and branch["properties"]["tag"].get("const") == route_tag
    ]
    if len(matching) != 1:
        return None
    outcome["anyOf"] = matching
    return filtered


def _route_anchored_repair_contract(contract: Mapping[str, Any], constraints: OutcomeRepairConstraints) -> dict[str, Any] | None:
    routes = contract.get("routes")
    if not isinstance(routes, Mapping) or constraints.route_tag not in routes:
        return None
    route_required_writes = contract.get("route_required_writes")
    anchored = dict(contract)
    anchored["available_routes"] = (constraints.route_tag,)
    anchored["routes"] = {constraints.route_tag: deepcopy(routes[constraints.route_tag])}
    anchored["route_required_writes"] = (
        {constraints.route_tag: tuple(route_required_writes.get(constraints.route_tag, ()))}
        if isinstance(route_required_writes, Mapping)
        else {}
    )
    anchored["response_schema"] = _filter_outcome_schema_to_route(
        anchored.get("response_schema") if isinstance(anchored.get("response_schema"), Mapping) else None,
        constraints.route_tag,
    )
    anchored["native_response_schema"] = _filter_outcome_schema_to_route(
        anchored.get("native_response_schema") if isinstance(anchored.get("native_response_schema"), Mapping) else None,
        constraints.route_tag,
    )
    anchored["retry_feedback"] = None
    anchored["route_handoff"] = None
    return anchored


def _compiled_read_name(value: ReadRef) -> str:
    if isinstance(value, ArtifactId):
        return value.qualified_name
    if isinstance(value, FanInRead):
        return value.path
    if isinstance(value.value, Path):
        return str(value.value)
    return value.value


def _compiled_require_name(value: RequireRef) -> str:
    if isinstance(value, ArtifactId):
        return value.qualified_name
    return value.path


def _compiled_write_name(value: WriteRef) -> str:
    return value.qualified_name


def _route_action_from_direct_control(result: _StepRouteResult) -> RouteAction:
    if result.destination == FINISH:
        return FinishAction(reason=result.runtime_control or "finish")
    if result.destination == AWAIT_INPUT:
        return AwaitInputAction(pending_input=result.pending_input)
    if result.destination == FAIL:
        return FailAction(reason=result.runtime_control)
    target_step = result.target_step or result.destination
    return Continue(target_step=target_step, reason=result.runtime_control or "route")


_T = TypeVar("_T")


def _response_schema_from_contract(contract: Mapping[str, Any]) -> Mapping[str, Any] | None:
    response_schema = contract.get("response_schema")
    if isinstance(response_schema, Mapping):
        return response_schema
    return None


class ProviderContractBuilder:
    """Builds provider-visible contracts for step execution."""

    def __init__(
        self,
        *,
        compiled: Any,
        services: ExecutionServices,
        allow_provider_questions: bool,
    ) -> None:
        if services.artifacts is None:
            raise ValueError("ProviderContractBuilder requires ExecutionServices.artifacts")
        if services.routes is None:
            raise ValueError("ProviderContractBuilder requires ExecutionServices.routes")
        self._compiled = compiled
        self._artifacts = services.artifacts
        self._routes = services.routes
        self._allow_provider_questions = allow_provider_questions

    def control_contract(
        self,
        step: PromptStepPlan,
        *,
        context: "Context",
        artifacts: ResolvedArtifacts,
        attempt: int,
        max_attempts: int,
        retry_feedback: str | None,
        route_handoff: str | None,
    ) -> dict[str, Any]:
        return self._provider_turn_contract(
            step,
            step.turn,
            context=context,
            artifacts=artifacts,
            attempt=attempt,
            max_attempts=max_attempts,
            retry_feedback=retry_feedback,
            route_handoff=route_handoff,
        )

    def pair_producer_contract(
        self,
        step: ProduceVerifyStepPlan,
        *,
        context: "Context",
        artifacts: ResolvedArtifacts,
        attempt: int,
        max_attempts: int,
        retry_feedback: str | None,
        route_handoff: str | None,
    ) -> dict[str, Any]:
        return self._provider_turn_contract(
            step,
            step.producer,
            context=context,
            artifacts=artifacts,
            attempt=attempt,
            max_attempts=max_attempts,
            retry_feedback=retry_feedback,
            route_handoff=route_handoff,
        )

    def pair_verifier_contract(
        self,
        step: ProduceVerifyStepPlan,
        *,
        context: "Context",
        artifacts: ResolvedArtifacts,
        attempt: int,
        max_attempts: int,
        retry_feedback: str | None,
        route_handoff: str | None,
    ) -> dict[str, Any]:
        return self._provider_turn_contract(
            step,
            step.verifier,
            context=context,
            artifacts=artifacts,
            attempt=attempt,
            max_attempts=max_attempts,
            retry_feedback=retry_feedback,
            route_handoff=route_handoff,
        )

    def _provider_turn_contract(
        self,
        step: StepPlan,
        turn: ProviderTurnPlan,
        *,
        context: "Context",
        artifacts: ResolvedArtifacts,
        attempt: int,
        max_attempts: int,
        retry_feedback: str | None,
        route_handoff: str | None,
    ) -> dict[str, Any]:
        include_routes = turn.kind != "producer"
        routes = self.routes(step) if include_routes else {}
        response_contract = (
            build_provider_outcome_contract(
                routes=routes,
                expected_output_schema=turn.expected_output_schema,
            )
            if include_routes
            else None
        )
        return {
            "expected_output_schema": deepcopy(turn.expected_output_schema),
            "available_routes": self.available_routes(step) if include_routes else (),
            "routes": deepcopy(routes),
            "readable_artifacts": self.readable_refs_from_turn(turn.io.reads, artifacts, context=context),
            "required_artifacts": self.required_artifact_refs_from_turn(turn.io.requires, artifacts, context=context),
            "writable_artifacts": self.writable_artifact_refs_from_turn(turn.io.writes, artifacts),
            "route_required_writes": self.route_required_writes(step) if include_routes else {},
            "response_schema": None if response_contract is None else response_contract.prompt_schema,
            "native_response_schema": None if response_contract is None else response_contract.native_schema,
            "response_schema_native_skip_reason": None if response_contract is None else response_contract.native_skip_reason,
            "retry_feedback": retry_feedback,
            "route_handoff": route_handoff,
            "attempt": attempt,
            "max_attempts": max_attempts,
        }

    def artifact_refs(
        self,
        names: tuple[str, ...],
        artifacts: ResolvedArtifacts,
    ) -> tuple[ProviderArtifactRef, ...]:
        return tuple(
            self.artifact_ref(resolved_name, artifacts[resolved_name])
            for resolved_name in (self._artifacts.artifact_lookup_name(name) for name in names)
        )

    def artifact_ref(self, name: str, handle: Any) -> ProviderArtifactRef:
        artifact = handle.artifact
        qualified_name = (
            artifact.qualified_name
            if artifact is not None and isinstance(artifact.qualified_name, str) and artifact.qualified_name
            else name
        )
        kind = artifact.kind if artifact is not None else "text"
        required = artifact.required if artifact is not None else False
        schema_name = self._artifacts.artifact_schema_name(artifact)
        return ProviderArtifactRef(
            name=handle.name,
            qualified_name=qualified_name,
            path=str(handle.path),
            kind=kind,
            required=required,
            exists=handle.exists(),
            schema_name=schema_name,
        )

    def readable_refs(
        self,
        names: tuple[str, ...],
        artifacts: ResolvedArtifacts,
        *,
        context: "Context",
    ) -> tuple[ProviderReadableRef, ...]:
        return tuple(self.readable_ref(name, artifacts, context=context) for name in names)

    def readable_refs_from_turn(
        self,
        refs: tuple[ReadRef, ...],
        artifacts: ResolvedArtifacts,
        *,
        context: "Context",
    ) -> tuple[ProviderReadableRef, ...]:
        return tuple(self._readable_ref_from_turn(ref, artifacts, context=context) for ref in refs)

    def required_artifact_refs_from_turn(
        self,
        refs: tuple[RequireRef, ...],
        artifacts: ResolvedArtifacts,
        *,
        context: "Context",
    ) -> tuple[ProviderArtifactRef, ...]:
        return tuple(self._required_artifact_ref_from_turn(ref, artifacts, context=context) for ref in refs)

    def writable_artifact_refs_from_turn(
        self,
        refs: tuple[WriteRef, ...],
        artifacts: ResolvedArtifacts,
    ) -> tuple[ProviderArtifactRef, ...]:
        return tuple(self.artifact_ref(_compiled_write_name(ref), artifacts[_compiled_write_name(ref)]) for ref in refs)

    def readable_ref(
        self,
        name: str,
        artifacts: ResolvedArtifacts,
        *,
        context: "Context",
    ) -> ProviderReadableRef:
        name = self._artifacts.artifact_lookup_name(name)
        if name in artifacts:
            handle = artifacts[name]
            artifact = handle.artifact
            return ProviderReadableRef(
                name=handle.name,
                path=str(handle.path),
                exists=handle.exists(),
                declared_artifact=True,
                kind=None if artifact is None else artifact.kind,
                qualified_name=None if artifact is None else artifact.qualified_name,
                schema_name=self._artifacts.artifact_schema_name(artifact),
            )
        workspace_path = self._artifacts.resolve_workspace_read_path(name, context=context)
        return ProviderReadableRef(
            name=name,
            path=str(workspace_path),
            exists=workspace_path.exists(),
            declared_artifact=False,
        )

    def _readable_ref_from_turn(
        self,
        ref: ReadRef,
        artifacts: ResolvedArtifacts,
        *,
        context: "Context",
    ) -> ProviderReadableRef:
        if isinstance(ref, FanInRead):
            path = self._fan_in_workspace_path(ref, context=context)
            return ProviderReadableRef(
                name=ref.path,
                path=str(path),
                exists=path.exists(),
                declared_artifact=False,
            )
        return self.readable_ref(_compiled_read_name(ref), artifacts, context=context)

    def _required_artifact_ref_from_turn(
        self,
        ref: RequireRef,
        artifacts: ResolvedArtifacts,
        *,
        context: "Context",
    ) -> ProviderArtifactRef:
        if isinstance(ref, ArtifactId):
            name = _compiled_require_name(ref)
            return self.artifact_ref(name, artifacts[name])
        path = (
            self._fan_in_workspace_path(ref, context=context)
            if isinstance(ref, FanInRead)
            else self._artifacts.resolve_workspace_read_path(_compiled_require_name(ref), context=context)
        )
        return ProviderArtifactRef(
            name=ref.path,
            qualified_name=ref.path,
            path=str(path),
            kind="text",
            required=True,
            exists=path.exists(),
            schema_name=None,
        )

    @staticmethod
    def _fan_in_workspace_path(ref: FanInRead, *, context: "Context") -> Path:
        fan_in = context.fan_in
        if fan_in is None:
            raise WorkflowExecutionError(f"fan-in helper {ref.helper!r} requires fan-in context")
        return fan_in.results_path if ref.helper == "results" else fan_in.context_path

    def route_required_writes(self, step: StepPlan) -> dict[str, tuple[str, ...]]:
        visible_routes = set(self.available_routes(step))
        return {
            route_tag: effective_route_required_writes_for_step(
                self._compiled,
                step=step,
                route_tag=route_tag,
            )
            for route_tag in self._compiled.routes.get(step.name, {})
            if route_tag in visible_routes
        }

    def routes(self, step: StepPlan) -> dict[str, ProviderRoute]:
        routes: dict[str, ProviderRoute] = {}
        for route_name in self.available_routes(step):
            compiled_route = self._compiled.routes.get(step.name, {}).get(route_name)
            if compiled_route is None:
                continue
            routes[route_name] = ProviderRoute(
                summary=compiled_route.summary,
                target=route_target_value(compiled_route.target),
                required_writes=tuple(artifact_id.qualified_name for artifact_id in compiled_route.required_writes.declared),
                explicit_required_writes=explicit_route_required_writes(compiled_route),
                handoff=compiled_route.handoff,
                provider_visible=True,
                provider_visibility=compiled_route.provider_visibility,
                payload_schema=payload_schema_for_route(
                    compiled_route,
                    expected_output_schema=step.expected_output_schema,
                ),
                route_fields_schema=route_fields_schema_for_route(compiled_route),
                preset_kind=compiled_route.preset_kind,
            )
        return routes

    def available_routes(self, step: StepPlan) -> tuple[str, ...]:
        if self._allow_provider_questions:
            return self._routes.provider_visible_route_tags(step.name, mode="interactive")
        return self._routes.provider_visible_route_tags(step.name, mode="full_auto")


class StepDispatcher:
    """Dispatches one workflow step plan through the engine execution path."""

    def __init__(
        self,
        *,
        services: ExecutionServices,
        hook_runner: "HookRunner",
        route_finalizer: "RouteFinalizer",
        branch_group_runtime: Any,
        provider_contract_builder: ProviderContractBuilder,
    ) -> None:
        if services.artifacts is None:
            raise ValueError("StepDispatcher requires ExecutionServices.artifacts")
        if services.routes is None:
            raise ValueError("StepDispatcher requires ExecutionServices.routes")
        if services.sessions is None:
            raise ValueError("StepDispatcher requires ExecutionServices.sessions")
        if services.providers is None:
            raise ValueError("StepDispatcher requires ExecutionServices.providers")
        if services.events is None:
            raise ValueError("StepDispatcher requires ExecutionServices.events")
        if services.child_workflows is None:
            raise ValueError("StepDispatcher requires ExecutionServices.child_workflows")
        self._artifacts = services.artifacts
        self._routes = services.routes
        self._sessions = services.sessions
        self._providers = services.providers
        self._events = services.events
        self._child_workflows = services.child_workflows
        self._hook_runner = hook_runner
        self._route_finalizer = route_finalizer
        self._branch_group_runtime = branch_group_runtime
        self._provider_contract_builder = provider_contract_builder

    def execute(
        self,
        step: StepPlan,
        context: "Context",
        state: "BaseModel",
        pending_handoffs: tuple["PendingHandoff", ...],
        *,
        route_mode: RouteMode = "finalize",
    ) -> StepExecutionResult:
        return run_awaitable_sync(
            lambda: self.execute_async(
                step,
                context,
                state,
                pending_handoffs,
                route_mode=route_mode,
            ),
            active_loop_error="Synchronous step execution cannot bridge async execution inside an active event loop.",
        )

    async def execute_async(
        self,
        step: StepPlan,
        context: "Context",
        state: "BaseModel",
        pending_handoffs: tuple["PendingHandoff", ...],
        *,
        route_mode: RouteMode = "finalize",
    ) -> StepExecutionResult:
        context._sync_state(state)
        context._sync_active_worklist(step.scope_name)
        resume_cursor = _provider_resume_cursor_for_step(context, step)
        if step.scope_name is not None:
            context.ensure_selection(step.scope_name)
        initial_artifacts = self._artifacts.resolve_artifacts(context)
        context._sync_artifacts(initial_artifacts)
        self._artifacts.ensure_required_artifacts(step, initial_artifacts)
        if isinstance(step, ProduceVerifyStepPlan):
            return await self._execute_pair_step_async(
                step,
                context,
                state,
                pending_handoffs,
                route_mode=route_mode,
                resume_cursor=resume_cursor,
            )
        from .step_plans import BranchGroupStepPlan, ChildWorkflowStepPlan, PythonStepPlan

        if isinstance(step, BranchGroupStepPlan):
            if resume_cursor is not None:
                raise WorkflowExecutionError("provider-attempt resume cursor cannot target a branch-group step")
            if route_mode != "finalize":
                raise WorkflowExecutionError("branch-group composite steps do not support capture mode")
            return await self._branch_group_runtime.run_async(step, context, state, pending_handoffs)

        if resume_cursor is None:
            before_result = self._hook_runner.run_before(step, context, state, artifacts=initial_artifacts)
            state = before_result.state
            context._sync_state(state)
            context._sync_artifacts(self._artifacts.resolve_artifacts(context))
            if before_result.control is not None:
                _, remaining_pending_handoffs = self._routes.matching_pending_handoffs(step, context, pending_handoffs)
                direct_control = self._routes.normalize_direct_runtime_control(
                    step=step,
                    context=context,
                    control=before_result.control,
                    hook_name=getattr(step.before_hook, "__name__", type(step.before_hook).__name__),
                    hook_phase="before",
                )
                scheduled_handoffs = (
                    ()
                    if route_mode == "capture"
                    else self._routes.schedule_direct_control_handoffs(
                        remaining_pending_handoffs,
                        control=direct_control,
                        context=context,
                        source_step=step.name,
                    )
                )
                return step_result_from_direct_control(
                    step=step,
                    state=state,
                    control=direct_control,
                    pending_handoffs=scheduled_handoffs,
                )
            if before_result.event is not None:
                _, remaining_pending_handoffs = self._routes.matching_pending_handoffs(step, context, pending_handoffs)
                finalization = self._complete_route(
                    route_mode=route_mode,
                    request=StepFinalizationRequest(
                        step=step,
                        context=context,
                        state=state,
                        artifacts=self._artifacts.resolve_artifacts(context),
                        candidate_event=before_result.event,
                        candidate_route_present=False,
                        after_subject=before_result.event,
                        pending_handoffs=remaining_pending_handoffs,
                        error_cls=WorkflowExecutionError,
                        provider_attributable=False,
                        source_hook=getattr(step.before_hook, "__name__", type(step.before_hook).__name__),
                        source_phase="before",
                    ),
                )
                return step_result_from_route_finalization(step=step, route_finalization=finalization)
        if isinstance(step, PromptStepPlan):
            return await self._execute_llm_step_async(
                step,
                context,
                state,
                pending_handoffs,
                route_mode=route_mode,
                resume_cursor=resume_cursor,
            )
        if resume_cursor is not None:
            raise WorkflowExecutionError(f"provider-attempt resume cursor cannot target {step.kind!r} step {step.name!r}")
        if isinstance(step, ChildWorkflowStepPlan):
            return self._execute_workflow_step_for_mode(
                step,
                context,
                state,
                pending_handoffs,
                route_mode=route_mode,
            )
        if isinstance(step, PythonStepPlan):
            return self._execute_python_step_for_mode(
                step,
                context,
                state,
                pending_handoffs,
                route_mode=route_mode,
            )
        raise WorkflowExecutionError(f"unsupported step kind {step.kind!r}")

    def _complete_route(
        self,
        *,
        route_mode: RouteMode,
        request: StepFinalizationRequest,
    ) -> _StepRouteResult:
        if route_mode == "capture":
            return self._route_finalizer.capture(request)
        return self._route_finalizer.finalize_result(request)

    def _execute_workflow_step_for_mode(
        self,
        step: StepPlan,
        context: "Context",
        state: BaseModel,
        pending_handoffs: tuple["PendingHandoff", ...],
        *,
        route_mode: RouteMode,
    ) -> StepExecutionResult:
        _, remaining_pending_handoffs = self._routes.matching_pending_handoffs(step, context, pending_handoffs)
        child_result = self._child_workflows.run_child_step(step, context)
        event = self._child_workflows.map_result(step, child_result)
        try:
            self._routes.validate_event(step, event, provider_attributable=False, error_cls=WorkflowExecutionError)
        except WorkflowExecutionError as exc:
            annotated = self._events.annotate_execution_error(
                exc,
                checkpoint_state=state,
                failure_context=FailureContext(
                    kind="route_validation",
                    step_name=step.name,
                    candidate_route=getattr(event, "tag", None) if isinstance(getattr(event, "tag", None), str) else None,
                    details={"error": str(exc), "error_type": type(exc).__name__},
                ),
            )
            if annotated is exc:
                raise
            raise annotated from exc
        finalization = self._complete_route(
            route_mode=route_mode,
            request=StepFinalizationRequest(
                step=step,
                context=context,
                state=state,
                artifacts=self._artifacts.resolve_artifacts(context),
                candidate_event=event,
                candidate_route=event.tag,
                candidate_route_present=True,
                after_subject=event,
                pending_handoffs=remaining_pending_handoffs,
                error_cls=WorkflowExecutionError,
                provider_attributable=False,
            ),
        )
        return step_result_from_route_finalization(step=step, route_finalization=finalization)

    def _execute_python_step_for_mode(
        self,
        step: StepPlan,
        context: "Context",
        state: BaseModel,
        pending_handoffs: tuple["PendingHandoff", ...],
        *,
        route_mode: RouteMode,
    ) -> StepExecutionResult:
        _, remaining_pending_handoffs = self._routes.matching_pending_handoffs(step, context, pending_handoffs)
        if step.python_handler is None:
            raise WorkflowExecutionError(f"{step.kind} step {step.name!r} has no compiled handler")
        context._sync_route(None)
        context._sync_event(None)
        context._sync_outcome(None)
        handler_name = getattr(step.python_handler, "__name__", step.name)
        invocation_id = f"{step.name}:python_step:{handler_name}"
        context._set_execution_source(
            hook_name=handler_name,
            phase="python_step",
            invocation_id=invocation_id,
        )
        try:
            result = step.python_handler(context)
            next_state = context.state
        finally:
            context._set_execution_source(hook_name=None, phase=None, invocation_id=None)
        try:
            hook_result = self._hook_runner.normalize_result(
                step,
                state=next_state,
                context=context,
                current_event=None,
                result=result,
                hook_phase="python_step",
                hook_name=handler_name,
            )
        except WorkflowExecutionError as exc:
            candidate_route: str | None = None
            if isinstance(result, str):
                candidate_route = result
            elif isinstance(result, Event):
                candidate_route = result.tag
            annotated = self._events.annotate_execution_error(
                exc,
                checkpoint_state=StateRuntimeService.clone_state(context.state),
                failure_context=FailureContext(
                    kind="route_validation",
                    step_name=step.name,
                    candidate_route=candidate_route,
                    source_hook=handler_name,
                    source_phase="python_step",
                    details={"error": str(exc), "error_type": type(exc).__name__},
                ),
            )
            if annotated is exc:
                raise
            raise annotated from exc
        if hook_result.control is not None:
            direct_control = self._routes.normalize_direct_runtime_control(
                step=step,
                context=context,
                control=hook_result.control,
                hook_name=handler_name,
                hook_phase="python_step",
            )
            scheduled_handoffs = (
                ()
                if route_mode == "capture"
                else self._routes.schedule_direct_control_handoffs(
                    remaining_pending_handoffs,
                    control=direct_control,
                    context=context,
                    source_step=step.name,
                )
            )
            return step_result_from_direct_control(
                step=step,
                state=next_state,
                control=direct_control,
                pending_handoffs=scheduled_handoffs,
            )
        event = hook_result.event or Event("done")
        finalization = self._complete_route(
            route_mode=route_mode,
            request=StepFinalizationRequest(
                step=step,
                context=context,
                state=next_state,
                artifacts=self._artifacts.resolve_artifacts(context),
                candidate_event=event,
                candidate_route=event.tag,
                candidate_route_present=True,
                after_subject=event,
                pending_handoffs=remaining_pending_handoffs,
                error_cls=WorkflowExecutionError,
                provider_attributable=False,
                source_hook=handler_name,
                source_phase="python_step",
            ),
        )
        return step_result_from_route_finalization(step=step, route_finalization=finalization)

    def _control_retry_response_schema(
        self,
        step: PromptStepPlan,
        context: "Context",
        artifacts: ResolvedArtifacts,
        *,
        attempt: int,
        max_attempts: int,
        retry_feedback: str | None,
        route_handoff: str | None,
    ) -> Mapping[str, Any] | None:
        try:
            contract = self._provider_contract_builder.control_contract(
                step,
                context=context,
                artifacts=artifacts,
                attempt=attempt,
                max_attempts=max_attempts,
                retry_feedback=retry_feedback,
                route_handoff=route_handoff,
            )
        except Exception:
            return None
        return _response_schema_from_contract(contract)

    def _pair_verifier_retry_response_schema(
        self,
        step: ProduceVerifyStepPlan,
        context: "Context",
        *,
        attempt: int,
        max_attempts: int,
        retry_feedback: str | None,
        route_handoff: str | None,
    ) -> Mapping[str, Any] | None:
        try:
            artifacts = self._artifacts.resolve_artifacts(context)
            contract = self._provider_contract_builder.pair_verifier_contract(
                step,
                context=context,
                artifacts=artifacts,
                attempt=attempt,
                max_attempts=max_attempts,
                retry_feedback=retry_feedback,
                route_handoff=route_handoff,
            )
        except Exception:
            return None
        return _response_schema_from_contract(contract)

    def _annotate_provider_turn_failure(
        self,
        exc: Exception,
        *,
        step_name: str,
        turn_kind: str,
    ) -> Exception:
        if not isinstance(exc, WorkflowExecutionError):
            return exc
        failure_context = self._events.failure_context_for_exception(exc)
        if failure_context is None:
            retry_kind = self._events.provider_retry_kind_for_exception(exc)
            failure_context = FailureContext(
                kind=retry_kind or "provider_execution_error",
                step_name=step_name,
                provider_attributable=isinstance(exc, ProviderExecutionError),
                details={"error": str(exc)},
            )
        details = dict(failure_context.details)
        details["provider_turn_kind"] = turn_kind
        return replace_execution_error(
            exc,
            failure_context=FailureContext(
                kind=failure_context.kind,
                step_name=failure_context.step_name or step_name,
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

    def _should_include_outcome_schema_feedback(
        self,
        exc: Exception,
        *,
        allowed_turn_kinds: set[str],
    ) -> bool:
        if self._events.provider_retry_kind_for_exception(exc) != "malformed_provider_output":
            return False
        failure_context = self._events.failure_context_for_exception(exc)
        if failure_context is None:
            return False
        return (
            failure_context.details.get("provider_failure_stage") == "outcome_contract"
            and failure_context.details.get("provider_turn_kind") in allowed_turn_kinds
        )

    def _should_retry_pair_verifier_only(self, exc: Exception) -> bool:
        retry_kind = self._events.provider_retry_kind_for_exception(exc)
        if retry_kind not in {
            "malformed_provider_output",
            "provider_transport_failure",
            "illegal_route",
            "invalid_payload",
        }:
            return False
        failure_context = self._events.failure_context_for_exception(exc)
        if failure_context is None:
            return False
        return failure_context.details.get("provider_turn_kind") == "verifier"

    def _should_repair_malformed_outcome(
        self,
        exc: Exception,
        *,
        allowed_turn_kinds: set[str],
    ) -> bool:
        if self._events.provider_retry_kind_for_exception(exc) != "malformed_provider_output":
            return False
        failure_context = self._events.failure_context_for_exception(exc)
        if failure_context is None:
            return False
        return (
            failure_context.details.get("provider_failure_stage") == "outcome_contract"
            and failure_context.details.get("provider_turn_kind") in allowed_turn_kinds
            and _exact_outcome_candidate(failure_context.details) is not None
        )

    def _persist_failed_provider_session(self, exc: Exception, *, context: "Context") -> None:
        session = _failed_provider_session(_failure_details(exc, self._events))
        if session is not None:
            self._sessions.persist_session(session, context=context)

    def _ensure_outcome_repair_preserves_constraints(
        self,
        *,
        step: StepPlan,
        outcome: Outcome,
        constraints: OutcomeRepairConstraints | None,
    ) -> None:
        if constraints is None or outcome_preserves_repair_constraints(outcome, constraints):
            return
        raise ProviderExecutionError(
            f"outcome repair changed route from {constraints.route_tag!r} to {outcome.tag!r}",
            failure_context=FailureContext(
                kind="malformed_provider_output",
                step_name=step.name,
                candidate_route=outcome.tag,
                provider_attributable=True,
                details={
                    "error": "outcome repair changed the provider-selected route",
                    "provider_failure_stage": "outcome_repair",
                    "expected_route": constraints.route_tag,
                    "actual_route": outcome.tag,
                },
            ),
            retry_kind="malformed_provider_output",
        )

    def _finalize_pair_outcome_result(
        self,
        *,
        step: ProduceVerifyStepPlan,
        context: "Context",
        route_mode: RouteMode,
        pair_result: PairProviderResult,
        pending_handoffs: tuple["PendingHandoff", ...],
    ) -> StepExecutionResult:
        self._sessions.persist_session(pair_result.producer_session, context=context)
        self._sessions.persist_session(pair_result.verifier_session, context=context)
        assert pair_result.outcome is not None
        final_event = self._routes.event_from_outcome(step, pair_result.outcome)
        finalization = self._complete_route(
            route_mode=route_mode,
            request=StepFinalizationRequest(
                step=step,
                context=context,
                state=pair_result.state or context.state,
                artifacts=self._artifacts.resolve_artifacts(context),
                candidate_event=final_event,
                candidate_route=final_event.tag,
                candidate_route_present=True,
                after_subject=pair_result.outcome,
                pending_handoffs=pending_handoffs,
                error_cls=ProviderExecutionError,
                provider_attributable=True,
                after_hook=step.after_verifier_hook,
                after_hook_phase="after_verifier",
            ),
        )
        return step_result_from_route_finalization(
            step=step,
            route_finalization=finalization,
            outcome=pair_result.outcome,
            producer_raw_output=pair_result.producer_raw_output,
            verifier_raw_output=pair_result.verifier_raw_output,
            provider_usage=pair_result.usage,
        )

    def _finalize_llm_outcome_result(
        self,
        *,
        step: PromptStepPlan,
        context: "Context",
        state: BaseModel,
        route_mode: RouteMode,
        llm_result: ProviderExecResult,
        pending_handoffs: tuple["PendingHandoff", ...],
    ) -> StepExecutionResult:
        assert llm_result.outcome is not None
        final_event = self._routes.event_from_outcome(step, llm_result.outcome)
        finalization = self._complete_route(
            route_mode=route_mode,
            request=StepFinalizationRequest(
                step=step,
                context=context,
                state=state,
                artifacts=self._artifacts.resolve_artifacts(context),
                candidate_event=final_event,
                candidate_route=final_event.tag,
                candidate_route_present=True,
                after_subject=llm_result.outcome,
                pending_handoffs=pending_handoffs,
                error_cls=ProviderExecutionError,
                provider_attributable=True,
            ),
        )
        self._sessions.persist_session(llm_result.session, context=context)
        return step_result_from_route_finalization(
            step=step,
            route_finalization=finalization,
            outcome=llm_result.outcome,
            producer_raw_output=llm_result.text,
            provider_usage=StepProviderUsage(llm=llm_result.usage),
        )

    async def _try_repair_pair_verifier_outcome(
        self,
        *,
        step: ProduceVerifyStepPlan,
        context: "Context",
        route_mode: RouteMode,
        exc: Exception,
        phase: PairVerifierPhase | None,
        attempt: int,
        max_attempts: int,
        retry_feedback: str | None,
        route_handoff: str | None,
        pending_handoffs: tuple["PendingHandoff", ...],
        resume_cursor: dict[str, Any] | None = None,
    ) -> StepExecutionResult | None:
        resuming_repair = _resume_cursor_turn_kind(resume_cursor) == "outcome_repair"
        if phase is None:
            return None
        if resuming_repair:
            candidate = _outcome_repair_candidate_from_cursor(resume_cursor or {})
            constraints = _outcome_repair_constraints_from_cursor(resume_cursor or {})
            details = _failure_details(exc, self._events)
        else:
            if not self._should_repair_malformed_outcome(exc, allowed_turn_kinds={"verifier"}):
                return None
            details = _failure_details(exc, self._events)
            candidate = _exact_outcome_candidate(details)
            constraints = extract_outcome_repair_constraints(candidate) if candidate is not None else None
        if candidate is None:
            return None
        failed_session = _failed_provider_session(details) or self._sessions.resolve_pair_review_session(
            step,
            context,
            producer_session=phase.producer_session,
        )
        failed_usage = _failed_provider_usage(details)
        try:
            repaired = None
            repair_usage = None
            repair_method = "deterministic"
            if not resuming_repair:
                repaired = self._try_deterministic_outcome_repair(
                    step=step,
                    context=context,
                    candidate=candidate,
                    failed_turn_kind="verifier",
                    attempt=attempt,
                )
                if repaired is not None:
                    self._ensure_outcome_repair_preserves_constraints(
                        step=step,
                        outcome=repaired,
                        constraints=constraints,
                    )
            if repaired is None and constraints is not None:
                repair_artifacts = self._artifacts.resolve_artifacts(context)
                repair_contract = _route_anchored_repair_contract(
                    self._provider_contract_builder.pair_verifier_contract(
                        step,
                        context=context,
                        artifacts=repair_artifacts,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        retry_feedback=retry_feedback,
                        route_handoff=route_handoff,
                    ),
                    constraints,
                )
                if repair_contract is None:
                    self._events.emit_provider_attempt_event(
                        "provider_outcome_repair_failed",
                        step=step,
                        context=context,
                        turn_kind="outcome_repair",
                        attempt=attempt,
                        failed_turn_kind="verifier",
                        method="fresh_finalizer",
                        reason="route_not_provider_visible",
                    )
                    return None
                repair_response = await self._run_outcome_repair_turn(
                    step=step,
                    context=context,
                    artifacts=repair_artifacts,
                    contract=repair_contract,
                    exc=exc,
                    candidate=candidate,
                    constraints=constraints,
                    failed_turn_kind="verifier",
                    failed_provider_session=failed_session,
                    failed_provider_usage=failed_usage,
                    phase=phase,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    resume_cursor=resume_cursor,
                )
                repaired = repair_response.outcome
                repair_usage = repair_response.usage
                repair_method = "fresh_finalizer"
            if repaired is None:
                return None
            self._ensure_outcome_repair_preserves_constraints(
                step=step,
                outcome=repaired,
                constraints=constraints,
            )
            self._providers.validate_outcome(step, repaired)
            if repair_method == "fresh_finalizer":
                self._emit_outcome_repair_finished(
                    step=step,
                    context=context,
                    failed_turn_kind="verifier",
                    attempt=attempt,
                    method=repair_method,
                    usage=repair_usage,
                )
        except asyncio.CancelledError:
            raise
        except Exception as repair_exc:
            self._emit_outcome_repair_failed(
                step=step,
                context=context,
                failed_turn_kind="verifier",
                attempt=attempt,
                method="repair",
                exc=repair_exc,
            )
            return None
        pair_result = PairProviderResult(
            producer_raw_output=phase.producer_raw_output,
            verifier_raw_output=repaired.raw_output,
            outcome=repaired,
            producer_session=phase.producer_session,
            verifier_session=failed_session,
            usage=StepProviderUsage(
                producer=phase.producer_usage,
                verifier=failed_usage,
                repair=repair_usage,
            ),
            state=context.state,
        )
        return self._finalize_pair_outcome_result(
            step=step,
            context=context,
            route_mode=route_mode,
            pair_result=pair_result,
            pending_handoffs=pending_handoffs,
        )

    async def _try_repair_llm_outcome(
        self,
        *,
        step: PromptStepPlan,
        context: "Context",
        state: BaseModel,
        route_mode: RouteMode,
        artifacts: ResolvedArtifacts,
        exc: Exception,
        attempt: int,
        max_attempts: int,
        retry_feedback: str | None,
        route_handoff: str | None,
        pending_handoffs: tuple["PendingHandoff", ...],
        resume_cursor: dict[str, Any] | None = None,
    ) -> StepExecutionResult | None:
        resuming_repair = _resume_cursor_turn_kind(resume_cursor) == "outcome_repair"
        if resuming_repair:
            candidate = _outcome_repair_candidate_from_cursor(resume_cursor or {})
            constraints = _outcome_repair_constraints_from_cursor(resume_cursor or {})
            details = _failure_details(exc, self._events)
        else:
            if not self._should_repair_malformed_outcome(exc, allowed_turn_kinds={"llm"}):
                return None
            details = _failure_details(exc, self._events)
            candidate = _exact_outcome_candidate(details)
            constraints = extract_outcome_repair_constraints(candidate) if candidate is not None else None
        if candidate is None:
            return None
        failed_session = _failed_provider_session(details)
        failed_usage = _failed_provider_usage(details)
        try:
            repaired = None
            repair_usage = None
            repair_method = "deterministic"
            if not resuming_repair:
                repaired = self._try_deterministic_outcome_repair(
                    step=step,
                    context=context,
                    candidate=candidate,
                    failed_turn_kind="llm",
                    attempt=attempt,
                )
                if repaired is not None:
                    self._ensure_outcome_repair_preserves_constraints(
                        step=step,
                        outcome=repaired,
                        constraints=constraints,
                    )
            if repaired is None and constraints is not None:
                repair_contract = _route_anchored_repair_contract(
                    self._provider_contract_builder.control_contract(
                        step,
                        context=context,
                        artifacts=artifacts,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        retry_feedback=retry_feedback,
                        route_handoff=route_handoff,
                    ),
                    constraints,
                )
                if repair_contract is None:
                    self._events.emit_provider_attempt_event(
                        "provider_outcome_repair_failed",
                        step=step,
                        context=context,
                        turn_kind="outcome_repair",
                        attempt=attempt,
                        failed_turn_kind="llm",
                        method="fresh_finalizer",
                        reason="route_not_provider_visible",
                    )
                    return None
                repair_response = await self._run_outcome_repair_turn(
                    step=step,
                    context=context,
                    artifacts=artifacts,
                    contract=repair_contract,
                    exc=exc,
                    candidate=candidate,
                    constraints=constraints,
                    failed_turn_kind="llm",
                    failed_provider_session=failed_session,
                    failed_provider_usage=failed_usage,
                    phase=None,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    resume_cursor=resume_cursor,
                )
                repaired = repair_response.outcome
                repair_usage = repair_response.usage
                repair_method = "fresh_finalizer"
            if repaired is None:
                return None
            self._ensure_outcome_repair_preserves_constraints(
                step=step,
                outcome=repaired,
                constraints=constraints,
            )
            self._providers.validate_outcome(step, repaired)
            if repair_method == "fresh_finalizer":
                self._emit_outcome_repair_finished(
                    step=step,
                    context=context,
                    failed_turn_kind="llm",
                    attempt=attempt,
                    method=repair_method,
                    usage=repair_usage,
                )
        except asyncio.CancelledError:
            raise
        except Exception as repair_exc:
            self._emit_outcome_repair_failed(
                step=step,
                context=context,
                failed_turn_kind="llm",
                attempt=attempt,
                method="repair",
                exc=repair_exc,
            )
            return None
        llm_result = ProviderExecResult(
            text=repaired.raw_output,
            session_id=getattr(failed_session, "session_id", None),
            provider_metadata={},
            usage=failed_usage,
            session=failed_session,
            outcome=repaired,
        )
        result = self._finalize_llm_outcome_result(
            step=step,
            context=context,
            state=state,
            route_mode=route_mode,
            llm_result=llm_result,
            pending_handoffs=pending_handoffs,
        )
        if repair_usage is not None:
            return replace(result, provider_usage=StepProviderUsage(llm=failed_usage, repair=repair_usage))
        return result

    def _try_deterministic_outcome_repair(
        self,
        *,
        step: StepPlan,
        context: "Context",
        candidate: str,
        failed_turn_kind: str,
        attempt: int,
    ) -> Outcome | None:
        self._events.emit_provider_attempt_event(
            "provider_outcome_repair_started",
            step=step,
            context=context,
            turn_kind="outcome_repair",
            attempt=attempt,
            failed_turn_kind=failed_turn_kind,
            method="deterministic",
        )
        repaired = repair_incomplete_outcome_json(candidate)
        if repaired is None:
            self._events.emit_provider_attempt_event(
                "provider_outcome_repair_failed",
                step=step,
                context=context,
                turn_kind="outcome_repair",
                attempt=attempt,
                failed_turn_kind=failed_turn_kind,
                method="deterministic",
                reason="not_structurally_repairable",
            )
            return None
        self._providers.validate_outcome(step, repaired.outcome)
        self._events.emit_provider_attempt_event(
            "provider_outcome_repair_finished",
            step=step,
            context=context,
            turn_kind="outcome_repair",
            attempt=attempt,
            failed_turn_kind=failed_turn_kind,
            method="deterministic",
        )
        return repaired.outcome

    async def _run_outcome_repair_turn(
        self,
        *,
        step: StepPlan,
        context: "Context",
        artifacts: ResolvedArtifacts,
        contract: Mapping[str, Any],
        exc: Exception,
        candidate: str,
        constraints: OutcomeRepairConstraints,
        failed_turn_kind: str,
        failed_provider_session: SessionBinding | None,
        failed_provider_usage: TokenUsage | None,
        phase: PairVerifierPhase | None,
        attempt: int,
        max_attempts: int,
        resume_cursor: dict[str, Any] | None,
    ) -> OutcomeResponse:
        if not _same_resume_attempt(resume_cursor, attempt, turn_kind="outcome_repair"):
            self._events.emit_provider_attempt_event(
                "provider_attempt_started",
                step=step,
                context=context,
                turn_kind="outcome_repair",
                attempt=attempt,
                failed_turn_kind=failed_turn_kind,
                method="fresh_finalizer",
            )
            self._events.emit_provider_attempt_event(
                "provider_outcome_repair_started",
                step=step,
                context=context,
                turn_kind="outcome_repair",
                attempt=attempt,
                failed_turn_kind=failed_turn_kind,
                method="fresh_finalizer",
            )
        repair_contract = dict(contract)
        repair_contract["retry_feedback"] = None
        repair_contract["route_handoff"] = None
        try:
            context._set_provider_attempt_checkpoint_data(
                _provider_checkpoint_data(
                    step=step,
                    context=context,
                    turn_kind="outcome_repair",
                    attempt=attempt,
                    max_attempts=max_attempts,
                    producer_raw_output=None if phase is None else phase.producer_raw_output,
                    producer_session=None if phase is None else phase.producer_session,
                    producer_usage=None if phase is None else phase.producer_usage,
                    outcome_repair_candidate=candidate,
                    outcome_repair_constraints=_outcome_repair_constraints_cursor_payload(constraints),
                    outcome_repair_failed_turn_kind=failed_turn_kind,
                    outcome_repair_failure_context=self._events.exception_failure_context_payload(exc),
                    failed_provider_session=_session_binding_cursor_payload(failed_provider_session),
                    failed_provider_usage=_token_usage_cursor_payload(failed_provider_usage),
                )
            )
            request = LLMRequest(
                step_name=step.name,
                prompt=ResolvedPrompt(
                    path=None,
                    text=self._outcome_repair_prompt_text(
                        exc=exc,
                        candidate=candidate,
                        failed_turn_kind=failed_turn_kind,
                    ),
                    source="inline",
                ),
                context=context,
                artifacts=artifacts,
                session=None,
                policy=_context_provider_policy(context),
                turn_kind="outcome_repair",
                **repair_contract,
            )
            _checkpoint_provider_attempt(context)
            response = await self._providers.run_llm(request)
            self._providers.validate_outcome(step, response.outcome)
            self._ensure_outcome_repair_preserves_constraints(
                step=step,
                outcome=response.outcome,
                constraints=constraints,
            )
        except asyncio.CancelledError:
            raise
        except Exception as repair_exc:
            annotated_exc = self._annotate_provider_turn_failure(
                repair_exc,
                step_name=step.name,
                turn_kind="outcome_repair",
            )
            self._events.emit_provider_attempt_failed(
                step=step,
                context=context,
                turn_kind="outcome_repair",
                attempt=attempt,
                exc=annotated_exc,
            )
            if annotated_exc is repair_exc:
                raise
            raise annotated_exc from repair_exc
        finally:
            context._set_provider_attempt_checkpoint_data(None)
        self._events.emit_provider_attempt_finished(
            step=step,
            context=context,
            turn_kind="outcome_repair",
            attempt=attempt,
            token_usage=response.usage,
        )
        return response

    def _emit_outcome_repair_finished(
        self,
        *,
        step: StepPlan,
        context: "Context",
        failed_turn_kind: str,
        attempt: int,
        method: str,
        usage: TokenUsage | None,
    ) -> None:
        self._events.emit_provider_attempt_event(
            "provider_outcome_repair_finished",
            step=step,
            context=context,
            turn_kind="outcome_repair",
            attempt=attempt,
            token_usage=usage,
            failed_turn_kind=failed_turn_kind,
            method=method,
        )

    def _emit_outcome_repair_failed(
        self,
        *,
        step: StepPlan,
        context: "Context",
        failed_turn_kind: str,
        attempt: int,
        method: str,
        exc: Exception,
    ) -> None:
        self._events.emit_provider_attempt_event(
            "provider_outcome_repair_failed",
            step=step,
            context=context,
            turn_kind="outcome_repair",
            attempt=attempt,
            failed_turn_kind=failed_turn_kind,
            method=method,
            failure_context=self._events.exception_failure_context_payload(exc),
        )

    def _outcome_repair_prompt_text(
        self,
        *,
        exc: Exception,
        candidate: str,
        failed_turn_kind: str,
    ) -> str:
        details = _failure_details(exc, self._events)
        diagnostic_lines = [
            f"Failed turn kind: {failed_turn_kind}",
            f"Parser error: {details.get('json_error_message') or str(exc)}",
        ]
        if details.get("json_error_line") is not None and details.get("json_error_column") is not None:
            diagnostic_lines.append(
                f"Location: line {details.get('json_error_line')}, column {details.get('json_error_column')}"
            )
        return "\n".join(
            [
                "Repair the malformed outcome JSON produced by the failed provider turn.",
                "Preserve the provider's chosen route and field values exactly. Do not invent or change semantic content.",
                "If a field is already present, keep its value. Only correct JSON syntax/envelope formatting.",
                "",
                "Diagnostics:",
                *diagnostic_lines,
                "",
                "Malformed outcome candidate:",
                "```text",
                candidate,
                "```",
            ]
        )

    async def _execute_pair_step_async(
        self,
        step: ProduceVerifyStepPlan,
        context: "Context",
        state: BaseModel,
        pending_handoffs: tuple["PendingHandoff", ...],
        *,
        route_mode: RouteMode,
        resume_cursor: dict[str, Any] | None = None,
    ) -> StepExecutionResult:
        baseline_session = self._sessions.resolve_session(step, context)
        route_handoff, remaining_pending_handoffs = self._routes.matching_pending_handoffs(step, context, pending_handoffs)
        pair_retry_feedback: str | None = None
        verifier_retry_feedback: str | None = None
        verifier_retry_phase: PairVerifierPhase | None = None
        max_attempts = step.producer.retry_policy.max_attempts
        start_attempt = _resume_cursor_attempt(resume_cursor) or 1
        for attempt in range(start_attempt, max_attempts + 1):
            artifacts = self._artifacts.resolve_artifacts(context)
            phase_tracker = _PairAttemptPhaseTracker(verifier_phase=verifier_retry_phase)
            active_retry_feedback = verifier_retry_feedback if verifier_retry_phase is not None else pair_retry_feedback
            try:
                attempt_resume_cursor = resume_cursor if attempt == start_attempt else None
                if _resume_cursor_turn_kind(attempt_resume_cursor) == "outcome_repair":
                    verifier_phase = self._pair_verifier_phase_from_resume_cursor(
                        step,
                        state,
                        baseline_session,
                        resume_cursor=attempt_resume_cursor,
                    )
                    phase_tracker.verifier_phase = verifier_phase
                    original_exc = _outcome_repair_original_exception(attempt_resume_cursor, step_name=step.name)
                    repaired_result = await self._try_repair_pair_verifier_outcome(
                        step=step,
                        context=context,
                        route_mode=route_mode,
                        exc=original_exc,
                        phase=verifier_phase,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        retry_feedback=active_retry_feedback,
                        route_handoff=route_handoff,
                        pending_handoffs=remaining_pending_handoffs,
                        resume_cursor=attempt_resume_cursor,
                    )
                    if repaired_result is not None:
                        return repaired_result
                    include_outcome_envelope = self._should_include_outcome_schema_feedback(
                        original_exc,
                        allowed_turn_kinds={"verifier"},
                    )
                    response_schema = (
                        self._pair_verifier_retry_response_schema(
                            step,
                            context,
                            attempt=attempt,
                            max_attempts=max_attempts,
                            retry_feedback=active_retry_feedback,
                            route_handoff=route_handoff,
                        )
                        if include_outcome_envelope
                        else None
                    )
                    next_feedback, annotated_exc = self._events.next_retry_feedback(
                        step,
                        original_exc,
                        attempt=attempt,
                        response_schema=response_schema,
                        include_outcome_envelope=include_outcome_envelope,
                    )
                    if next_feedback is None:
                        if annotated_exc is original_exc:
                            raise original_exc
                        raise annotated_exc from original_exc
                    verifier_retry_phase = verifier_phase
                    verifier_retry_feedback = next_feedback
                    pair_retry_feedback = None
                    continue
                pair_result = await self._run_pair_step_async(
                    step,
                    context,
                    state,
                    artifacts,
                    baseline_session,
                    route_mode=route_mode,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    retry_feedback=active_retry_feedback,
                    route_handoff=route_handoff,
                    consumed_pending_handoffs=remaining_pending_handoffs,
                    restorable_pending_handoffs=pending_handoffs,
                    resume_cursor=attempt_resume_cursor,
                    verifier_retry_phase=verifier_retry_phase,
                    phase_tracker=phase_tracker,
                )
                phase_tracker.verifier_phase = None
                if pair_result.direct_control is not None:
                    scheduled_handoffs = (
                        ()
                        if route_mode == "capture"
                        else self._routes.schedule_direct_control_handoffs(
                            remaining_pending_handoffs,
                            control=pair_result.direct_control,
                            context=context,
                            source_step=step.name,
                        )
                    )
                    return step_result_from_direct_control(
                        step=step,
                        state=pair_result.state or context.state,
                        control=pair_result.direct_control,
                        pending_handoffs=scheduled_handoffs,
                        producer_raw_output=pair_result.producer_raw_output,
                        verifier_raw_output=pair_result.verifier_raw_output,
                        provider_usage=pair_result.usage,
                    )
                if pair_result.short_circuit_event is not None:
                    finalization = self._complete_route(
                        route_mode=route_mode,
                        request=StepFinalizationRequest(
                            step=step,
                            context=context,
                            state=pair_result.state or context.state,
                            artifacts=self._artifacts.resolve_artifacts(context),
                            candidate_event=pair_result.short_circuit_event,
                            candidate_route_present=False,
                            after_subject=pair_result.short_circuit_event,
                            pending_handoffs=remaining_pending_handoffs,
                            error_cls=ProviderExecutionError,
                            provider_attributable=False,
                            source_hook=pair_result.source_hook,
                            source_phase=pair_result.source_phase,
                        ),
                    )
                    return step_result_from_route_finalization(
                        step=step,
                        route_finalization=finalization,
                        producer_raw_output=pair_result.producer_raw_output,
                        verifier_raw_output=pair_result.verifier_raw_output,
                        provider_usage=pair_result.usage,
                    )
                return self._finalize_pair_outcome_result(
                    step=step,
                    context=context,
                    route_mode=route_mode,
                    pair_result=pair_result,
                    pending_handoffs=remaining_pending_handoffs,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                repaired_result = await self._try_repair_pair_verifier_outcome(
                    step=step,
                    context=context,
                    route_mode=route_mode,
                    exc=exc,
                    phase=phase_tracker.verifier_phase,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    retry_feedback=active_retry_feedback,
                    route_handoff=route_handoff,
                    pending_handoffs=remaining_pending_handoffs,
                    resume_cursor=None,
                )
                if repaired_result is not None:
                    return repaired_result
                include_outcome_envelope = self._should_include_outcome_schema_feedback(
                    exc,
                    allowed_turn_kinds={"verifier"},
                )
                response_schema = (
                    self._pair_verifier_retry_response_schema(
                        step,
                        context,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        retry_feedback=active_retry_feedback,
                        route_handoff=route_handoff,
                    )
                    if include_outcome_envelope
                    else None
                )
                next_feedback, annotated_exc = self._events.next_retry_feedback(
                    step,
                    exc,
                    attempt=attempt,
                    response_schema=response_schema,
                    include_outcome_envelope=include_outcome_envelope,
                )
                if next_feedback is None:
                    if annotated_exc is exc:
                        raise
                    raise annotated_exc from exc
                if self._should_retry_pair_verifier_only(annotated_exc) and phase_tracker.verifier_phase is not None:
                    verifier_retry_phase = phase_tracker.verifier_phase
                    verifier_retry_feedback = next_feedback
                    pair_retry_feedback = None
                else:
                    verifier_retry_phase = None
                    verifier_retry_feedback = None
                    pair_retry_feedback = next_feedback
        raise AssertionError("pair-step retry loop exhausted without returning or raising")

    async def _execute_llm_step_async(
        self,
        step: PromptStepPlan,
        context: "Context",
        state: BaseModel,
        pending_handoffs: tuple["PendingHandoff", ...],
        *,
        route_mode: RouteMode,
        resume_cursor: dict[str, Any] | None = None,
    ) -> StepExecutionResult:
        baseline_session = self._sessions.resolve_session(step, context)
        route_handoff, remaining_pending_handoffs = self._routes.matching_pending_handoffs(step, context, pending_handoffs)
        retry_feedback: str | None = None
        max_attempts = step.turn.retry_policy.max_attempts
        start_attempt = _resume_cursor_attempt(resume_cursor) or 1
        for attempt in range(start_attempt, max_attempts + 1):
            artifacts = self._artifacts.resolve_artifacts(context)
            try:
                attempt_resume_cursor = resume_cursor if attempt == start_attempt else None
                if _resume_cursor_turn_kind(attempt_resume_cursor) == "outcome_repair":
                    original_exc = _outcome_repair_original_exception(attempt_resume_cursor, step_name=step.name)
                    repaired_result = await self._try_repair_llm_outcome(
                        step=step,
                        context=context,
                        state=state,
                        route_mode=route_mode,
                        artifacts=artifacts,
                        exc=original_exc,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        retry_feedback=retry_feedback,
                        route_handoff=route_handoff,
                        pending_handoffs=remaining_pending_handoffs,
                        resume_cursor=attempt_resume_cursor,
                    )
                    if repaired_result is not None:
                        return repaired_result
                    include_outcome_envelope = self._should_include_outcome_schema_feedback(
                        original_exc,
                        allowed_turn_kinds={"llm"},
                    )
                    response_schema = (
                        self._control_retry_response_schema(
                            step,
                            context,
                            artifacts,
                            attempt=attempt,
                            max_attempts=max_attempts,
                            retry_feedback=retry_feedback,
                            route_handoff=route_handoff,
                        )
                        if include_outcome_envelope
                        else None
                    )
                    next_feedback, annotated_exc = self._events.next_retry_feedback(
                        step,
                        original_exc,
                        attempt=attempt,
                        response_schema=response_schema,
                        include_outcome_envelope=include_outcome_envelope,
                    )
                    if next_feedback is None:
                        if annotated_exc is original_exc:
                            raise original_exc
                        raise annotated_exc from original_exc
                    retry_feedback = next_feedback
                    continue
                llm_result = await self._run_llm_step_async(
                    step,
                    context,
                    artifacts,
                    baseline_session,
                    route_mode=route_mode,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    retry_feedback=retry_feedback,
                    route_handoff=route_handoff,
                    consumed_pending_handoffs=remaining_pending_handoffs,
                    restorable_pending_handoffs=pending_handoffs,
                    resume_cursor=attempt_resume_cursor,
                )
                return self._finalize_llm_outcome_result(
                    step=step,
                    context=context,
                    state=state,
                    route_mode=route_mode,
                    llm_result=llm_result,
                    pending_handoffs=remaining_pending_handoffs,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                repaired_result = await self._try_repair_llm_outcome(
                    step=step,
                    context=context,
                    state=state,
                    route_mode=route_mode,
                    artifacts=artifacts,
                    exc=exc,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    retry_feedback=retry_feedback,
                    route_handoff=route_handoff,
                    pending_handoffs=remaining_pending_handoffs,
                )
                if repaired_result is not None:
                    return repaired_result
                include_outcome_envelope = self._should_include_outcome_schema_feedback(
                    exc,
                    allowed_turn_kinds={"llm"},
                )
                response_schema = (
                    self._control_retry_response_schema(
                        step,
                        context,
                        artifacts,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        retry_feedback=retry_feedback,
                        route_handoff=route_handoff,
                    )
                    if include_outcome_envelope
                    else None
                )
                next_feedback, annotated_exc = self._events.next_retry_feedback(
                    step,
                    exc,
                    attempt=attempt,
                    response_schema=response_schema,
                    include_outcome_envelope=include_outcome_envelope,
                )
                if next_feedback is None:
                    if annotated_exc is exc:
                        raise
                    raise annotated_exc from exc
                retry_feedback = next_feedback
        raise AssertionError("llm-step retry loop exhausted without returning or raising")

    async def _run_pair_step_async(
        self,
        step: ProduceVerifyStepPlan,
        context: "Context",
        state: BaseModel,
        artifacts: ResolvedArtifacts,
        session: "SessionBinding | None",
        *,
        route_mode: RouteMode,
        attempt: int,
        max_attempts: int,
        retry_feedback: str | None,
        route_handoff: str | None,
        consumed_pending_handoffs: tuple["PendingHandoff", ...],
        restorable_pending_handoffs: tuple["PendingHandoff", ...],
        resume_cursor: dict[str, Any] | None = None,
        verifier_retry_phase: PairVerifierPhase | None = None,
        phase_tracker: _PairAttemptPhaseTracker | None = None,
    ) -> PairProviderResult:
        del route_mode
        if verifier_retry_phase is not None:
            if phase_tracker is not None:
                phase_tracker.verifier_phase = verifier_retry_phase
            try:
                return await self._run_pair_verifier_turn_async(
                    step,
                    context,
                    verifier_retry_phase,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    retry_feedback=retry_feedback,
                    route_handoff=route_handoff,
                    restorable_pending_handoffs=restorable_pending_handoffs,
                    resume_cursor=resume_cursor,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                annotated_exc = self._events.annotate_execution_error(exc, pending_handoffs=consumed_pending_handoffs)
                if annotated_exc is exc:
                    raise
                raise annotated_exc from exc
        if _resume_cursor_turn_kind(resume_cursor) == "verifier":
            verifier_phase = self._pair_verifier_phase_from_resume_cursor(
                step,
                state,
                session,
                resume_cursor=resume_cursor,
            )
            if phase_tracker is not None:
                phase_tracker.verifier_phase = verifier_phase
            try:
                return await self._run_pair_verifier_turn_async(
                    step,
                    context,
                    verifier_phase,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    retry_feedback=retry_feedback,
                    route_handoff=route_handoff,
                    restorable_pending_handoffs=restorable_pending_handoffs,
                    resume_cursor=resume_cursor,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                annotated_exc = self._events.annotate_execution_error(exc, pending_handoffs=consumed_pending_handoffs)
                if annotated_exc is exc:
                    raise
                raise annotated_exc from exc

        producer_phase = await self._run_pair_producer_phase_async(
            step,
            context,
            state,
            artifacts,
            session,
            attempt=attempt,
            max_attempts=max_attempts,
            retry_feedback=retry_feedback,
            route_handoff=route_handoff,
            restorable_pending_handoffs=restorable_pending_handoffs,
            resume_cursor=resume_cursor,
        )
        if producer_phase.direct_control is not None or producer_phase.short_circuit_event is not None:
            return self._pair_result_from_producer_phase(producer_phase)

        try:
            verifier_phase_or_result = self._prepare_pair_verifier_phase(step, context, producer_phase)
            if isinstance(verifier_phase_or_result, PairProviderResult):
                return verifier_phase_or_result
            if phase_tracker is not None:
                phase_tracker.verifier_phase = verifier_phase_or_result
            return await self._run_pair_verifier_turn_async(
                step,
                context,
                attempt=attempt,
                phase=verifier_phase_or_result,
                max_attempts=max_attempts,
                retry_feedback=retry_feedback,
                route_handoff=route_handoff,
                restorable_pending_handoffs=restorable_pending_handoffs,
                resume_cursor=resume_cursor,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            annotated_exc = self._events.annotate_execution_error(exc, pending_handoffs=consumed_pending_handoffs)
            if annotated_exc is exc:
                raise
            raise annotated_exc from exc

    async def _run_pair_producer_phase_async(
        self,
        step: ProduceVerifyStepPlan,
        context: "Context",
        state: BaseModel,
        artifacts: ResolvedArtifacts,
        session: "SessionBinding | None",
        *,
        attempt: int,
        max_attempts: int,
        retry_feedback: str | None,
        route_handoff: str | None,
        restorable_pending_handoffs: tuple["PendingHandoff", ...],
        resume_cursor: dict[str, Any] | None,
    ) -> PairProducerPhaseResult:
        if _resume_cursor_turn_kind(resume_cursor) != "producer":
            before_producer_result = self._hook_runner.run_before(
                step,
                context,
                state,
                artifacts=artifacts,
                hook=step.before_producer_hook,
                hook_phase="before_producer",
            )
            producer_state = before_producer_result.state
            context._sync_state(producer_state)
            context._sync_artifacts(self._artifacts.resolve_artifacts(context))
            if before_producer_result.control is not None:
                direct_control = self._routes.normalize_direct_runtime_control(
                    step=step,
                    context=context,
                    control=before_producer_result.control,
                    hook_name=getattr(step.before_producer_hook, "__name__", type(step.before_producer_hook).__name__),
                    hook_phase="before_producer",
                )
                return PairProducerPhaseResult(
                    producer_raw_output=None,
                    producer_session=session,
                    producer_usage=None,
                    state=producer_state,
                    direct_control=direct_control,
                )
            if before_producer_result.event is not None:
                return PairProducerPhaseResult(
                    producer_raw_output=None,
                    producer_session=session,
                    producer_usage=None,
                    state=producer_state,
                    short_circuit_event=before_producer_result.event,
                    source_hook=getattr(step.before_producer_hook, "__name__", type(step.before_producer_hook).__name__),
                    source_phase="before_producer",
                )
        else:
            producer_state = state
            context._sync_state(producer_state)

        producer_prompt = self._providers.resolve_prompt(step.producer.prompt, context=context)
        if not _same_resume_attempt(resume_cursor, attempt, turn_kind="producer"):
            self._events.emit_provider_attempt_event(
                "provider_attempt_started",
                step=step,
                context=context,
                turn_kind="producer",
                attempt=attempt,
            )
        try:
            context._set_provider_attempt_checkpoint_data(
                _provider_checkpoint_data(
                    step=step,
                    context=context,
                    turn_kind="producer",
                    attempt=attempt,
                    max_attempts=max_attempts,
                )
            )
            producer_request = ProducerRequest(
                step_name=step.name,
                producer_prompt=producer_prompt,
                context=context,
                artifacts=artifacts,
                session=session,
                policy=_context_provider_policy(context),
                **self._provider_contract_builder.pair_producer_contract(
                    step,
                    context=context,
                    artifacts=artifacts,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    retry_feedback=retry_feedback,
                    route_handoff=route_handoff,
                ),
            )
            _checkpoint_provider_attempt(context)
            producer_response = await self._providers.run_producer(producer_request)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            annotated_exc = self._annotate_provider_turn_failure(exc, step_name=step.name, turn_kind="producer")
            if route_handoff is not None:
                annotated_exc = self._events.annotate_execution_error(
                    annotated_exc,
                    pending_handoffs=restorable_pending_handoffs,
                )
            self._events.emit_provider_attempt_failed(
                step=step,
                context=context,
                turn_kind="producer",
                attempt=attempt,
                exc=annotated_exc,
            )
            if annotated_exc is exc:
                raise
            raise annotated_exc from exc
        finally:
            context._set_provider_attempt_checkpoint_data(None)

        producer_exec = provider_exec_result(response=producer_response, text=producer_response.raw_output)
        self._events.emit_provider_attempt_finished(
            step=step,
            context=context,
            turn_kind="producer",
            attempt=attempt,
            token_usage=producer_exec.usage,
        )
        self._artifacts.append_logs(step, artifacts, producer_exec.text)
        if producer_exec.session is not None:
            self._sessions.persist_session(producer_exec.session, context=context)
        after_producer_result = self._hook_runner.run_after(
            step,
            context,
            state=producer_state,
            artifacts=self._artifacts.resolve_artifacts(context),
            subject=producer_exec.text,
            candidate_event=None,
            hook=step.after_producer_hook,
            hook_phase="after_producer",
        )
        next_state = after_producer_result.state
        context._sync_state(next_state)
        producer_session = producer_exec.session or session
        if after_producer_result.control is not None:
            direct_control = self._routes.normalize_direct_runtime_control(
                step=step,
                context=context,
                control=after_producer_result.control,
                hook_name=getattr(step.after_producer_hook, "__name__", type(step.after_producer_hook).__name__),
                hook_phase="after_producer",
            )
            return PairProducerPhaseResult(
                producer_raw_output=producer_exec.text,
                producer_session=producer_session,
                producer_usage=producer_exec.usage,
                state=next_state,
                direct_control=direct_control,
            )
        if after_producer_result.event is not None:
            return PairProducerPhaseResult(
                producer_raw_output=producer_exec.text,
                producer_session=producer_session,
                producer_usage=producer_exec.usage,
                state=next_state,
                short_circuit_event=after_producer_result.event,
                source_hook=getattr(step.after_producer_hook, "__name__", type(step.after_producer_hook).__name__),
                source_phase="after_producer",
            )
        return PairProducerPhaseResult(
            producer_raw_output=producer_exec.text,
            producer_session=producer_session,
            producer_usage=producer_exec.usage,
            state=next_state,
        )

    def _prepare_pair_verifier_phase(
        self,
        step: ProduceVerifyStepPlan,
        context: "Context",
        producer_phase: PairProducerPhaseResult,
    ) -> PairVerifierPhase | PairProviderResult:
        assert producer_phase.producer_raw_output is not None
        review_artifacts = self._artifacts.resolve_artifacts(context)
        context._sync_artifacts(review_artifacts)
        self._artifacts.ensure_named_artifacts_exist(step.verifier_requires, review_artifacts, step_name=step.name)
        before_verifier_result = self._hook_runner.run_before(
            step,
            context,
            producer_phase.state,
            artifacts=review_artifacts,
            hook=step.before_verifier_hook,
            hook_phase="before_verifier",
        )
        review_state = before_verifier_result.state
        context._sync_state(review_state)
        if before_verifier_result.control is not None:
            direct_control = self._routes.normalize_direct_runtime_control(
                step=step,
                context=context,
                control=before_verifier_result.control,
                hook_name=getattr(step.before_verifier_hook, "__name__", type(step.before_verifier_hook).__name__),
                hook_phase="before_verifier",
            )
            return PairProviderResult(
                producer_raw_output=producer_phase.producer_raw_output,
                verifier_raw_output=None,
                outcome=None,
                producer_session=producer_phase.producer_session,
                verifier_session=None,
                usage=StepProviderUsage(producer=producer_phase.producer_usage),
                state=review_state,
                direct_control=direct_control,
            )
        if before_verifier_result.event is not None:
            return PairProviderResult(
                producer_raw_output=producer_phase.producer_raw_output,
                verifier_raw_output=None,
                outcome=None,
                producer_session=producer_phase.producer_session,
                verifier_session=None,
                usage=StepProviderUsage(producer=producer_phase.producer_usage),
                state=review_state,
                short_circuit_event=before_verifier_result.event,
                source_hook=getattr(step.before_verifier_hook, "__name__", type(step.before_verifier_hook).__name__),
                source_phase="before_verifier",
            )
        return PairVerifierPhase(
            producer_raw_output=producer_phase.producer_raw_output,
            producer_session=producer_phase.producer_session,
            producer_usage=producer_phase.producer_usage,
            state=review_state,
        )

    async def _run_pair_verifier_turn_async(
        self,
        step: ProduceVerifyStepPlan,
        context: "Context",
        phase: PairVerifierPhase,
        *,
        attempt: int,
        max_attempts: int,
        retry_feedback: str | None,
        route_handoff: str | None,
        restorable_pending_handoffs: tuple["PendingHandoff", ...],
        resume_cursor: dict[str, Any] | None,
    ) -> PairProviderResult:
        context._sync_state(phase.state)
        review_artifacts = self._artifacts.resolve_artifacts(context)
        context._sync_artifacts(review_artifacts)
        self._artifacts.ensure_named_artifacts_exist(step.verifier_requires, review_artifacts, step_name=step.name)
        verifier_prompt = self._providers.resolve_prompt(step.verifier.prompt, context=context)
        verifier_session = self._sessions.resolve_pair_review_session(
            step,
            context,
            producer_session=phase.producer_session,
        )
        if not _same_resume_attempt(resume_cursor, attempt, turn_kind="verifier"):
            self._events.emit_provider_attempt_event(
                "provider_attempt_started",
                step=step,
                context=context,
                turn_kind="verifier",
                attempt=attempt,
            )
        try:
            context._set_provider_attempt_checkpoint_data(
                _provider_checkpoint_data(
                    step=step,
                    context=context,
                    turn_kind="verifier",
                    attempt=attempt,
                    max_attempts=max_attempts,
                    producer_raw_output=phase.producer_raw_output,
                    producer_session=phase.producer_session,
                    producer_usage=phase.producer_usage,
                )
            )
            verifier_request = VerifierRequest(
                step_name=step.name,
                verifier_prompt=verifier_prompt,
                producer_raw_output=phase.producer_raw_output,
                context=context,
                artifacts=review_artifacts,
                session=verifier_session,
                policy=_context_provider_policy(context),
                **self._provider_contract_builder.pair_verifier_contract(
                    step,
                    context=context,
                    artifacts=review_artifacts,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    retry_feedback=retry_feedback,
                    route_handoff=route_handoff,
                ),
            )
            _checkpoint_provider_attempt(context)
            verifier_response = await self._providers.run_verifier(verifier_request)
            self._providers.validate_outcome(step, verifier_response.outcome)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            annotated_exc = self._annotate_provider_turn_failure(exc, step_name=step.name, turn_kind="verifier")
            self._persist_failed_provider_session(annotated_exc, context=context)
            if route_handoff is not None:
                annotated_exc = self._events.annotate_execution_error(
                    annotated_exc,
                    pending_handoffs=restorable_pending_handoffs,
                )
            self._events.emit_provider_attempt_failed(
                step=step,
                context=context,
                turn_kind="verifier",
                attempt=attempt,
                exc=annotated_exc,
            )
            if annotated_exc is exc:
                raise
            raise annotated_exc from exc
        finally:
            context._set_provider_attempt_checkpoint_data(None)

        verifier_exec = provider_exec_result(
            response=verifier_response,
            text=verifier_response.outcome.raw_output,
        )
        self._events.emit_provider_attempt_finished(
            step=step,
            context=context,
            turn_kind="verifier",
            attempt=attempt,
            token_usage=verifier_exec.usage,
        )
        return PairProviderResult(
            producer_raw_output=phase.producer_raw_output,
            verifier_raw_output=verifier_exec.text,
            outcome=verifier_response.outcome,
            producer_session=phase.producer_session,
            verifier_session=verifier_exec.session or verifier_session,
            usage=StepProviderUsage(
                producer=phase.producer_usage,
                verifier=verifier_exec.usage,
            ),
            state=context.state,
        )

    @staticmethod
    def _pair_result_from_producer_phase(phase: PairProducerPhaseResult) -> PairProviderResult:
        return PairProviderResult(
            producer_raw_output=phase.producer_raw_output,
            verifier_raw_output=None,
            outcome=None,
            producer_session=phase.producer_session,
            verifier_session=None,
            usage=StepProviderUsage(producer=phase.producer_usage),
            state=phase.state,
            direct_control=phase.direct_control,
            short_circuit_event=phase.short_circuit_event,
            source_hook=phase.source_hook,
            source_phase=phase.source_phase,
        )

    def _pair_verifier_phase_from_resume_cursor(
        self,
        step: ProduceVerifyStepPlan,
        state: BaseModel,
        session: "SessionBinding | None",
        *,
        resume_cursor: dict[str, Any],
    ) -> PairVerifierPhase:
        producer_raw_output = resume_cursor.get("producer_raw_output")
        if not isinstance(producer_raw_output, str):
            raise WorkflowExecutionError(
                f"provider-attempt resume cursor for verifier step {step.name!r} is missing producer output"
            )
        producer_session = _session_binding_from_cursor(resume_cursor.get("producer_session")) or session
        producer_usage = _token_usage_from_cursor(resume_cursor.get("producer_usage"))
        return PairVerifierPhase(
            producer_raw_output=producer_raw_output,
            producer_session=producer_session,
            producer_usage=producer_usage,
            state=state,
        )

    async def _run_llm_step_async(
        self,
        step: PromptStepPlan,
        context: "Context",
        artifacts: ResolvedArtifacts,
        session: "SessionBinding | None",
        *,
        route_mode: RouteMode,
        attempt: int,
        max_attempts: int,
        retry_feedback: str | None,
        route_handoff: str | None,
        consumed_pending_handoffs: tuple["PendingHandoff", ...],
        restorable_pending_handoffs: tuple["PendingHandoff", ...],
        resume_cursor: dict[str, Any] | None = None,
    ) -> ProviderExecResult:
        prompt = self._providers.resolve_prompt(step.turn.prompt, context=context)
        if not _same_resume_attempt(resume_cursor, attempt, turn_kind="llm"):
            self._events.emit_provider_attempt_event(
                "provider_attempt_started",
                step=step,
                context=context,
                turn_kind="llm",
                attempt=attempt,
            )
        try:
            context._set_provider_attempt_checkpoint_data(
                _provider_checkpoint_data(
                    step=step,
                    context=context,
                    turn_kind="llm",
                    attempt=attempt,
                    max_attempts=max_attempts,
                )
            )
            llm_request = LLMRequest(
                step_name=step.name,
                prompt=prompt,
                context=context,
                artifacts=artifacts,
                session=session,
                policy=_context_provider_policy(context),
                **self._provider_contract_builder.control_contract(
                    step,
                    context=context,
                    artifacts=artifacts,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    retry_feedback=retry_feedback,
                    route_handoff=route_handoff,
                ),
            )
            _checkpoint_provider_attempt(context)
            response = await self._providers.run_llm(llm_request)
            self._providers.validate_outcome(step, response.outcome)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            annotated_exc = self._annotate_provider_turn_failure(exc, step_name=step.name, turn_kind="llm")
            self._persist_failed_provider_session(annotated_exc, context=context)
            if route_handoff is not None:
                annotated_exc = self._events.annotate_execution_error(
                    annotated_exc,
                    pending_handoffs=restorable_pending_handoffs,
                )
            self._events.emit_provider_attempt_failed(
                step=step,
                context=context,
                turn_kind="llm",
                attempt=attempt,
                exc=annotated_exc,
            )
            annotated_exc = self._events.annotate_execution_error(
                annotated_exc,
                pending_handoffs=consumed_pending_handoffs,
            )
            if annotated_exc is exc:
                raise
            raise annotated_exc from exc
        finally:
            context._set_provider_attempt_checkpoint_data(None)
        provider_exec = provider_exec_result(response=response, text=response.outcome.raw_output)
        self._events.emit_provider_attempt_finished(
            step=step,
            context=context,
            turn_kind="llm",
            attempt=attempt,
            token_usage=provider_exec.usage,
        )
        self._artifacts.append_logs(step, artifacts, provider_exec.text)
        resolved_session = provider_exec.session or session
        resolved_session_id = getattr(resolved_session, "session_id", None)
        return replace(
            provider_exec,
            session=resolved_session,
            session_id=resolved_session_id if isinstance(resolved_session_id, str) else None,
            outcome=response.outcome,
        )


def run_awaitable_sync(
    awaitable_factory: Callable[[], Awaitable[_T]],
    *,
    active_loop_error: str,
) -> _T:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable_factory())
    raise RuntimeError(active_loop_error)


class RouteFinalizer:
    """Owns step finalization entrypoints."""

    def __init__(
        self,
        services: ExecutionServices,
        *,
        artifact_inventory: "Mapping[str, Any]",
    ) -> None:
        if services.artifacts is None:
            raise ValueError("RouteFinalizer requires ExecutionServices.artifacts")
        if services.routes is None:
            raise ValueError("RouteFinalizer requires ExecutionServices.routes")
        if services.hooks is None:
            raise ValueError("RouteFinalizer requires ExecutionServices.hooks")
        if services.state is None:
            raise ValueError("RouteFinalizer requires ExecutionServices.state")
        self._artifacts = services.artifacts
        self._routes = services.routes
        self._hooks = services.hooks
        self._state = services.state
        self._artifact_inventory = dict(artifact_inventory)

    def _route_decision_for_route(
        self,
        *,
        route: RouteContract,
        result: _StepRouteResult,
    ) -> RouteDecision:
        return RouteDecision(
            final_route=result.final_route,
            contract=route,
            action=route_action_for_contract(
                route,
                pending_input=result.pending_input,
            ),
            runtime_control=result.runtime_control,
            pending_handoffs=result.scheduled_handoffs,
            provider_attributable=result.provider_attributable,
            source_hook=result.source_hook,
            source_phase=result.source_phase,
        )

    @staticmethod
    def _route_decision_for_direct_control(result: _StepRouteResult) -> RouteDecision:
        return RouteDecision(
            final_route=result.final_route,
            contract=None,
            action=_route_action_from_direct_control(result),
            runtime_control=result.runtime_control,
            pending_handoffs=result.scheduled_handoffs,
            provider_attributable=result.provider_attributable,
            source_hook=result.source_hook,
            source_phase=result.source_phase,
        )

    def capture(self, request: StepFinalizationRequest) -> _StepRouteResult:
        step = request.step
        context = request.context
        candidate_event = request.candidate_event
        try:
            self._routes.validate_event(
                step,
                candidate_event,
                provider_attributable=request.provider_attributable,
                error_cls=request.error_cls,
            )
        except WorkflowExecutionError as exc:
            annotated = self._routes.annotate_execution_error(
                exc,
                checkpoint_state=request.state,
                failure_context=FailureContext(
                    kind="route_validation",
                    step_name=step.name,
                    candidate_route=candidate_event.tag,
                    details={"error": str(exc), "error_type": type(exc).__name__},
                ),
            )
            if annotated is exc:
                raise
            raise annotated from exc

        candidate_route = request.candidate_route if request.candidate_route_present else None
        after_result = self._hooks.run_after(
            step,
            context,
            state=request.state,
            artifacts=request.artifacts,
            subject=request.after_subject,
            candidate_event=candidate_event,
            hook=request.after_hook,
            hook_phase=request.after_hook_phase,
        )
        final_state = after_result.state
        final_event = after_result.event or candidate_event
        explicit_event_override = after_result.explicit_event_override
        after_redirect = after_result.redirect
        context._sync_state(final_state)
        finalized_artifacts = self._artifacts.resolve_artifacts(context)
        context._sync_artifacts(finalized_artifacts)
        route_redirects: list[HookRouteRedirect] = []
        final_source_hook = request.source_hook
        final_source_phase = request.source_phase
        if after_redirect is not None:
            route_redirects.append(replace(after_redirect, redirect_index=len(route_redirects) + 1))
            self._routes.ensure_hook_redirect_limit(step, candidate_route=candidate_route, redirects=route_redirects)
            final_source_hook = after_redirect.hook
            final_source_phase = after_redirect.phase

        if after_result.control is not None:
            direct_control = self._routes.normalize_direct_runtime_control(
                step=step,
                context=context,
                control=after_result.control,
                hook_name=getattr(request.after_hook or step.after_hook, "__name__", type(request.after_hook or step.after_hook).__name__),
                hook_phase=request.after_hook_phase,
            )
            result = _StepRouteResult(
                state=final_state,
                destination=direct_control.destination,
                finalized_event=None,
                candidate_route=candidate_route,
                final_route=None,
                runtime_control=direct_control.control,
                target_step=direct_control.target_step,
                terminal=direct_control.terminal,
                pending_input=direct_control.pending_input,
                source_hook=direct_control.source_hook,
                source_phase=direct_control.source_phase,
                provider_attributable=False,
                hook_route_override_from=route_redirects[0].from_route if route_redirects else None,
                hook_route_override_to=route_redirects[-1].to_route if route_redirects else None,
                hook_route_redirects=tuple(route_redirects),
                scheduled_handoffs=(),
            )
            return replace(result, decision=self._route_decision_for_direct_control(result))

        try:
            final_route = self._routes.compiled_route_for_step(step, final_event.tag)
        except Exception as exc:
            context._sync_route(None)
            context._sync_event(None)
            context._sync_outcome(None)
            annotated = self._routes.annotate_execution_error(
                exc,
                checkpoint_state=self._state.clone_state(context.state),
            )
            if annotated is exc:
                raise
            raise annotated from exc

        context._sync_route(
            {
                "tag": final_event.tag,
                "target": route_target_value(final_route.target),
                "summary": final_route.summary,
                "handoff": final_route.handoff,
            }
        )
        context._sync_event(self._routes.event_context_payload(final_event))
        context._sync_outcome(request.after_subject)

        final_provider_attributable = request.provider_attributable and not explicit_event_override
        final_error_cls = request.error_cls if final_provider_attributable else WorkflowExecutionError
        self._artifacts.enforce_artifact_contracts(
            step,
            context,
            finalized_artifacts,
            route_tag=final_event.tag,
            state=final_state,
            error_cls=final_error_cls,
            provider_attributable=final_provider_attributable,
        )
        destination = route_target_value(final_route.target)
        pending_input = (
            self._routes.pending_input_from_event(source_step=step.name, event=final_event)
            if destination == AWAIT_INPUT
            else None
        )
        self._state.update_final_step_runtime_state(step, getattr(context, "_step_state", None), final_event)
        self._state.update_final_step_runtime_state(step, getattr(context, "_step_item_state", None), final_event)
        self._state.update_final_item_runtime_state(getattr(context, "_item_state", None), final_event)
        result = _StepRouteResult(
            state=final_state,
            destination=destination,
            finalized_event=final_event,
            candidate_route=candidate_route,
            final_route=final_event.tag,
            runtime_control=None,
            target_step=None,
            terminal=None,
            pending_input=pending_input,
            source_hook=final_source_hook,
            source_phase=final_source_phase,
            provider_attributable=final_provider_attributable,
            hook_route_override_from=route_redirects[0].from_route if route_redirects else None,
            hook_route_override_to=route_redirects[-1].to_route if route_redirects else None,
            hook_route_redirects=tuple(route_redirects),
            scheduled_handoffs=(),
        )
        return replace(result, decision=self._route_decision_for_route(route=final_route, result=result))

    def finalize_result(self, request: StepFinalizationRequest) -> _StepRouteResult:
        step = request.step
        context = request.context
        candidate_event = request.candidate_event
        try:
            self._routes.validate_event(
                step,
                candidate_event,
                provider_attributable=request.provider_attributable,
                error_cls=request.error_cls,
            )
        except WorkflowExecutionError as exc:
            annotated = self._routes.annotate_execution_error(
                exc,
                checkpoint_state=request.state,
                failure_context=FailureContext(
                    kind="route_validation",
                    step_name=step.name,
                    candidate_route=candidate_event.tag,
                    details={"error": str(exc), "error_type": type(exc).__name__},
                ),
            )
            if annotated is exc:
                raise
            raise annotated from exc

        candidate_route = request.candidate_route if request.candidate_route_present else None
        after_result = self._hooks.run_after(
            step,
            context,
            state=request.state,
            artifacts=request.artifacts,
            subject=request.after_subject,
            candidate_event=candidate_event,
            hook=request.after_hook,
            hook_phase=request.after_hook_phase,
        )
        final_state = after_result.state
        final_event = after_result.event or candidate_event
        explicit_event_override = after_result.explicit_event_override
        after_redirect = after_result.redirect
        context._sync_state(final_state)
        finalized_artifacts = self._artifacts.resolve_artifacts(context)
        context._sync_artifacts(finalized_artifacts)
        route_redirects: list[HookRouteRedirect] = []
        final_source_hook = request.source_hook
        final_source_phase = request.source_phase
        if after_redirect is not None:
            route_redirects.append(replace(after_redirect, redirect_index=len(route_redirects) + 1))
            self._routes.ensure_hook_redirect_limit(step, candidate_route=candidate_route, redirects=route_redirects)
            final_source_hook = after_redirect.hook
            final_source_phase = after_redirect.phase

        if after_result.control is not None:
            direct_control = self._routes.normalize_direct_runtime_control(
                step=step,
                context=context,
                control=after_result.control,
                hook_name=getattr(request.after_hook or step.after_hook, "__name__", type(request.after_hook or step.after_hook).__name__),
                hook_phase=request.after_hook_phase,
            )
            scheduled_handoffs = self._routes.schedule_direct_control_handoffs(
                request.pending_handoffs,
                control=direct_control,
                context=context,
                source_step=step.name,
            )
            result = _StepRouteResult(
                state=final_state,
                destination=direct_control.destination,
                finalized_event=None,
                candidate_route=candidate_route,
                final_route=None,
                runtime_control=direct_control.control,
                target_step=direct_control.target_step,
                terminal=direct_control.terminal,
                pending_input=direct_control.pending_input,
                source_hook=direct_control.source_hook,
                source_phase=direct_control.source_phase,
                provider_attributable=False,
                hook_route_override_from=route_redirects[0].from_route if route_redirects else None,
                hook_route_override_to=route_redirects[-1].to_route if route_redirects else None,
                hook_route_redirects=tuple(route_redirects),
                scheduled_handoffs=scheduled_handoffs,
            )
            return replace(result, decision=self._route_decision_for_direct_control(result))

        final_route: RouteContract
        try:
            while True:
                final_route = self._routes.compiled_route_for_step(step, final_event.tag)
                context._sync_route(
                    {
                        "tag": final_event.tag,
                        "target": route_target_value(final_route.target),
                        "summary": final_route.summary,
                        "handoff": final_route.handoff,
                    }
                )
                context._sync_event(self._routes.event_context_payload(final_event))
                context._sync_outcome(request.after_subject)
                route_result = self._hooks.run_route(
                    step,
                    context,
                    final_state,
                    finalized_artifacts,
                    event=final_event,
                    hook=final_route.on_taken,
                    hook_phase="on_taken",
                )
                final_state = route_result.state
                if route_result.event is not None:
                    final_event = route_result.event
                explicit_event_override = explicit_event_override or route_result.explicit_event_override
                context._sync_state(final_state)
                route_redirect = route_result.redirect
                if route_redirect is not None:
                    route_redirects.append(replace(route_redirect, redirect_index=len(route_redirects) + 1))
                    self._routes.ensure_hook_redirect_limit(step, candidate_route=candidate_route, redirects=route_redirects)
                    final_source_hook = route_redirect.hook
                    final_source_phase = route_redirect.phase
                    continue
                if route_result.control is not None:
                    finalized_artifacts = self._artifacts.resolve_artifacts(context)
                    context._sync_artifacts(finalized_artifacts)
                    final_provider_attributable = request.provider_attributable and not explicit_event_override
                    final_error_cls = request.error_cls if final_provider_attributable else WorkflowExecutionError
                    self._artifacts.enforce_artifact_contracts(
                        step,
                        context,
                        finalized_artifacts,
                        route_tag=final_event.tag,
                        state=final_state,
                        error_cls=final_error_cls,
                        provider_attributable=final_provider_attributable,
                    )
                    direct_control = self._routes.normalize_direct_runtime_control(
                        step=step,
                        context=context,
                        control=route_result.control,
                        hook_name=getattr(final_route.on_taken, "__name__", type(final_route.on_taken).__name__),
                        hook_phase="on_taken",
                    )
                    scheduled_handoffs = self._routes.schedule_direct_control_handoffs(
                        request.pending_handoffs,
                        control=direct_control,
                        context=context,
                        source_step=step.name,
                    )
                    result = _StepRouteResult(
                        state=final_state,
                        destination=direct_control.destination,
                        finalized_event=None,
                        candidate_route=candidate_route,
                        final_route=None,
                        runtime_control=direct_control.control,
                        target_step=direct_control.target_step,
                        terminal=direct_control.terminal,
                        pending_input=direct_control.pending_input,
                        source_hook=direct_control.source_hook,
                        source_phase=direct_control.source_phase,
                        provider_attributable=False,
                        hook_route_override_from=route_redirects[0].from_route if route_redirects else None,
                        hook_route_override_to=route_redirects[-1].to_route if route_redirects else None,
                        hook_route_redirects=tuple(route_redirects),
                        scheduled_handoffs=scheduled_handoffs,
                    )
                    return replace(result, decision=self._route_decision_for_direct_control(result))
                break
        except Exception as exc:
            context._sync_route(None)
            context._sync_event(None)
            context._sync_outcome(None)
            annotated = self._routes.annotate_execution_error(
                exc,
                checkpoint_state=self._state.clone_state(context.state),
            )
            if annotated is exc:
                raise
            raise annotated from exc

        final_provider_attributable = request.provider_attributable and not explicit_event_override
        final_error_cls = request.error_cls if final_provider_attributable else WorkflowExecutionError
        self._artifacts.enforce_artifact_contracts(
            step,
            context,
            finalized_artifacts,
            route_tag=final_event.tag,
            state=final_state,
            error_cls=final_error_cls,
            provider_attributable=final_provider_attributable,
        )
        destination = route_target_value(final_route.target)
        pending_input = (
            self._routes.pending_input_from_event(source_step=step.name, event=final_event)
            if destination == AWAIT_INPUT
            else None
        )
        self._state.update_final_step_runtime_state(step, getattr(context, "_step_state", None), final_event)
        self._state.update_final_step_runtime_state(step, getattr(context, "_step_item_state", None), final_event)
        self._state.update_final_item_runtime_state(getattr(context, "_item_state", None), final_event)
        result = _StepRouteResult(
            state=final_state,
            destination=destination,
            finalized_event=final_event,
            candidate_route=candidate_route,
            final_route=final_event.tag,
            runtime_control=None,
            target_step=None,
            terminal=None,
            pending_input=pending_input,
            source_hook=final_source_hook,
            source_phase=final_source_phase,
            provider_attributable=final_provider_attributable,
            hook_route_override_from=route_redirects[0].from_route if route_redirects else None,
            hook_route_override_to=route_redirects[-1].to_route if route_redirects else None,
            hook_route_redirects=tuple(route_redirects),
            scheduled_handoffs=self._routes.schedule_route_handoffs(
                request.pending_handoffs,
                route=final_route,
                event=final_event,
                destination=destination,
                context=context,
                source_step=step.name,
            ),
        )
        return replace(result, decision=self._route_decision_for_route(route=final_route, result=result))

    def finalize(self, request: StepFinalizationRequest) -> RouteDecision:
        return self.finalize_result(request).decision


class HookRunner:
    """Owns hook execution entrypoints."""

    def __init__(self, services: ExecutionServices) -> None:
        if services.routes is None:
            raise ValueError("HookRunner requires ExecutionServices.routes")
        if services.events is None:
            raise ValueError("HookRunner requires ExecutionServices.events")
        if services.state is None:
            raise ValueError("HookRunner requires ExecutionServices.state")
        self._routes = services.routes
        self._events = services.events
        self._state = services.state

    def run_before(
        self,
        step: StepPlan,
        context: "Context",
        state: BaseModel,
        *,
        artifacts: ResolvedArtifacts,
        hook: Callable[..., Any] | None = None,
        hook_phase: str = "before",
    ) -> HookExecutionResult:
        hook = step.before_hook if hook is None else hook
        if hook is None:
            return HookExecutionResult(state=state)
        hook_name = getattr(hook, "__name__", type(hook).__name__)
        self._events.emit_hook_event("hook_started", step=step, context=context, hook_name=hook_name, phase=hook_phase)
        try:
            context._sync_state(state)
            context._sync_artifacts(artifacts)
            context._sync_route(None)
            context._sync_event(None)
            context._sync_outcome(None)
            invocation_id = f"{step.name}:{hook_phase}:{hook_name}"
            context._set_execution_source(
                hook_name=hook_name,
                phase=hook_phase,
                invocation_id=invocation_id,
            )
            try:
                result = hook(context)
            finally:
                context._set_execution_source(hook_name=None, phase=None, invocation_id=None)
            next_state = context.state
            hook_result = self.normalize_result(
                step,
                state=next_state,
                context=context,
                current_event=None,
                result=result,
                hook_phase=hook_phase,
                hook_name=hook_name,
            )
            self._events.emit_hook_event(
                "hook_finished",
                step=step,
                context=context,
                hook_name=hook_name,
                phase=hook_phase,
                route=hook_result.event.tag if hook_result.event is not None else None,
            )
            return hook_result
        except Exception as exc:
            self._events.emit_hook_event(
                "hook_failed",
                step=step,
                context=context,
                hook_name=hook_name,
                phase=hook_phase,
                error=str(exc),
            )
            annotated = self._events.annotate_execution_error(
                exc,
                checkpoint_state=self._state.clone_state(context.state),
                failure_context=FailureContext(
                    kind="hook_failure",
                    step_name=step.name,
                    source_hook=hook_name,
                    source_phase=hook_phase,
                    details={"error": str(exc), "error_type": type(exc).__name__},
                ),
            )
            if annotated is exc:
                raise
            raise annotated from exc

    def run_after(
        self,
        step: StepPlan,
        context: "Context",
        *,
        state: BaseModel,
        artifacts: ResolvedArtifacts,
        subject: Any,
        candidate_event: Event | None,
        hook: Callable[..., Any] | None = None,
        hook_phase: str = "after",
    ) -> HookExecutionResult:
        hook = step.after_hook if hook is None else hook
        if hook is None:
            return HookExecutionResult(state=state)
        hook_name = getattr(hook, "__name__", type(hook).__name__)
        self._events.emit_hook_event(
            "hook_started",
            step=step,
            context=context,
            hook_name=hook_name,
            phase=hook_phase,
            route=None if candidate_event is None else candidate_event.tag,
        )
        try:
            context._sync_state(state)
            context._sync_artifacts(artifacts)
            if candidate_event is not None:
                compiled_route = self._routes.compiled_route_for_step(step, candidate_event.tag)
                context._sync_route(
                    {
                        "tag": candidate_event.tag,
                        "target": route_target_value(compiled_route.target),
                        "summary": compiled_route.summary,
                        "handoff": compiled_route.handoff,
                    }
                )
                context._sync_event(self._routes.event_context_payload(candidate_event))
            else:
                context._sync_route(None)
                context._sync_event(None)
            context._sync_outcome(subject)
            invocation_id = f"{step.name}:{hook_phase}:{hook_name}"
            context._set_execution_source(
                hook_name=hook_name,
                phase=hook_phase,
                invocation_id=invocation_id,
            )
            try:
                result = hook(context)
            finally:
                context._set_execution_source(hook_name=None, phase=None, invocation_id=None)
            next_state = context.state
            hook_result = self.normalize_result(
                step,
                state=next_state,
                context=context,
                current_event=candidate_event,
                result=result,
                hook_phase=hook_phase,
                hook_name=hook_name,
            )
            self._events.emit_hook_event(
                "hook_finished",
                step=step,
                context=context,
                hook_name=hook_name,
                phase=hook_phase,
                route=hook_result.event.tag if hook_result.event is not None else None if candidate_event is None else candidate_event.tag,
            )
            return hook_result
        except Exception as exc:
            self._events.emit_hook_event(
                "hook_failed",
                step=step,
                context=context,
                hook_name=hook_name,
                phase=hook_phase,
                route=None if candidate_event is None else candidate_event.tag,
                error=str(exc),
            )
            annotated = self._events.annotate_execution_error(
                exc,
                checkpoint_state=self._state.clone_state(context.state),
                failure_context=FailureContext(
                    kind="hook_failure",
                    step_name=step.name,
                    candidate_route=None if candidate_event is None else candidate_event.tag,
                    source_hook=hook_name,
                    source_phase=hook_phase,
                    details={"error": str(exc), "error_type": type(exc).__name__},
                ),
            )
            if annotated is exc:
                raise
            raise annotated from exc

    def normalize_result(
        self,
        step: StepPlan,
        *,
        state: BaseModel,
        context: "Context",
        current_event: Event | None,
        result: Any,
        hook_phase: str,
        hook_name: str,
    ) -> HookExecutionResult:
        next_event = current_event
        if result is None:
            return HookExecutionResult(state=state)
        if isinstance(result, BaseModel):
            raise WorkflowExecutionError(
                f"{hook_phase} hook for step {step.name!r} returned unsupported value {type(result)!r}"
            )
        if isinstance(result, Effects):
            override = self._apply_effects(
                step,
                context=context,
                effects=result,
                hook_phase=hook_phase,
            )
            if override is None:
                return HookExecutionResult(state=state)
            return self.normalize_result(
                step,
                state=state,
                context=context,
                current_event=current_event,
                result=override,
                hook_phase=hook_phase,
                hook_name=hook_name,
            )
        if isinstance(result, WorklistEffect):
            return self.normalize_result(
                step,
                state=state,
                context=context,
                current_event=current_event,
                result=Effects(worklists=(result,)),
                hook_phase=hook_phase,
                hook_name=hook_name,
            )
        if isinstance(result, str):
            if result in {FINISH, FAIL}:
                normalized = HookResult(control=cast(HookTerminalControl, result))
                return HookExecutionResult(
                    state=state,
                    control=normalized.control,
                )
            override_event = self._routes.validate_hook_event_override(
                step,
                Event(
                    tag=result,
                    reason=None if next_event is None else next_event.reason,
                    question=None if next_event is None else next_event.question,
                    handoff=None if next_event is None else next_event.handoff,
                ),
            )
            redirect_record = None
            if next_event is not None:
                redirect_record = self._routes.build_hook_redirect_record(
                    step=step,
                    context=context,
                    hook_name=hook_name,
                    hook_phase=hook_phase,
                    previous_event=next_event,
                    next_event=override_event,
                )
            normalized = HookResult(event=override_event)
            return HookExecutionResult(
                state=state,
                event=normalized.event,
                explicit_event_override=True,
                redirect=redirect_record,
            )
        if isinstance(result, Event):
            override_event = self._routes.validate_hook_event_override(step, result)
            redirect_record = None
            if next_event is not None:
                redirect_record = self._routes.build_hook_redirect_record(
                    step=step,
                    context=context,
                    hook_name=hook_name,
                    hook_phase=hook_phase,
                    previous_event=next_event,
                    next_event=override_event,
                )
            normalized = HookResult(event=override_event)
            return HookExecutionResult(
                state=state,
                event=normalized.event,
                explicit_event_override=True,
                redirect=redirect_record,
            )
        if isinstance(result, (RequestInput, Goto, Fail)):
            normalized = HookResult(control=result)
            return HookExecutionResult(
                state=state,
                control=normalized.control,
            )
        raise WorkflowExecutionError(f"{hook_phase} hook for step {step.name!r} returned unsupported value {type(result)!r}")

    def _apply_effects(
        self,
        step: StepPlan,
        *,
        context: "Context",
        effects: Effects,
        hook_phase: str,
    ) -> Any:
        exhausted_override: Any = None
        for effect in effects.worklists:
            if effect.refresh:
                self._worklist_view_for_effect(
                    step,
                    context=context,
                    worklist_name=effect.worklist,
                    hook_phase=hook_phase,
                ).refresh()
        for effect in effects.worklists:
            if effect.set_current_status is not None:
                self._worklist_view_for_effect(
                    step,
                    context=context,
                    worklist_name=effect.worklist,
                    hook_phase=hook_phase,
                ).set_current_status(effect.set_current_status)
            elif effect.reset_current_status:
                self._worklist_view_for_effect(
                    step,
                    context=context,
                    worklist_name=effect.worklist,
                    hook_phase=hook_phase,
                ).reset_current_status()
        for effect in effects.worklists:
            if not effect.advance:
                continue
            exhausted = self._worklist_view_for_effect(
                step,
                context=context,
                worklist_name=effect.worklist,
                hook_phase=hook_phase,
            ).advance_or(effect.exhausted)
            if exhausted is not None and exhausted_override is None:
                exhausted_override = exhausted
        if effects.event is not None:
            return effects.event
        return exhausted_override

    def _worklist_view_for_effect(
        self,
        step: StepPlan,
        *,
        context: "Context",
        worklist_name: str | None,
        hook_phase: str,
    ):
        if worklist_name is None:
            try:
                return context.current_worklist
            except WorkflowExecutionError as exc:
                raise WorkflowExecutionError(
                    f"{hook_phase} hook for step {step.name!r} returned a worklist effect without an active worklist"
                ) from exc
        return context.worklist(worklist_name)

    def run_route(
        self,
        step: StepPlan,
        context: "Context",
        state: BaseModel,
        artifacts: ResolvedArtifacts,
        *,
        event: Event,
        hook: Callable[..., Any] | None = None,
        hook_phase: str = "on_taken",
    ) -> HookExecutionResult:
        if hook is None:
            return HookExecutionResult(state=state)
        hook_name = getattr(hook, "__name__", type(hook).__name__)
        self._events.emit_hook_event(
            "hook_started",
            step=step,
            context=context,
            hook_name=hook_name,
            phase=hook_phase,
            route=event.tag,
        )
        try:
            context._sync_state(state)
            context._sync_artifacts(artifacts)
            compiled_route = self._routes.compiled_route_for_step(step, event.tag)
            context._sync_route(
                {
                    "tag": event.tag,
                    "target": route_target_value(compiled_route.target),
                    "summary": compiled_route.summary,
                    "handoff": compiled_route.handoff,
                }
            )
            context._sync_event(self._routes.event_context_payload(event))
            invocation_id = f"{step.name}:{hook_phase}:{hook_name}"
            context._set_execution_source(
                hook_name=hook_name,
                phase=hook_phase,
                invocation_id=invocation_id,
            )
            try:
                result = hook(context)
            finally:
                context._set_execution_source(hook_name=None, phase=None, invocation_id=None)
            next_state = context.state
            hook_result = self.normalize_result(
                step,
                state=next_state,
                context=context,
                current_event=event,
                result=result,
                hook_phase=hook_phase,
                hook_name=hook_name,
            )
            self._events.emit_hook_event(
                "hook_finished",
                step=step,
                context=context,
                hook_name=hook_name,
                phase=hook_phase,
                route=hook_result.event.tag if hook_result.event is not None else event.tag,
            )
            return hook_result
        except Exception as exc:
            self._events.emit_hook_event(
                "hook_failed",
                step=step,
                context=context,
                hook_name=hook_name,
                phase=hook_phase,
                route=event.tag,
                error=str(exc),
            )
            annotated = self._events.annotate_execution_error(
                exc,
                checkpoint_state=self._state.clone_state(context.state),
                failure_context=FailureContext(
                    kind="hook_failure",
                    step_name=step.name,
                    candidate_route=event.tag,
                    source_hook=hook_name,
                    source_phase=hook_phase,
                    details={"error": str(exc), "error_type": type(exc).__name__},
                ),
            )
            if annotated is exc:
                raise
            raise annotated from exc


class ArtifactGuard:
    """Owns artifact contract enforcement entrypoints."""

    def __init__(self, services: ExecutionServices) -> None:
        if services.artifacts is None:
            raise ValueError("ArtifactGuard requires ExecutionServices.artifacts")
        self._artifacts = services.artifacts

    def enforce(self, *args: Any, **kwargs: Any) -> None:
        self._artifacts.enforce_artifact_contracts(*args, **kwargs)


class StateRuntime:
    """Owns worklist selection state helpers."""

    def __init__(self, services: ExecutionServices) -> None:
        if services.state is None:
            raise ValueError("StateRuntime requires ExecutionServices.state")
        self._state = services.state

    def restore_worklist_selections(
        self,
        context: "Context",
        snapshots: "Mapping[str, SelectionSnapshot]",
    ) -> dict[str, "SelectionSnapshot"]:
        return self._state.restore_worklist_selections(context, snapshots)

    def ensure_worklist_selection(
        self,
        context: "Context",
        worklist_name: str,
    ) -> "Selection[Any]":
        return self._state.ensure_worklist_selection(context, worklist_name)


class SessionRuntime:
    """Owns session-store state transitions."""

    def __init__(self, services: ExecutionServices) -> None:
        if services.sessions is None:
            raise ValueError("SessionRuntime requires ExecutionServices.sessions")
        self._sessions = services.sessions

    def restore(self, snapshot: Any) -> None:
        self._sessions.restore(snapshot)

    def snapshot(self) -> Any:
        return self._sessions.snapshot()


class CheckpointManager:
    """Owns checkpoint persistence entrypoints."""

    def __init__(self, services: ExecutionServices) -> None:
        if services.checkpoints is None:
            raise ValueError("CheckpointManager requires ExecutionServices.checkpoints")
        self._checkpoints = services.checkpoints

    def save(self, *args: Any, **kwargs: Any) -> Any:
        return self._checkpoints.save(*args, **kwargs)


class OperationRecorder:
    """Owns operation-runtime binding for step execution."""

    def __init__(self, services: ExecutionServices) -> None:
        if services.operations is None:
            raise ValueError("OperationRecorder requires ExecutionServices.operations")
        self._operations = services.operations

    @contextmanager
    def bind_step(
        self,
        *,
        step: StepPlan,
        context: "Context",
        run_folder: "Path",
        step_name: str,
        step_visit: int,
    ):
        with self._operations.bind_step(
            step=step,
            context=context,
            run_folder=run_folder,
            step_name=step_name,
            step_visit=step_visit,
        ) as runtime:
            yield runtime

    def set_provider_policy_resolver(self, resolver: Any) -> None:
        self._operations.set_provider_policy_resolver(resolver)


def _context_provider_policy(context: "Context") -> object | None:
    return getattr(context, "_provider_policy", None)


class WorkflowInvoker:
    """Owns child-workflow invocation entrypoints."""

    def __init__(self, services: ExecutionServices) -> None:
        if services.child_workflows is None:
            raise ValueError("WorkflowInvoker requires ExecutionServices.child_workflows")
        self._child_workflows = services.child_workflows

    def run_child_step(self, step: StepPlan, context: "Context") -> Any:
        return self._child_workflows.run_child_step(step, context)
