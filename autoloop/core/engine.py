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
from typing import TYPE_CHECKING, Any, Callable, Literal, Mapping
from uuid import uuid4

from pydantic import BaseModel, TypeAdapter

from .artifacts import Artifact, ArtifactHandle, ResolvedArtifacts, render_runtime_template, resolve_artifact_template
from .branch_groups.runtime import BranchGroupRuntime
from .compiler import CompiledRoute, CompiledStep, CompiledWorkflow, compile_workflow
from .context import Context, _DEFAULT_MESSAGE, _resolve_context_root, context_runtime
from .engine_collaborators import (
    ArtifactGuard,
    CheckpointManager,
    HookRunner,
    OperationRecorder,
    ProviderContractBuilder,
    ProviderExecResult,
    RouteFinalizer,
    RouteFinalizationResult,
    SessionRuntime,
    StateRuntime,
    StepExecutionResult,
    StepDispatcher,
    WorkflowInvoker,
    run_awaitable_sync,
)
from .extensions import BoundWorkflowExtension, HookRouteRedirect, RunBinding, StepFinish, StepStart, TerminalFinish
from .errors import (
    FailureContext,
    MissingArtifactError,
    ProviderExecutionError,
    StepExecutionError,
    WorkflowExecutionError,
    enrich_execution_error,
    exception_checkpoint_state,
    exception_failure_context,
    exception_failure_context_payload,
    exception_pending_handoffs,
    exception_retry_kind,
    replace_execution_error,
)
from .operations import serialize_context_values
from .outcome_contract import (
    is_question_style_route,
    normalize_route_fields_for_route,
    project_questions_markdown,
)
from .primitives import AWAIT_INPUT, Checkpoint, Event, FAIL, FINISH, Fail, Goto, Outcome, PendingHandoff, RequestInput
from .prompts import Prompt, PromptRegistry, ResolvedPrompt
from .providers.models import (
    LLMRequest,
    ProducerRequest,
    RuntimeInteractionPolicy,
    StepProviderUsage,
    VerifierRequest,
)
from .providers.protocols import LLMProvider, validate_llm_provider
from .providers.retries import ProviderRetryPolicy, build_retry_feedback
from .route_required_writes import (
    effective_route_required_writes,
)
from .stores.protocols import (
    CheckpointStore,
    PendingInput,
    SessionBinding,
    SessionSnapshot,
    SessionStore,
    normalize_session_snapshot,
)
from .statuses import route_is_replan, route_is_rework
from .steps import ChildWorkflowStep
from .worklists import Selection, SelectionSnapshot

