"""Focused engine collaborators extracted from the monolithic engine."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Callable

from pydantic import BaseModel

from .artifacts import ResolvedArtifacts
from .compiler import CompiledRoute
from .context import context_runtime
from .errors import FailureContext, WorkflowExecutionError
from .extensions import HookRouteRedirect
from .operations import OperationRuntime, bind_operation_runtime, provider_configuration
from .primitives import Event, Fail, Goto, Outcome, RequestInput
from .providers.models import ProviderArtifactRef, ProviderReadableRef, ProviderRoute, StepProviderUsage, TokenUsage
from .route_required_writes import effective_route_required_writes_map, explicit_route_required_writes
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


@dataclass(frozen=True, slots=True)
class ProviderExecResult:
    text: str
    session_id: str | None
    provider_metadata: dict[str, object]
    usage: TokenUsage | None = None
    session: "SessionBinding | None" = None
    outcome: Outcome | None = None


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
        return {
            "expected_output_schema": deepcopy(step.expected_output_schema),
            "available_routes": self.available_routes(step),
            "routes": deepcopy(self.routes(step)),
            "readable_artifacts": self.readable_refs(step.reads, artifacts, context=context),
            "required_artifacts": self.artifact_refs(step.requires, artifacts),
            "writable_artifacts": self.artifact_refs(step.writes, artifacts),
            "route_required_writes": self.route_required_writes(step),
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
        return {
            "expected_output_schema": deepcopy(step.expected_output_schema),
            "available_routes": self.available_routes(step),
            "routes": deepcopy(self.routes(step)),
            "readable_artifacts": self.readable_refs(readable_names, artifacts, context=context),
            "required_artifacts": self.artifact_refs(step.verifier_requires, artifacts),
            "writable_artifacts": self.artifact_refs(writable_names, artifacts),
            "route_required_writes": self.route_required_writes(step),
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
            route_tag: required_writes
            for route_tag, required_writes in effective_route_required_writes_map(
                self._engine.compiled,
                step_name=step.name,
            ).items()
            if route_tag in visible_routes
        }

    def routes(self, step: "CompiledStep") -> dict[str, ProviderRoute]:
        routes: dict[str, ProviderRoute] = {}
        for route_name in self.available_routes(step):
            compiled_route = (
                self._engine.compiled.routes.get(step.name, {}).get(route_name)
                or self._engine.compiled.global_routes.get(route_name)
            )
            if compiled_route is None:
                continue
            routes[route_name] = ProviderRoute(
                summary=compiled_route.summary,
                required_writes=tuple(compiled_route.required_writes or ()),
                explicit_required_writes=explicit_route_required_writes(compiled_route),
                handoff=compiled_route.handoff,
                provider_visible=compiled_route.provider_visible,
            )
        return routes

    def available_routes(self, step: "CompiledStep") -> tuple[str, ...]:
        visible_routes: list[str] = []
        for route_name in step.available_routes:
            compiled_route = (
                self._engine.compiled.routes.get(step.name, {}).get(route_name)
                or self._engine.compiled.global_routes.get(route_name)
            )
            if compiled_route is None or not compiled_route.provider_visible:
                continue
            visible_routes.append(route_name)
        return tuple(visible_routes)


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
    ) -> StepExecutionResult:
        runtime = context_runtime(context)
        runtime.set_state(state)
        runtime.set_active_worklist(step.scope_name)
        initial_artifacts = self._engine._resolve_artifacts(context)
        runtime.set_artifacts(initial_artifacts)
        self._engine._ensure_required_artifacts(step, initial_artifacts)
        if step.kind == "produce_verify":
            return self._engine._execute_pair_step(step, context, state, pending_handoffs)

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
            scheduled_handoffs = self._engine._schedule_direct_control_handoffs(
                remaining_pending_handoffs,
                control=direct_control,
                context=context,
                source_step=step.name,
            )
            return self._engine._step_result_from_direct_control(
                step=step,
                state=state,
                control=direct_control,
                pending_handoffs=scheduled_handoffs,
            )
        if before_result.event is not None:
            _, remaining_pending_handoffs = self._engine._matching_pending_handoffs(step, context, pending_handoffs)
            finalization = self._engine.route_finalizer.finalize(
                StepFinalizationRequest(
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
                )
            )
            return self._engine._step_result_from_route_finalization(
                step=step,
                route_finalization=finalization,
            )
        if step.kind == "step":
            return self._engine._execute_llm_step(step, context, state, pending_handoffs)
        if step.kind == "workflow":
            return self._engine._execute_workflow_step(step, context, state, pending_handoffs)
        if step.kind in {"python", "operation"}:
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
                scheduled_handoffs = self._engine._schedule_direct_control_handoffs(
                    remaining_pending_handoffs,
                    control=direct_control,
                    context=context,
                    source_step=step.name,
                )
                return self._engine._step_result_from_direct_control(
                    step=step,
                    state=next_state,
                    control=direct_control,
                    pending_handoffs=scheduled_handoffs,
                )
            event = hook_result.event or Event("done")
            finalization = self._engine.route_finalizer.finalize(
                StepFinalizationRequest(
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
                )
            )
            return self._engine._step_result_from_route_finalization(
                step=step,
                route_finalization=finalization,
            )
        raise WorkflowExecutionError(f"unsupported step kind {step.kind!r}")


class RouteFinalizer:
    """Owns step finalization entrypoints."""

    def __init__(self, engine: "Engine") -> None:
        self._engine = engine

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
        if after_redirect is not None:
            route_redirects.append(replace(after_redirect, redirect_index=len(route_redirects) + 1))
            self._engine._ensure_hook_redirect_limit(step, candidate_route=candidate_route, redirects=route_redirects)

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
                final_route = self._engine.compiled.route(step.name, final_event.tag)
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
            source_hook=None,
            source_phase=None,
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
                compiled_route = self._engine.compiled.route(step.name, candidate_event.tag)
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
            compiled_route = self._engine.compiled.route(step.name, event.tag)
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

    def initialize_worklist_selections(self, context: "Context") -> dict[str, "Selection[Any]"]:
        return self._engine._initialize_worklist_selections(context)

    def restore_worklist_selections(
        self,
        context: "Context",
        snapshots: "Mapping[str, SelectionSnapshot]",
    ) -> dict[str, "Selection[Any]"]:
        return self._engine._restore_worklist_selections(context, snapshots)


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
        context: "Context",
        run_folder: "Path",
        step_name: str,
        step_visit: int,
    ):
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
                event_sink=self._engine.runtime_event_sink,
            )
        ) as runtime:
            yield runtime


class WorkflowInvoker:
    """Owns child-workflow invocation entrypoints."""

    def __init__(self, engine: "Engine") -> None:
        self._engine = engine

    def run_child_step(self, step: "CompiledStep", context: "Context") -> Any:
        return self._engine._run_workflow_step(step, context)
