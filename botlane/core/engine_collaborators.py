"""Focused engine collaborators extracted from the monolithic engine."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal, TypeVar

from pydantic import BaseModel

from .artifacts import ResolvedArtifacts
from .effects import Effects, WorklistEffect
from .errors import FailureContext, ProviderExecutionError, WorkflowExecutionError
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
from .providers.models import (
    LLMRequest,
    ProducerRequest,
    ProviderArtifactRef,
    ProviderReadableRef,
    ProviderRoute,
    StepProviderUsage,
    TokenUsage,
    VerifierRequest,
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
from .stores.protocols import PendingHandoff, PendingInput, SessionBinding

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from .context import Context
    from .engine import StepFinalizationRecord
    from .worklists import Selection, SelectionSnapshot


@dataclass(frozen=True, slots=True)
class HookResult:
    event: Event | None = None
    control: RequestInput | Goto | Fail | None = None


@dataclass(frozen=True, slots=True)
class HookExecutionResult:
    state: BaseModel
    event: Event | None = None
    control: RequestInput | Goto | Fail | None = None
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
class ProviderExecResult:
    text: str
    session_id: str | None
    provider_metadata: dict[str, object]
    usage: TokenUsage | None = None
    session: "SessionBinding | None" = None
    outcome: Outcome | None = None


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
        if step.scope_name is not None:
            context.ensure_selection(step.scope_name)
        initial_artifacts = self._artifacts.resolve_artifacts(context)
        context._sync_artifacts(initial_artifacts)
        self._artifacts.ensure_required_artifacts(step, initial_artifacts)
        if isinstance(step, ProduceVerifyStepPlan):
            return await self._execute_pair_step_async(step, context, state, pending_handoffs, route_mode=route_mode)
        from .step_plans import BranchGroupStepPlan, ChildWorkflowStepPlan, PythonStepPlan

        if isinstance(step, BranchGroupStepPlan):
            if route_mode != "finalize":
                raise WorkflowExecutionError("branch-group composite steps do not support capture mode")
            return await self._branch_group_runtime.run_async(step, context, state, pending_handoffs)

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
            return await self._execute_llm_step_async(step, context, state, pending_handoffs, route_mode=route_mode)
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

    async def _execute_pair_step_async(
        self,
        step: ProduceVerifyStepPlan,
        context: "Context",
        state: BaseModel,
        pending_handoffs: tuple["PendingHandoff", ...],
        *,
        route_mode: RouteMode,
    ) -> StepExecutionResult:
        baseline_session = self._sessions.resolve_session(step, context)
        route_handoff, remaining_pending_handoffs = self._routes.matching_pending_handoffs(step, context, pending_handoffs)
        retry_feedback: str | None = None
        max_attempts = step.producer.retry_policy.max_attempts
        for attempt in range(1, max_attempts + 1):
            artifacts = self._artifacts.resolve_artifacts(context)
            try:
                pair_result = await self._run_pair_step_async(
                    step,
                    context,
                    state,
                    artifacts,
                    baseline_session,
                    route_mode=route_mode,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    retry_feedback=retry_feedback,
                    route_handoff=route_handoff,
                    consumed_pending_handoffs=remaining_pending_handoffs,
                    restorable_pending_handoffs=pending_handoffs,
                )
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
                        pending_handoffs=remaining_pending_handoffs,
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
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                next_feedback, annotated_exc = self._events.next_retry_feedback(step, exc, attempt=attempt)
                if next_feedback is None:
                    if annotated_exc is exc:
                        raise
                    raise annotated_exc from exc
                retry_feedback = next_feedback
        raise AssertionError("pair-step retry loop exhausted without returning or raising")

    async def _execute_llm_step_async(
        self,
        step: PromptStepPlan,
        context: "Context",
        state: BaseModel,
        pending_handoffs: tuple["PendingHandoff", ...],
        *,
        route_mode: RouteMode,
    ) -> StepExecutionResult:
        baseline_session = self._sessions.resolve_session(step, context)
        route_handoff, remaining_pending_handoffs = self._routes.matching_pending_handoffs(step, context, pending_handoffs)
        retry_feedback: str | None = None
        max_attempts = step.turn.retry_policy.max_attempts
        for attempt in range(1, max_attempts + 1):
            artifacts = self._artifacts.resolve_artifacts(context)
            try:
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
                )
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
                        pending_handoffs=remaining_pending_handoffs,
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
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                next_feedback, annotated_exc = self._events.next_retry_feedback(step, exc, attempt=attempt)
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
    ) -> PairProviderResult:
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
            return PairProviderResult(
                producer_raw_output=None,
                verifier_raw_output=None,
                outcome=None,
                producer_session=session,
                verifier_session=None,
                usage=StepProviderUsage(),
                state=producer_state,
                direct_control=direct_control,
            )
        if before_producer_result.event is not None:
            return PairProviderResult(
                producer_raw_output=None,
                verifier_raw_output=None,
                outcome=None,
                producer_session=session,
                verifier_session=None,
                usage=StepProviderUsage(),
                state=producer_state,
                short_circuit_event=before_producer_result.event,
                source_hook=getattr(step.before_producer_hook, "__name__", type(step.before_producer_hook).__name__),
                source_phase="before_producer",
            )

        producer_prompt = self._providers.resolve_prompt(step.producer.prompt, context=context)
        self._events.emit_provider_attempt_event(
            "provider_attempt_started",
            step=step,
            context=context,
            turn_kind="producer",
            attempt=attempt,
        )
        try:
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
            producer_response = await self._providers.run_producer(producer_request)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            annotated_exc = exc
            if route_handoff is not None:
                annotated_exc = self._events.annotate_execution_error(exc, pending_handoffs=restorable_pending_handoffs)
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
        if after_producer_result.control is not None:
            direct_control = self._routes.normalize_direct_runtime_control(
                step=step,
                context=context,
                control=after_producer_result.control,
                hook_name=getattr(step.after_producer_hook, "__name__", type(step.after_producer_hook).__name__),
                hook_phase="after_producer",
            )
            return PairProviderResult(
                producer_raw_output=producer_exec.text,
                verifier_raw_output=None,
                outcome=None,
                producer_session=producer_exec.session or session,
                verifier_session=None,
                usage=StepProviderUsage(producer=producer_exec.usage),
                state=next_state,
                direct_control=direct_control,
            )
        if after_producer_result.event is not None:
            return PairProviderResult(
                producer_raw_output=producer_exec.text,
                verifier_raw_output=None,
                outcome=None,
                producer_session=producer_exec.session or session,
                verifier_session=None,
                usage=StepProviderUsage(producer=producer_exec.usage),
                state=next_state,
                short_circuit_event=after_producer_result.event,
                source_hook=getattr(step.after_producer_hook, "__name__", type(step.after_producer_hook).__name__),
                source_phase="after_producer",
            )
        try:
            review_artifacts = self._artifacts.resolve_artifacts(context)
            context._sync_artifacts(review_artifacts)
            self._artifacts.ensure_named_artifacts_exist(step.verifier_requires, review_artifacts, step_name=step.name)
            before_verifier_result = self._hook_runner.run_before(
                step,
                context,
                next_state,
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
                    producer_raw_output=producer_exec.text,
                    verifier_raw_output=None,
                    outcome=None,
                    producer_session=producer_exec.session or session,
                    verifier_session=None,
                    usage=StepProviderUsage(producer=producer_exec.usage),
                    state=review_state,
                    direct_control=direct_control,
                )
            if before_verifier_result.event is not None:
                return PairProviderResult(
                    producer_raw_output=producer_exec.text,
                    verifier_raw_output=None,
                    outcome=None,
                    producer_session=producer_exec.session or session,
                    verifier_session=None,
                    usage=StepProviderUsage(producer=producer_exec.usage),
                    state=review_state,
                    short_circuit_event=before_verifier_result.event,
                    source_hook=getattr(step.before_verifier_hook, "__name__", type(step.before_verifier_hook).__name__),
                    source_phase="before_verifier",
                )
            verifier_prompt = self._providers.resolve_prompt(step.verifier.prompt, context=context)
            verifier_session = self._sessions.resolve_pair_review_session(
                step,
                context,
                producer_session=producer_exec.session or session,
            )
            self._events.emit_provider_attempt_event(
                "provider_attempt_started",
                step=step,
                context=context,
                turn_kind="verifier",
                attempt=attempt,
            )
            try:
                verifier_request = VerifierRequest(
                    step_name=step.name,
                    verifier_prompt=verifier_prompt,
                    producer_raw_output=producer_exec.text,
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
                verifier_response = await self._providers.run_verifier(verifier_request)
                self._providers.validate_outcome(step, verifier_response.outcome)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                annotated_exc = exc
                if route_handoff is not None:
                    annotated_exc = self._events.annotate_execution_error(exc, pending_handoffs=restorable_pending_handoffs)
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
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            annotated_exc = self._events.annotate_execution_error(exc, pending_handoffs=consumed_pending_handoffs)
            if annotated_exc is exc:
                raise
            raise annotated_exc from exc
        return PairProviderResult(
            producer_raw_output=producer_exec.text,
            verifier_raw_output=verifier_exec.text,
            outcome=verifier_response.outcome,
            producer_session=producer_exec.session or session,
            verifier_session=verifier_exec.session or verifier_session,
            usage=StepProviderUsage(
                producer=producer_exec.usage,
                verifier=verifier_exec.usage,
            ),
            state=context.state,
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
    ) -> ProviderExecResult:
        prompt = self._providers.resolve_prompt(step.turn.prompt, context=context)
        self._events.emit_provider_attempt_event(
            "provider_attempt_started",
            step=step,
            context=context,
            turn_kind="llm",
            attempt=attempt,
        )
        try:
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
            response = await self._providers.run_llm(llm_request)
            self._providers.validate_outcome(step, response.outcome)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            annotated_exc = exc
            if route_handoff is not None:
                annotated_exc = self._events.annotate_execution_error(exc, pending_handoffs=restorable_pending_handoffs)
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
