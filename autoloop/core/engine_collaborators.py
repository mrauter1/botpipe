"""Focused engine collaborators extracted from the monolithic engine."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal, TypeVar

from pydantic import BaseModel

from .artifacts import ResolvedArtifacts
from .compiler import CompiledRoute
from .context import context_runtime
from .effects import Effects, WorklistEffect
from .errors import FailureContext, ProviderExecutionError, WorkflowExecutionError
from .extensions import HookRouteRedirect
from .operations import OperationRuntime, bind_operation_runtime, provider_configuration
from .outcome_contract import (
    build_provider_outcome_schema,
    payload_schema_for_route,
    route_fields_schema_for_route,
)
from .provider_policy import ProviderPolicyError, policy_fingerprint
from .primitives import Event, Fail, Goto, Outcome, RequestInput
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
from .stores.protocols import PendingHandoff, PendingInput

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from .compiler import CompiledStep
    from .context import Context
    from .engine import Engine, StepFinalizationRecord
    from .worklists import Selection, SelectionSnapshot
    from .stores.protocols import SessionBinding


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
    step: "CompiledStep"
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
class RouteFinalizationResult:
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


@dataclass(frozen=True, slots=True)
class StepExecutionResult:
    state: BaseModel
    destination: str
    event: Event | None
    outcome: Any | None
    pending_handoffs: tuple[PendingHandoff, ...]
    producer_raw_output: str | None = None
    verifier_raw_output: str | None = None
    provider_usage: StepProviderUsage | None = None
    finalization: "StepFinalizationRecord | None" = None
    pending_input: PendingInput | None = None
    route_finalization: RouteFinalizationResult | None = None


RouteMode = Literal["capture", "finalize"]


@dataclass(frozen=True, slots=True)
class PairProviderResult:
    producer_raw_output: str
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


_T = TypeVar("_T")


class ProviderContractBuilder:
    """Builds provider-visible contracts for step execution."""

    def __init__(self, engine: "Engine") -> None:
        self._engine = engine

    def control_contract(
        self,
        step: "CompiledStep",
        *,
        context: "Context",
        artifacts: ResolvedArtifacts,
        attempt: int,
        max_attempts: int,
        retry_feedback: str | None,
        route_handoff: str | None,
    ) -> dict[str, Any]:
        routes = self.routes(step)
        response_schema, response_schema_simplified = build_provider_outcome_schema(
            routes=routes,
            expected_output_schema=step.expected_output_schema,
        )
        return {
            "expected_output_schema": deepcopy(step.expected_output_schema),
            "available_routes": self.available_routes(step),
            "routes": deepcopy(routes),
            "readable_artifacts": self.readable_refs(step.reads, artifacts, context=context),
            "required_artifacts": self.artifact_refs(step.requires, artifacts),
            "writable_artifacts": self.artifact_refs(step.writes, artifacts),
            "route_required_writes": self.route_required_writes(step),
            "response_schema": response_schema,
            "response_schema_simplified": response_schema_simplified,
            "retry_feedback": retry_feedback,
            "route_handoff": route_handoff,
            "attempt": attempt,
            "max_attempts": max_attempts,
        }

    def pair_producer_contract(
        self,
        step: "CompiledStep",
        *,
        context: "Context",
        artifacts: ResolvedArtifacts,
        attempt: int,
        max_attempts: int,
        retry_feedback: str | None,
        route_handoff: str | None,
    ) -> dict[str, Any]:
        return {
            "expected_output_schema": None,
            "available_routes": (),
            "routes": {},
            "readable_artifacts": self.readable_refs(step.producer_reads, artifacts, context=context),
            "required_artifacts": self.artifact_refs(step.producer_requires, artifacts),
            "writable_artifacts": self.artifact_refs(step.producer_writes, artifacts),
            "route_required_writes": {},
            "response_schema": None,
            "response_schema_simplified": False,
            "retry_feedback": retry_feedback,
            "route_handoff": route_handoff,
            "attempt": attempt,
            "max_attempts": max_attempts,
        }

    def pair_verifier_contract(
        self,
        step: "CompiledStep",
        *,
        context: "Context",
        artifacts: ResolvedArtifacts,
        attempt: int,
        max_attempts: int,
        retry_feedback: str | None,
        route_handoff: str | None,
    ) -> dict[str, Any]:
        readable_names = tuple(dict.fromkeys(step.verifier_reads))
        writable_names = step.verifier_writes or step.writes
        routes = self.routes(step)
        response_schema, response_schema_simplified = build_provider_outcome_schema(
            routes=routes,
            expected_output_schema=step.expected_output_schema,
        )
        return {
            "expected_output_schema": deepcopy(step.expected_output_schema),
            "available_routes": self.available_routes(step),
            "routes": deepcopy(routes),
            "readable_artifacts": self.readable_refs(readable_names, artifacts, context=context),
            "required_artifacts": self.artifact_refs(step.verifier_requires, artifacts),
            "writable_artifacts": self.artifact_refs(writable_names, artifacts),
            "route_required_writes": self.route_required_writes(step),
            "response_schema": response_schema,
            "response_schema_simplified": response_schema_simplified,
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
            for resolved_name in (self._engine._artifact_lookup_name(name) for name in names)
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
        schema_name = self._engine._artifact_schema_name(artifact)
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

    def readable_ref(
        self,
        name: str,
        artifacts: ResolvedArtifacts,
        *,
        context: "Context",
    ) -> ProviderReadableRef:
        name = self._engine._artifact_lookup_name(name)
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
                schema_name=self._engine._artifact_schema_name(artifact),
            )
        workspace_path = self._engine._resolve_workspace_read_path(name, context=context)
        return ProviderReadableRef(
            name=name,
            path=str(workspace_path),
            exists=workspace_path.exists(),
            declared_artifact=False,
        )

    def route_required_writes(self, step: "CompiledStep") -> dict[str, tuple[str, ...]]:
        visible_routes = set(self.available_routes(step))
        return {
            route_tag: effective_route_required_writes_for_step(
                self._engine.compiled,
                step=step,
                route_tag=route_tag,
            )
            for route_tag, compiled_route in self._engine._route_table_for_step(step).items()
            if route_tag in visible_routes
        }

    def routes(self, step: "CompiledStep") -> dict[str, ProviderRoute]:
        routes: dict[str, ProviderRoute] = {}
        for route_name in self.available_routes(step):
            compiled_route = self._engine._route_table_for_step(step).get(route_name)
            if compiled_route is None:
                continue
            routes[route_name] = ProviderRoute(
                summary=compiled_route.summary,
                target=compiled_route.target,
                required_writes=tuple(compiled_route.required_writes or ()),
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

    def available_routes(self, step: "CompiledStep") -> tuple[str, ...]:
        if self._engine.interaction_policy.allow_provider_questions:
            return step.provider_visible_routes_interactive
        return step.provider_visible_routes_full_auto


class StepDispatcher:
    """Dispatches one compiled step through the engine execution path."""

    def __init__(self, engine: "Engine") -> None:
        self._engine = engine

    def execute(
        self,
        step: "CompiledStep",
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
        step: "CompiledStep",
        context: "Context",
        state: "BaseModel",
        pending_handoffs: tuple["PendingHandoff", ...],
        *,
        route_mode: RouteMode = "finalize",
    ) -> StepExecutionResult:
        runtime = context_runtime(context)
        runtime.set_state(state)
        runtime.set_active_worklist(step.scope_name)
        if step.scope_name is not None:
            context.ensure_selection(step.scope_name)
        initial_artifacts = self._engine._resolve_artifacts(context)
        runtime.set_artifacts(initial_artifacts)
        self._engine._ensure_required_artifacts(step, initial_artifacts)
        if step.kind == "produce_verify":
            return await self._execute_pair_step_async(step, context, state, pending_handoffs, route_mode=route_mode)
        if step.kind == "branch_group":
            if route_mode != "finalize":
                raise WorkflowExecutionError("branch-group composite steps do not support capture mode")
            return await self._engine.branch_group_runtime.run_async(step, context, state, pending_handoffs)

        before_result = self._engine.hook_runner.run_before(step, context, state, artifacts=initial_artifacts)
        state = before_result.state
        runtime.set_state(state)
        runtime.set_artifacts(self._engine._resolve_artifacts(context))
        if before_result.control is not None:
            _, remaining_pending_handoffs = self._engine._matching_pending_handoffs(step, context, pending_handoffs)
            direct_control = self._engine._normalize_direct_runtime_control(
                step=step,
                context=context,
                control=before_result.control,
                hook_name=getattr(step.before_hook, "__name__", type(step.before_hook).__name__),
                hook_phase="before",
            )
            scheduled_handoffs = (
                ()
                if route_mode == "capture"
                else self._engine._schedule_direct_control_handoffs(
                    remaining_pending_handoffs,
                    control=direct_control,
                    context=context,
                    source_step=step.name,
                )
            )
            return self._engine._step_result_from_direct_control(
                step=step,
                state=state,
                control=direct_control,
                pending_handoffs=scheduled_handoffs,
            )
        if before_result.event is not None:
            _, remaining_pending_handoffs = self._engine._matching_pending_handoffs(step, context, pending_handoffs)
            finalization = self._complete_route(
                route_mode=route_mode,
                request=StepFinalizationRequest(
                    step=step,
                    context=context,
                    state=state,
                    artifacts=self._engine._resolve_artifacts(context),
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
            return self._engine._step_result_from_route_finalization(step=step, route_finalization=finalization)
        if step.kind == "step":
            return await self._execute_llm_step_async(step, context, state, pending_handoffs, route_mode=route_mode)
        if step.kind == "workflow":
            return self._execute_workflow_step_for_mode(
                step,
                context,
                state,
                pending_handoffs,
                route_mode=route_mode,
            )
        if step.kind in {"python", "operation"}:
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
    ) -> RouteFinalizationResult:
        if route_mode == "capture":
            return self._engine.route_finalizer.capture(request)
        return self._engine.route_finalizer.finalize(request)

    async def _call_provider(
        self,
        *,
        call: Callable[[Any], Awaitable[_T]],
    ) -> _T:
        return await call(self._engine.provider)

    def _execute_workflow_step_for_mode(
        self,
        step: "CompiledStep",
        context: "Context",
        state: BaseModel,
        pending_handoffs: tuple["PendingHandoff", ...],
        *,
        route_mode: RouteMode,
    ) -> StepExecutionResult:
        _, remaining_pending_handoffs = self._engine._matching_pending_handoffs(step, context, pending_handoffs)
        child_result = self._engine.workflow_invoker.run_child_step(step, context)
        event = self._engine._map_workflow_step_result(step, child_result)
        try:
            self._engine._validate_event(step, event, provider_attributable=False, error_cls=WorkflowExecutionError)
        except WorkflowExecutionError as exc:
            annotated = self._engine._annotate_execution_error(
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
                artifacts=self._engine._resolve_artifacts(context),
                candidate_event=event,
                candidate_route=event.tag,
                candidate_route_present=True,
                after_subject=event,
                pending_handoffs=remaining_pending_handoffs,
                error_cls=WorkflowExecutionError,
                provider_attributable=False,
            ),
        )
        return self._engine._step_result_from_route_finalization(step=step, route_finalization=finalization)

    def _execute_python_step_for_mode(
        self,
        step: "CompiledStep",
        context: "Context",
        state: BaseModel,
        pending_handoffs: tuple["PendingHandoff", ...],
        *,
        route_mode: RouteMode,
    ) -> StepExecutionResult:
        _, remaining_pending_handoffs = self._engine._matching_pending_handoffs(step, context, pending_handoffs)
        if step.python_handler is None:
            raise WorkflowExecutionError(f"{step.kind} step {step.name!r} has no compiled handler")
        runtime = context_runtime(context)
        runtime.set_route(None)
        runtime.set_event(None)
        runtime.set_outcome(None)
        handler_name = getattr(step.python_handler, "__name__", step.name)
        invocation_id = f"{step.name}:python_step:{handler_name}"
        runtime.set_execution_source(
            hook_name=handler_name,
            phase="python_step",
            invocation_id=invocation_id,
        )
        try:
            result = step.python_handler(context)
            next_state = context.state
        finally:
            runtime.set_execution_source(hook_name=None, phase=None, invocation_id=None)
        try:
            hook_result = self._engine.hook_runner.normalize_result(
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
            annotated = self._engine._annotate_execution_error(
                exc,
                checkpoint_state=self._engine._clone_state(context.state),
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
            direct_control = self._engine._normalize_direct_runtime_control(
                step=step,
                context=context,
                control=hook_result.control,
                hook_name=handler_name,
                hook_phase="python_step",
            )
            scheduled_handoffs = (
                ()
                if route_mode == "capture"
                else self._engine._schedule_direct_control_handoffs(
                    remaining_pending_handoffs,
                    control=direct_control,
                    context=context,
                    source_step=step.name,
                )
            )
            return self._engine._step_result_from_direct_control(
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
                artifacts=self._engine._resolve_artifacts(context),
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
        return self._engine._step_result_from_route_finalization(step=step, route_finalization=finalization)

    async def _execute_pair_step_async(
        self,
        step: "CompiledStep",
        context: "Context",
        state: BaseModel,
        pending_handoffs: tuple["PendingHandoff", ...],
        *,
        route_mode: RouteMode,
    ) -> StepExecutionResult:
        baseline_session = self._engine._resolve_session(step, context)
        route_handoff, remaining_pending_handoffs = self._engine._matching_pending_handoffs(step, context, pending_handoffs)
        retry_feedback: str | None = None
        max_attempts = step.retry_policy.max_attempts
        for attempt in range(1, max_attempts + 1):
            artifacts = self._engine._resolve_artifacts(context)
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
                        else self._engine._schedule_direct_control_handoffs(
                            remaining_pending_handoffs,
                            control=pair_result.direct_control,
                            context=context,
                            source_step=step.name,
                        )
                    )
                    return self._engine._step_result_from_direct_control(
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
                            artifacts=self._engine._resolve_artifacts(context),
                            candidate_event=pair_result.short_circuit_event,
                            candidate_route=pair_result.short_circuit_event.tag,
                            candidate_route_present=True,
                            after_subject=pair_result.short_circuit_event,
                            pending_handoffs=remaining_pending_handoffs,
                            error_cls=ProviderExecutionError,
                            provider_attributable=False,
                            source_hook=pair_result.source_hook,
                            source_phase=pair_result.source_phase,
                        ),
                    )
                    return self._engine._step_result_from_route_finalization(
                        step=step,
                        route_finalization=finalization,
                        producer_raw_output=pair_result.producer_raw_output,
                        verifier_raw_output=pair_result.verifier_raw_output,
                        provider_usage=pair_result.usage,
                    )
                self._engine._persist_session(pair_result.producer_session, context=context)
                self._engine._persist_session(pair_result.verifier_session, context=context)
                assert pair_result.outcome is not None
                final_event = self._engine._event_from_outcome(step, pair_result.outcome)
                finalization = self._complete_route(
                    route_mode=route_mode,
                    request=StepFinalizationRequest(
                        step=step,
                        context=context,
                        state=pair_result.state or context.state,
                        artifacts=self._engine._resolve_artifacts(context),
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
                return self._engine._step_result_from_route_finalization(
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
                next_feedback, annotated_exc = self._engine._next_retry_feedback(step, exc, attempt=attempt)
                if next_feedback is None:
                    if annotated_exc is exc:
                        raise
                    raise annotated_exc from exc
                retry_feedback = next_feedback
        raise AssertionError("pair-step retry loop exhausted without returning or raising")

    async def _execute_llm_step_async(
        self,
        step: "CompiledStep",
        context: "Context",
        state: BaseModel,
        pending_handoffs: tuple["PendingHandoff", ...],
        *,
        route_mode: RouteMode,
    ) -> StepExecutionResult:
        baseline_session = self._engine._resolve_session(step, context)
        route_handoff, remaining_pending_handoffs = self._engine._matching_pending_handoffs(step, context, pending_handoffs)
        retry_feedback: str | None = None
        max_attempts = step.retry_policy.max_attempts
        for attempt in range(1, max_attempts + 1):
            artifacts = self._engine._resolve_artifacts(context)
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
                final_event = self._engine._event_from_outcome(step, llm_result.outcome)
                finalization = self._complete_route(
                    route_mode=route_mode,
                    request=StepFinalizationRequest(
                        step=step,
                        context=context,
                        state=state,
                        artifacts=self._engine._resolve_artifacts(context),
                        candidate_event=final_event,
                        candidate_route=final_event.tag,
                        candidate_route_present=True,
                        after_subject=llm_result.outcome,
                        pending_handoffs=remaining_pending_handoffs,
                        error_cls=ProviderExecutionError,
                        provider_attributable=True,
                    ),
                )
                self._engine._persist_session(llm_result.session, context=context)
                return self._engine._step_result_from_route_finalization(
                    step=step,
                    route_finalization=finalization,
                    outcome=llm_result.outcome,
                    producer_raw_output=llm_result.text,
                    provider_usage=StepProviderUsage(llm=llm_result.usage),
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                next_feedback, annotated_exc = self._engine._next_retry_feedback(step, exc, attempt=attempt)
                if next_feedback is None:
                    if annotated_exc is exc:
                        raise
                    raise annotated_exc from exc
                retry_feedback = next_feedback
        raise AssertionError("llm-step retry loop exhausted without returning or raising")

    async def _run_pair_step_async(
        self,
        step: "CompiledStep",
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
        producer_prompt = self._engine._resolve_prompt(step.producer_prompt, context=context)
        self._engine._emit_provider_attempt_event(
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
                **self._engine.provider_contract_builder.pair_producer_contract(
                    step,
                    context=context,
                    artifacts=artifacts,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    retry_feedback=retry_feedback,
                    route_handoff=route_handoff,
                ),
            )
            producer_response = await self._call_provider(
                call=lambda provider: provider.run_producer(producer_request),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            annotated_exc = exc
            if route_handoff is not None:
                annotated_exc = self._engine._annotate_execution_error(exc, pending_handoffs=restorable_pending_handoffs)
            self._engine._emit_provider_attempt_failed(
                step=step,
                context=context,
                turn_kind="producer",
                attempt=attempt,
                exc=annotated_exc,
            )
            if annotated_exc is exc:
                raise
            raise annotated_exc from exc
        producer_exec = self._engine._provider_exec_result(response=producer_response, text=producer_response.raw_output)
        self._engine._emit_provider_attempt_finished(
            step=step,
            context=context,
            turn_kind="producer",
            attempt=attempt,
            token_usage=producer_exec.usage,
        )
        self._engine._append_logs(step, artifacts, producer_exec.text)
        if producer_exec.session is not None:
            self._engine._persist_session(producer_exec.session, context=context)
        after_producer_result = self._engine.hook_runner.run_after(
            step,
            context,
            state=state,
            artifacts=self._engine._resolve_artifacts(context),
            subject=producer_exec.text,
            candidate_event=None,
            hook=step.after_producer_hook,
            hook_phase="after_producer",
        )
        next_state = after_producer_result.state
        runtime = context_runtime(context)
        runtime.set_state(next_state)
        if after_producer_result.control is not None:
            direct_control = self._engine._normalize_direct_runtime_control(
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
            review_artifacts = self._engine._resolve_artifacts(context)
            runtime.set_artifacts(review_artifacts)
            self._engine._ensure_named_artifacts_exist(step.verifier_requires, review_artifacts, step_name=step.name)
            before_verifier_result = self._engine.hook_runner.run_before(
                step,
                context,
                next_state,
                artifacts=review_artifacts,
                hook=step.before_verifier_hook,
                hook_phase="before_verifier",
            )
            review_state = before_verifier_result.state
            runtime.set_state(review_state)
            if before_verifier_result.control is not None:
                direct_control = self._engine._normalize_direct_runtime_control(
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
            verifier_prompt = self._engine._resolve_prompt(step.verifier_prompt, context=context)
            verifier_session = self._engine._resolve_pair_review_session(
                step,
                context,
                producer_session=producer_exec.session or session,
            )
            self._engine._emit_provider_attempt_event(
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
                    **self._engine.provider_contract_builder.pair_verifier_contract(
                        step,
                        context=context,
                        artifacts=review_artifacts,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        retry_feedback=retry_feedback,
                        route_handoff=route_handoff,
                    ),
                )
                verifier_response = await self._call_provider(
                    call=lambda provider: provider.run_verifier(verifier_request),
                )
                self._engine._validate_outcome(step, verifier_response.outcome)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                annotated_exc = exc
                if route_handoff is not None:
                    annotated_exc = self._engine._annotate_execution_error(exc, pending_handoffs=restorable_pending_handoffs)
                self._engine._emit_provider_attempt_failed(
                    step=step,
                    context=context,
                    turn_kind="verifier",
                    attempt=attempt,
                    exc=annotated_exc,
                )
                if annotated_exc is exc:
                    raise
                raise annotated_exc from exc
            verifier_exec = self._engine._provider_exec_result(
                response=verifier_response,
                text=verifier_response.outcome.raw_output,
            )
            self._engine._emit_provider_attempt_finished(
                step=step,
                context=context,
                turn_kind="verifier",
                attempt=attempt,
                token_usage=verifier_exec.usage,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            annotated_exc = self._engine._annotate_execution_error(exc, pending_handoffs=consumed_pending_handoffs)
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
        step: "CompiledStep",
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
        prompt = self._engine._resolve_prompt(step.producer_prompt, context=context)
        self._engine._emit_provider_attempt_event(
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
                **self._engine.provider_contract_builder.control_contract(
                    step,
                    context=context,
                    artifacts=artifacts,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    retry_feedback=retry_feedback,
                    route_handoff=route_handoff,
                ),
            )
            response = await self._call_provider(
                call=lambda provider: provider.run_llm(llm_request),
            )
            self._engine._validate_outcome(step, response.outcome)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            annotated_exc = exc
            if route_handoff is not None:
                annotated_exc = self._engine._annotate_execution_error(exc, pending_handoffs=restorable_pending_handoffs)
            self._engine._emit_provider_attempt_failed(
                step=step,
                context=context,
                turn_kind="llm",
                attempt=attempt,
                exc=annotated_exc,
            )
            annotated_exc = self._engine._annotate_execution_error(
                annotated_exc,
                pending_handoffs=consumed_pending_handoffs,
            )
            if annotated_exc is exc:
                raise
            raise annotated_exc from exc
        provider_exec = self._engine._provider_exec_result(response=response, text=response.outcome.raw_output)
        self._engine._emit_provider_attempt_finished(
            step=step,
            context=context,
            turn_kind="llm",
            attempt=attempt,
            token_usage=provider_exec.usage,
        )
        self._engine._append_logs(step, artifacts, provider_exec.text)
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

    def __init__(self, engine: "Engine") -> None:
        self._engine = engine

    def capture(self, request: StepFinalizationRequest) -> RouteFinalizationResult:
        step = request.step
        context = request.context
        candidate_event = request.candidate_event
        try:
            self._engine._validate_event(
                step,
                candidate_event,
                provider_attributable=request.provider_attributable,
                error_cls=request.error_cls,
            )
        except WorkflowExecutionError as exc:
            annotated = self._engine._annotate_execution_error(
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
        after_result = self._engine.hook_runner.run_after(
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
        runtime = context_runtime(context)
        runtime.set_state(final_state)
        finalized_artifacts = self._engine._resolve_artifacts(context)
        runtime.set_artifacts(finalized_artifacts)
        route_redirects: list[HookRouteRedirect] = []
        final_source_hook = request.source_hook
        final_source_phase = request.source_phase
        if after_redirect is not None:
            route_redirects.append(replace(after_redirect, redirect_index=len(route_redirects) + 1))
            self._engine._ensure_hook_redirect_limit(step, candidate_route=candidate_route, redirects=route_redirects)
            final_source_hook = after_redirect.hook
            final_source_phase = after_redirect.phase

        if after_result.control is not None:
            direct_control = self._engine._normalize_direct_runtime_control(
                step=step,
                context=context,
                control=after_result.control,
                hook_name=getattr(request.after_hook or step.after_hook, "__name__", type(request.after_hook or step.after_hook).__name__),
                hook_phase=request.after_hook_phase,
            )
            return RouteFinalizationResult(
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

        try:
            final_route = self._engine._compiled_route_for_step(step, final_event.tag)
        except Exception as exc:
            runtime.set_route(None)
            runtime.set_event(None)
            runtime.set_outcome(None)
            annotated = self._engine._annotate_execution_error(exc, checkpoint_state=self._engine._clone_state(context.state))
            if annotated is exc:
                raise
            raise annotated from exc

        runtime.set_route(
            {
                "tag": final_event.tag,
                "target": final_route.target,
                "summary": final_route.summary,
                "handoff": final_route.handoff,
            }
        )
        runtime.set_event(self._engine._event_context_payload(final_event))
        runtime.set_outcome(request.after_subject)

        final_provider_attributable = request.provider_attributable and not explicit_event_override
        final_error_cls = request.error_cls if final_provider_attributable else WorkflowExecutionError
        self._engine.artifact_guard.enforce(
            step,
            context,
            finalized_artifacts,
            route_tag=final_event.tag,
            state=final_state,
            error_cls=final_error_cls,
            provider_attributable=final_provider_attributable,
        )
        destination = final_route.target
        self._engine._update_final_step_runtime_state(step, getattr(context, "_step_state", None), final_event)
        self._engine._update_final_step_runtime_state(step, getattr(context, "_step_item_state", None), final_event)
        self._engine._update_final_item_runtime_state(getattr(context, "_item_state", None), final_event)
        return RouteFinalizationResult(
            state=final_state,
            destination=destination,
            finalized_event=final_event,
            candidate_route=candidate_route,
            final_route=final_event.tag,
            runtime_control=None,
            target_step=None,
            terminal=None,
            pending_input=None,
            source_hook=final_source_hook,
            source_phase=final_source_phase,
            provider_attributable=final_provider_attributable,
            hook_route_override_from=route_redirects[0].from_route if route_redirects else None,
            hook_route_override_to=route_redirects[-1].to_route if route_redirects else None,
            hook_route_redirects=tuple(route_redirects),
            scheduled_handoffs=(),
        )

    def finalize(self, request: StepFinalizationRequest) -> RouteFinalizationResult:
        step = request.step
        context = request.context
        candidate_event = request.candidate_event
        try:
            self._engine._validate_event(
                step,
                candidate_event,
                provider_attributable=request.provider_attributable,
                error_cls=request.error_cls,
            )
        except WorkflowExecutionError as exc:
            annotated = self._engine._annotate_execution_error(
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
        after_result = self._engine.hook_runner.run_after(
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
        runtime = context_runtime(context)
        runtime.set_state(final_state)
        finalized_artifacts = self._engine._resolve_artifacts(context)
        runtime.set_artifacts(finalized_artifacts)
        route_redirects: list[HookRouteRedirect] = []
        final_source_hook = request.source_hook
        final_source_phase = request.source_phase
        if after_redirect is not None:
            route_redirects.append(replace(after_redirect, redirect_index=len(route_redirects) + 1))
            self._engine._ensure_hook_redirect_limit(step, candidate_route=candidate_route, redirects=route_redirects)
            final_source_hook = after_redirect.hook
            final_source_phase = after_redirect.phase

        if after_result.control is not None:
            direct_control = self._engine._normalize_direct_runtime_control(
                step=step,
                context=context,
                control=after_result.control,
                hook_name=getattr(request.after_hook or step.after_hook, "__name__", type(request.after_hook or step.after_hook).__name__),
                hook_phase=request.after_hook_phase,
            )
            scheduled_handoffs = self._engine._schedule_direct_control_handoffs(
                request.pending_handoffs,
                control=direct_control,
                context=context,
                source_step=step.name,
            )
            return RouteFinalizationResult(
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

        final_route: CompiledRoute
        try:
            while True:
                final_route = self._engine._compiled_route_for_step(step, final_event.tag)
                runtime.set_route(
                    {
                        "tag": final_event.tag,
                        "target": final_route.target,
                        "summary": final_route.summary,
                        "handoff": final_route.handoff,
                    }
                )
                runtime.set_event(self._engine._event_context_payload(final_event))
                runtime.set_outcome(request.after_subject)
                route_result = self._engine.hook_runner.run_route(
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
                runtime.set_state(final_state)
                route_redirect = route_result.redirect
                if route_redirect is not None:
                    route_redirects.append(replace(route_redirect, redirect_index=len(route_redirects) + 1))
                    self._engine._ensure_hook_redirect_limit(step, candidate_route=candidate_route, redirects=route_redirects)
                    final_source_hook = route_redirect.hook
                    final_source_phase = route_redirect.phase
                    continue
                if route_result.control is not None:
                    direct_control = self._engine._normalize_direct_runtime_control(
                        step=step,
                        context=context,
                        control=route_result.control,
                        hook_name=getattr(final_route.on_taken, "__name__", type(final_route.on_taken).__name__),
                        hook_phase="on_taken",
                    )
                    scheduled_handoffs = self._engine._schedule_direct_control_handoffs(
                        request.pending_handoffs,
                        control=direct_control,
                        context=context,
                        source_step=step.name,
                    )
                    return RouteFinalizationResult(
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
                break
        except Exception as exc:
            runtime.set_route(None)
            runtime.set_event(None)
            runtime.set_outcome(None)
            annotated = self._engine._annotate_execution_error(exc, checkpoint_state=self._engine._clone_state(context.state))
            if annotated is exc:
                raise
            raise annotated from exc

        final_provider_attributable = request.provider_attributable and not explicit_event_override
        final_error_cls = request.error_cls if final_provider_attributable else WorkflowExecutionError
        self._engine.artifact_guard.enforce(
            step,
            context,
            finalized_artifacts,
            route_tag=final_event.tag,
            state=final_state,
            error_cls=final_error_cls,
            provider_attributable=final_provider_attributable,
        )
        destination = final_route.target
        self._engine._update_final_step_runtime_state(step, getattr(context, "_step_state", None), final_event)
        self._engine._update_final_step_runtime_state(step, getattr(context, "_step_item_state", None), final_event)
        self._engine._update_final_item_runtime_state(getattr(context, "_item_state", None), final_event)
        return RouteFinalizationResult(
            state=final_state,
            destination=destination,
            finalized_event=final_event,
            candidate_route=candidate_route,
            final_route=final_event.tag,
            runtime_control=None,
            target_step=None,
            terminal=None,
            pending_input=None,
            source_hook=final_source_hook,
            source_phase=final_source_phase,
            provider_attributable=final_provider_attributable,
            hook_route_override_from=route_redirects[0].from_route if route_redirects else None,
            hook_route_override_to=route_redirects[-1].to_route if route_redirects else None,
            hook_route_redirects=tuple(route_redirects),
            scheduled_handoffs=self._engine._schedule_route_handoffs(
                request.pending_handoffs,
                route=final_route,
                event=final_event,
                destination=destination,
                context=context,
                source_step=step.name,
            ),
        )


class HookRunner:
    """Owns hook execution entrypoints."""

    def __init__(self, engine: "Engine") -> None:
        self._engine = engine

    def run_before(
        self,
        step: "CompiledStep",
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
        runtime = context_runtime(context)
        self._engine._emit_hook_event("hook_started", step=step, context=context, hook_name=hook_name, phase=hook_phase)
        try:
            runtime.set_state(state)
            runtime.set_artifacts(artifacts)
            runtime.set_route(None)
            runtime.set_event(None)
            runtime.set_outcome(None)
            invocation_id = f"{step.name}:{hook_phase}:{hook_name}"
            runtime.set_execution_source(
                hook_name=hook_name,
                phase=hook_phase,
                invocation_id=invocation_id,
            )
            try:
                result = hook(context)
            finally:
                runtime.set_execution_source(hook_name=None, phase=None, invocation_id=None)
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
            self._engine._emit_hook_event(
                "hook_finished",
                step=step,
                context=context,
                hook_name=hook_name,
                phase=hook_phase,
                route=hook_result.event.tag if hook_result.event is not None else None,
            )
            return hook_result
        except Exception as exc:
            self._engine._emit_hook_event(
                "hook_failed",
                step=step,
                context=context,
                hook_name=hook_name,
                phase=hook_phase,
                error=str(exc),
            )
            annotated = self._engine._annotate_execution_error(
                exc,
                checkpoint_state=self._engine._clone_state(context.state),
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
        step: "CompiledStep",
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
        runtime = context_runtime(context)
        self._engine._emit_hook_event(
            "hook_started",
            step=step,
            context=context,
            hook_name=hook_name,
            phase=hook_phase,
            route=None if candidate_event is None else candidate_event.tag,
        )
        try:
            runtime.set_state(state)
            runtime.set_artifacts(artifacts)
            if candidate_event is not None:
                compiled_route = self._engine._compiled_route_for_step(step, candidate_event.tag)
                runtime.set_route(
                    {
                        "tag": candidate_event.tag,
                        "target": compiled_route.target,
                        "summary": compiled_route.summary,
                        "handoff": compiled_route.handoff,
                    }
                )
                runtime.set_event(self._engine._event_context_payload(candidate_event))
            else:
                runtime.set_route(None)
                runtime.set_event(None)
            runtime.set_outcome(subject)
            invocation_id = f"{step.name}:{hook_phase}:{hook_name}"
            runtime.set_execution_source(
                hook_name=hook_name,
                phase=hook_phase,
                invocation_id=invocation_id,
            )
            try:
                result = hook(context)
            finally:
                runtime.set_execution_source(hook_name=None, phase=None, invocation_id=None)
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
            self._engine._emit_hook_event(
                "hook_finished",
                step=step,
                context=context,
                hook_name=hook_name,
                phase=hook_phase,
                route=hook_result.event.tag if hook_result.event is not None else None if candidate_event is None else candidate_event.tag,
            )
            return hook_result
        except Exception as exc:
            self._engine._emit_hook_event(
                "hook_failed",
                step=step,
                context=context,
                hook_name=hook_name,
                phase=hook_phase,
                route=None if candidate_event is None else candidate_event.tag,
                error=str(exc),
            )
            annotated = self._engine._annotate_execution_error(
                exc,
                checkpoint_state=self._engine._clone_state(context.state),
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
        step: "CompiledStep",
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
            override_event = self._engine._validate_hook_event_override(
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
                redirect_record = self._engine._build_hook_redirect_record(
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
            override_event = self._engine._validate_hook_event_override(step, result)
            redirect_record = None
            if next_event is not None:
                redirect_record = self._engine._build_hook_redirect_record(
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
        step: "CompiledStep",
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
        step: "CompiledStep",
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
        step: "CompiledStep",
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
        runtime = context_runtime(context)
        self._engine._emit_hook_event(
            "hook_started",
            step=step,
            context=context,
            hook_name=hook_name,
            phase=hook_phase,
            route=event.tag,
        )
        try:
            runtime.set_state(state)
            runtime.set_artifacts(artifacts)
            compiled_route = self._engine._compiled_route_for_step(step, event.tag)
            runtime.set_route(
                {
                    "tag": event.tag,
                    "target": compiled_route.target,
                    "summary": compiled_route.summary,
                    "handoff": compiled_route.handoff,
                }
            )
            runtime.set_event(self._engine._event_context_payload(event))
            invocation_id = f"{step.name}:{hook_phase}:{hook_name}"
            runtime.set_execution_source(
                hook_name=hook_name,
                phase=hook_phase,
                invocation_id=invocation_id,
            )
            try:
                result = hook(context)
            finally:
                runtime.set_execution_source(hook_name=None, phase=None, invocation_id=None)
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
            self._engine._emit_hook_event(
                "hook_finished",
                step=step,
                context=context,
                hook_name=hook_name,
                phase=hook_phase,
                route=hook_result.event.tag if hook_result.event is not None else event.tag,
            )
            return hook_result
        except Exception as exc:
            self._engine._emit_hook_event(
                "hook_failed",
                step=step,
                context=context,
                hook_name=hook_name,
                phase=hook_phase,
                route=event.tag,
                error=str(exc),
            )
            annotated = self._engine._annotate_execution_error(
                exc,
                checkpoint_state=self._engine._clone_state(context.state),
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

    def __init__(self, engine: "Engine") -> None:
        self._engine = engine

    def enforce(self, *args: Any, **kwargs: Any) -> None:
        self._engine._enforce_artifact_contracts(*args, **kwargs)


class StateRuntime:
    """Owns worklist selection state helpers."""

    def __init__(self, engine: "Engine") -> None:
        self._engine = engine

    def restore_worklist_selections(
        self,
        context: "Context",
        snapshots: "Mapping[str, SelectionSnapshot]",
    ) -> dict[str, "SelectionSnapshot"]:
        return self._engine._restore_worklist_selections(context, snapshots)

    def ensure_worklist_selection(
        self,
        context: "Context",
        worklist_name: str,
    ) -> "Selection[Any]":
        return self._engine._ensure_worklist_selection(context, worklist_name)


class SessionRuntime:
    """Owns session-store state transitions."""

    def __init__(self, engine: "Engine") -> None:
        self._engine = engine

    def restore(self, snapshot: Any) -> None:
        self._engine.session_store.restore(snapshot)

    def snapshot(self) -> Any:
        return self._engine.session_store.snapshot()


class CheckpointManager:
    """Owns checkpoint persistence entrypoints."""

    def __init__(self, engine: "Engine") -> None:
        self._engine = engine

    def save(self, *args: Any, **kwargs: Any) -> Any:
        return self._engine._save_checkpoint(*args, **kwargs)


class OperationRecorder:
    """Owns operation-runtime binding for step execution."""

    def __init__(self, engine: "Engine") -> None:
        self._engine = engine

    @contextmanager
    def bind_step(
        self,
        *,
        step: "CompiledStep",
        context: "Context",
        run_folder: "Path",
        step_name: str,
        step_visit: int,
    ):
        resolved_policy = None
        if self._engine.provider_policy_resolver is not None and _step_uses_provider_policy(step):
            try:
                resolved_policy = self._engine.provider_policy_resolver.resolve_for_step(step)
            except ProviderPolicyError as exc:
                context_runtime(context).emit_runtime_event(
                    "provider_policy_violation",
                    policy_fingerprint=None,
                    error_message=str(exc),
                )
                raise
            context._provider_policy = resolved_policy
            context_runtime(context).emit_runtime_event(
                "provider_policy_resolved",
                policy_fingerprint=policy_fingerprint(resolved_policy),
            )
        with bind_operation_runtime(
            OperationRuntime(
                provider=self._engine.provider,
                provider_configuration=provider_configuration(
                    self._engine.provider,
                    default_session_name=self._engine.compiled.default_session_name,
                ),
                prompt_registry=self._engine.prompt_registry,
                context=context,
                run_folder=run_folder,
                workflow_name=self._engine.compiled.workflow_name,
                topology_hash=self._engine.compiled.topology_hash,
                source_hash=self._engine.compiled.source_hash,
                step_name=step_name,
                step_visit=step_visit,
                default_session_name=self._engine.compiled.default_session_name,
                replay_mismatch_behavior=self._engine.operation_replay_mismatch_behavior,
                policy=resolved_policy,
                provider_policy_resolver=self._engine.provider_policy_resolver,
                event_sink=self._engine.runtime_event_sink,
            )
        ) as runtime:
            yield runtime


def _context_provider_policy(context: "Context") -> object | None:
    return getattr(context, "_provider_policy", None)


def _step_uses_provider_policy(step: "CompiledStep") -> bool:
    return step.kind in {"produce_verify", "step", "python", "operation"}


class WorkflowInvoker:
    """Owns child-workflow invocation entrypoints."""

    def __init__(self, engine: "Engine") -> None:
        self._engine = engine

    def run_child_step(self, step: "CompiledStep", context: "Context") -> Any:
        return self._engine._run_workflow_step(step, context)