if TYPE_CHECKING:
    from autoloop.runtime.provider_policy_resolver import ProviderPolicyResolver


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
    pending_input_id: str | None = None
    target_step: str | None = None
    terminal: str | None = None
    provider_attributable: bool = False
    provider_attempted: bool | None = None
    producer_attempted: bool | None = None
    verifier_attempted: bool | None = None
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
        interaction_policy: RuntimeInteractionPolicy | None = None,
        runtime_extension_factories: Sequence[Callable[[RunBinding], BoundWorkflowExtension]] = (),
        hook_event_sink: Callable[[str, Mapping[str, Any]], None] | None = None,
        runtime_event_sink: Callable[[str, Mapping[str, Any]], None] | None = None,
        provider_policy_resolver: "ProviderPolicyResolver | None" = None,
    ) -> None:
        self.compiled = workflow if isinstance(workflow, CompiledWorkflow) else compile_workflow(workflow)
        self.provider = validate_llm_provider(provider)
        self.session_store = session_store
        self.checkpoint_store = checkpoint_store
        self.prompt_registry = prompt_registry
        self.operation_replay_mismatch_behavior = operation_replay_mismatch_behavior
        self.interaction_policy = interaction_policy or RuntimeInteractionPolicy()
        self.runtime_extension_factories = tuple(runtime_extension_factories)
        self.hook_event_sink = hook_event_sink
        self.runtime_event_sink = runtime_event_sink
        self.provider_policy_resolver = provider_policy_resolver
        self.step_dispatcher = StepDispatcher(self)
        self.route_finalizer = RouteFinalizer(self)
        self.hook_runner = HookRunner(self)
        self.artifact_guard = ArtifactGuard(self)
        self.state_runtime = StateRuntime(self)
        self.session_runtime = SessionRuntime(self)
        self.checkpoint_manager = CheckpointManager(self)
        self.operation_recorder = OperationRecorder(self)
        self.workflow_invoker = WorkflowInvoker(self)
        self.provider_contract_builder = ProviderContractBuilder(self)
        self.branch_group_runtime = BranchGroupRuntime(self)

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
        request_file: Path | None = None,
        task_request_file: Path | None = None,
        params: BaseModel | None = None,
        workflow_params: Mapping[str, Any] | None = None,
        message: str | None | object = _DEFAULT_MESSAGE,
        workflow_input: BaseModel | None = None,
        workflow_invoker: Callable[..., Any] | None = None,
        initial_state: BaseModel | None = None,
        resume: bool = False,
        answer: str | None = None,
        max_steps: int = 100,
    ) -> RunResult:
        return run_awaitable_sync(
            lambda: self.run_async(
                task_id=task_id,
                run_id=run_id,
                task_folder=task_folder,
                workflow_folder=workflow_folder,
                run_folder=run_folder,
                package_folder=package_folder,
                root=root,
                request_file=request_file,
                task_request_file=task_request_file,
                params=params,
                workflow_params=workflow_params,
                message=message,
                workflow_input=workflow_input,
                workflow_invoker=workflow_invoker,
                initial_state=initial_state,
                resume=resume,
                answer=answer,
                max_steps=max_steps,
            ),
            active_loop_error="Synchronous engine execution cannot bridge async execution inside an active event loop.",
        )

    async def run_async(
        self,
        *,
        task_id: str,
        run_id: str,
        task_folder: Path,
        workflow_folder: Path | None = None,
        run_folder: Path,
        package_folder: Path | None = None,
        root: Path | None = None,
        request_file: Path | None = None,
        task_request_file: Path | None = None,
        params: BaseModel | None = None,
        workflow_params: Mapping[str, Any] | None = None,
        message: str | None | object = _DEFAULT_MESSAGE,
        workflow_input: BaseModel | None = None,
        workflow_invoker: Callable[..., Any] | None = None,
        initial_state: BaseModel | None = None,
        resume: bool = False,
        answer: str | None = None,
        max_steps: int = 100,
    ) -> RunResult:
        resolved_workflow_folder = workflow_folder or task_folder / f"wf_{self.compiled.workflow_name}"
        resolved_package_folder = package_folder or (root.resolve() if root is not None else task_folder)
        previous_provider_policy_resolver = self.provider_policy_resolver
        if previous_provider_policy_resolver is None:
            from autoloop.runtime.provider_policy_resolver import create_provider_policy_resolver

            self.provider_policy_resolver = create_provider_policy_resolver(
                workflow_policy=self.compiled.provider_policy,
                workspace_root=_resolve_context_root(
                    root=root,
                    task_folder=task_folder,
                    package_folder=resolved_package_folder,
                ),
            )
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
        selection_snapshots: dict[str, SelectionSnapshot] = {}
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
                checkpoint = self.checkpoint_store.load()
                if checkpoint is None:
                    raise WorkflowExecutionError("resume requested but no checkpoint is available")
                self._validate_resume_checkpoint_target(checkpoint)
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
                    request_file=request_file,
                    task_request_file=task_request_file,
                    state=state,
                    session_store=self.session_store,
                    session_definitions=self.compiled.sessions,
                    worklists=self.compiled.worklists,
                    selections={},
                    selection_snapshots={},
                    params=params,
                    workflow_params=workflow_params,
                    message=message,
                    workflow_input=workflow_input,
                    workflow_invoker=workflow_invoker,
                    answer=None,
                    input_response=None,
                    default_session_name=self.compiled.default_session_name,
                    values=values,
                )
                selection_snapshots = self.state_runtime.restore_worklist_selections(
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
                        worklist_selection_snapshots=selection_snapshots,
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
                    request_file=request_file,
                    task_request_file=task_request_file,
                    state=state,
                    session_store=self.session_store,
                    session_definitions=self.compiled.sessions,
                    worklists=self.compiled.worklists,
                    selections=selections,
                    selection_snapshots=selection_snapshots,
                    params=params,
                    workflow_params=workflow_params,
                    message=message,
                    workflow_input=workflow_input,
                    workflow_invoker=workflow_invoker,
                    answer=None,
                    input_response=None,
                    default_session_name=self.compiled.default_session_name,
                    values=values,
                )
                runtime = context_runtime(context)
                runtime.set_worklist_selection_resolver(
                    lambda worklist_name, *, _context=context: self.state_runtime.ensure_worklist_selection(
                        _context,
                        worklist_name,
                    )
                )
                if self.compiled.default_session_open:
                    context.open_session(self.compiled.default_session_name)
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
                    request_file=request_file,
                    task_request_file=task_request_file,
                    state=state,
                    session_store=self.session_store,
                    session_definitions=self.compiled.sessions,
                    worklists=self.compiled.worklists,
                    selections=selections,
                    selection_snapshots=selection_snapshots,
                    active_worklist=step.scope_name,
                    params=params,
                    workflow_params=workflow_params,
                    message=message,
                    workflow_input=workflow_input,
                    workflow_invoker=workflow_invoker,
                    answer=current_answer,
                    input_response=current_input_response,
                    step_name=step.name,
                    default_session_name=self.compiled.default_session_name,
                    values=values,
                    runtime_event_sink=self.runtime_event_sink,
                )
                runtime = context_runtime(context)
                runtime.set_worklist_selection_resolver(
                    lambda worklist_name, *, _context=context: self.state_runtime.ensure_worklist_selection(
                        _context,
                        worklist_name,
                    )
                )
                step_state_store = self._ensure_step_state_store(step_states, step)
                self._increment_step_runtime_state(step_state_store)
                runtime.set_step_state_store(step_state_store)
                if step.scope_name is not None:
                    context.ensure_selection(step.scope_name)
                current_item_key = self._current_item_state_key(context, step)
                item_state_store = self._ensure_item_state_store(item_states, step, item_key=current_item_key)
                step_item_state_store = self._ensure_step_item_state_store(
                    step_item_states,
                    step,
                    item_key=current_item_key,
                )
                if item_state_store is not None:
                    runtime.set_item_state_store(item_state_store)
                if step_item_state_store is not None:
                    self._increment_step_runtime_state(step_item_state_store)
                    runtime.set_step_item_state_store(step_item_state_store)
                self._update_item_runtime_state_on_entry(step, context, getattr(context, "_item_state", None))
                runtime.set_worklist_selection_sync(
                    lambda worklist_name, *, _context=context, _step=step, _item_states=item_states, _step_item_states=step_item_states: self._sync_context_scoped_state_after_worklist_selection_change(
                        _context,
                        _step,
                        _item_states,
                        _step_item_states,
                        worklist_name=worklist_name,
                    )
                )
                runtime.set_values(values)
                runtime.set_meta(
                    {
                        "step": {
                            "name": step.name,
                            "kind": step.kind,
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
                        step=step,
                        context=context,
                        run_folder=run_folder,
                        step_name=step.name,
                        step_visit=self._step_execution_visit(step, step_state_store, step_item_state_store),
                    ):
                        step_result = await self.step_dispatcher.execute_async(step, context, state, pending_handoffs)
                        state = step_result.state
                        destination = step_result.destination
                        last_event = step_result.event
                        last_outcome = step_result.outcome
                        producer_raw_output = step_result.producer_raw_output
                        verifier_raw_output = step_result.verifier_raw_output
                        provider_usage = step_result.provider_usage
                        pending_handoffs = step_result.pending_handoffs
                        last_transition = step_result.finalization
                        assert last_transition is not None
                        candidate_route = last_transition.candidate_route
                        final_route = last_transition.final_route
                        runtime_control = last_transition.runtime_control
                        pending_input_id = last_transition.pending_input_id
                        target_step = last_transition.target_step
                        control_terminal = last_transition.terminal
                        final_provider_attributable = last_transition.provider_attributable
                        provider_attempted = last_transition.provider_attempted
                        producer_attempted = last_transition.producer_attempted
                        verifier_attempted = last_transition.verifier_attempted
                        control_source_hook = last_transition.source_hook
                        control_source_phase = last_transition.source_phase
                        hook_route_override_from = None if not last_transition.hook_route_redirects else last_transition.hook_route_redirects[0].from_route
                        hook_route_override_to = None if not last_transition.hook_route_redirects else last_transition.hook_route_redirects[-1].to_route
                        hook_route_redirects = last_transition.hook_route_redirects
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
                                pending_input_id=pending_input_id,
                                target_step=target_step,
                                terminal=control_terminal,
                                provider_attributable=final_provider_attributable,
                                provider_attempted=provider_attempted,
                                producer_attempted=producer_attempted,
                                verifier_attempted=verifier_attempted,
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
                        worklist_selection_snapshots=selection_snapshots,
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
                            worklist_selection_snapshots=selection_snapshots,
                            pending_handoffs=pending_handoffs,
                            pending_input=None,
                            pending_answer=None,
                        )
                        terminal_failure_handled = True
                        raise
                    self.checkpoint_store.clear()
                    return result
                if destination == AWAIT_INPUT:
                    pending_input = step_result.pending_input or self._pending_input_from_event(
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
                        worklist_selection_snapshots=selection_snapshots,
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
                        worklist_selection_snapshots=selection_snapshots,
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
                        worklist_selection_snapshots=selection_snapshots,
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
        finally:
            self.provider_policy_resolver = previous_provider_policy_resolver

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
        request_file: Path | None = None,
        task_request_file: Path | None = None,
        params: BaseModel | None = None,
        workflow_params: Mapping[str, Any] | None = None,
        message: str | None | object = _DEFAULT_MESSAGE,
        workflow_input: BaseModel | None = None,
        workflow_invoker: Callable[..., Any] | None = None,
        answer: str | None = None,
        max_steps: int = 100,
    ) -> RunResult:
        return run_awaitable_sync(
            lambda: self.resume_async(
                task_id=task_id,
                run_id=run_id,
                task_folder=task_folder,
                workflow_folder=workflow_folder,
                run_folder=run_folder,
                package_folder=package_folder,
                root=root,
                request_file=request_file,
                task_request_file=task_request_file,
                params=params,
                workflow_params=workflow_params,
                message=message,
                workflow_input=workflow_input,
                workflow_invoker=workflow_invoker,
                answer=answer,
                max_steps=max_steps,
            ),
            active_loop_error="Synchronous engine execution cannot bridge async execution inside an active event loop.",
        )

    async def resume_async(
        self,
        *,
        task_id: str,
        run_id: str,
        task_folder: Path,
        workflow_folder: Path | None = None,
        run_folder: Path,
        package_folder: Path | None = None,
        root: Path | None = None,
        request_file: Path | None = None,
        task_request_file: Path | None = None,
        params: BaseModel | None = None,
        workflow_params: Mapping[str, Any] | None = None,
        message: str | None | object = _DEFAULT_MESSAGE,
        workflow_input: BaseModel | None = None,
        workflow_invoker: Callable[..., Any] | None = None,
        answer: str | None = None,
        max_steps: int = 100,
    ) -> RunResult:
        return await self.run_async(
            task_id=task_id,
            run_id=run_id,
            task_folder=task_folder,
            workflow_folder=workflow_folder,
            run_folder=run_folder,
            package_folder=package_folder,
            root=root,
            request_file=request_file,
            task_request_file=task_request_file,
            params=params,
            workflow_params=workflow_params,
            message=message,
            workflow_input=workflow_input,
            workflow_invoker=workflow_invoker,
            resume=True,
            answer=answer,
            max_steps=max_steps,
        )

    def _normalize_direct_runtime_control(
        self,
        *,
        step: CompiledStep,
        context: Context,
        control: RequestInput | Goto | Fail,
        hook_name: str,
        hook_phase: str,
    ) -> _DirectRuntimeControl:
        runtime_control = "request_input"
        target_step: str | None = None
        pending_input_id: str | None = None
        try:
            if isinstance(control, RequestInput):
                pending_input = self._build_pending_input(step.name, hook_name, hook_phase, control)
                pending_input_id = pending_input.pending_input_id
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
                runtime_control = "goto"
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
            runtime_control = "fail"
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
        except Exception as exc:
            annotated = self._annotate_execution_error(
                exc,
                checkpoint_state=self._clone_state(context.state),
                failure_context=FailureContext(
                    kind="runtime_control_validation",
                    step_name=step.name,
                    runtime_control=runtime_control,
                    source_hook=hook_name,
                    source_phase=hook_phase,
                    target_step=target_step,
                    pending_input_id=pending_input_id,
                    details={"error": str(exc), "error_type": type(exc).__name__},
                ),
            )
            if annotated is exc:
                raise
            raise annotated from exc

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
            session=context._session_store.snapshot(),
        )

    def _restore_hook_context(self, context: Context, snapshot: _HookSnapshot) -> None:
        context._session_store.restore(snapshot.session)
        if snapshot.state is not None:
            context_runtime(context).set_state(self._clone_state(snapshot.state))
        self._restore_model_or_dict(getattr(context, "_step_state", None), snapshot.step_state)
        self._restore_model_or_dict(getattr(context, "_item_state", None), snapshot.item_state)
        self._restore_model_or_dict(getattr(context, "_step_item_state", None), snapshot.step_item_state)

    def _resolve_session(self, step: CompiledStep, context: Context) -> SessionBinding | None:
        return self._select_session(step, context)

    def _select_session(self, step: CompiledStep, context: Context) -> SessionBinding | None:
        if step.session_name is None:
            return None
        active_key = context._session_store.snapshot().active_keys_by_slot.get(step.session_name)
        if active_key is not None and active_key.domain in {"explicit_scope", "explicit_key"}:
            binding = context.get_session(step.session_name)
            return binding or context.open_session(step.session_name)
        session_definition = self.compiled.sessions.get(step.session_name)
        continuity = session_definition.continuity if session_definition is not None else None
        binding = context.get_session(step.session_name, continuity=continuity)
        return binding or context.open_session(step.session_name, continuity=continuity)

    def _persist_session(self, binding: SessionBinding | None, *, context: Context | None = None) -> None:
        if binding is not None:
            target_store = self.session_store if context is None else context._session_store
            target_store.upsert(binding)

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

    def _route_table_for_step(self, step: CompiledStep) -> dict[str, CompiledRoute]:
        if step.route_table is not None:
            return dict(step.route_table)
        route_table = dict(self.compiled.global_routes)
        route_table.update(self.compiled.routes.get(step.name, {}))
        return route_table

    def _compiled_route_for_step(self, step: CompiledStep, route_tag: str) -> CompiledRoute:
        if step.route_table is not None:
            compiled_route = step.route_table.get(route_tag)
            if compiled_route is None:
                raise RoutingError(f"no route for step {step.name!r} and tag {route_tag!r}")
            return compiled_route
        return self.compiled.route(step.name, route_tag)

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
            error = self._annotate_execution_error(
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

    def _resolve_prompt(self, prompt: str | Prompt | None, *, context: Context) -> ResolvedPrompt:
        if prompt is None:
            raise WorkflowExecutionError("missing prompt specification")
        if self.prompt_registry is not None:
            resolved = self.prompt_registry.resolve(prompt)
        elif isinstance(prompt, Prompt):
            if prompt.source == "inline":
                resolved = ResolvedPrompt(path=prompt.path, text=prompt.text, source="inline")
            elif prompt.path is not None:
                candidate = Path(prompt.path)
                if candidate.is_absolute() and candidate.exists():
                    resolved = ResolvedPrompt(path=str(candidate), text=candidate.read_text(encoding="utf-8"), source=prompt.source)
                else:
                    resolved = ResolvedPrompt(path=prompt.path, text=None, source=prompt.source)
            else:
                resolved = ResolvedPrompt(path=prompt.path, text=None, source=prompt.source)
        else:
            resolved = ResolvedPrompt(path=prompt, text=None, source="registry")
        if resolved.text is None:
            return resolved
        placeholder_label = "prompt placeholder"
        if context._step_name:
            placeholder_label = f"prompt placeholder on step {context._step_name!r}"
        return replace(
            resolved,
            text=render_runtime_template(
                resolved.text,
                context,
                placeholder_label=placeholder_label,
                replace_roots=frozenset({"ctx", "item", "worklist", "branch", "fan_in"}),
            ),
        )

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
        if not isinstance(outcome.payload, dict):
            raise ProviderExecutionError(
                f"provider returned non-object payload for step {step.name!r} route {outcome.tag!r}",
                failure_context=FailureContext(
                    kind="invalid_payload",
                    step_name=step.name,
                    candidate_route=outcome.tag,
                    provider_attributable=True,
                    details={"step": step.name, "route": outcome.tag, "error": "payload must be an object"},
                ),
                retry_kind="invalid_payload",
            )
        if not isinstance(outcome.route_fields, dict):
            raise ProviderExecutionError(
                f"provider returned non-object route_fields for step {step.name!r} route {outcome.tag!r}",
                failure_context=FailureContext(
                    kind="invalid_payload",
                    step_name=step.name,
                    candidate_route=outcome.tag,
                    provider_attributable=True,
                    details={"step": step.name, "route": outcome.tag, "error": "route_fields must be an object"},
                ),
                retry_kind="invalid_payload",
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
                    details={"step": step.name, "route": outcome.tag, "legal_routes": list(provider_available_routes)},
                ),
                retry_kind="illegal_route",
            )
        compiled_route = self._route_table_for_step(step).get(outcome.tag)
        if compiled_route is None:
            raise ProviderExecutionError(
                f"provider returned route {outcome.tag!r} without compiled metadata for step {step.name!r}",
                failure_context=FailureContext(
                    kind="illegal_route",
                    step_name=step.name,
                    candidate_route=outcome.tag,
                    provider_attributable=True,
                    details={"step": step.name, "route": outcome.tag, "error": "route is not compiled for this step"},
                ),
                retry_kind="illegal_route",
            )
        legacy_route_fields = dict(outcome.route_fields)
        if is_question_style_route(compiled_route, tag=outcome.tag) and "questions" not in legacy_route_fields:
            if isinstance(outcome.question, str) and outcome.question.strip():
                legacy_route_fields["questions"] = [outcome.question.strip()]
        if (compiled_route.preset_kind in {"question", "blocked", "failed"} or outcome.tag in {"blocked", "failed"}) and "reason" not in legacy_route_fields:
            legacy_route_fields["reason"] = outcome.reason or None
        normalized_route_fields = normalize_route_fields_for_route(compiled_route, legacy_route_fields)
        if normalized_route_fields != outcome.route_fields:
            object.__setattr__(outcome, "route_fields", normalized_route_fields)
            object.__setattr__(outcome, "question", project_questions_markdown(normalized_route_fields.get("questions")))
            route_reason = normalized_route_fields.get("reason")
            object.__setattr__(outcome, "reason", route_reason if isinstance(route_reason, str) else "")
        if is_question_style_route(compiled_route, tag=outcome.tag) and (
            not isinstance(outcome.question, str) or not outcome.question.strip()
        ):
            raise ProviderExecutionError(
                f"provider returned question route without a non-empty question for step {step.name!r}",
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
        payload_validator = None
        if compiled_route.payload_schema_mode == "explicit":
            payload_validator = compiled_route.payload_validator
        elif compiled_route.payload_schema_mode == "inherit":
            payload_validator = step.expected_output_validator
        try:
            if payload_validator is not None:
                payload_validator(outcome.payload)
            self._validate_outcome_route_fields(step, compiled_route, outcome)
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

    def _validate_outcome_route_fields(
        self,
        step: CompiledStep,
        route: CompiledRoute,
        outcome: Outcome,
    ) -> None:
        if route.route_fields_validator is not None:
            route.route_fields_validator(outcome.route_fields)
            return
        if is_question_style_route(route, tag=outcome.tag):
            questions = outcome.route_fields.get("questions")
            if not isinstance(questions, list) or not questions:
                raise ValueError("question route requires a non-empty route_fields.questions list")
            for question in questions:
                if not isinstance(question, str) or not question.strip():
                    raise ValueError("question route requires non-empty strings in route_fields.questions")
            reason = outcome.route_fields.get("reason")
            if reason is not None and not isinstance(reason, str):
                raise ValueError("question route route_fields.reason must be a string or null")
            return
        if route.preset_kind in {"blocked", "failed"} or outcome.tag in {"blocked", "failed"}:
            reason = outcome.route_fields.get("reason")
            if reason is not None and not isinstance(reason, str):
                raise ValueError(f"{route.preset_kind} route route_fields.reason must be a string or null")
            return
        if route.route_fields_schema is None and outcome.route_fields:
            raise ValueError("route does not declare route_fields metadata")

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
        compiled_route = self._route_table_for_step(step).get(event.tag)
        if compiled_route is not None and is_question_style_route(compiled_route, tag=event.tag) and (
            not isinstance(event.question, str) or not event.question.strip()
        ):
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
    def _resolve_workspace_read_path(self, raw_path: str, *, context: Context) -> Path:
        candidate = Path(raw_path)
        if candidate.is_absolute():
            return candidate
        if candidate.parts and candidate.parts[0] == "_branch_groups":
            return (context.workflow_folder / candidate).resolve()
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

    def _provider_available_routes_for_step(self, step: CompiledStep) -> tuple[str, ...]:
        return self.provider_contract_builder.available_routes(step)

    def _resolve_pair_review_session(
        self,
        step: CompiledStep,
        context: Context,
        *,
        producer_session: SessionBinding | None,
    ) -> SessionBinding | None:
        if step.verifier_session_name is None:
            return producer_session
        active_key = context._session_store.snapshot().active_keys_by_slot.get(step.verifier_session_name)
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

    def _restore_worklist_selections(
        self,
        context: Context,
        snapshots: Mapping[str, SelectionSnapshot],
    ) -> dict[str, SelectionSnapshot]:
        selection_snapshots: dict[str, SelectionSnapshot] = {}
        for name, snapshot in snapshots.items():
            if name in self.compiled.worklists:
                selection_snapshots[name] = snapshot
        context_runtime(context).set_selection_snapshots(selection_snapshots)
        return selection_snapshots

    def _ensure_worklist_selection(
        self,
        context: Context,
        worklist_name: str,
    ) -> Selection[Any]:
        existing = getattr(context, "_selections", {}).get(worklist_name)
        if existing is not None:
            return existing
        worklist = self.compiled.worklists.get(worklist_name)
        if worklist is None:
            raise WorkflowExecutionError(f"unknown worklist {worklist_name!r}")
        snapshot = getattr(context, "_selection_snapshots", {}).get(worklist_name)
        source_type = worklist.source_type
        source_path = self._worklist_source_path(worklist, context)
        try:
            worklist.ensure_source(context)
        except Exception as exc:
            raise self._worklist_selection_resolution_error(
                worklist_name=worklist_name,
                source_type=source_type,
                source_path=source_path,
                phase="ensure",
                error=exc,
            ) from exc
        try:
            items = worklist._load_source_items(context, ensure=False)
        except Exception as exc:
            raise self._worklist_selection_resolution_error(
                worklist_name=worklist_name,
                source_type=source_type,
                source_path=source_path,
                phase="load",
                error=exc,
            ) from exc
        try:
            worklist._validate_loaded_items(context, items)
        except Exception as exc:
            raise self._worklist_selection_resolution_error(
                worklist_name=worklist_name,
                source_type=source_type,
                source_path=source_path,
                phase="validate",
                error=exc,
            ) from exc
        try:
            cached_items = worklist._cache_loaded_items(context, items)
            selection = worklist._selection_from_loaded_items(context, cached_items, snapshot=snapshot)
        except Exception as exc:
            raise self._worklist_selection_resolution_error(
                worklist_name=worklist_name,
                source_type=source_type,
                source_path=source_path,
                phase="restore" if snapshot is not None else "select",
                error=exc,
                selector_details=self._worklist_selector_details(worklist),
            ) from exc
        runtime = context_runtime(context)
        runtime.set_selection(worklist_name, selection)
        runtime.sync_scoped_state_after_worklist_selection_change(worklist_name)
        runtime.emit_worklist_selection_resolved(
            worklist_name=worklist_name,
            selection=selection,
            lazy=True,
            source=self._worklist_source_descriptor(worklist, context),
        )
        return selection

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
        worklist_selection_snapshots: Mapping[str, SelectionSnapshot] | None = None,
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
            worklist_selections=self._snapshot_worklist_selections(
                worklist_selections,
                snapshots=worklist_selection_snapshots,
            ),
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
        *,
        snapshots: Mapping[str, SelectionSnapshot] | None = None,
    ) -> dict[str, SelectionSnapshot] | None:
        if not selections and not snapshots:
            return None
        serialized: dict[str, SelectionSnapshot] = {}
        if snapshots:
            for name, snapshot in snapshots.items():
                if name in self.compiled.worklists:
                    serialized[name] = snapshot
        for name, selection in (selections or {}).items():
            worklist = self.compiled.worklists.get(name)
            if worklist is None:
                continue
            serialized[name] = worklist.snapshot_selection(selection)
        return serialized or None

    def _worklist_source_path(self, worklist: Any, context: Context) -> str | None:
        descriptor = self._worklist_source_descriptor(worklist, context)
        if ":" not in descriptor:
            return None
        return descriptor.split(":", 1)[1]

    def _worklist_source_descriptor(self, worklist: Any, context: Context) -> str:
        if hasattr(worklist, "source_descriptor"):
            return worklist.source_descriptor(context)
        return "unknown"

    @staticmethod
    def _worklist_selector_details(worklist: Any) -> str | None:
        selector = getattr(worklist, "selector", None)
        if selector is None:
            return None
        parts: list[str] = []
        default_mode = getattr(selector, "default_mode", None)
        allowed_modes = getattr(selector, "allowed_modes", None)
        item_param = getattr(selector, "item_param", None)
        mode_param = getattr(selector, "mode_param", None)
        if isinstance(default_mode, str) and default_mode:
            parts.append(f"default_mode={default_mode}")
        if isinstance(allowed_modes, Sequence) and allowed_modes:
            parts.append("allowed_modes=" + ",".join(str(mode) for mode in allowed_modes))
        if isinstance(item_param, str) and item_param:
            parts.append(f"item_param={item_param}")
        if isinstance(mode_param, str) and mode_param:
            parts.append(f"mode_param={mode_param}")
        if not parts:
            return None
        return "; ".join(parts)

    @staticmethod
    def _worklist_selection_resolution_error(
        *,
        worklist_name: str,
        source_type: str,
        source_path: str | None,
        phase: str,
        error: Exception,
        selector_details: str | None = None,
    ) -> WorkflowExecutionError:
        details = [f"phase={phase}"]
        if source_path is not None:
            details.append(f"path={source_path}")
        if selector_details is not None:
            details.append(f"selector={selector_details}")
        underlying = str(error).strip() or type(error).__name__
        return WorkflowExecutionError(
            f"worklist {worklist_name!r} could not resolve selection from {source_type} source "
            f"({', '.join(details)}): {underlying}"
        )

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
        return exception_checkpoint_state(exc, current_state=current_state)

    def _failure_context_for_exception(self, exc: Exception) -> FailureContext | None:
        return exception_failure_context(exc)

    @staticmethod
    def _pending_handoffs_for_exception(
        exc: Exception,
        pending_handoffs: tuple[PendingHandoff, ...],
    ) -> tuple[PendingHandoff, ...]:
        return exception_pending_handoffs(exc, default=pending_handoffs)

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
        return exception_retry_kind(exc)

    def _annotate_execution_error(
        self,
        exc: Exception,
        *,
        checkpoint_state: BaseModel | None = None,
        failure_context: FailureContext | None = None,
        retry_kind: str | None = None,
        pending_handoffs: tuple[PendingHandoff, ...] | None = None,
    ) -> Exception:
        return enrich_execution_error(
            exc,
            checkpoint_state=checkpoint_state,
            failure_context=failure_context,
            retry_kind=retry_kind,
            pending_handoffs=pending_handoffs,
        )

    def _next_retry_feedback(
        self,
        step: CompiledStep,
        exc: Exception,
        *,
        attempt: int,
    ) -> tuple[str | None, Exception]:
        kind = self._provider_retry_kind(exc)
        if kind is None:
            return None, exc
        if not self._retry_policy_allows(step.retry_policy, kind):
            return None, exc
        if attempt >= step.retry_policy.max_attempts:
            return None, self._annotate_retry_exhaustion(exc, step=step, attempt=attempt, kind=kind)
        updated_exc = self._ensure_retry_failure_context(exc, step=step, kind=kind)
        return build_retry_feedback(
            updated_exc,
            step_name=step.name,
            attempt=attempt + 1,
            max_attempts=step.retry_policy.max_attempts,
        ), updated_exc

    def _annotate_retry_exhaustion(
        self,
        exc: Exception,
        *,
        step: CompiledStep,
        attempt: int,
        kind: str,
    ) -> Exception:
        updated_exc = self._ensure_retry_failure_context(exc, step=step, kind=kind)
        failure_context = self._failure_context_for_exception(updated_exc)
        if failure_context is None:
            return updated_exc
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
        if isinstance(updated_exc, WorkflowExecutionError):
            return replace_execution_error(updated_exc, failure_context=updated)
        return WorkflowExecutionError(str(updated_exc), failure_context=updated)

    def _ensure_retry_failure_context(
        self,
        exc: Exception,
        *,
        step: CompiledStep,
        kind: str,
    ) -> Exception:
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
        if isinstance(exc, WorkflowExecutionError):
            return replace_execution_error(exc, failure_context=failure_context, retry_kind=kind)
        return WorkflowExecutionError(str(exc), failure_context=failure_context, retry_kind=kind)

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
        explicit = exception_retry_kind(exc)
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
            return render_runtime_template(
                step.message,
                context,
                placeholder_label=f"workflow step {step.name!r} message placeholder",
                replace_roots=frozenset({"ctx", "item", "worklist", "branch", "fan_in"}),
            )
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

    def _map_workflow_step_result(self, step: CompiledStep, child_result: Any) -> Event:
        terminal = getattr(child_result, "terminal", None)
        last_event = getattr(child_result, "last_event", None)
        checkpoint = getattr(child_result, "checkpoint", None)
        pending_input = getattr(checkpoint, "pending_input", None)
        pending_question = pending_input.question if isinstance(pending_input, PendingInput) else None
        if terminal == FINISH:
            return Event("done")
        if terminal == FAIL:
            self._ensure_child_workflow_route_declared(
                step,
                child_terminal=terminal,
                mapped_route="failed",
            )
            reason = last_event.reason if isinstance(last_event, Event) and last_event.reason else "Child workflow failed."
            return Event("failed", reason=reason)
        if terminal == AWAIT_INPUT and isinstance(last_event, Event) and isinstance(last_event.question, str) and last_event.question.strip():
            return Event("question", reason=last_event.reason, question=last_event.question)
        if terminal == AWAIT_INPUT and isinstance(pending_question, str) and pending_question:
            reason = last_event.reason if isinstance(last_event, Event) else ""
            return Event("question", reason=reason, question=pending_question)
        if terminal == AWAIT_INPUT:
            self._ensure_child_workflow_route_declared(
                step,
                child_terminal=terminal,
                mapped_route="blocked",
            )
            reason = (
                last_event.reason
                if isinstance(last_event, Event) and last_event.reason
                else "Child workflow is awaiting input."
            )
            return Event("blocked", reason=reason)
        raise WorkflowExecutionError(f"child workflow returned unsupported terminal {terminal!r}")

    @staticmethod
    def _ensure_child_workflow_route_declared(
        step: CompiledStep,
        *,
        child_terminal: str,
        mapped_route: str,
    ) -> None:
        if mapped_route in step.available_routes:
            return
        declared_routes = ", ".join(step.authored_routes) or "<none>"
        raise WorkflowExecutionError(
            f"child workflow step {step.name!r} returned terminal {child_terminal!r}, which maps to route "
            f"{mapped_route!r}, but declared routes are: {declared_routes}. "
            "Recommended fix: declare the route or change child-result mapping."
        )

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
            route_fields=deepcopy(outcome.route_fields),
        )

    def _event_from_outcome(self, step: CompiledStep, outcome: Outcome) -> Event:
        compiled_route = self._route_table_for_step(step).get(outcome.tag)
        question = outcome.question
        if compiled_route is not None and is_question_style_route(compiled_route, tag=outcome.tag):
            question = project_questions_markdown(outcome.route_fields.get("questions"))
        reason_value = outcome.route_fields.get("reason") if isinstance(outcome.route_fields, dict) else None
        reason = reason_value if isinstance(reason_value, str) else outcome.reason
        return Event(outcome.tag, reason=reason, question=question)

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

    def _validate_resume_checkpoint_target(self, checkpoint: Checkpoint) -> None:
        stage = checkpoint.stage
        if not isinstance(stage, str) or not stage:
            raise WorkflowExecutionError("resume checkpoint does not declare the step to continue")
        if stage not in self.compiled.steps:
            raise WorkflowExecutionError(
                f"resume checkpoint refers to step {stage!r}, but the current workflow does not declare that step"
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
                if route_is_rework(final_event.tag):
                    step_state.rework_count = getattr(step_state, "rework_count", 0) + 1
                if route_is_replan(final_event.tag):
                    step_state.replan_count = getattr(step_state, "replan_count", 0) + 1
            return
        step_state["last_route"] = final_event.tag
        step_state["last_reason"] = final_event.reason
        if step.kind == "produce_verify":
            if route_is_rework(final_event.tag):
                current_rework = step_state.get("rework_count", 0)
                step_state["rework_count"] = current_rework + 1 if isinstance(current_rework, int) else 1
            if route_is_replan(final_event.tag):
                current_replan = step_state.get("replan_count", 0)
                step_state["replan_count"] = current_replan + 1 if isinstance(current_replan, int) else 1

    @staticmethod
    def _update_item_runtime_state_on_entry(
        step: CompiledStep,
        context: Context,
        item_state: BaseModel | dict[str, Any] | None,
    ) -> None:
        if step.scope_name is None or item_state is None:
            return
        current_item = context.current(step.scope_name)
        current_status = None if current_item is None else current_item.status
        if isinstance(item_state, BaseModel):
            item_state.status = current_status
            item_state.last_step = step.name
            return
        item_state["status"] = current_status
        item_state["last_step"] = step.name

    @staticmethod
    def _update_final_item_runtime_state(
        item_state: BaseModel | dict[str, Any] | None,
        final_event: Event,
    ) -> None:
        if item_state is None:
            return
        if isinstance(item_state, BaseModel):
            item_state.last_route = final_event.tag
            return
        item_state["last_route"] = final_event.tag

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
        state_model = worklist.runtime_item_state_model if worklist is not None else None
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

    def _sync_context_scoped_state_after_worklist_selection_change(
        self,
        context: Context,
        step: CompiledStep,
        item_states: dict[str, BaseModel | dict[str, Any]],
        step_item_states: dict[str, dict[str, BaseModel | dict[str, Any]]],
        *,
        worklist_name: str,
    ) -> None:
        if step.scope_name != worklist_name:
            return
        item_key = self._current_item_state_key(context, step)
        item_state_store = self._ensure_item_state_store(item_states, step, item_key=item_key)
        step_item_state_store = self._ensure_step_item_state_store(step_item_states, step, item_key=item_key)
        runtime = context_runtime(context)
        runtime.set_item_state_store(item_state_store)
        runtime.set_step_item_state_store(step_item_state_store)
        self._update_item_runtime_state_on_entry(step, context, item_state_store)

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
        self,
        *,
        step: CompiledStep,
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
    ) -> StepFinalizationRecord:
        provider_attempted, producer_attempted, verifier_attempted = self._provider_attempt_flags(
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

    def _step_result_from_direct_control(
        self,
        *,
        step: CompiledStep,
        state: BaseModel,
        control: _DirectRuntimeControl,
        pending_handoffs: tuple[PendingHandoff, ...],
        producer_raw_output: str | None = None,
        verifier_raw_output: str | None = None,
        provider_usage: StepProviderUsage | None = None,
    ) -> StepExecutionResult:
        pending_input = control.pending_input
        finalization = self._build_step_finalization_record(
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
        return StepExecutionResult(
            state=state,
            destination=control.destination,
            event=None,
            outcome=None,
            pending_handoffs=pending_handoffs,
            producer_raw_output=producer_raw_output,
            verifier_raw_output=verifier_raw_output,
            provider_usage=provider_usage,
            finalization=finalization,
            pending_input=pending_input,
        )

    def _step_result_from_route_finalization(
        self,
        *,
        step: CompiledStep,
        route_finalization: RouteFinalizationResult,
        outcome: Outcome | None = None,
        producer_raw_output: str | None = None,
        verifier_raw_output: str | None = None,
        provider_usage: StepProviderUsage | None = None,
    ) -> StepExecutionResult:
        finalization = self._build_step_finalization_record(
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
            finalization=finalization,
            pending_input=route_finalization.pending_input,
            route_finalization=route_finalization,
        )

    @staticmethod
    def _provider_exec_result(response: Any, *, text: str) -> ProviderExecResult:
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

    @staticmethod
    def _exception_failure_context(exc: Exception) -> dict[str, Any]:
        return exception_failure_context_payload(exc)

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
