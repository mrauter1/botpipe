"""Deterministic workflow execution engine."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import importlib
import inspect
import json
from pathlib import Path
from typing import Any, Callable, Literal, Mapping
from uuid import uuid4

from pydantic import BaseModel, TypeAdapter

from .artifacts import Artifact, ArtifactHandle, ResolvedArtifacts, resolve_artifact_template
from .compiler import CompiledRoute, CompiledStep, CompiledWorkflow, compile_workflow
from .effects import Advance, Handoff, Refresh, ResetCompletion, SetStatus
from .context import Context
from .engine_collaborators import (
    ArtifactGuard,
    CheckpointManager,
    HookRunner,
    OperationRecorder,
    RouteFinalizer,
    SessionRuntime,
    StateRuntime,
    StepFinalizationRequest,
    StepDispatcher,
    WorkflowInvoker,
)
from .extensions import BoundWorkflowExtension, HookRouteRedirect, RunBinding, StepFinish, StepStart, TerminalFinish
from .errors import FailureContext, MissingArtifactError, ProviderExecutionError, StepExecutionError, WorkflowExecutionError
from .operations import serialize_context_values
from .primitives import AWAIT_INPUT, Checkpoint, Event, FAIL, FINISH, Fail, Goto, Outcome, PendingHandoff, RequestInput
from .prompts import Prompt, PromptRegistry, ResolvedPrompt
from .providers.models import (
    LLMRequest,
    ProducerRequest,
    ProviderArtifactRef,
    ProviderReadableRef,
    ProviderRoute,
    StepProviderUsage,
    VerifierRequest,
)
from .providers.protocols import LLMProvider
from .providers.retries import ProviderRetryPolicy, build_retry_feedback
from .route_required_writes import (
    effective_route_required_writes,
    effective_route_required_writes_map,
    explicit_route_required_writes,
)
from .routes import normalize_route_spec
from .stores.protocols import (
    CheckpointStore,
    PendingInput,
    SessionBinding,
    SessionSnapshot,
    SessionStore,
    normalize_session_snapshot,
)
from .step_state import DEFAULT_REPLAN_ROUTE_TAGS, DEFAULT_REWORK_ROUTE_TAGS
from .steps import ChildWorkflowStep
from .worklists import Selection, SelectionSnapshot


@dataclass(frozen=True, slots=True)
class RunResult:
    """Final run outcome."""

    terminal: str
    state: BaseModel
    history: tuple[str, ...]
    checkpoint: Checkpoint | None = None
    last_event: Event | None = None
    last_outcome: Outcome | None = None
    last_transition: "StepFinalizationRecord | None" = None
    output: Any | None = None
    output_validation_error: str | None = None


@dataclass(frozen=True, slots=True)
class StepFinalizationRecord:
    """Summary of the most recent finalized step transition."""

    candidate_route: str | None = None
    final_route: str | None = None
    runtime_control: str | None = None
    target_step: str | None = None
    terminal: str | None = None
    provider_attributable: bool = False
    source_hook: str | None = None
    source_phase: str | None = None
    hook_route_redirects: tuple[HookRouteRedirect, ...] = ()


@dataclass(frozen=True, slots=True)
class _HookSnapshot:
    state: BaseModel | None
    step_state: BaseModel | dict[str, Any] | None
    item_state: BaseModel | dict[str, Any] | None
    step_item_state: BaseModel | dict[str, Any] | None
    session: SessionSnapshot


@dataclass(frozen=True, slots=True)
class _DirectRuntimeControl:
    control: str
    destination: str
    pending_input: PendingInput | None = None
    target_step: str | None = None
    terminal: str | None = None
    handoff: str | None = None
    source_hook: str | None = None
    source_phase: str | None = None


class Engine:
    """Strict workflow engine."""

    max_hook_redirects = 16

    def __init__(
        self,
        workflow: type[Any] | CompiledWorkflow,
        *,
        provider: LLMProvider,
        session_store: SessionStore,
        checkpoint_store: CheckpointStore,
        prompt_registry: PromptRegistry | None = None,
        operation_replay_mismatch_behavior: Literal["warn", "fail"] = "warn",
        runtime_extension_factories: Sequence[Callable[[RunBinding], BoundWorkflowExtension]] = (),
        hook_event_sink: Callable[[str, Mapping[str, Any]], None] | None = None,
        runtime_event_sink: Callable[[str, Mapping[str, Any]], None] | None = None,
    ) -> None:
        self.compiled = workflow if isinstance(workflow, CompiledWorkflow) else compile_workflow(workflow)
        self.provider = provider
        self.session_store = session_store
        self.checkpoint_store = checkpoint_store
        self.prompt_registry = prompt_registry
        self.operation_replay_mismatch_behavior = operation_replay_mismatch_behavior
        self.runtime_extension_factories = tuple(runtime_extension_factories)
        self.hook_event_sink = hook_event_sink
        self.runtime_event_sink = runtime_event_sink
        self.step_dispatcher = StepDispatcher(self)
        self.route_finalizer = RouteFinalizer(self)
        self.hook_runner = HookRunner(self)
        self.artifact_guard = ArtifactGuard(self)
        self.state_runtime = StateRuntime(self)
        self.session_runtime = SessionRuntime(self)
        self.checkpoint_manager = CheckpointManager(self)
        self.operation_recorder = OperationRecorder(self)
        self.workflow_invoker = WorkflowInvoker(self)

    def run(
        self,
        *,
        task_id: str,
        run_id: str,
        task_folder: Path,
        workflow_folder: Path | None = None,
        run_folder: Path,
        package_folder: Path | None = None,
        root: Path | None = None,
        params: BaseModel | None = None,
        workflow_params: Mapping[str, Any] | None = None,
        workflow_input: BaseModel | None = None,
        workflow_invoker: Callable[..., Any] | None = None,
        initial_state: BaseModel | None = None,
        resume: bool = False,
        answer: str | None = None,
        max_steps: int = 100,
    ) -> RunResult:
        resolved_workflow_folder = workflow_folder or task_folder / f"wf_{self.compiled.workflow_name}"
        resolved_package_folder = package_folder or (root.resolve() if root is not None else task_folder)
        workflow_instance = self.compiled.workflow_cls()
        binding = self._build_run_binding(
            task_id=task_id,
            run_id=run_id,
            task_folder=task_folder,
            workflow_folder=resolved_workflow_folder,
            run_folder=run_folder,
            package_folder=resolved_package_folder,
            root=root,
        )
        extensions = self._bind_extensions(binding)
        history: list[str] = []
        current_step_name: str | None = None
        state: BaseModel | None = None
        current_answer: str | None = None
        current_input_response: Any | None = None
        selections: dict[str, Selection[Any]] = {}
        values: dict[str, Any] = {}
        step_states: dict[str, BaseModel | dict[str, Any]] = {}
        item_states: dict[str, BaseModel | dict[str, Any]] = {}
        step_item_states: dict[str, dict[str, BaseModel | dict[str, Any]]] = {}
        pending_handoffs: tuple[PendingHandoff, ...] = ()
        checkpoint: Checkpoint | None = None
        terminal_failure_handled = False

        last_event: Event | None = None
        last_outcome: Outcome | None = None
        last_transition: StepFinalizationRecord | None = None
        try:
            if resume:
                self._assert_resume_topology_compatible(run_folder)
                checkpoint = self.checkpoint_store.load()
                if checkpoint is None:
                    raise WorkflowExecutionError("resume requested but no checkpoint is available")
                self.session_runtime.restore(normalize_session_snapshot(checkpoint.session_bindings, run_id=run_id))
                state = checkpoint.state
                values = deepcopy(checkpoint.values or {})
                step_states = deepcopy(checkpoint.step_states or {})
                item_states = deepcopy(checkpoint.item_states or {})
                step_item_states = deepcopy(checkpoint.step_item_states or {})
                selection_context = Context(
                    root=root,
                    task_id=task_id,
                    run_id=run_id,
                    workflow_name=self.compiled.workflow_name,
                    task_folder=task_folder,
                    workflow_folder=resolved_workflow_folder,
                    run_folder=run_folder,
                    package_folder=resolved_package_folder,
                    state=state,
                    session_store=self.session_store,
                    session_definitions=self.compiled.sessions,
                    worklists=self.compiled.worklists,
                    selections={},
                    params=params,
                    workflow_params=workflow_params,
                    workflow_input=workflow_input,
                    workflow_invoker=workflow_invoker,
                    answer=None,
                    input_response=None,
                    default_session_name=self.compiled.default_session_name,
                    values=values,
                )
                selections = self.state_runtime.restore_worklist_selections(
                    selection_context,
                    checkpoint.worklist_selections or {},
                )
                pending_handoffs = checkpoint.pending_handoffs
                current_step_name = checkpoint.stage
                current_answer = answer if answer is not None else checkpoint.pending_answer
                try:
                    current_input_response = self._resume_input_response(checkpoint=checkpoint, answer=current_answer)
                except Exception as exc:
                    self.checkpoint_manager.save(
                        stage=current_step_name,
                        state=self._state_for_failure(state, exc) or state,
                        values=values,
                        step_states=step_states,
                        item_states=item_states,
                        step_item_states=step_item_states,
                        worklist_selections=selections,
                        pending_handoffs=pending_handoffs,
                        pending_input=checkpoint.pending_input,
                        pending_answer=current_answer,
                        failure_context=self._failure_context_for_exception(exc),
                    )
                    raise
            else:
                self.session_runtime.restore(SessionSnapshot(bindings=(), active_keys_by_slot={}))
                state = initial_state if initial_state is not None else self.compiled.new_state()
                context = Context(
                    root=root,
                    task_id=task_id,
                    run_id=run_id,
                    workflow_name=self.compiled.workflow_name,
                    task_folder=task_folder,
                    workflow_folder=resolved_workflow_folder,
                    run_folder=run_folder,
                    package_folder=resolved_package_folder,
                    state=state,
                    session_store=self.session_store,
                    session_definitions=self.compiled.sessions,
                    worklists=self.compiled.worklists,
                    selections=selections,
                    params=params,
                    workflow_params=workflow_params,
                    workflow_input=workflow_input,
                    workflow_invoker=workflow_invoker,
                    answer=None,
                    input_response=None,
                    default_session_name=self.compiled.default_session_name,
                    values=values,
                )
                selections = self.state_runtime.initialize_worklist_selections(context)
                context._set_selections(selections)
                if self.compiled.default_session_open:
                    context.open_session(self.compiled.default_session_name)
                if self.compiled.has_start_hook:
                    workflow_instance.on_start(context)
                state = context.state
                current_step_name = self.compiled.entry_step_name
                current_answer = None
                current_input_response = None

            for _ in range(max_steps):
                assert state is not None
                assert current_step_name is not None
                step = self.compiled.steps[current_step_name]
                context = Context(
                    root=root,
                    task_id=task_id,
                    run_id=run_id,
                    workflow_name=self.compiled.workflow_name,
                    task_folder=task_folder,
                    workflow_folder=resolved_workflow_folder,
                    run_folder=run_folder,
                    package_folder=resolved_package_folder,
                    state=state,
                    session_store=self.session_store,
                    session_definitions=self.compiled.sessions,
                    worklists=self.compiled.worklists,
                    selections=selections,
                    active_worklist=step.scope_name,
                    params=params,
                    workflow_params=workflow_params,
                    workflow_input=workflow_input,
                    workflow_invoker=workflow_invoker,
                    answer=current_answer,
                    input_response=current_input_response,
                    step_name=step.name,
                    default_session_name=self.compiled.default_session_name,
                    values=values,
                )
                current_item_key = self._current_item_state_key(context, step)
                step_state_store = self._ensure_step_state_store(step_states, step)
                self._increment_step_runtime_state(step_state_store)
                context._set_step_state_store(step_state_store)
                item_state_store = self._ensure_item_state_store(item_states, step, item_key=current_item_key)
                step_item_state_store = self._ensure_step_item_state_store(
                    step_item_states,
                    step,
                    item_key=current_item_key,
                )
                if item_state_store is not None:
                    context._set_item_state_store(item_state_store)
                if step_item_state_store is not None:
                    self._increment_step_runtime_state(step_item_state_store)
                    context._set_step_item_state_store(step_item_state_store)
                context._set_values(values)
                context._set_meta(
                    {
                        "step": {
                            "name": step.name,
                            "visits": self._step_runtime_visits(step_state_store),
                            "last_route": getattr(step_state_store, "last_route", None),
                        }
                    }
                )
                history.append(step.name)
                step_visit = self._step_execution_visit(step, step_state_store, step_item_state_store)
                scope_name, item_id = self._current_step_scope_item(context, step)
                step_execution_id = self._step_execution_id(
                    step_name=step.name,
                    visit=step_visit,
                    scope_name=scope_name,
                    item_id=item_id,
                )
                self._notify_before_step(
                    extensions,
                    StepStart(
                        binding=binding,
                        step_name=step.name,
                        step_kind=step.kind,
                        state=self._clone_state(state),
                        answer=current_answer,
                        visit=step_visit,
                        step_execution_id=step_execution_id,
                        scope=scope_name,
                        item_id=item_id,
                    ),
                )
                state_before = self._clone_state(state)
                try:
                    with self.operation_recorder.bind_step(
                        context=context,
                        run_folder=run_folder,
                        step_name=step.name,
                        step_visit=self._step_execution_visit(step, step_state_store, step_item_state_store),
                    ):
                        (
                            state,
                            destination,
                            last_event,
                            last_outcome,
                            producer_raw_output,
                            verifier_raw_output,
                            provider_usage,
                            pending_handoffs,
                            candidate_route,
                            final_route,
                            runtime_control,
                            target_step,
                            control_terminal,
                            control_pending_input,
                            control_source_hook,
                            control_source_phase,
                            final_provider_attributable,
                            hook_route_override_from,
                            hook_route_override_to,
                            hook_route_redirects,
                        ) = self.step_dispatcher.execute(step, context, state, pending_handoffs)
                        last_transition = StepFinalizationRecord(
                            candidate_route=candidate_route,
                            final_route=final_route,
                            runtime_control=runtime_control,
                            target_step=target_step,
                            terminal=control_terminal,
                            provider_attributable=bool(final_provider_attributable),
                            source_hook=control_source_hook,
                            source_phase=control_source_phase,
                            hook_route_redirects=hook_route_redirects,
                        )
                        self._notify_after_step(
                            extensions,
                            StepFinish(
                                binding=binding,
                                step_name=step.name,
                                step_kind=step.kind,
                                state_before=state_before,
                                state_after=self._clone_state(state),
                                event=self._clone_event(last_event),
                                outcome=self._clone_outcome(last_outcome),
                                producer_raw_output=producer_raw_output,
                                verifier_raw_output=verifier_raw_output,
                                provider_usage=provider_usage,
                                candidate_route=candidate_route,
                                final_route=final_route,
                                runtime_control=runtime_control,
                                target_step=target_step,
                                terminal=control_terminal,
                                provider_attributable=final_provider_attributable,
                                source_hook=control_source_hook,
                                source_phase=control_source_phase,
                                hook_route_override_from=hook_route_override_from,
                                hook_route_override_to=hook_route_override_to,
                                hook_route_redirects=hook_route_redirects,
                                visit=step_visit,
                                step_execution_id=step_execution_id,
                                scope=scope_name,
                                item_id=item_id,
                            ),
                        )
                except Exception as exc:
                    checkpoint = self.checkpoint_manager.save(
                        stage=current_step_name,
                        state=self._state_for_failure(state, exc),
                        values=values,
                        step_states=step_states,
                        item_states=item_states,
                        step_item_states=step_item_states,
                        worklist_selections=selections,
                        pending_handoffs=self._pending_handoffs_for_exception(exc, pending_handoffs),
                        pending_input=None,
                        pending_answer=current_answer,
                        failure_context=self._failure_context_for_exception(exc),
                    )
                    raise

                current_answer = None
                current_input_response = None
                if destination == FINISH:
                    output, output_validation_error = self._build_workflow_output(context, state)
                    result = RunResult(
                        terminal=FINISH,
                        state=state,
                        history=tuple(history),
                        checkpoint=None,
                        last_event=last_event,
                        last_outcome=last_outcome,
                        last_transition=last_transition,
                        output=output,
                        output_validation_error=output_validation_error,
                    )
                    try:
                        self._notify_terminal(
                            extensions,
                            TerminalFinish(
                                binding=binding,
                                terminal=FINISH,
                                step_name=step.name,
                                state=self._clone_state(state),
                                event=self._clone_event(last_event),
                                outcome=self._clone_outcome(last_outcome),
                            ),
                        )
                    except Exception:
                        checkpoint = self._save_checkpoint(
                            stage=step.name,
                            state=state,
                            values=values,
                            step_states=step_states,
                            item_states=item_states,
                            step_item_states=step_item_states,
                            worklist_selections=selections,
                            pending_handoffs=pending_handoffs,
                            pending_input=None,
                            pending_answer=None,
                        )
                        terminal_failure_handled = True
                        raise
                    self.checkpoint_store.clear()
                    return result
                if destination == AWAIT_INPUT:
                    pending_input = control_pending_input or self._pending_input_from_event(
                        source_step=step.name,
                        event=last_event,
                    )
                    checkpoint = self._save_checkpoint(
                        stage=current_step_name,
                        state=state,
                        values=values,
                        step_states=step_states,
                        item_states=item_states,
                        step_item_states=step_item_states,
                        worklist_selections=selections,
                        pending_handoffs=pending_handoffs,
                        pending_input=pending_input,
                        pending_answer=None,
                    )
                    output, output_validation_error = self._build_workflow_output(context, state)
                    result = RunResult(
                        terminal=AWAIT_INPUT,
                        state=state,
                        history=tuple(history),
                        checkpoint=checkpoint,
                        last_event=last_event,
                        last_outcome=last_outcome,
                        last_transition=last_transition,
                        output=output,
                        output_validation_error=output_validation_error,
                    )
                    try:
                        self._notify_terminal(
                            extensions,
                            TerminalFinish(
                                binding=binding,
                                terminal=AWAIT_INPUT,
                                step_name=step.name,
                                state=self._clone_state(state),
                                event=self._clone_event(last_event),
                                outcome=self._clone_outcome(last_outcome),
                            ),
                        )
                    except Exception:
                        terminal_failure_handled = True
                        raise
                    return result
                if destination == FAIL:
                    checkpoint = self._save_checkpoint(
                        stage=current_step_name,
                        state=state,
                        values=values,
                        step_states=step_states,
                        item_states=item_states,
                        step_item_states=step_item_states,
                        worklist_selections=selections,
                        pending_handoffs=pending_handoffs,
                        pending_input=None,
                        pending_answer=None,
                    )
                    output, output_validation_error = self._build_workflow_output(context, state)
                    result = RunResult(
                        terminal=FAIL,
                        state=state,
                        history=tuple(history),
                        checkpoint=checkpoint,
                        last_event=last_event,
                        last_outcome=last_outcome,
                        last_transition=last_transition,
                        output=output,
                        output_validation_error=output_validation_error,
                    )
                    try:
                        self._notify_terminal(
                            extensions,
                            TerminalFinish(
                                binding=binding,
                                terminal=FAIL,
                                step_name=step.name,
                                state=self._clone_state(state),
                                event=self._clone_event(last_event),
                                outcome=self._clone_outcome(last_outcome),
                            ),
                        )
                    except Exception:
                        terminal_failure_handled = True
                        raise
                    return result
                if runtime_control == "goto":
                    checkpoint = self._save_checkpoint(
                        stage=destination,
                        state=state,
                        values=values,
                        step_states=step_states,
                        item_states=item_states,
                        step_item_states=step_item_states,
                        worklist_selections=selections,
                        pending_handoffs=pending_handoffs,
                        pending_input=None,
                        pending_answer=None,
                    )
                current_step_name = destination
            raise WorkflowExecutionError(f"workflow exceeded max_steps={max_steps}")
        except Exception as exc:
            if not terminal_failure_handled:
                fatal_event = TerminalFinish(
                    binding=binding,
                    terminal="fatal",
                    step_name=history[-1] if history else current_step_name,
                    state=self._clone_state(state),
                    event=self._clone_event(last_event),
                    outcome=self._clone_outcome(last_outcome),
                )
                fatal_error = self._notify_fatal(extensions, fatal_event, exc)
                self._notify_terminal(extensions, fatal_event)
                if fatal_error is not None:
                    raise fatal_error from exc
            raise

    def resume(
        self,
        *,
        task_id: str,
        run_id: str,
        task_folder: Path,
        workflow_folder: Path | None = None,
        run_folder: Path,
        package_folder: Path | None = None,
        root: Path | None = None,
        params: BaseModel | None = None,
        workflow_params: Mapping[str, Any] | None = None,
        workflow_input: BaseModel | None = None,
        workflow_invoker: Callable[..., Any] | None = None,
        answer: str | None = None,
        max_steps: int = 100,
    ) -> RunResult:
        return self.run(
            task_id=task_id,
            run_id=run_id,
            task_folder=task_folder,
            workflow_folder=workflow_folder,
            run_folder=run_folder,
            package_folder=package_folder,
            root=root,
            params=params,
            workflow_params=workflow_params,
            workflow_input=workflow_input,
            workflow_invoker=workflow_invoker,
            resume=True,
            answer=answer,
            max_steps=max_steps,
        )

    def _execute_pair_step(
        self,
        step: CompiledStep,
        context: Context,
        state: BaseModel,
        pending_handoffs: tuple[PendingHandoff, ...],
    ) -> tuple[
        BaseModel,
        str,
        Event | None,
        Outcome | None,
        str | None,
        str | None,
        StepProviderUsage | None,
        tuple[PendingHandoff, ...],
        str | None,
        str | None,
        str | None,
        str | None,
        str | None,
        str | None,
        str | None,
        PendingInput | None,
        str | None,
        str | None,
        bool,
        tuple[HookRouteRedirect, ...],
    ]:
        baseline_session = self._resolve_session(step, context)
        route_handoff, remaining_pending_handoffs = self._matching_pending_handoffs(step, context, pending_handoffs)
        retry_feedback: str | None = None
        max_attempts = step.retry_policy.max_attempts
        for attempt in range(1, max_attempts + 1):
            artifacts = self._resolve_artifacts(context)
            context._set_artifacts(artifacts)
            try:
                before_result = self.hook_runner.run_before(
                    step,
                    context,
                    state,
                    artifacts=artifacts,
                    hook=step.before_producer_hook,
                    hook_phase="before_producer",
                )
                state = before_result.state
                context._set_state(state)
                if before_result.result.control is not None:
                    direct_control = self._normalize_direct_runtime_control(
                        step=step,
                        context=context,
                        control=before_result.result.control,
                        hook_name=getattr(step.before_producer_hook, "__name__", type(step.before_producer_hook).__name__),
                        hook_phase="before_producer",
                    )
                    scheduled_handoffs = self._schedule_direct_control_handoffs(
                        remaining_pending_handoffs,
                        control=direct_control,
                        context=context,
                        source_step=step.name,
                    )
                    return (
                        state,
                        direct_control.destination,
                        None,
                        None,
                        None,
                        None,
                        None,
                        scheduled_handoffs,
                        None,
                        None,
                        direct_control.control,
                        direct_control.target_step,
                        direct_control.terminal,
                        direct_control.pending_input,
                        direct_control.source_hook,
                        direct_control.source_phase,
                        False,
                        None,
                        None,
                        (),
                    )
                if before_result.result.event is not None:
                    finalization = self.route_finalizer.finalize(
                        StepFinalizationRequest(
                            step=step,
                            context=context,
                            state=state,
                            artifacts=self._resolve_artifacts(context),
                            candidate_event=before_result.result.event,
                            candidate_route_present=False,
                            after_subject=before_result.result.event,
                            pending_handoffs=remaining_pending_handoffs,
                            error_cls=WorkflowExecutionError,
                            provider_attributable=False,
                            after_hook=None,
                        )
                    )
                    return (
                        finalization.state,
                        finalization.destination,
                        finalization.finalized_event,
                        None,
                        None,
                        None,
                        None,
                        finalization.scheduled_handoffs,
                        finalization.candidate_route,
                        finalization.final_route,
                        finalization.runtime_control,
                        finalization.target_step,
                        finalization.terminal,
                        finalization.pending_input,
                        finalization.source_hook,
                        finalization.source_phase,
                        finalization.provider_attributable,
                        finalization.hook_route_override_from,
                        finalization.hook_route_override_to,
                        finalization.hook_route_redirects,
                    )
                (
                    producer_raw_output,
                    verifier_raw_output,
                    outcome,
                    resolved_producer_session,
                    resolved_verifier_session,
                    provider_usage,
                    direct_control_state,
                    direct_control,
                    short_circuit_event,
                ) = self._run_pair_step(
                    step,
                    context,
                    state,
                    artifacts,
                    baseline_session,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    retry_feedback=retry_feedback,
                    route_handoff=route_handoff,
                    consumed_pending_handoffs=remaining_pending_handoffs,
                    restorable_pending_handoffs=pending_handoffs,
                )
                if resolved_producer_session is not None:
                    self._persist_session(resolved_producer_session)
                if resolved_verifier_session is not None:
                    self._persist_session(resolved_verifier_session)
                if direct_control is not None:
                    assert direct_control_state is not None
                    scheduled_handoffs = self._schedule_direct_control_handoffs(
                        remaining_pending_handoffs,
                        control=direct_control,
                        context=context,
                        source_step=step.name,
                    )
                    return (
                        direct_control_state,
                        direct_control.destination,
                        None,
                        None,
                        producer_raw_output,
                        verifier_raw_output,
                        provider_usage,
                        scheduled_handoffs,
                        None,
                        None,
                        direct_control.control,
                        direct_control.target_step,
                        direct_control.terminal,
                        direct_control.pending_input,
                        direct_control.source_hook,
                        direct_control.source_phase,
                        False,
                        None,
                        None,
                        (),
                    )
                if short_circuit_event is not None:
                    assert direct_control_state is not None
                    finalization = self.route_finalizer.finalize(
                        StepFinalizationRequest(
                            step=step,
                            context=context,
                            state=direct_control_state,
                            artifacts=self._resolve_artifacts(context),
                            candidate_event=short_circuit_event,
                            candidate_route_present=False,
                            after_subject=short_circuit_event,
                            pending_handoffs=remaining_pending_handoffs,
                            error_cls=WorkflowExecutionError,
                            provider_attributable=False,
                            after_hook=None,
                        )
                    )
                    return (
                        finalization.state,
                        finalization.destination,
                        finalization.finalized_event,
                        None,
                        producer_raw_output,
                        verifier_raw_output,
                        provider_usage,
                        finalization.scheduled_handoffs,
                        finalization.candidate_route,
                        finalization.final_route,
                        finalization.runtime_control,
                        finalization.target_step,
                        finalization.terminal,
                        finalization.pending_input,
                        finalization.source_hook,
                        finalization.source_phase,
                        finalization.provider_attributable,
                        finalization.hook_route_override_from,
                        finalization.hook_route_override_to,
                        finalization.hook_route_redirects,
                    )
                assert outcome is not None
                event = self._apply_outcome(step, context, artifacts, state, outcome)
                next_state = (
                    state
                    if event is not None
                    else self._normalize_state(state, self._apply_outcome_handler(step, state, outcome, artifacts))
                )
                final_event = event or Event(outcome.tag, reason=outcome.reason, question=outcome.question)
                artifacts = self._resolve_artifacts(context)
                finalization = self.route_finalizer.finalize(
                    StepFinalizationRequest(
                        step=step,
                        context=context,
                        state=next_state,
                        artifacts=artifacts,
                        candidate_event=final_event,
                        candidate_route=final_event.tag,
                        candidate_route_present=True,
                        after_subject=outcome,
                        pending_handoffs=remaining_pending_handoffs,
                        error_cls=ProviderExecutionError,
                        provider_attributable=True,
                        after_hook=step.after_verifier_hook,
                        after_hook_phase="after_verifier",
                    )
                )
                return (
                    finalization.state,
                    finalization.destination,
                    finalization.finalized_event,
                    outcome,
                    producer_raw_output,
                    verifier_raw_output,
                    provider_usage,
                    finalization.scheduled_handoffs,
                    finalization.candidate_route,
                    finalization.final_route,
                    finalization.runtime_control,
                    finalization.target_step,
                    finalization.terminal,
                    finalization.pending_input,
                    finalization.source_hook,
                    finalization.source_phase,
                    finalization.provider_attributable,
                    finalization.hook_route_override_from,
                    finalization.hook_route_override_to,
                    finalization.hook_route_redirects,
                )
            except Exception as exc:
                next_feedback = self._next_retry_feedback(step, exc, attempt=attempt)
                if next_feedback is None:
                    raise
                retry_feedback = next_feedback
        raise AssertionError("pair-step retry loop exhausted without returning or raising")

    def _execute_llm_step(
        self,
        step: CompiledStep,
        context: Context,
        state: BaseModel,
        pending_handoffs: tuple[PendingHandoff, ...],
    ) -> tuple[
        BaseModel,
        str,
        Event | None,
        Outcome | None,
        str | None,
        str | None,
        StepProviderUsage | None,
        tuple[PendingHandoff, ...],
        str | None,
        str | None,
        str | None,
        str | None,
        str | None,
        str | None,
        str | None,
        PendingInput | None,
        str | None,
        str | None,
        bool,
        tuple[HookRouteRedirect, ...],
    ]:
        baseline_session = self._resolve_session(step, context)
        route_handoff, remaining_pending_handoffs = self._matching_pending_handoffs(step, context, pending_handoffs)
        retry_feedback: str | None = None
        max_attempts = step.retry_policy.max_attempts
        for attempt in range(1, max_attempts + 1):
            artifacts = self._resolve_artifacts(context)
            try:
                outcome, resolved_session, provider_usage = self._run_llm_step(
                    step,
                    context,
                    artifacts,
                    baseline_session,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    retry_feedback=retry_feedback,
                    route_handoff=route_handoff,
                    consumed_pending_handoffs=remaining_pending_handoffs,
                    restorable_pending_handoffs=pending_handoffs,
                )
                event = self._apply_outcome(step, context, artifacts, state, outcome)
                next_state = (
                    state
                    if event is not None
                    else self._normalize_state(state, self._apply_outcome_handler(step, state, outcome, artifacts))
                )
                final_event = event or Event(outcome.tag, reason=outcome.reason, question=outcome.question)
                artifacts = self._resolve_artifacts(context)
                finalization = self.route_finalizer.finalize(
                    StepFinalizationRequest(
                        step=step,
                        context=context,
                        state=next_state,
                        artifacts=artifacts,
                        candidate_event=final_event,
                        candidate_route=final_event.tag,
                        candidate_route_present=True,
                        after_subject=outcome,
                        pending_handoffs=remaining_pending_handoffs,
                        error_cls=ProviderExecutionError,
                        provider_attributable=True,
                    )
                )
                self._persist_session(resolved_session)
                return (
                    finalization.state,
                    finalization.destination,
                    finalization.finalized_event,
                    outcome,
                    outcome.raw_output,
                    None,
                    provider_usage,
                    finalization.scheduled_handoffs,
                    finalization.candidate_route,
                    finalization.final_route,
                    finalization.runtime_control,
                    finalization.target_step,
                    finalization.terminal,
                    finalization.pending_input,
                    finalization.source_hook,
                    finalization.source_phase,
                    finalization.provider_attributable,
                    finalization.hook_route_override_from,
                    finalization.hook_route_override_to,
                    finalization.hook_route_redirects,
                )
            except Exception as exc:
                next_feedback = self._next_retry_feedback(step, exc, attempt=attempt)
                if next_feedback is None:
                    raise
                retry_feedback = next_feedback
        raise AssertionError("llm-step retry loop exhausted without returning or raising")

    def _execute_workflow_step(
        self,
        step: CompiledStep,
        context: Context,
        state: BaseModel,
        pending_handoffs: tuple[PendingHandoff, ...],
    ) -> tuple[
        BaseModel,
        str,
        Event | None,
        Outcome | None,
        str | None,
        str | None,
        StepProviderUsage | None,
        tuple[PendingHandoff, ...],
        str | None,
        str | None,
        str | None,
        str | None,
        str | None,
        str | None,
        str | None,
        PendingInput | None,
        str | None,
        str | None,
        bool,
        tuple[HookRouteRedirect, ...],
    ]:
        _, remaining_pending_handoffs = self._matching_pending_handoffs(step, context, pending_handoffs)
        child_result = self.workflow_invoker.run_child_step(step, context)
        event = self._map_workflow_step_result(child_result)
        try:
            self._validate_event(step, event, provider_attributable=False, error_cls=WorkflowExecutionError)
        except WorkflowExecutionError as exc:
            annotated = self._annotate_execution_error(
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
        finalization = self.route_finalizer.finalize(
            StepFinalizationRequest(
                step=step,
                context=context,
                state=state,
                artifacts=self._resolve_artifacts(context),
                candidate_event=event,
                candidate_route=event.tag,
                candidate_route_present=True,
                after_subject=event,
                pending_handoffs=remaining_pending_handoffs,
                error_cls=WorkflowExecutionError,
                provider_attributable=False,
            )
        )
        return (
            finalization.state,
            finalization.destination,
            finalization.finalized_event,
            None,
            None,
            None,
            None,
            finalization.scheduled_handoffs,
            finalization.candidate_route,
            finalization.final_route,
            finalization.runtime_control,
            finalization.target_step,
            finalization.terminal,
            finalization.pending_input,
            finalization.source_hook,
            finalization.source_phase,
            finalization.provider_attributable,
            finalization.hook_route_override_from,
            finalization.hook_route_override_to,
            finalization.hook_route_redirects,
        )

    def _run_pair_step(
        self,
        step: CompiledStep,
        context: Context,
        state: BaseModel,
        artifacts: ResolvedArtifacts,
        session: SessionBinding | None,
        *,
        attempt: int,
        max_attempts: int,
        retry_feedback: str | None,
        route_handoff: str | None,
        consumed_pending_handoffs: tuple[PendingHandoff, ...],
        restorable_pending_handoffs: tuple[PendingHandoff, ...],
    ) -> tuple[
        str,
        str | None,
        Outcome | None,
        SessionBinding | None,
        SessionBinding | None,
        StepProviderUsage,
        BaseModel | None,
        _DirectRuntimeControl | None,
        Event | None,
    ]:
        producer_prompt = self._resolve_prompt(step.producer_prompt)
        self._emit_provider_attempt_event(
            "provider_attempt_started",
            step=step,
            context=context,
            turn_kind="producer",
            attempt=attempt,
        )
        try:
            producer_response = self.provider.run_producer(
                ProducerRequest(
                    step_name=step.name,
                    producer_prompt=producer_prompt,
                    context=context,
                    artifacts=artifacts,
                    session=session,
                    **self._request_pair_producer_contract(
                        step,
                        context=context,
                        artifacts=artifacts,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        retry_feedback=retry_feedback,
                        route_handoff=route_handoff,
                    ),
                )
            )
        except Exception as exc:
            if route_handoff is not None:
                setattr(exc, "pending_handoffs", restorable_pending_handoffs)
            self._emit_provider_attempt_failed(
                step=step,
                context=context,
                turn_kind="producer",
                attempt=attempt,
                exc=exc,
            )
            raise
        self._emit_provider_attempt_finished(
            step=step,
            context=context,
            turn_kind="producer",
            attempt=attempt,
            token_usage=producer_response.usage,
        )
        self._append_logs(step, artifacts, producer_response.raw_output)
        if producer_response.session is not None:
            self._persist_session(producer_response.session)
        after_producer_result = self.hook_runner.run_after(
            step,
            context,
            state=state,
            artifacts=self._resolve_artifacts(context),
            subject=producer_response.raw_output,
            candidate_event=None,
            hook=step.after_producer_hook,
            hook_phase="after_producer",
        )
        next_state = after_producer_result.state
        context._set_state(next_state)
        if after_producer_result.result.control is not None:
            direct_control = self._normalize_direct_runtime_control(
                step=step,
                context=context,
                control=after_producer_result.result.control,
                hook_name=getattr(step.after_producer_hook, "__name__", type(step.after_producer_hook).__name__),
                hook_phase="after_producer",
            )
            return (
                producer_response.raw_output,
                None,
                None,
                producer_response.session or session,
                None,
                StepProviderUsage(producer=producer_response.usage),
                next_state,
                direct_control,
                None,
            )
        if after_producer_result.result.event is not None:
            return (
                producer_response.raw_output,
                None,
                None,
                producer_response.session or session,
                None,
                StepProviderUsage(producer=producer_response.usage),
                next_state,
                None,
                after_producer_result.result.event,
            )

        try:
            review_artifacts = self._resolve_artifacts(context)
            context._set_artifacts(review_artifacts)
            self._ensure_named_artifacts_exist(step.verifier_requires, review_artifacts, step_name=step.name)
            before_verifier_result = self.hook_runner.run_before(
                step,
                context,
                next_state,
                artifacts=review_artifacts,
                hook=step.before_verifier_hook,
                hook_phase="before_verifier",
            )
            review_state = before_verifier_result.state
            context._set_state(review_state)
            if before_verifier_result.result.control is not None:
                direct_control = self._normalize_direct_runtime_control(
                    step=step,
                    context=context,
                    control=before_verifier_result.result.control,
                    hook_name=getattr(step.before_verifier_hook, "__name__", type(step.before_verifier_hook).__name__),
                    hook_phase="before_verifier",
                )
                return (
                    producer_response.raw_output,
                    None,
                    None,
                    producer_response.session or session,
                    None,
                    StepProviderUsage(producer=producer_response.usage),
                    review_state,
                    direct_control,
                    None,
                )
            if before_verifier_result.result.event is not None:
                return (
                    producer_response.raw_output,
                    None,
                    None,
                    producer_response.session or session,
                    None,
                    StepProviderUsage(producer=producer_response.usage),
                    review_state,
                    None,
                    before_verifier_result.result.event,
                )
            verifier_prompt = self._resolve_prompt(step.verifier_prompt)
            verifier_session = self._resolve_pair_review_session(
                step,
                context,
                producer_session=producer_response.session or session,
            )
            self._emit_provider_attempt_event(
                "provider_attempt_started",
                step=step,
                context=context,
                turn_kind="verifier",
                attempt=attempt,
            )
            try:
                verifier_response = self.provider.run_verifier(
                    VerifierRequest(
                        step_name=step.name,
                        verifier_prompt=verifier_prompt,
                        producer_raw_output=producer_response.raw_output,
                        context=context,
                        artifacts=review_artifacts,
                        session=verifier_session,
                        **self._request_pair_verifier_contract(
                            step,
                            context=context,
                            artifacts=review_artifacts,
                            attempt=attempt,
                            max_attempts=max_attempts,
                            retry_feedback=retry_feedback,
                            route_handoff=route_handoff,
                        ),
                    )
                )
                self._validate_outcome(step, verifier_response.outcome)
            except Exception as exc:
                if route_handoff is not None:
                    setattr(exc, "pending_handoffs", restorable_pending_handoffs)
                self._emit_provider_attempt_failed(
                    step=step,
                    context=context,
                    turn_kind="verifier",
                    attempt=attempt,
                    exc=exc,
                )
                raise
            self._emit_provider_attempt_finished(
                step=step,
                context=context,
                turn_kind="verifier",
                attempt=attempt,
                token_usage=verifier_response.usage,
            )
        except Exception as exc:
            if not isinstance(getattr(exc, "pending_handoffs", None), tuple):
                setattr(exc, "pending_handoffs", consumed_pending_handoffs)
            raise
        return (
            producer_response.raw_output,
            verifier_response.outcome.raw_output,
            verifier_response.outcome,
            producer_response.session or session,
            verifier_response.session or verifier_session,
            StepProviderUsage(
                producer=producer_response.usage,
                verifier=verifier_response.usage,
            ),
            None,
            None,
            None,
        )

    def _run_llm_step(
        self,
        step: CompiledStep,
        context: Context,
        artifacts: ResolvedArtifacts,
        session: SessionBinding | None,
        *,
        attempt: int,
        max_attempts: int,
        retry_feedback: str | None,
        route_handoff: str | None,
        consumed_pending_handoffs: tuple[PendingHandoff, ...],
        restorable_pending_handoffs: tuple[PendingHandoff, ...],
    ) -> tuple[Outcome, SessionBinding | None, StepProviderUsage]:
        prompt = self._resolve_prompt(step.producer_prompt)
        self._emit_provider_attempt_event(
            "provider_attempt_started",
            step=step,
            context=context,
            turn_kind="llm",
            attempt=attempt,
        )
        try:
            response = self.provider.run_llm(
                LLMRequest(
                    step_name=step.name,
                    prompt=prompt,
                    context=context,
                    artifacts=artifacts,
                    session=session,
                    **self._request_control_contract(
                        step,
                        context=context,
                        artifacts=artifacts,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        retry_feedback=retry_feedback,
                        route_handoff=route_handoff,
                    ),
                )
            )
            self._validate_outcome(step, response.outcome)
        except Exception as exc:
            if route_handoff is not None:
                setattr(exc, "pending_handoffs", restorable_pending_handoffs)
            self._emit_provider_attempt_failed(
                step=step,
                context=context,
                turn_kind="llm",
                attempt=attempt,
                exc=exc,
            )
            if not isinstance(getattr(exc, "pending_handoffs", None), tuple):
                setattr(exc, "pending_handoffs", consumed_pending_handoffs)
            raise
        self._emit_provider_attempt_finished(
            step=step,
            context=context,
            turn_kind="llm",
            attempt=attempt,
            token_usage=response.usage,
        )
        self._append_logs(step, artifacts, response.outcome.raw_output)
        return response.outcome, response.session or session, StepProviderUsage(llm=response.usage)

    def _apply_outcome(
        self,
        step: CompiledStep,
        context: Context,
        artifacts: ResolvedArtifacts,
        state: BaseModel,
        outcome: Outcome,
    ) -> Event | None:
        if self.compiled.middleware is None:
            return None
        event = self.compiled.middleware(state, outcome)
        if event is not None and not isinstance(event, Event):
            raise ProviderExecutionError("middleware must return Event or None")
        if event is not None:
            try:
                self._validate_event(step, event, provider_attributable=True, error_cls=ProviderExecutionError)
            except WorkflowExecutionError as exc:
                annotated = self._annotate_execution_error(exc, checkpoint_state=state)
                if annotated is exc:
                    raise
                raise annotated from exc
        return event

    def _apply_outcome_handler(
        self,
        step: CompiledStep,
        state: BaseModel,
        outcome: Outcome,
        artifacts: ResolvedArtifacts,
    ) -> BaseModel:
        if step.outcome_handler is None:
            return state
        next_state = step.outcome_handler(state, outcome, artifacts)
        if not isinstance(next_state, BaseModel):
            raise WorkflowExecutionError(f"handler for step {step.name!r} must return a pydantic model")
        return next_state

    def _normalize_direct_runtime_control(
        self,
        *,
        step: CompiledStep,
        context: Context,
        control: RequestInput | Goto | Fail,
        hook_name: str,
        hook_phase: str,
    ) -> _DirectRuntimeControl:
        if isinstance(control, RequestInput):
            pending_input = self._build_pending_input(step.name, hook_name, hook_phase, control)
            self._emit_runtime_event(
                "hook_runtime_control",
                **self._step_runtime_event_payload(step=step, context=context),
                control="request_input",
                hook=hook_name,
                source_phase=hook_phase,
                question=control.question,
                reason=control.reason,
                pending_input_id=pending_input.pending_input_id,
            )
            return _DirectRuntimeControl(
                control="request_input",
                destination=AWAIT_INPUT,
                pending_input=pending_input,
                terminal=AWAIT_INPUT,
                source_hook=hook_name,
                source_phase=hook_phase,
            )
        if isinstance(control, Goto):
            target_step = self._resolve_goto_target(control.target)
            self._emit_runtime_event(
                "hook_runtime_control",
                **self._step_runtime_event_payload(step=step, context=context),
                control="goto",
                hook=hook_name,
                source_phase=hook_phase,
                target_step=target_step,
                reason=control.reason,
            )
            return _DirectRuntimeControl(
                control="goto",
                destination=target_step,
                target_step=target_step,
                handoff=control.handoff,
                source_hook=hook_name,
                source_phase=hook_phase,
            )
        self._emit_runtime_event(
            "hook_runtime_control",
            **self._step_runtime_event_payload(step=step, context=context),
            control="fail",
            hook=hook_name,
            source_phase=hook_phase,
            reason=control.reason,
        )
        return _DirectRuntimeControl(
            control="fail",
            destination=FAIL,
            terminal=FAIL,
            source_hook=hook_name,
            source_phase=hook_phase,
        )

    def _build_pending_input(
        self,
        source_step: str,
        source_hook: str | None,
        source_phase: str | None,
        request_input: RequestInput,
    ) -> PendingInput:
        schema_payload, schema_model = self._serialize_pending_input_schema(request_input.input_schema)
        return PendingInput(
            pending_input_id=uuid4().hex,
            source_step=source_step,
            source_hook=source_hook,
            source_phase=source_phase,
            question=request_input.question,
            reason=request_input.reason,
            best_supposition=request_input.best_supposition,
            input_schema=schema_payload,
            input_schema_model=schema_model,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def _pending_input_from_event(
        self,
        *,
        source_step: str,
        event: Event | None,
    ) -> PendingInput | None:
        if event is None or not isinstance(event.question, str) or not event.question.strip():
            return None
        return PendingInput(
            pending_input_id=uuid4().hex,
            source_step=source_step,
            source_phase="provider" if event.tag == "question" else "route",
            question=event.question,
            reason=event.reason or None,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def _serialize_pending_input_schema(
        self,
        input_schema: type[BaseModel] | dict[str, object] | None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        if input_schema is None:
            return None, None
        if isinstance(input_schema, type) and issubclass(input_schema, BaseModel):
            adapter = TypeAdapter(input_schema)
            return adapter.json_schema(), f"{input_schema.__module__}:{input_schema.__qualname__}"
        schema = dict(input_schema)
        self._validate_json_schema_mapping(schema, label="RequestInput.input_schema")
        return schema, None

    def _resolve_goto_target(self, target: str | object) -> str:
        if isinstance(target, str):
            target_step = target.strip()
        else:
            target_step = getattr(target, "name", None)
        if not isinstance(target_step, str) or not target_step:
            raise WorkflowExecutionError("Goto.target must resolve to a declared workflow step")
        if target_step not in self.compiled.steps:
            raise WorkflowExecutionError(f"Goto target {target_step!r} is not a declared workflow step")
        return target_step

    def _validate_hook_event_override(self, step: CompiledStep, event: Event) -> Event:
        self._validate_event(
            step,
            event,
            provider_attributable=False,
            error_cls=WorkflowExecutionError,
        )
        return event

    def _build_hook_redirect_record(
        self,
        *,
        step: CompiledStep,
        context: Context,
        hook_name: str,
        hook_phase: str,
        previous_event: Event,
        next_event: Event,
    ) -> HookRouteRedirect | None:
        if previous_event.tag == next_event.tag:
            return None
        self._emit_hook_event(
            "hook_route_redirected",
            step=step,
            context=context,
            hook=hook_name,
            hook_name=hook_name,
            phase=hook_phase,
            from_route=previous_event.tag,
            to_route=next_event.tag,
        )
        return HookRouteRedirect(
            hook=hook_name,
            phase=hook_phase,
            from_route=previous_event.tag,
            to_route=next_event.tag,
        )

    def _ensure_hook_redirect_limit(
        self,
        step: CompiledStep,
        *,
        candidate_route: str,
        redirects: Sequence[HookRouteRedirect],
    ) -> None:
        if len(redirects) <= self.max_hook_redirects:
            return
        redirect_chain = " -> ".join((candidate_route, *(redirect.to_route for redirect in redirects)))
        raise WorkflowExecutionError(
            f"Hook redirect limit exceeded for step {step.name!r}. "
            f"Possible redirect cycle: {redirect_chain}."
        )

    def _event_context_payload(self, event: Event) -> dict[str, Any]:
        payload: dict[str, Any] = {"tag": event.tag, "reason": event.reason}
        if event.question is not None:
            payload["question"] = event.question
        if event.handoff is not None:
            payload["handoff"] = event.handoff
        return payload

    def _snapshot_hook_context(self, context: Context, state: BaseModel) -> _HookSnapshot:
        return _HookSnapshot(
            state=self._clone_state(state),
            step_state=self._clone_model_or_dict(getattr(context, "_step_state", None)),
            item_state=self._clone_model_or_dict(getattr(context, "_item_state", None)),
            step_item_state=self._clone_model_or_dict(getattr(context, "_step_item_state", None)),
            session=self.session_store.snapshot(),
        )

    def _restore_hook_context(self, context: Context, snapshot: _HookSnapshot) -> None:
        self.session_store.restore(snapshot.session)
        if snapshot.state is not None:
            context._set_state(self._clone_state(snapshot.state))
        self._restore_model_or_dict(getattr(context, "_step_state", None), snapshot.step_state)
        self._restore_model_or_dict(getattr(context, "_item_state", None), snapshot.item_state)
        self._restore_model_or_dict(getattr(context, "_step_item_state", None), snapshot.step_item_state)

    def _resolve_session(self, step: CompiledStep, context: Context) -> SessionBinding | None:
        return self._select_session(step, context)

    def _select_session(self, step: CompiledStep, context: Context) -> SessionBinding | None:
        if step.session_name is None:
            return None
        active_key = self.session_store.snapshot().active_keys_by_slot.get(step.session_name)
        if active_key is not None and active_key.domain in {"explicit_scope", "explicit_key"}:
            binding = context.get_session(step.session_name)
            return binding or context.open_session(step.session_name)
        session_definition = self.compiled.sessions.get(step.session_name)
        continuity = session_definition.continuity if session_definition is not None else None
        binding = context.get_session(step.session_name, continuity=continuity)
        return binding or context.open_session(step.session_name, continuity=continuity)

    def _persist_session(self, binding: SessionBinding | None) -> None:
        if binding is not None:
            self.session_store.upsert(binding)

    def _append_logs(self, step: CompiledStep, artifacts: ResolvedArtifacts, content: str) -> None:
        for name in step.log_artifacts:
            artifacts[name].append(content)

    def _resolve_artifacts(self, context: Context) -> ResolvedArtifacts:
        canonical_handles = {
            name: ArtifactHandle(
                name=self._artifact_display_name(artifact),
                path=resolve_artifact_template(self._runtime_artifact_spec(artifact), context),
                artifact=self._runtime_artifact_spec(artifact),
            )
            for name, artifact in self.compiled.artifacts_by_qualified_name.items()
        }
        handles = dict(canonical_handles)
        for name, artifact in self.compiled.artifacts.items():
            canonical_name = artifact.qualified_name or name
            handles[name] = canonical_handles.get(
                canonical_name,
                ArtifactHandle(
                    name=self._artifact_display_name(artifact),
                    path=resolve_artifact_template(self._runtime_artifact_spec(artifact), context),
                    artifact=self._runtime_artifact_spec(artifact),
                ),
            )
        return ResolvedArtifacts(handles)

    def _ensure_required_artifacts(self, step: CompiledStep, artifacts: ResolvedArtifacts) -> None:
        self._ensure_named_artifacts_exist(step.requires, artifacts, step_name=step.name)

    def _ensure_named_artifacts_exist(
        self,
        names: tuple[str, ...],
        artifacts: ResolvedArtifacts,
        *,
        step_name: str,
    ) -> None:
        for name in names:
            if not artifacts[name].exists():
                raise MissingArtifactError(f"required artifact {name!r} does not exist for step {step_name!r}")

    def _enforce_artifact_contracts(
        self,
        step: CompiledStep,
        context: Context,
        artifacts: ResolvedArtifacts,
        *,
        route_tag: str,
        state: BaseModel,
        error_cls: type[WorkflowExecutionError],
        provider_attributable: bool,
    ) -> None:
        required_names = self._required_output_artifacts(step, route_tag)
        optional_names = tuple(
            name
            for name in step.writes
            if name not in required_names and self._should_validate_optional_output(artifacts[name])
        )
        for name in required_names:
            self._validate_output_artifact(
                step,
                context=context,
                route_tag=route_tag,
                handle=artifacts[name],
                state=state,
                required=True,
                error_cls=error_cls,
                provider_attributable=provider_attributable,
            )
        for name in optional_names:
            self._validate_output_artifact(
                step,
                context=context,
                route_tag=route_tag,
                handle=artifacts[name],
                state=state,
                required=False,
                error_cls=error_cls,
                provider_attributable=provider_attributable,
            )

    def _required_output_artifacts(self, step: CompiledStep, route_tag: str) -> tuple[str, ...]:
        return effective_route_required_writes(
            self.compiled,
            step_name=step.name,
            route_tag=route_tag,
        )

    def _should_validate_optional_output(self, handle: ArtifactHandle) -> bool:
        artifact = handle.artifact
        if artifact is None or artifact.schema is None:
            return False
        return handle.exists()

    def _validate_output_artifact(
        self,
        step: CompiledStep,
        *,
        context: Context,
        route_tag: str,
        handle: ArtifactHandle,
        state: BaseModel,
        required: bool,
        error_cls: type[WorkflowExecutionError],
        provider_attributable: bool,
    ) -> None:
        if required and not handle.exists():
            self._raise_artifact_validation_error(
                error_cls,
                step=step,
                context=context,
                step_name=step.name,
                route_tag=route_tag,
                handle=handle,
                state=state,
                errors=("artifact file does not exist",),
                required=required,
                provider_attributable=provider_attributable,
            )
        result = handle.validate()
        if result.ok:
            return
        self._raise_artifact_validation_error(
            error_cls,
            step=step,
            context=context,
            step_name=step.name,
            route_tag=route_tag,
            handle=handle,
            state=state,
            errors=result.errors,
            required=required,
            provider_attributable=provider_attributable,
        )

    def _raise_artifact_validation_error(
        self,
        error_cls: type[WorkflowExecutionError],
        *,
        step: CompiledStep,
        context: Context,
        step_name: str,
        route_tag: str,
        handle: ArtifactHandle,
        state: BaseModel,
        errors: tuple[str, ...],
        required: bool,
        provider_attributable: bool,
    ) -> None:
        artifact = handle.artifact
        qualified_name = artifact.qualified_name if artifact is not None else None
        retry_kind = "invalid_output_artifact"
        if required and "artifact file does not exist" in errors:
            retry_kind = "missing_required_output_artifact"
        failure_context = {
            "kind": retry_kind,
            "step": step_name,
            "route": route_tag,
            "artifact_name": handle.name,
            "qualified_name": qualified_name,
            "path": str(handle.path),
            "errors": list(errors),
            "provider_attributable": provider_attributable,
        }
        validation_kind = "invalid_artifact"
        if required and "artifact file does not exist" in errors:
            validation_kind = "missing_required_artifact"
        elif any("schema" in error.lower() for error in errors):
            validation_kind = "schema_validation_failure"
        self._emit_runtime_event(
            "artifact_validation_failed",
            **self._step_runtime_event_payload(step=step, context=context),
            route=route_tag,
            artifact_name=handle.name,
            qualified_name=qualified_name,
            path=str(handle.path),
            validation_kind=validation_kind,
            errors=list(errors),
            provider_attributable=provider_attributable,
        )
        message = self._format_artifact_validation_error(
            step_name=step_name,
            route_tag=route_tag,
            handle=handle,
            errors=errors,
        )
        if issubclass(error_cls, StepExecutionError):
            error = error_cls(
                message,
                checkpoint_state=state,
                failure_context=FailureContext(
                    kind=retry_kind,
                    step_name=step_name,
                    candidate_route=route_tag,
                    final_route=route_tag,
                    provider_attributable=provider_attributable,
                    details=failure_context,
                ),
                retry_kind=retry_kind if provider_attributable and issubclass(error_cls, ProviderExecutionError) else None,
            )
        else:
            error = error_cls(message)
            self._annotate_execution_error(
                error,
                checkpoint_state=state,
                failure_context=FailureContext(
                    kind=retry_kind,
                    step_name=step_name,
                    candidate_route=route_tag,
                    final_route=route_tag,
                    provider_attributable=provider_attributable,
                    details=failure_context,
                ),
            )
        raise error

    def _format_artifact_validation_error(
        self,
        *,
        step_name: str,
        route_tag: str,
        handle: ArtifactHandle,
        errors: tuple[str, ...],
    ) -> str:
        artifact = handle.artifact
        qualified_name = artifact.qualified_name if artifact is not None else None
        details = "; ".join(errors)
        if qualified_name is None:
            return (
                f"artifact validation failed for step {step_name!r} route {route_tag!r}: "
                f"artifact={handle.name!r} path={str(handle.path)!r}; {details}"
            )
        return (
            f"artifact validation failed for step {step_name!r} route {route_tag!r}: "
            f"artifact={handle.name!r} qualified={qualified_name!r} path={str(handle.path)!r}; {details}"
        )

    def _resolve_prompt(self, prompt: str | Prompt | None) -> ResolvedPrompt:
        if prompt is None:
            raise WorkflowExecutionError("missing prompt specification")
        if self.prompt_registry is not None:
            return self.prompt_registry.resolve(prompt)
        if isinstance(prompt, Prompt):
            if prompt.source == "inline":
                return ResolvedPrompt(path=prompt.path, text=prompt.text, source="inline")
            if prompt.path is not None:
                candidate = Path(prompt.path)
                if candidate.is_absolute() and candidate.exists():
                    return ResolvedPrompt(path=str(candidate), text=candidate.read_text(encoding="utf-8"), source=prompt.source)
            return ResolvedPrompt(path=prompt.path, text=None, source=prompt.source)
        return ResolvedPrompt(path=prompt, text=None, source="registry")

    def _validate_outcome(self, step: CompiledStep, outcome: Outcome) -> None:
        if not isinstance(outcome, Outcome):
            raise ProviderExecutionError(
                "provider must return Outcome instances",
                failure_context=FailureContext(
                    kind="malformed_provider_output",
                    step_name=step.name,
                    provider_attributable=True,
                    details={"step": step.name, "error": "provider must return Outcome instances"},
                ),
                retry_kind="malformed_provider_output",
            )
        provider_available_routes = self._provider_available_routes_for_step(step)
        if outcome.tag not in provider_available_routes:
            legal_routes = ", ".join(provider_available_routes) or "<none>"
            raise ProviderExecutionError(
                f"provider returned illegal route {outcome.tag!r} for step {step.name!r}; "
                f"legal routes: {legal_routes}",
                failure_context=FailureContext(
                    kind="illegal_route",
                    step_name=step.name,
                    candidate_route=outcome.tag,
                    provider_attributable=True,
                    details={"step": step.name, "route": outcome.tag, "legal_routes": list(step.available_routes)},
                ),
                retry_kind="illegal_route",
            )
        if outcome.tag == "question" and (not isinstance(outcome.question, str) or not outcome.question.strip()):
            raise ProviderExecutionError(
                f"provider returned question route without a non-empty question for step {step.name!r}"
                ,
                failure_context=FailureContext(
                    kind="invalid_payload",
                    step_name=step.name,
                    candidate_route=outcome.tag,
                    provider_attributable=True,
                    details={
                        "step": step.name,
                        "route": outcome.tag,
                        "error": "question route requires a non-empty question field",
                    },
                ),
                retry_kind="invalid_payload",
            )
        if outcome.tag in {"blocked", "failed"} and not outcome.reason.strip():
            raise ProviderExecutionError(
                f"provider returned {outcome.tag!r} route without a non-empty reason for step {step.name!r}"
                ,
                failure_context=FailureContext(
                    kind="invalid_payload",
                    step_name=step.name,
                    candidate_route=outcome.tag,
                    provider_attributable=True,
                    details={
                        "step": step.name,
                        "route": outcome.tag,
                        "error": f"{outcome.tag} route requires a non-empty reason field",
                    },
                ),
                retry_kind="invalid_payload",
            )
        if step.expected_output_validator is None:
            return
        try:
            step.expected_output_validator(outcome.payload)
        except Exception as exc:
            raise ProviderExecutionError(
                f"provider returned invalid payload for step {step.name!r} route {outcome.tag!r}: {exc}",
                failure_context=FailureContext(
                    kind="invalid_payload",
                    step_name=step.name,
                    candidate_route=outcome.tag,
                    provider_attributable=True,
                    details={"step": step.name, "route": outcome.tag, "error": str(exc)},
                ),
                retry_kind="invalid_payload",
            ) from exc

    def _validate_event(
        self,
        step: CompiledStep,
        event: Event,
        *,
        provider_attributable: bool,
        error_cls: type[WorkflowExecutionError] = WorkflowExecutionError,
    ) -> None:
        if not isinstance(event, Event):
            raise WorkflowExecutionError(f"step {step.name!r} must produce Event instances")
        if event.tag not in step.available_routes:
            legal_routes = ", ".join(step.available_routes) or "<none>"
            message = f"step {step.name!r} produced illegal route {event.tag!r}; legal routes: {legal_routes}"
            if provider_attributable:
                raise ProviderExecutionError(
                    message,
                    failure_context=FailureContext(
                        kind="illegal_route",
                        step_name=step.name,
                        candidate_route=event.tag,
                        provider_attributable=True,
                        details={
                            "step": step.name,
                            "route": event.tag,
                            "legal_routes": list(step.available_routes),
                            "provider_attributable": True,
                        },
                    ),
                    retry_kind="illegal_route",
                )
            raise error_cls(message)
        if event.tag == "question" and (not isinstance(event.question, str) or not event.question.strip()):
            message = f"step {step.name!r} produced question route without a non-empty question"
            if provider_attributable:
                raise ProviderExecutionError(
                    message,
                    failure_context=FailureContext(
                        kind="invalid_payload",
                        step_name=step.name,
                        candidate_route=event.tag,
                        provider_attributable=True,
                        details={
                            "step": step.name,
                            "route": event.tag,
                            "error": "question route requires a non-empty question field",
                            "provider_attributable": True,
                        },
                    ),
                    retry_kind="invalid_payload",
                )
            raise error_cls(message)
        if event.tag in {"blocked", "failed"} and not event.reason.strip():
            message = f"step {step.name!r} produced {event.tag!r} route without a non-empty reason"
            if provider_attributable:
                raise ProviderExecutionError(
                    message,
                    failure_context=FailureContext(
                        kind="invalid_payload",
                        step_name=step.name,
                        candidate_route=event.tag,
                        provider_attributable=True,
                        details={
                            "step": step.name,
                            "route": event.tag,
                            "error": f"{event.tag} route requires a non-empty reason field",
                            "provider_attributable": True,
                        },
                    ),
                    retry_kind="invalid_payload",
                )
            raise error_cls(message)

    def _request_control_contract(
        self,
        step: CompiledStep,
        *,
        context: Context,
        artifacts: ResolvedArtifacts,
        attempt: int,
        max_attempts: int,
        retry_feedback: str | None,
        route_handoff: str | None,
    ) -> dict[str, Any]:
        return {
            "expected_output_schema": deepcopy(step.expected_output_schema),
            "available_routes": self._provider_available_routes_for_step(step),
            "routes": deepcopy(self._routes_for_step(step)),
            "readable_artifacts": self._provider_readable_refs(step.reads, artifacts, context=context),
            "required_artifacts": self._provider_artifact_refs(step.requires, artifacts),
            "writable_artifacts": self._provider_artifact_refs(step.writes, artifacts),
            "route_required_writes": self._route_required_writes_for_step(step),
            "retry_feedback": retry_feedback,
            "route_handoff": route_handoff,
            "attempt": attempt,
            "max_attempts": max_attempts,
        }

    def _request_pair_producer_contract(
        self,
        step: CompiledStep,
        *,
        context: Context,
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
            "readable_artifacts": self._provider_readable_refs(step.producer_reads, artifacts, context=context),
            "required_artifacts": self._provider_artifact_refs(step.producer_requires, artifacts),
            "writable_artifacts": self._provider_artifact_refs(step.producer_writes, artifacts),
            "route_required_writes": {},
            "retry_feedback": retry_feedback,
            "route_handoff": route_handoff,
            "attempt": attempt,
            "max_attempts": max_attempts,
        }

    def _request_pair_verifier_contract(
        self,
        step: CompiledStep,
        *,
        context: Context,
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
            "available_routes": self._provider_available_routes_for_step(step),
            "routes": deepcopy(self._routes_for_step(step)),
            "readable_artifacts": self._provider_readable_refs(readable_names, artifacts, context=context),
            "required_artifacts": self._provider_artifact_refs(step.verifier_requires, artifacts),
            "writable_artifacts": self._provider_artifact_refs(writable_names, artifacts),
            "route_required_writes": self._route_required_writes_for_step(step),
            "retry_feedback": retry_feedback,
            "route_handoff": route_handoff,
            "attempt": attempt,
            "max_attempts": max_attempts,
        }

    def _provider_artifact_ref(self, name: str, handle: ArtifactHandle) -> ProviderArtifactRef:
        artifact = handle.artifact
        qualified_name = (
            artifact.qualified_name
            if artifact is not None and isinstance(artifact.qualified_name, str) and artifact.qualified_name
            else name
        )
        kind = artifact.kind if artifact is not None else "text"
        required = artifact.required if artifact is not None else False
        schema_name = self._artifact_schema_name(artifact)
        return ProviderArtifactRef(
            name=handle.name,
            qualified_name=qualified_name,
            path=str(handle.path),
            kind=kind,
            required=required,
            exists=handle.exists(),
            schema_name=schema_name,
        )

    def _provider_artifact_refs(
        self,
        names: tuple[str, ...],
        artifacts: ResolvedArtifacts,
    ) -> tuple[ProviderArtifactRef, ...]:
        return tuple(
            self._provider_artifact_ref(
                resolved_name,
                artifacts[resolved_name],
            )
            for resolved_name in (self._artifact_lookup_name(name) for name in names)
        )

    def _provider_readable_refs(
        self,
        names: tuple[str, ...],
        artifacts: ResolvedArtifacts,
        *,
        context: Context,
    ) -> tuple[ProviderReadableRef, ...]:
        return tuple(self._provider_readable_ref(name, artifacts, context=context) for name in names)

    def _provider_readable_ref(
        self,
        name: str,
        artifacts: ResolvedArtifacts,
        *,
        context: Context,
    ) -> ProviderReadableRef:
        name = self._artifact_lookup_name(name)
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
                schema_name=self._artifact_schema_name(artifact),
            )
        workspace_path = self._resolve_workspace_read_path(name, context=context)
        return ProviderReadableRef(
            name=name,
            path=str(workspace_path),
            exists=workspace_path.exists(),
            declared_artifact=False,
        )

    def _resolve_workspace_read_path(self, raw_path: str, *, context: Context) -> Path:
        candidate = Path(raw_path)
        if candidate.is_absolute():
            return candidate
        return (context.root / candidate).resolve()

    @staticmethod
    def _artifact_lookup_name(name: object) -> str:
        if isinstance(name, str):
            return name
        qualified_name = getattr(name, "qualified_name", None)
        if isinstance(qualified_name, str) and qualified_name:
            return qualified_name
        local_name = getattr(name, "name", None)
        if isinstance(local_name, str) and local_name:
            return local_name
        return str(name)

    def _route_required_writes_for_step(
        self,
        step: CompiledStep,
    ) -> dict[str, tuple[str, ...]]:
        visible_routes = set(self._provider_available_routes_for_step(step))
        return {
            route_tag: required_writes
            for route_tag, required_writes in effective_route_required_writes_map(
                self.compiled,
                step_name=step.name,
            ).items()
            if route_tag in visible_routes
        }

    def _routes_for_step(self, step: CompiledStep) -> dict[str, ProviderRoute]:
        routes: dict[str, ProviderRoute] = {}
        for route_name in self._provider_available_routes_for_step(step):
            compiled_route = (
                self.compiled.routes.get(step.name, {}).get(route_name)
                or self.compiled.global_routes.get(route_name)
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

    def _provider_available_routes_for_step(self, step: CompiledStep) -> tuple[str, ...]:
        visible_routes: list[str] = []
        for route_name in step.available_routes:
            compiled_route = self.compiled.routes.get(step.name, {}).get(route_name) or self.compiled.global_routes.get(route_name)
            if compiled_route is None or not compiled_route.provider_visible:
                continue
            visible_routes.append(route_name)
        return tuple(visible_routes)

    def _resolve_pair_review_session(
        self,
        step: CompiledStep,
        context: Context,
        *,
        producer_session: SessionBinding | None,
    ) -> SessionBinding | None:
        if step.verifier_session_name is None:
            return producer_session
        active_key = self.session_store.snapshot().active_keys_by_slot.get(step.verifier_session_name)
        if active_key is not None and active_key.domain in {"explicit_scope", "explicit_key"}:
            binding = context.get_session(step.verifier_session_name)
            return binding or context.open_session(step.verifier_session_name)
        session_definition = self.compiled.sessions.get(step.verifier_session_name)
        continuity = session_definition.continuity if session_definition is not None else None
        binding = context.get_session(step.verifier_session_name, continuity=continuity)
        return binding or context.open_session(step.verifier_session_name, continuity=continuity)

    @staticmethod
    def _artifact_schema_name(artifact: Artifact | None) -> str | None:
        if artifact is None or artifact.schema is None:
            return None
        if isinstance(artifact.schema, type):
            return artifact.schema.__name__
        if isinstance(artifact.schema, dict):
            return "JSONSchema"
        return type(artifact.schema).__name__

    def _apply_route_effects(self, route: CompiledRoute, context: Context, *, step: CompiledStep) -> str | None:
        destination_override: str | None = None
        for effect in route.effects:
            effect_destination = self._execute_route_effect(effect, context, step=step)
            if effect_destination is not None:
                destination_override = effect_destination
        return destination_override

    def _execute_route_effect(self, effect: object, context: Context, *, step: CompiledStep) -> str | None:
        if isinstance(effect, Handoff):
            return None
        if isinstance(effect, Refresh):
            worklist_name = self._effect_worklist_name(effect)
            worklist = self.compiled.worklists[worklist_name]
            context._set_selection(worklist_name, worklist.refresh_selection(context, context.selection(worklist_name)))
            return None
        if isinstance(effect, ResetCompletion):
            worklist_name = self._effect_worklist_name(effect)
            worklist = self.compiled.worklists[worklist_name]
            context._set_selection(worklist_name, worklist.set_current_status(context, context.selection(worklist_name), None))
            return None
        if isinstance(effect, SetStatus):
            worklist_name = self._effect_worklist_name(effect)
            worklist = self.compiled.worklists[worklist_name]
            context._set_selection(
                worklist_name,
                worklist.set_current_status(context, context.selection(worklist_name), effect.status),
            )
            return None
        if isinstance(effect, Advance):
            return self._advance_worklist(effect, context, step=step)
        raise WorkflowExecutionError(f"unsupported route effect {type(effect).__name__!r}")

    @staticmethod
    def _effect_worklist_name(effect: object) -> str:
        worklist = getattr(effect, "worklist", None)
        if isinstance(worklist, str):
            return worklist
        name = getattr(worklist, "name", None)
        if isinstance(name, str) and name:
            return name
        return "<unknown>"

    def _initialize_worklist_selections(self, context: Context) -> dict[str, Selection[Any]]:
        selections: dict[str, Selection[Any]] = {}
        for name, worklist in self.compiled.worklists.items():
            selections[name] = worklist.initial_selection(context)
        return selections

    def _restore_worklist_selections(
        self,
        context: Context,
        snapshots: Mapping[str, SelectionSnapshot],
    ) -> dict[str, Selection[Any]]:
        selections = self._initialize_worklist_selections(context)
        for name, worklist in self.compiled.worklists.items():
            snapshot = snapshots.get(name)
            if snapshot is None:
                continue
            selections[name] = worklist.restore_selection(context, snapshot)
        return selections

    def _advance_worklist(self, effect: Advance, context: Context, *, step: CompiledStep) -> str:
        worklist_name = self._effect_worklist_name(effect)
        if step.scope_name != worklist_name:
            raise WorkflowExecutionError(
                f"step {step.name!r} cannot Advance worklist {worklist_name!r} without matching scope"
            )
        selection = context.selection(worklist_name).advance()
        context._set_selection(worklist_name, selection)
        if selection.current is not None:
            return step.name
        if effect.if_exhausted == "complete":
            return FINISH
        if effect.if_exhausted == "pause":
            return AWAIT_INPUT
        if effect.if_exhausted == "fail":
            return FAIL
        if effect.if_exhausted == "route" and effect.route_to is not None:
            destination = normalize_route_spec(effect.route_to).target
            if hasattr(destination, "name") and not isinstance(destination, str):
                return getattr(destination, "name")
            if isinstance(destination, str):
                return destination
        raise WorkflowExecutionError(
            f"Advance for worklist {worklist_name!r} resolved invalid exhaustion behavior"
        )

    def _save_checkpoint(
        self,
        *,
        stage: str,
        state: BaseModel,
        values: Mapping[str, Any] | None = None,
        step_states: Mapping[str, BaseModel | dict[str, Any]] | None = None,
        item_states: Mapping[str, BaseModel | dict[str, Any]] | None = None,
        step_item_states: Mapping[str, Mapping[str, BaseModel | dict[str, Any]]] | None = None,
        worklist_selections: Mapping[str, Selection[Any]] | None = None,
        pending_handoffs: tuple[PendingHandoff, ...] = (),
        pending_input: PendingInput | None,
        pending_answer: str | None,
        failure_context: FailureContext | Mapping[str, Any] | None = None,
    ) -> Checkpoint:
        payload_failure_context = self._failure_context_payload(failure_context)
        checkpoint = Checkpoint(
            stage=stage,
            state=state,
            session_bindings=self.session_store.snapshot(),
            values=serialize_context_values(values or {}),
            step_states=self._serialize_step_states(step_states),
            item_states=self._serialize_item_states(item_states),
            step_item_states=self._serialize_step_item_states(step_item_states),
            worklist_selections=self._snapshot_worklist_selections(worklist_selections),
            pending_handoffs=tuple(pending_handoffs),
            pending_input=replace(pending_input) if pending_input is not None else None,
            pending_question=None,
            pending_answer=pending_answer,
            failure_context=payload_failure_context,
        )
        self.checkpoint_store.save(checkpoint)
        return checkpoint

    def _snapshot_worklist_selections(
        self,
        selections: Mapping[str, Selection[Any]] | None,
    ) -> dict[str, SelectionSnapshot] | None:
        if not selections:
            return None
        snapshots: dict[str, SelectionSnapshot] = {}
        for name, selection in selections.items():
            worklist = self.compiled.worklists.get(name)
            if worklist is None:
                continue
            snapshots[name] = worklist.snapshot_selection(selection)
        return snapshots or None

    def _build_workflow_output(
        self,
        context: Context,
        state: BaseModel,
    ) -> tuple[Any | None, str | None]:
        if self.compiled.output_model is None:
            return None, None
        if self.compiled.output_builder is None:
            return None, (
                f"workflow {self.compiled.workflow_name!r} declares Output but does not define build_output(state, ctx)"
            )
        try:
            raw_output = self.compiled.output_builder(state, context)
        except Exception as exc:
            return None, f"build_output failed: {type(exc).__name__}: {exc}"
        try:
            return self.compiled.output_model.model_validate(raw_output, strict=True), None
        except Exception as exc:
            return None, f"typed output validation failed: {type(exc).__name__}: {exc}"

    def _normalize_state(self, current_state: BaseModel, next_state: BaseModel) -> BaseModel:
        expected_cls = type(current_state)
        if not isinstance(next_state, BaseModel):
            raise WorkflowExecutionError(
                f"handler returned {type(next_state)!r}; expected a pydantic model compatible with {expected_cls.__name__}"
            )
        if isinstance(next_state, expected_cls):
            return expected_cls.model_validate(next_state.model_dump(mode="python", warnings=False))
        return expected_cls.model_validate(next_state.model_dump(mode="python", warnings=False))

    @staticmethod
    def _event_with_route(event: Event, route_tag: str) -> Event:
        return Event(
            tag=route_tag,
            reason=event.reason,
            question=event.question,
            handoff=event.handoff,
        )

    @staticmethod
    def _callable_positional_arity(func: Callable[..., Any]) -> int:
        signature = inspect.signature(func)
        if any(parameter.kind == inspect.Parameter.VAR_POSITIONAL for parameter in signature.parameters.values()):
            return 99
        return sum(
            1
            for parameter in signature.parameters.values()
            if parameter.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        )

    def _clone_binding(self, binding: SessionBinding | None) -> SessionBinding | None:
        if binding is None:
            return None
        return SessionBinding(
            key=binding.key,
            session_id=binding.session_id,
            provider=binding.provider,
            provider_metadata=deepcopy(binding.provider_metadata),
            metadata=deepcopy(binding.metadata),
        )

    def _clone_checkpoint(self, checkpoint: Checkpoint | None) -> Checkpoint | None:
        if checkpoint is None:
            return None
        return Checkpoint(
            stage=checkpoint.stage,
            state=self._clone_state(checkpoint.state),
            session_bindings=SessionSnapshot(
                bindings=tuple(self._clone_binding(binding) for binding in checkpoint.session_bindings.bindings),
                active_keys_by_slot=deepcopy(checkpoint.session_bindings.active_keys_by_slot),
                active_scopes=deepcopy(checkpoint.session_bindings.active_scopes),
            ),
            values=deepcopy(checkpoint.values),
            step_states=deepcopy(checkpoint.step_states),
            item_states=deepcopy(checkpoint.item_states),
            step_item_states=deepcopy(checkpoint.step_item_states),
            worklist_selections=deepcopy(checkpoint.worklist_selections),
            pending_handoffs=deepcopy(checkpoint.pending_handoffs),
            pending_input=replace(checkpoint.pending_input) if checkpoint.pending_input is not None else None,
            pending_question=checkpoint.pending_question,
            pending_answer=checkpoint.pending_answer,
            failure_context=deepcopy(checkpoint.failure_context),
        )

    @staticmethod
    def _pending_question_for_terminal(
        *,
        event: Event | None,
        pending_input: PendingInput | None,
    ) -> str | None:
        if pending_input is not None:
            return pending_input.question
        if event is not None and isinstance(event.question, str):
            return event.question
        return None

    def _resume_input_response(
        self,
        *,
        checkpoint: Checkpoint,
        answer: str | None,
    ) -> Any | None:
        pending_input = checkpoint.pending_input
        if answer is None:
            return None
        if pending_input is None and checkpoint.pending_question is not None:
            raise StepExecutionError(
                "resume requested with legacy pending-question metadata; this checkpoint cannot be resumed safely",
                checkpoint_state=self._clone_state(checkpoint.state),
                failure_context=FailureContext(
                    kind="resume_input_validation",
                    step_name=checkpoint.stage or "<resume>",
                    details={
                        "error": "legacy pending_question checkpoint cannot validate resumed input",
                        "pending_question": checkpoint.pending_question,
                    },
                ),
            )
        if pending_input is None:
            return answer
        payload = self._resume_input_payload(answer)
        model_cls = self._load_pending_input_model(pending_input.input_schema_model)
        if model_cls is not None:
            try:
                return TypeAdapter(model_cls).validate_python(payload, strict=True)
            except Exception as exc:
                raise StepExecutionError(
                    f"resumed input did not satisfy {pending_input.input_schema_model}: {exc}",
                    checkpoint_state=self._clone_state(checkpoint.state),
                    failure_context=FailureContext(
                        kind="resume_input_validation",
                        step_name=pending_input.source_step or checkpoint.stage or "<resume>",
                        pending_input_id=pending_input.pending_input_id,
                        source_hook=pending_input.source_hook,
                        source_phase=pending_input.source_phase,
                        details={"error": str(exc)},
                    ),
                ) from exc
        if pending_input.input_schema is not None:
            schema = dict(pending_input.input_schema)
            self._validate_json_schema_mapping(schema, label="pending input schema")
            from jsonschema import Draft202012Validator
            try:
                Draft202012Validator(schema).validate(payload)
            except Exception as exc:
                raise StepExecutionError(
                    "resumed input did not satisfy the pending input schema",
                    checkpoint_state=self._clone_state(checkpoint.state),
                    failure_context=FailureContext(
                        kind="resume_input_validation",
                        step_name=pending_input.source_step or checkpoint.stage or "<resume>",
                        pending_input_id=pending_input.pending_input_id,
                        source_hook=pending_input.source_hook,
                        source_phase=pending_input.source_phase,
                        details={"error": str(exc)},
                    ),
                ) from exc
        return payload

    @staticmethod
    def _resume_input_payload(answer: str) -> Any:
        try:
            return json.loads(answer)
        except json.JSONDecodeError:
            return answer

    @staticmethod
    def _load_pending_input_model(model_path: str | None) -> type[BaseModel] | None:
        if not isinstance(model_path, str) or ":" not in model_path:
            return None
        module_name, _, qualname = model_path.partition(":")
        try:
            module = importlib.import_module(module_name)
        except Exception:
            return None
        resolved: object = module
        for part in qualname.split("."):
            resolved = getattr(resolved, part, None)
            if resolved is None:
                return None
        if isinstance(resolved, type) and issubclass(resolved, BaseModel):
            return resolved
        return None

    @staticmethod
    def _validate_json_schema_mapping(schema: dict[str, Any], *, label: str) -> None:
        try:
            from jsonschema import Draft202012Validator
        except ModuleNotFoundError as exc:
            raise WorkflowExecutionError(f"{label} requires the optional jsonschema dependency") from exc
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:
            raise WorkflowExecutionError(f"{label} must be a valid JSON schema mapping") from exc

    @staticmethod
    def _state_for_failure(current_state: BaseModel | None, exc: Exception) -> BaseModel | None:
        checkpoint_state = getattr(exc, "checkpoint_state", None)
        if isinstance(checkpoint_state, BaseModel):
            return checkpoint_state
        return current_state

    def _failure_context_for_exception(self, exc: Exception) -> FailureContext | None:
        failure_context = getattr(exc, "failure_context", None)
        if isinstance(failure_context, FailureContext):
            return FailureContext.from_payload(failure_context.to_payload())
        if isinstance(failure_context, dict):
            return FailureContext.from_payload(deepcopy(failure_context))
        return None

    @staticmethod
    def _pending_handoffs_for_exception(
        exc: Exception,
        pending_handoffs: tuple[PendingHandoff, ...],
    ) -> tuple[PendingHandoff, ...]:
        annotated = getattr(exc, "pending_handoffs", None)
        if isinstance(annotated, tuple):
            return tuple(item for item in annotated if isinstance(item, PendingHandoff))
        return pending_handoffs

    @staticmethod
    def _failure_context_payload(
        failure_context: FailureContext | Mapping[str, Any] | None,
    ) -> dict[str, Any] | None:
        if isinstance(failure_context, FailureContext):
            return failure_context.to_payload()
        if isinstance(failure_context, Mapping):
            return dict(failure_context) or None
        return None

    @staticmethod
    def _retry_kind_for_exception(exc: Exception) -> str | None:
        retry_kind = getattr(exc, "retry_kind", None)
        if isinstance(retry_kind, str) and retry_kind:
            return retry_kind
        return None

    def _annotate_execution_error(
        self,
        exc: Exception,
        *,
        checkpoint_state: BaseModel | None = None,
        failure_context: FailureContext | None = None,
        retry_kind: str | None = None,
    ) -> Exception:
        if checkpoint_state is not None and getattr(exc, "checkpoint_state", None) is None:
            setattr(exc, "checkpoint_state", checkpoint_state)
        if failure_context is not None and getattr(exc, "failure_context", None) is None:
            setattr(exc, "failure_context", failure_context)
        if retry_kind is not None and getattr(exc, "retry_kind", None) is None:
            setattr(exc, "retry_kind", retry_kind)
        return exc

    def _next_retry_feedback(
        self,
        step: CompiledStep,
        exc: Exception,
        *,
        attempt: int,
    ) -> str | None:
        kind = self._provider_retry_kind(exc)
        if kind is None:
            return None
        if not self._retry_policy_allows(step.retry_policy, kind):
            return None
        if attempt >= step.retry_policy.max_attempts:
            self._annotate_retry_exhaustion(exc, step=step, attempt=attempt, kind=kind)
            return None
        self._ensure_retry_failure_context(exc, step=step, kind=kind)
        return build_retry_feedback(
            exc,
            step_name=step.name,
            attempt=attempt + 1,
            max_attempts=step.retry_policy.max_attempts,
        )

    def _annotate_retry_exhaustion(
        self,
        exc: Exception,
        *,
        step: CompiledStep,
        attempt: int,
        kind: str,
    ) -> None:
        self._ensure_retry_failure_context(exc, step=step, kind=kind)
        failure_context = self._failure_context_for_exception(exc)
        if failure_context is None:
            return
        updated_details = dict(failure_context.details)
        updated_details["retry_attempts_consumed"] = attempt
        updated_details["retry_max_attempts"] = step.retry_policy.max_attempts
        updated_details["retry_exhausted"] = True
        updated = FailureContext(
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
            details=updated_details,
        )
        setattr(exc, "failure_context", updated)

    def _ensure_retry_failure_context(
        self,
        exc: Exception,
        *,
        step: CompiledStep,
        kind: str,
    ) -> None:
        existing = self._failure_context_for_exception(exc)
        if existing is None:
            details = {"step": step.name, "error": str(exc)}
            failure_context = FailureContext(
                kind=kind,
                step_name=step.name,
                provider_attributable=isinstance(exc, ProviderExecutionError),
                details=details,
            )
        else:
            details = dict(existing.details)
            details.setdefault("step", step.name)
            details.setdefault("error", str(exc))
            failure_context = FailureContext(
                kind=existing.kind or kind,
                step_name=existing.step_name or step.name,
                candidate_route=existing.candidate_route,
                final_route=existing.final_route,
                runtime_control=existing.runtime_control,
                provider_attributable=existing.provider_attributable or isinstance(exc, ProviderExecutionError),
                source_hook=existing.source_hook,
                source_phase=existing.source_phase,
                target_step=existing.target_step,
                pending_input_id=existing.pending_input_id,
                details=details,
            )
        setattr(exc, "failure_context", failure_context)
        setattr(exc, "retry_kind", kind)

    @staticmethod
    def _retry_policy_allows(policy: ProviderRetryPolicy, kind: str) -> bool:
        if kind in {"provider_transport_failure", "malformed_provider_output"}:
            return policy.retry_provider_execution_error
        if kind == "illegal_route":
            return policy.retry_illegal_route
        if kind == "invalid_payload":
            return policy.retry_invalid_payload
        if kind == "missing_required_output_artifact":
            return policy.retry_missing_required_output_artifact
        if kind == "invalid_output_artifact":
            return policy.retry_invalid_output_artifact
        return False

    @staticmethod
    def _provider_retry_kind(exc: Exception) -> str | None:
        explicit = getattr(exc, "retry_kind", None)
        if isinstance(explicit, str) and explicit:
            return explicit
        if not isinstance(exc, ProviderExecutionError):
            return None
        message = str(exc)
        if "failed while running step" in message or "did not return a resumable session_id" in message:
            return "provider_transport_failure"
        if (
            "malformed outcome JSON" in message
            or "outcome JSON" in message
            or "malformed JSON output" in message
            or "returned unusable JSONL output" in message
            or "did not return assistant text in JSONL output" in message
            or "must return Outcome instances" in message
        ):
            return "malformed_provider_output"
        return None

    @staticmethod
    def _artifact_display_name(artifact: Any) -> str:
        qualified_name = getattr(artifact, "qualified_name", None)
        if isinstance(qualified_name, str) and qualified_name:
            return qualified_name.rsplit(".", 1)[-1]
        name = getattr(artifact, "name", None)
        if isinstance(name, str) and name:
            return name.rsplit(".", 1)[-1]
        return "artifact"

    def _runtime_artifact_spec(self, artifact: Any) -> Artifact:
        runtime_artifact = Artifact(
            artifact.template,
            name=self._artifact_display_name(artifact),
            kind=artifact.kind,
            schema=artifact.schema,
            required=artifact.required,
            owner_step=artifact.owner_step,
            qualified_name=artifact.qualified_name,
        )
        return runtime_artifact

    def _clone_event(self, event: Event | None) -> Event | None:
        if event is None:
            return None
        return Event(tag=event.tag, reason=event.reason, question=event.question, handoff=event.handoff)

    def _matching_pending_handoffs(
        self,
        step: CompiledStep,
        context: Context,
        pending_handoffs: tuple[PendingHandoff, ...],
    ) -> tuple[str | None, tuple[PendingHandoff, ...]]:
        if not pending_handoffs:
            return None, ()
        current_item = context.current(step.scope_name) if step.scope_name is not None else None
        current_item_id = current_item.id if current_item is not None else None
        matched: list[PendingHandoff] = []
        remaining: list[PendingHandoff] = []
        for handoff in pending_handoffs:
            if handoff.target_step != step.name:
                remaining.append(handoff)
                continue
            if handoff.worklist_name is not None and handoff.worklist_name != step.scope_name:
                remaining.append(handoff)
                continue
            if handoff.item_id is not None and handoff.item_id != current_item_id:
                remaining.append(handoff)
                continue
            matched.append(handoff)
        if not matched:
            return None, pending_handoffs
        combined = "\n\n".join(handoff.message for handoff in matched if handoff.message)
        return (combined or None), tuple(remaining)

    def _schedule_route_handoffs(
        self,
        pending_handoffs: tuple[PendingHandoff, ...],
        *,
        route: CompiledRoute,
        event: Event | None,
        destination: str,
        context: Context,
        source_step: str,
    ) -> tuple[PendingHandoff, ...]:
        messages: list[str] = []
        if route.handoff is not None:
            messages.append(route.handoff)
        messages.extend(effect.message for effect in route.effects if isinstance(effect, Handoff))
        if event is not None and event.handoff is not None:
            messages.append(event.handoff)
        if not messages:
            return pending_handoffs
        target_step = self.compiled.steps.get(destination)
        if target_step is None or target_step.kind in {"python", "workflow", "operation"}:
            return pending_handoffs
        worklist_name, item_id = self._handoff_scope_for_target(target_step, context)
        combined_message = "\n\n".join(message.strip() for message in messages if message and message.strip())
        if not combined_message:
            return pending_handoffs
        return (
            *pending_handoffs,
            PendingHandoff(
                source_step=source_step,
                route_tag=route.tag,
                target_step=target_step.name,
                message=combined_message,
                worklist_name=worklist_name,
                item_id=item_id,
            ),
        )

    def _schedule_direct_control_handoffs(
        self,
        pending_handoffs: tuple[PendingHandoff, ...],
        *,
        control: _DirectRuntimeControl,
        context: Context,
        source_step: str,
    ) -> tuple[PendingHandoff, ...]:
        if control.control != "goto" or control.handoff is None or control.target_step is None:
            return pending_handoffs
        target_step = self.compiled.steps.get(control.target_step)
        if target_step is None or target_step.kind in {"python", "workflow", "operation"}:
            return pending_handoffs
        combined_message = control.handoff.strip()
        if not combined_message:
            return pending_handoffs
        worklist_name, item_id = self._handoff_scope_for_target(target_step, context)
        return (
            *pending_handoffs,
            PendingHandoff(
                source_step=source_step,
                route_tag=control.control,
                target_step=target_step.name,
                message=combined_message,
                worklist_name=worklist_name,
                item_id=item_id,
            ),
        )

    def _handoff_scope_for_target(
        self,
        step: CompiledStep,
        context: Context,
    ) -> tuple[str | None, str | None]:
        if step.scope_name is None:
            return None, None
        item = context.current(step.scope_name)
        if item is None:
            return step.scope_name, None
        return step.scope_name, item.id

    def _run_workflow_step(self, step: CompiledStep, context: Context) -> Any:
        workflow_step = step.step
        if not isinstance(workflow_step, ChildWorkflowStep):
            raise WorkflowExecutionError(f"workflow step {step.name!r} is missing workflow-step metadata")
        message = self._resolve_workflow_step_message(workflow_step, context)
        child_result = context.invoke_workflow(
            workflow_step.workflow,
            message=message,
            parameters=dict(workflow_step.params),
            input=workflow_step.input,
        )
        self._write_workflow_step_outputs(context, step=workflow_step, child_result=child_result)
        return child_result

    def _resolve_workflow_step_message(self, step: Any, context: Context) -> str:
        if step.message is not None:
            return step.message
        message_from = step.message_from
        if message_from is not None:
            handle = self._workflow_step_message_handle(message_from, context)
            try:
                return handle.read_text()
            except FileNotFoundError as exc:
                raise WorkflowExecutionError(
                    f"workflow step {step.name!r} message source {str(handle.path)!r} does not exist"
                ) from exc
        workflow_name = step.workflow if isinstance(step.workflow, str) else step.workflow.__name__
        return f"Run child workflow {workflow_name}."

    def _workflow_step_message_handle(self, message_from: object, context: Context) -> ArtifactHandle:
        if isinstance(message_from, Artifact):
            runtime_artifact = self._runtime_artifact_spec(message_from)
            return ArtifactHandle(
                name=self._artifact_display_name(runtime_artifact),
                path=resolve_artifact_template(runtime_artifact, context),
                artifact=runtime_artifact,
            )
        if isinstance(message_from, Path):
            path = message_from if message_from.is_absolute() else context.root / message_from
            return ArtifactHandle(name=message_from.name, path=path)
        if isinstance(message_from, str):
            artifacts = self._resolve_artifacts(context)
            if message_from in artifacts:
                return artifacts[message_from]
            path = Path(message_from)
            if not path.is_absolute():
                path = context.root / path
            return ArtifactHandle(name=path.name or message_from, path=path)
        raise WorkflowExecutionError(f"workflow step message_from {message_from!r} is unsupported")

    def _write_workflow_step_outputs(
        self,
        context: Context,
        *,
        step: Any,
        child_result: Any,
    ) -> None:
        declared_step = step
        if not declared_step.writes:
            return
        payload = self._workflow_step_output_payload(child_result)
        summary = self._workflow_step_output_summary(payload)
        raw_json = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        for artifact in declared_step.writes.values():
            handle = ArtifactHandle(
                name=artifact.name or "output",
                path=resolve_artifact_template(artifact, context),
                artifact=artifact,
            )
            if artifact.kind == "json":
                handle.write_json(payload)
            elif artifact.kind == "raw":
                handle.write_text(raw_json)
            else:
                handle.write_text(summary)

    def _workflow_step_output_payload(self, child_result: Any) -> dict[str, Any]:
        last_event = getattr(child_result, "last_event", None)
        last_event_tag = last_event.tag if isinstance(last_event, Event) else None
        output_artifacts = getattr(child_result, "output_artifacts", {}) or {}
        return {
            "workflow_name": getattr(child_result, "workflow_name", None),
            "run_id": getattr(child_result, "run_id", None),
            "terminal": getattr(child_result, "terminal", None),
            "status": getattr(child_result, "status", None),
            "last_event": last_event_tag,
            "output_artifacts": {name: str(path) for name, path in output_artifacts.items()},
            "output_metadata": dict(getattr(child_result, "output_metadata", {}) or {}),
        }

    def _workflow_step_output_summary(self, payload: Mapping[str, Any]) -> str:
        lines = [
            f"Child workflow: {payload.get('workflow_name') or '<unknown>'}",
            f"Run id: {payload.get('run_id') or '<unknown>'}",
            f"Terminal: {payload.get('terminal') or '<unknown>'}",
            f"Status: {payload.get('status') or '<unknown>'}",
        ]
        last_event = payload.get("last_event")
        if isinstance(last_event, str) and last_event:
            lines.append(f"Last event: {last_event}")
        output_artifacts = payload.get("output_artifacts")
        if isinstance(output_artifacts, Mapping) and output_artifacts:
            lines.append("Output artifacts:")
            for name, path in output_artifacts.items():
                lines.append(f"- {name}: {path}")
        return "\n".join(lines) + "\n"

    def _map_workflow_step_result(self, child_result: Any) -> Event:
        terminal = getattr(child_result, "terminal", None)
        last_event = getattr(child_result, "last_event", None)
        checkpoint = getattr(child_result, "checkpoint", None)
        pending_input = getattr(checkpoint, "pending_input", None)
        pending_question = pending_input.question if isinstance(pending_input, PendingInput) else None
        if terminal == FINISH:
            return Event("done")
        if terminal == FAIL:
            reason = last_event.reason if isinstance(last_event, Event) and last_event.reason else "Child workflow failed."
            return Event("failed", reason=reason)
        if terminal == AWAIT_INPUT and isinstance(last_event, Event) and last_event.tag == "question":
            return Event("question", reason=last_event.reason, question=last_event.question)
        if terminal == AWAIT_INPUT and isinstance(pending_question, str) and pending_question:
            reason = last_event.reason if isinstance(last_event, Event) else ""
            return Event("question", reason=reason, question=pending_question)
        if terminal == AWAIT_INPUT:
            reason = (
                last_event.reason
                if isinstance(last_event, Event) and last_event.reason
                else "Child workflow is awaiting input."
            )
            return Event("blocked", reason=reason)
        raise WorkflowExecutionError(f"child workflow returned unsupported terminal {terminal!r}")

    def _clone_outcome(self, outcome: Outcome | None) -> Outcome | None:
        if outcome is None:
            return None
        return Outcome(
            raw_output=outcome.raw_output,
            tag=outcome.tag,
            reason=outcome.reason,
            clarification=outcome.clarification,
            question=outcome.question,
            payload=deepcopy(outcome.payload),
        )

    def _clone_state(self, state: BaseModel | None) -> BaseModel | None:
        if state is None:
            return None
        state_cls = type(state)
        return state_cls.model_validate(deepcopy(state.model_dump(mode="python", warnings=False)))

    def _clone_model_or_dict(
        self,
        value: BaseModel | dict[str, Any] | None,
    ) -> BaseModel | dict[str, Any] | None:
        if value is None:
            return None
        if isinstance(value, BaseModel):
            return self._clone_state(value)
        if isinstance(value, dict):
            return deepcopy(value)
        return None

    def _restore_model_or_dict(
        self,
        target: BaseModel | dict[str, Any] | None,
        snapshot: BaseModel | dict[str, Any] | None,
    ) -> None:
        if target is None or snapshot is None:
            return
        if isinstance(target, BaseModel):
            if isinstance(snapshot, BaseModel):
                restored = snapshot
            else:
                restored = type(target).model_validate(deepcopy(snapshot))
            self._restore_base_model(target, restored)
            return
        if isinstance(target, dict):
            if isinstance(snapshot, BaseModel):
                restored = snapshot.model_dump(mode="python", warnings=False)
            else:
                restored = deepcopy(snapshot)
            target.clear()
            target.update(restored)

    @staticmethod
    def _restore_base_model(target: BaseModel, source: BaseModel) -> None:
        target.__dict__.clear()
        target.__dict__.update(deepcopy(source.__dict__))
        target.__pydantic_fields_set__ = set(source.__pydantic_fields_set__)
        if hasattr(target, "__pydantic_extra__"):
            target.__pydantic_extra__ = deepcopy(getattr(source, "__pydantic_extra__", None))
        if hasattr(target, "__pydantic_private__"):
            target.__pydantic_private__ = deepcopy(getattr(source, "__pydantic_private__", None))

    def _build_run_binding(
        self,
        *,
        task_id: str,
        run_id: str,
        task_folder: Path,
        workflow_folder: Path,
        run_folder: Path,
        package_folder: Path,
        root: Path | None,
    ) -> RunBinding:
        return RunBinding(
            root=root.resolve() if root is not None else task_folder.resolve(),
            task_id=task_id,
            run_id=run_id,
            workflow_name=self.compiled.workflow_name,
            task_folder=task_folder,
            workflow_folder=workflow_folder,
            run_folder=run_folder,
            package_folder=package_folder,
        )

    def _assert_resume_topology_compatible(self, run_folder: Path) -> None:
        run_meta_file = run_folder / "run.json"
        if not run_meta_file.is_file():
            return
        try:
            payload = json.loads(run_meta_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        topology = payload.get("topology")
        if not isinstance(topology, Mapping):
            return
        saved_hash = topology.get("topology_hash")
        if not isinstance(saved_hash, str) or not saved_hash:
            return
        if saved_hash == self.compiled.topology_hash:
            return
        raise WorkflowExecutionError(
            "resume requested with a different compiled topology: "
            f"saved={saved_hash!r} current={self.compiled.topology_hash!r}"
        )

    def _current_item_state_key(self, context: Context, step: CompiledStep) -> str | None:
        if step.scope_name is None:
            return None
        item = context.current(step.scope_name)
        if item is None:
            return None
        item_id = getattr(item, "id", None)
        if not isinstance(item_id, str) or not item_id:
            return None
        return f"{step.scope_name}:{item_id}"

    @staticmethod
    def _step_runtime_visits(step_state: BaseModel | dict[str, Any] | None) -> int | None:
        if isinstance(step_state, BaseModel):
            visits = getattr(step_state, "visits", None)
            return visits if isinstance(visits, int) else None
        if isinstance(step_state, dict):
            visits = step_state.get("visits")
            return visits if isinstance(visits, int) else None
        return None

    @staticmethod
    def _increment_step_runtime_state(step_state: BaseModel | dict[str, Any]) -> None:
        if isinstance(step_state, BaseModel):
            current_visits = getattr(step_state, "visits", 0)
            step_state.visits = current_visits + 1 if isinstance(current_visits, int) else 1
            return
        current_visits = step_state.get("visits", 0)
        step_state["visits"] = current_visits + 1 if isinstance(current_visits, int) else 1

    @staticmethod
    def _update_final_step_runtime_state(
        step: CompiledStep,
        step_state: BaseModel | dict[str, Any] | None,
        final_event: Event,
    ) -> None:
        if step_state is None:
            return
        if isinstance(step_state, BaseModel):
            step_state.last_route = final_event.tag
            step_state.last_reason = final_event.reason
            if step.kind == "produce_verify":
                if final_event.tag in DEFAULT_REWORK_ROUTE_TAGS:
                    step_state.rework_count = getattr(step_state, "rework_count", 0) + 1
                if final_event.tag in DEFAULT_REPLAN_ROUTE_TAGS:
                    step_state.replan_count = getattr(step_state, "replan_count", 0) + 1
            return
        step_state["last_route"] = final_event.tag
        step_state["last_reason"] = final_event.reason
        if step.kind == "produce_verify":
            if final_event.tag in DEFAULT_REWORK_ROUTE_TAGS:
                current_rework = step_state.get("rework_count", 0)
                step_state["rework_count"] = current_rework + 1 if isinstance(current_rework, int) else 1
            if final_event.tag in DEFAULT_REPLAN_ROUTE_TAGS:
                current_replan = step_state.get("replan_count", 0)
                step_state["replan_count"] = current_replan + 1 if isinstance(current_replan, int) else 1

    def _ensure_step_state_store(
        self,
        step_states: dict[str, BaseModel | dict[str, Any]],
        step: CompiledStep,
    ) -> BaseModel:
        state_model = step.step_state_model
        store = step_states.get(step.name)
        if isinstance(store, state_model):
            return store
        if isinstance(store, BaseModel):
            normalized_store = state_model.model_validate(store.model_dump(mode="python", warnings=False))
        elif isinstance(store, dict):
            normalized_store = state_model.model_validate(deepcopy(store))
        else:
            normalized_store = state_model()
        step_states[step.name] = normalized_store
        return normalized_store

    @staticmethod
    def _serialize_model_or_dict_store(
        store: BaseModel | dict[str, Any],
    ) -> dict[str, Any] | None:
        if isinstance(store, BaseModel):
            return store.model_dump(mode="json", warnings=False)
        if isinstance(store, dict):
            return deepcopy(store)
        return None

    @staticmethod
    def _serialize_step_states(
        step_states: Mapping[str, BaseModel | dict[str, Any]] | None,
    ) -> dict[str, dict[str, Any]] | None:
        if not step_states:
            return None
        serialized: dict[str, dict[str, Any]] = {}
        for step_name, store in step_states.items():
            payload = Engine._serialize_model_or_dict_store(store)
            if payload is not None:
                serialized[step_name] = payload
        return serialized or None

    @staticmethod
    def _serialize_item_states(
        item_states: Mapping[str, BaseModel | dict[str, Any]] | None,
    ) -> dict[str, dict[str, Any]] | None:
        if not item_states:
            return None
        serialized: dict[str, dict[str, Any]] = {}
        for item_key, store in item_states.items():
            payload = Engine._serialize_model_or_dict_store(store)
            if payload is not None:
                serialized[item_key] = payload
        return serialized or None

    @staticmethod
    def _serialize_step_item_states(
        step_item_states: Mapping[str, Mapping[str, BaseModel | dict[str, Any]]] | None,
    ) -> dict[str, dict[str, dict[str, Any]]] | None:
        if not step_item_states:
            return None
        serialized: dict[str, dict[str, dict[str, Any]]] = {}
        for step_name, item_store in step_item_states.items():
            serialized_items: dict[str, dict[str, Any]] = {}
            for item_key, store in item_store.items():
                payload = Engine._serialize_model_or_dict_store(store)
                if payload is not None:
                    serialized_items[item_key] = payload
            if serialized_items:
                serialized[step_name] = serialized_items
        return serialized or None

    def _ensure_item_state_store(
        self,
        item_states: dict[str, BaseModel | dict[str, Any]],
        step: CompiledStep,
        item_key: str | None,
    ) -> BaseModel | dict[str, Any] | None:
        if item_key is None:
            return None
        worklist = self.compiled.worklists.get(step.scope_name or "")
        state_model = worklist.item_state_model if worklist is not None else None
        if state_model is None:
            return None
        store = item_states.get(item_key)
        if isinstance(store, state_model):
            return store
        if isinstance(store, BaseModel):
            normalized_store = state_model.model_validate(store.model_dump(mode="python", warnings=False))
        elif isinstance(store, dict):
            normalized_store = state_model.model_validate(deepcopy(store))
        else:
            normalized_store = state_model()
        item_states[item_key] = normalized_store
        return normalized_store

    def _ensure_step_item_state_store(
        self,
        step_item_states: dict[str, dict[str, BaseModel | dict[str, Any]]],
        step: CompiledStep,
        item_key: str | None,
    ) -> BaseModel | dict[str, Any] | None:
        if item_key is None or step.step_item_state_model is None:
            return None
        step_store = step_item_states.setdefault(step.name, {})
        store = step_store.get(item_key)
        state_model = step.step_item_state_model
        if isinstance(store, state_model):
            return store
        if isinstance(store, BaseModel):
            normalized_store = state_model.model_validate(store.model_dump(mode="python", warnings=False))
        elif isinstance(store, dict):
            normalized_store = state_model.model_validate(deepcopy(store))
        else:
            normalized_store = state_model()
        step_store[item_key] = normalized_store
        return normalized_store

    def _emit_runtime_event(self, event_type: str, **payload: Any) -> None:
        if self.runtime_event_sink is None:
            return
        self.runtime_event_sink(event_type, payload)

    def _emit_provider_attempt_event(
        self,
        event_type: str,
        *,
        step: CompiledStep,
        context: Context,
        turn_kind: str,
        attempt: int,
        token_usage: Any | None = None,
        failure_context: Mapping[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            **self._step_runtime_event_payload(step=step, context=context),
            "turn_kind": turn_kind,
            "attempt": attempt,
        }
        if token_usage is not None:
            payload["token_usage"] = self._serialize_token_usage(token_usage)
        if failure_context:
            payload["failure_context"] = dict(failure_context)
        self._emit_runtime_event(event_type, **payload)

    def _emit_provider_attempt_finished(
        self,
        *,
        step: CompiledStep,
        context: Context,
        turn_kind: str,
        attempt: int,
        token_usage: Any | None,
    ) -> None:
        self._emit_provider_attempt_event(
            "provider_attempt_finished",
            step=step,
            context=context,
            turn_kind=turn_kind,
            attempt=attempt,
            token_usage=token_usage,
        )

    def _emit_provider_attempt_failed(
        self,
        *,
        step: CompiledStep,
        context: Context,
        turn_kind: str,
        attempt: int,
        exc: Exception,
    ) -> None:
        self._emit_provider_attempt_event(
            "provider_attempt_failed",
            step=step,
            context=context,
            turn_kind=turn_kind,
            attempt=attempt,
            failure_context=self._exception_failure_context(exc),
        )

    def _step_runtime_event_payload(
        self,
        *,
        step: CompiledStep,
        context: Context,
    ) -> dict[str, Any]:
        step_state_store = getattr(context, "_step_state", None)
        step_item_state_store = getattr(context, "_step_item_state", None)
        visit = self._step_execution_visit(step, step_state_store, step_item_state_store)
        scope_name, item_id = self._current_step_scope_item(context, step)
        payload: dict[str, Any] = {
            "step_name": step.name,
            "visit": visit,
            "step_execution_id": self._step_execution_id(
                step_name=step.name,
                visit=visit,
                scope_name=scope_name,
                item_id=item_id,
            ),
        }
        if scope_name is not None:
            payload["scope"] = scope_name
        if item_id is not None:
            payload["item_id"] = item_id
        return payload

    @staticmethod
    def _serialize_token_usage(token_usage: Any) -> dict[str, Any]:
        if hasattr(token_usage, "__dataclass_fields__"):
            return {key: value for key, value in asdict(token_usage).items() if value is not None}
        if isinstance(token_usage, Mapping):
            return {str(key): value for key, value in token_usage.items()}
        return {"value": token_usage}

    @staticmethod
    def _exception_failure_context(exc: Exception) -> dict[str, Any]:
        failure_context = getattr(exc, "failure_context", None)
        if isinstance(failure_context, FailureContext):
            return failure_context.to_payload()
        if isinstance(failure_context, dict) and failure_context:
            return deepcopy(failure_context)
        return {
            "error": str(exc),
            "error_type": type(exc).__name__,
        }

    @staticmethod
    def _current_step_scope_item(context: Context, step: CompiledStep) -> tuple[str | None, str | None]:
        if step.scope_name is None:
            return None, None
        item = context.current(step.scope_name)
        item_id = getattr(item, "id", None)
        if not isinstance(item_id, str) or not item_id:
            return step.scope_name, None
        return step.scope_name, item_id

    def _step_execution_visit(
        self,
        step: CompiledStep,
        step_state: BaseModel | dict[str, Any] | None,
        step_item_state: BaseModel | dict[str, Any] | None,
    ) -> int | None:
        if step.scope_name is not None and step_item_state is not None:
            return self._step_runtime_visits(step_item_state)
        return self._step_runtime_visits(step_state)

    @staticmethod
    def _step_execution_id(
        *,
        step_name: str,
        visit: int | None,
        scope_name: str | None,
        item_id: str | None,
    ) -> str | None:
        if visit is None:
            return None
        if scope_name is not None and item_id is not None:
            return f"{step_name}:{scope_name}:{item_id}:{visit}"
        return f"{step_name}:{visit}"

    def _emit_hook_event(
        self,
        event_type: str,
        *,
        step: CompiledStep | None = None,
        context: Context | None = None,
        **payload: Any,
    ) -> None:
        if self.hook_event_sink is None:
            return
        if step is not None and context is not None:
            payload = {
                **self._step_runtime_event_payload(step=step, context=context),
                **payload,
            }
        self.hook_event_sink(event_type, payload)

    def _bind_extensions(self, binding: RunBinding) -> tuple[BoundWorkflowExtension, ...]:
        bound: list[BoundWorkflowExtension] = []
        for factory in self.runtime_extension_factories:
            candidate = factory(binding)
            self._validate_bound_extension(candidate, factory)
            bound.append(candidate)
        for extension in self.compiled.extensions:
            candidate = extension.bind(binding)
            self._validate_bound_extension(candidate, extension)
            bound.append(candidate)
        return tuple(bound)

    def _notify_before_step(self, extensions: Sequence[BoundWorkflowExtension], event: StepStart) -> None:
        for extension in extensions:
            extension.before_step(event)

    def _notify_after_step(self, extensions: Sequence[BoundWorkflowExtension], event: StepFinish) -> None:
        for extension in extensions:
            extension.after_step(event)

    def _notify_terminal(self, extensions: Sequence[BoundWorkflowExtension], event: TerminalFinish) -> None:
        for extension in extensions:
            extension.on_terminal(event)

    def _notify_fatal(
        self,
        extensions: Sequence[BoundWorkflowExtension],
        event: TerminalFinish,
        error: BaseException,
    ) -> Exception | None:
        fatal_errors: list[Exception] = []
        for extension in extensions:
            fatal_handler = getattr(extension, "on_fatal", None)
            if callable(fatal_handler):
                try:
                    fatal_handler(event, error)
                except Exception as exc:
                    if getattr(extension, "propagate_fatal_exceptions", False):
                        fatal_errors.append(exc)
                    continue
        if not fatal_errors:
            return None
        if len(fatal_errors) == 1:
            return fatal_errors[0]
        return ExceptionGroup("fatal extension handlers failed", fatal_errors)

    @staticmethod
    def _validate_bound_extension(bound: object, extension: object) -> None:
        for method_name in ("before_step", "after_step", "on_terminal"):
            if not callable(getattr(bound, method_name, None)):
                raise WorkflowExecutionError(
                    f"workflow extension {extension!r} bound to {bound!r} without callable {method_name}()"
                )
