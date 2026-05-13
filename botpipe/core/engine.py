"""Deterministic workflow execution engine."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
from typing import Any, Callable, Literal, Mapping
from uuid import uuid4

from pydantic import BaseModel, TypeAdapter
from .branch_groups.runtime import BranchGroupRuntime
from .compiler import compile_workflow, runtime_workflow_validation_message
from .context import Context, _DEFAULT_MESSAGE, _resolve_context_root, _step_execution_id
from .engine_collaborators import (
    ArtifactGuard,
    CheckpointManager,
    HookRunner,
    OperationRecorder,
    ProviderContractBuilder,
    RouteFinalizer,
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
    StepExecutionError,
    WorkflowExecutionError,
    WorkflowValidationError,
    exception_checkpoint_state,
    exception_failure_context,
    exception_pending_handoffs,
)
from .execution_services import ExecutionServices
from .execution_runtime_services import (
    ArtifactRuntimeService,
    CheckpointRuntimeService,
    ChildWorkflowRuntimeService,
    EventRuntimeService,
    OperationBindingService,
    ProviderRuntimeService,
    RouteRuntimeService,
    SessionRuntimeService,
    StateRuntimeService,
    _validate_json_schema_mapping,
)
from .operations import serialize_context_values
from .provider_policy import SYSTEM_DEFAULT_PROVIDER_POLICY
from .provider_policy_resolution import LayeredProviderPolicyResolver, ProviderPolicyResolverProtocol
from .primitives import AWAIT_INPUT, Checkpoint, Event, FAIL, FINISH, Outcome, PendingHandoff
from .prompts import PromptRegistry
from .providers.models import (
    RuntimeInteractionPolicy,
)
from .providers.protocols import LLMProvider, validate_llm_provider
from .route_contracts import (
    AwaitInput as AwaitInputAction,
    Continue,
    FailAction,
    Finish as FinishAction,
)
from .step_plans import StepPlan
from .stores.protocols import (
    CheckpointStore,
    PendingInput,
    SessionSnapshot,
    SessionStore,
    normalize_session_snapshot,
)
from .workflow_plan import WorkflowPlan
from .worklists import Selection, SelectionSnapshot, _snapshot_worklist_selections


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
class _RouteControl:
    control: str
    destination: str
    pending_input: PendingInput | None = None
    target_step: str | None = None
    terminal: str | None = None
    handoff: str | None = None
    source_hook: str | None = None
    source_phase: str | None = None


@dataclass(frozen=True, slots=True)
class _RunEnvironment:
    task_id: str
    run_id: str
    task_folder: Path
    workflow_folder: Path
    run_folder: Path
    package_folder: Path
    root: Path | None
    request_file: Path | None
    task_request_file: Path | None
    params: BaseModel | None
    workflow_params: Mapping[str, Any] | None
    message: str | None | object
    workflow_input: BaseModel | None
    workflow_invoker: Callable[..., Any] | None
    binding: RunBinding
    extensions: tuple[BoundWorkflowExtension, ...]
    previous_provider_policy_resolver: ProviderPolicyResolverProtocol | None


@dataclass(slots=True)
class _RunLoopState:
    history: list[str]
    current_step_name: str | None
    state: BaseModel | None
    current_answer: str | None
    current_input_response: Any | None
    selections: dict[str, Selection[Any]]
    selection_snapshots: dict[str, SelectionSnapshot]
    values: dict[str, Any]
    step_states: dict[str, BaseModel | dict[str, Any]]
    item_states: dict[str, BaseModel | dict[str, Any]]
    step_item_states: dict[str, dict[str, BaseModel | dict[str, Any]]]
    pending_handoffs: tuple[PendingHandoff, ...] = ()
    checkpoint: Checkpoint | None = None
    terminal_failure_handled: bool = False
    last_event: Event | None = None
    last_outcome: Outcome | None = None
    last_transition: "StepFinalizationRecord | None" = None


@dataclass(frozen=True, slots=True)
class _StepFrame:
    step: StepPlan
    context: Context
    step_state_store: BaseModel | dict[str, Any]
    step_item_state_store: BaseModel | dict[str, Any] | None
    step_visit: int
    scope_name: str | None
    item_id: str | None
    step_execution_id: str

class Engine:
    """Strict workflow engine."""

    max_hook_redirects = 16

    def __init__(
        self,
        workflow: type[Any] | WorkflowPlan,
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
        provider_policy_resolver: ProviderPolicyResolverProtocol | None = None,
    ) -> None:
        self.compiled = workflow if isinstance(workflow, WorkflowPlan) else self._compile_runtime_workflow(workflow)
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
        event_service = EventRuntimeService(
            hook_event_sink=hook_event_sink,
            runtime_event_sink=runtime_event_sink,
        )
        state_service = StateRuntimeService(compiled=self.compiled)
        artifact_service = ArtifactRuntimeService(compiled=self.compiled, events=event_service)
        route_service = RouteRuntimeService(
            compiled=self.compiled,
            interaction_policy=self.interaction_policy,
            max_hook_redirects=self.max_hook_redirects,
            events=event_service,
        )
        session_service = SessionRuntimeService(compiled=self.compiled, session_store=self.session_store)
        provider_service = ProviderRuntimeService(
            compiled=self.compiled,
            provider=self.provider,
            prompt_registry=self.prompt_registry,
            interaction_policy=self.interaction_policy,
        )
        operation_service = OperationBindingService(
            compiled=self.compiled,
            provider=self.provider,
            prompt_registry=self.prompt_registry,
            operation_replay_mismatch_behavior=self.operation_replay_mismatch_behavior,
            provider_policy_resolver=self.provider_policy_resolver,
            runtime_event_sink=self.runtime_event_sink,
        )
        self.execution_services = ExecutionServices(
            artifacts=artifact_service,
            routes=route_service,
            sessions=session_service,
            events=event_service,
            providers=provider_service,
            operations=operation_service,
            state=state_service,
        )
        self.hook_runner = HookRunner(self.execution_services)
        self.execution_services = replace(self.execution_services, hooks=self.hook_runner)
        self.artifact_guard = ArtifactGuard(self.execution_services)
        self.route_finalizer = RouteFinalizer(
            self.execution_services,
            artifact_inventory=self.compiled.artifacts_by_qualified_name,
        )
        child_workflow_service = ChildWorkflowRuntimeService(
            compiled=self.compiled,
            artifacts=artifact_service,
            routes=route_service,
        )
        checkpoint_service = CheckpointRuntimeService(
            compiled=self.compiled,
            checkpoint_store=self.checkpoint_store,
            sessions=session_service,
            state=state_service,
        )
        self.execution_services = replace(
            self.execution_services,
            checkpoints=checkpoint_service,
            child_workflows=child_workflow_service,
        )
        self.operation_recorder = OperationRecorder(self.execution_services)
        self.provider_contract_builder = ProviderContractBuilder(
            compiled=self.compiled,
            services=self.execution_services,
            allow_provider_questions=self.interaction_policy.allow_provider_questions,
        )
        self.step_dispatcher = StepDispatcher(
            services=self.execution_services,
            hook_runner=self.hook_runner,
            route_finalizer=self.route_finalizer,
            branch_group_runtime=None,
            provider_contract_builder=self.provider_contract_builder,
        )
        self.branch_group_runtime = BranchGroupRuntime(
            services=self.execution_services,
            step_dispatcher=self.step_dispatcher,
            route_finalizer=self.route_finalizer,
            operation_recorder=self.operation_recorder,
        )
        self.step_dispatcher._branch_group_runtime = self.branch_group_runtime
        self.state_runtime = StateRuntime(self.execution_services)
        self.session_runtime = SessionRuntime(self.execution_services)
        self.checkpoint_manager = CheckpointManager(self.execution_services)
        self.workflow_invoker = WorkflowInvoker(self.execution_services)

    @staticmethod
    def _compile_runtime_workflow(workflow: type[Any]) -> WorkflowPlan:
        try:
            return compile_workflow(workflow)
        except WorkflowValidationError as exc:
            message = runtime_workflow_validation_message(exc)
            if message is None:
                raise
            raise WorkflowExecutionError(message) from exc

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
        env = self._prepare_run_environment(
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
        )
        loop = self._new_run_loop_state()
        try:
            loop = self._restore_or_initialize_run_loop(
                env,
                loop=loop,
                initial_state=initial_state,
                resume=resume,
                answer=answer,
            )
            return await self._run_loop(env, loop, max_steps=max_steps)
        except Exception as exc:
            self._handle_run_failure(env, loop, exc)
            raise
        finally:
            self.provider_policy_resolver = env.previous_provider_policy_resolver
            self.operation_recorder.set_provider_policy_resolver(self.provider_policy_resolver)

    @staticmethod
    def _new_run_loop_state() -> _RunLoopState:
        return _RunLoopState(
            history=[],
            current_step_name=None,
            state=None,
            current_answer=None,
            current_input_response=None,
            selections={},
            selection_snapshots={},
            values={},
            step_states={},
            item_states={},
            step_item_states={},
        )

    def _prepare_run_environment(
        self,
        *,
        task_id: str,
        run_id: str,
        task_folder: Path,
        workflow_folder: Path | None,
        run_folder: Path,
        package_folder: Path | None,
        root: Path | None,
        request_file: Path | None,
        task_request_file: Path | None,
        params: BaseModel | None,
        workflow_params: Mapping[str, Any] | None,
        message: str | None | object,
        workflow_input: BaseModel | None,
        workflow_invoker: Callable[..., Any] | None,
    ) -> _RunEnvironment:
        resolved_workflow_folder = workflow_folder or task_folder / f"wf_{self.compiled.workflow_name}"
        resolved_package_folder = package_folder or (root.resolve() if root is not None else task_folder)
        previous_provider_policy_resolver = self.provider_policy_resolver
        if previous_provider_policy_resolver is None:
            self.provider_policy_resolver = LayeredProviderPolicyResolver(
                base_policy=SYSTEM_DEFAULT_PROVIDER_POLICY,
                policy_layers=(self.compiled.provider_policy,),
                workspace_root=_resolve_context_root(
                    root=root,
                    task_folder=task_folder,
                    package_folder=resolved_package_folder,
                ),
            )
        self.operation_recorder.set_provider_policy_resolver(self.provider_policy_resolver)
        self.compiled.workflow_cls()
        binding = RunBinding(
            root=root.resolve() if root is not None else task_folder.resolve(),
            task_id=task_id,
            run_id=run_id,
            workflow_name=self.compiled.workflow_name,
            task_folder=task_folder,
            workflow_folder=resolved_workflow_folder,
            run_folder=run_folder,
            package_folder=resolved_package_folder,
        )
        return _RunEnvironment(
            task_id=task_id,
            run_id=run_id,
            task_folder=task_folder,
            workflow_folder=resolved_workflow_folder,
            run_folder=run_folder,
            package_folder=resolved_package_folder,
            root=root,
            request_file=request_file,
            task_request_file=task_request_file,
            params=params,
            workflow_params=workflow_params,
            message=message,
            workflow_input=workflow_input,
            workflow_invoker=workflow_invoker,
            binding=binding,
            extensions=self._bind_extensions(binding),
            previous_provider_policy_resolver=previous_provider_policy_resolver,
        )

    def _restore_or_initialize_run_loop(
        self,
        env: _RunEnvironment,
        *,
        loop: _RunLoopState,
        initial_state: BaseModel | None,
        resume: bool,
        answer: str | None,
    ) -> _RunLoopState:
        if resume:
            return self._restore_run_loop(env, loop=loop, answer=answer)
        return self._initialize_run_loop(env, loop=loop, initial_state=initial_state)

    def _restore_run_loop(
        self,
        env: _RunEnvironment,
        *,
        loop: _RunLoopState,
        answer: str | None,
    ) -> _RunLoopState:
        checkpoint = self.checkpoint_store.load()
        if checkpoint is None:
            raise WorkflowExecutionError("resume requested but no checkpoint is available")
        self._validate_resume_checkpoint_target(checkpoint)
        self.session_runtime.restore(normalize_session_snapshot(checkpoint.session_bindings, run_id=env.run_id))
        state = checkpoint.state
        values = deepcopy(checkpoint.values or {})
        step_states = deepcopy(checkpoint.step_states or {})
        item_states = deepcopy(checkpoint.item_states or {})
        step_item_states = deepcopy(checkpoint.step_item_states or {})
        selection_context = self._build_run_context(
            env,
            state=state,
            selections={},
            selection_snapshots={},
            values=values,
        )
        selection_snapshots = self.state_runtime.restore_worklist_selections(
            selection_context,
            checkpoint.worklist_selections or {},
        )
        loop.current_step_name = checkpoint.stage
        loop.state = state
        loop.current_answer = answer if answer is not None else checkpoint.pending_answer
        loop.current_input_response = None
        loop.selection_snapshots = selection_snapshots
        loop.values = values
        loop.step_states = step_states
        loop.item_states = item_states
        loop.step_item_states = step_item_states
        loop.pending_handoffs = checkpoint.pending_handoffs
        loop.checkpoint = checkpoint
        try:
            loop.current_input_response = self._resume_input_response(checkpoint=checkpoint, answer=loop.current_answer)
        except Exception as exc:
            loop.checkpoint = self._save_loop_checkpoint(
                loop,
                stage=checkpoint.stage,
                state=self._state_for_failure(loop.state, exc) or loop.state,
                pending_input=checkpoint.pending_input,
                pending_answer=loop.current_answer,
                failure_context=self._failure_context_for_exception(exc),
            )
            raise
        return loop

    def _initialize_run_loop(
        self,
        env: _RunEnvironment,
        *,
        loop: _RunLoopState,
        initial_state: BaseModel | None,
    ) -> _RunLoopState:
        self.session_runtime.restore(SessionSnapshot(bindings=(), active_keys_by_slot={}))
        state = initial_state if initial_state is not None else self.compiled.new_state()
        loop.current_step_name = self.compiled.entry_step_name
        loop.state = state
        context = self._build_run_context(
            env,
            state=state,
            selections=loop.selections,
            selection_snapshots=loop.selection_snapshots,
            values=loop.values,
        )
        self._configure_context_frame(context)
        if self.compiled.default_session_open:
            context.open_session(self.compiled.default_session_name)
        loop.state = context.state
        return loop

    def _build_run_context(
        self,
        env: _RunEnvironment,
        *,
        state: BaseModel,
        selections: Mapping[str, Selection[Any]],
        selection_snapshots: Mapping[str, SelectionSnapshot],
        values: Mapping[str, Any],
        step: StepPlan | None = None,
        answer: str | None = None,
        input_response: Any | None = None,
        runtime_event_sink: Callable[[str, Mapping[str, Any]], None] | None = None,
    ) -> Context:
        return Context(
            root=env.root,
            task_id=env.task_id,
            run_id=env.run_id,
            workflow_name=self.compiled.workflow_name,
            task_folder=env.task_folder,
            workflow_folder=env.workflow_folder,
            run_folder=env.run_folder,
            package_folder=env.package_folder,
            request_file=env.request_file,
            task_request_file=env.task_request_file,
            state=state,
            session_store=self.session_store,
            session_definitions=self.compiled.sessions,
            worklists=self.compiled.worklists,
            selections=selections,
            selection_snapshots=selection_snapshots,
            active_worklist=None if step is None else step.scope_name,
            params=env.params,
            workflow_params=env.workflow_params,
            message=env.message,
            workflow_input=env.workflow_input,
            workflow_invoker=env.workflow_invoker,
            answer=answer,
            input_response=input_response,
            step_name=None if step is None else step.name,
            default_session_name=self.compiled.default_session_name,
            values=values,
            runtime_event_sink=runtime_event_sink,
        )

    def _configure_context_frame(self, context: Context) -> Context:
        context._set_worklist_selection_resolver(
            lambda worklist_name, *, _context=context: self.state_runtime.ensure_worklist_selection(
                _context,
                worklist_name,
            )
        )
        return context

    async def _run_loop(
        self,
        env: _RunEnvironment,
        loop: _RunLoopState,
        *,
        max_steps: int,
    ) -> RunResult:
        for _ in range(max_steps):
            frame = self._prepare_step_frame(env, loop)
            step_result = await self._execute_step_frame(env, loop, frame)
            terminal = self._handle_step_result(env, loop, frame, step_result)
            if terminal is not None:
                return terminal
        raise WorkflowExecutionError(f"workflow exceeded max_steps={max_steps}")

    def _prepare_step_frame(
        self,
        env: _RunEnvironment,
        loop: _RunLoopState,
    ) -> _StepFrame:
        assert loop.state is not None
        assert loop.current_step_name is not None
        step = self.compiled.steps[loop.current_step_name]
        context = self._build_run_context(
            env,
            state=loop.state,
            selections=loop.selections,
            selection_snapshots=loop.selection_snapshots,
            values=loop.values,
            step=step,
            answer=loop.current_answer,
            input_response=loop.current_input_response,
            runtime_event_sink=self.runtime_event_sink,
        )
        runtime = self._configure_context_frame(context)
        step_state_store = self._ensure_step_state_store(loop.step_states, step)
        self._increment_step_runtime_state(step_state_store)
        runtime._sync_step_state(step_state_store)
        if step.scope_name is not None:
            context.ensure_selection(step.scope_name)
        current_item_key = self._current_item_state_key(context, step)
        item_state_store = self._ensure_item_state_store(loop.item_states, step, item_key=current_item_key)
        step_item_state_store = self._ensure_step_item_state_store(
            loop.step_item_states,
            step,
            item_key=current_item_key,
        )
        if item_state_store is not None:
            runtime._sync_item_state(item_state_store)
        if step_item_state_store is not None:
            self._increment_step_runtime_state(step_item_state_store)
            runtime._sync_step_item_state(step_item_state_store)
        self._update_item_runtime_state_on_entry(step, context, getattr(context, "_item_state", None))
        runtime._sync_worklist_selection(
            lambda worklist_name, *, _context=context, _step=step, _item_states=loop.item_states, _step_item_states=loop.step_item_states: self._sync_context_scoped_state_after_worklist_selection_change(
                _context,
                _step,
                _item_states,
                _step_item_states,
                worklist_name=worklist_name,
            )
        )
        runtime._sync_values(loop.values)
        runtime._sync_meta(
            {
                "step": {
                    "name": step.name,
                    "kind": step.kind,
                    "visits": self._step_runtime_visits(step_state_store),
                    "last_route": getattr(step_state_store, "last_route", None),
                }
            }
        )
        loop.history.append(step.name)
        step_visit = self._step_execution_visit(step, step_state_store, step_item_state_store)
        scope_name, item_id = self._current_step_scope_item(context, step)
        return _StepFrame(
            step=step,
            context=context,
            step_state_store=step_state_store,
            step_item_state_store=step_item_state_store,
            step_visit=step_visit,
            scope_name=scope_name,
            item_id=item_id,
            step_execution_id=_step_execution_id(
                step_name=step.name,
                visit=step_visit,
                scope_name=scope_name,
                item_id=item_id,
            ),
        )

    async def _execute_step_frame(
        self,
        env: _RunEnvironment,
        loop: _RunLoopState,
        frame: _StepFrame,
    ) -> StepExecutionResult:
        assert loop.state is not None
        self._notify_before_step(
            env.extensions,
            StepStart(
                binding=env.binding,
                step_name=frame.step.name,
                step_kind=frame.step.kind,
                state=self._clone_state(loop.state),
                answer=loop.current_answer,
                visit=frame.step_visit,
                step_execution_id=frame.step_execution_id,
                scope=frame.scope_name,
                item_id=frame.item_id,
            ),
        )
        state_before = self._clone_state(loop.state)
        failure_state = loop.state
        failure_handoffs = loop.pending_handoffs
        try:
            with self.operation_recorder.bind_step(
                step=frame.step,
                context=frame.context,
                run_folder=env.run_folder,
                step_name=frame.step.name,
                step_visit=frame.step_visit,
            ):
                step_result = await self.step_dispatcher.execute_async(
                    frame.step,
                    frame.context,
                    loop.state,
                    loop.pending_handoffs,
                )
            failure_state = step_result.state
            failure_handoffs = step_result.pending_handoffs
            loop.state = step_result.state
            loop.pending_handoffs = step_result.pending_handoffs
            loop.last_event = step_result.event
            loop.last_outcome = step_result.outcome
            loop.last_transition = step_result.transition
            self._emit_after_step_notification(env, frame, state_before, step_result)
        except Exception as exc:
            loop.checkpoint = self._save_loop_checkpoint(
                loop,
                stage=loop.current_step_name or frame.step.name,
                state=self._state_for_failure(failure_state, exc),
                pending_input=None,
                pending_answer=loop.current_answer,
                pending_handoffs=exception_pending_handoffs(exc, default=failure_handoffs),
                failure_context=self._failure_context_for_exception(exc),
            )
            raise
        return step_result

    def _emit_after_step_notification(
        self,
        env: _RunEnvironment,
        frame: _StepFrame,
        state_before: BaseModel | None,
        step_result: StepExecutionResult,
    ) -> None:
        state_after = step_result.state
        last_transition = step_result.transition
        assert last_transition is not None
        hook_route_override_from = None
        hook_route_override_to = None
        if last_transition.hook_route_redirects:
            hook_route_override_from = last_transition.hook_route_redirects[0].from_route
            hook_route_override_to = last_transition.hook_route_redirects[-1].to_route
        self._notify_after_step(
            env.extensions,
            StepFinish(
                binding=env.binding,
                step_name=frame.step.name,
                step_kind=frame.step.kind,
                state_before=state_before,
                state_after=self._clone_state(state_after),
                event=self._clone_event(step_result.event),
                outcome=self._clone_outcome(step_result.outcome),
                producer_raw_output=step_result.producer_raw_output,
                verifier_raw_output=step_result.verifier_raw_output,
                provider_usage=step_result.provider_usage,
                candidate_route=last_transition.candidate_route,
                final_route=last_transition.final_route,
                runtime_control=last_transition.runtime_control,
                pending_input_id=last_transition.pending_input_id,
                target_step=last_transition.target_step,
                terminal=last_transition.terminal,
                provider_attributable=last_transition.provider_attributable,
                provider_attempted=last_transition.provider_attempted,
                producer_attempted=last_transition.producer_attempted,
                verifier_attempted=last_transition.verifier_attempted,
                source_hook=last_transition.source_hook,
                source_phase=last_transition.source_phase,
                hook_route_override_from=hook_route_override_from,
                hook_route_override_to=hook_route_override_to,
                hook_route_redirects=last_transition.hook_route_redirects,
                visit=frame.step_visit,
                step_execution_id=frame.step_execution_id,
                scope=frame.scope_name,
                item_id=frame.item_id,
            ),
        )

    def _handle_step_result(
        self,
        env: _RunEnvironment,
        loop: _RunLoopState,
        frame: _StepFrame,
        step_result: StepExecutionResult,
    ) -> RunResult | None:
        loop.state = step_result.state
        loop.pending_handoffs = step_result.pending_handoffs
        loop.last_event = step_result.event
        loop.last_outcome = step_result.outcome
        loop.last_transition = step_result.transition
        action = step_result.action
        loop.current_answer = None
        loop.current_input_response = None
        if isinstance(action, FinishAction):
            return self._finish_terminal(env, loop, frame)
        if isinstance(action, AwaitInputAction):
            return self._await_input_terminal(env, loop, frame, step_result=step_result)
        if isinstance(action, FailAction):
            return self._fail_terminal(env, loop, frame)
        if not isinstance(action, Continue):
            raise WorkflowExecutionError(
                f"step {frame.step.name!r} completed without a canonical route action"
            )
        destination = action.target_step
        if loop.last_transition is not None and loop.last_transition.runtime_control == "goto":
            loop.checkpoint = self._save_loop_checkpoint(
                loop,
                stage=destination,
                pending_input=None,
                pending_answer=None,
            )
        loop.current_step_name = destination
        return None

    def _finish_terminal(
        self,
        env: _RunEnvironment,
        loop: _RunLoopState,
        frame: _StepFrame,
    ) -> RunResult:
        assert loop.state is not None
        result = self._terminal_run_result(loop, frame.context, terminal=FINISH, checkpoint=None)
        try:
            self._notify_terminal(env.extensions, self._terminal_event(env, loop, terminal=FINISH, step_name=frame.step.name))
        except Exception:
            loop.checkpoint = self._save_loop_checkpoint(
                loop,
                stage=frame.step.name,
                pending_input=None,
                pending_answer=None,
            )
            loop.terminal_failure_handled = True
            raise
        self.checkpoint_store.clear()
        return result

    def _await_input_terminal(
        self,
        env: _RunEnvironment,
        loop: _RunLoopState,
        frame: _StepFrame,
        *,
        step_result: StepExecutionResult,
    ) -> RunResult:
        pending_input = step_result.pending_input or self._pending_input_from_event(
            source_step=frame.step.name,
            event=loop.last_event,
        )
        loop.checkpoint = self._save_loop_checkpoint(
            loop,
            stage=frame.step.name,
            pending_input=pending_input,
            pending_answer=None,
        )
        result = self._terminal_run_result(loop, frame.context, terminal=AWAIT_INPUT, checkpoint=loop.checkpoint)
        try:
            self._notify_terminal(
                env.extensions,
                self._terminal_event(env, loop, terminal=AWAIT_INPUT, step_name=frame.step.name),
            )
        except Exception:
            loop.terminal_failure_handled = True
            raise
        return result

    def _fail_terminal(
        self,
        env: _RunEnvironment,
        loop: _RunLoopState,
        frame: _StepFrame,
    ) -> RunResult:
        loop.checkpoint = self._save_loop_checkpoint(
            loop,
            stage=frame.step.name,
            pending_input=None,
            pending_answer=None,
        )
        result = self._terminal_run_result(loop, frame.context, terminal=FAIL, checkpoint=loop.checkpoint)
        try:
            self._notify_terminal(env.extensions, self._terminal_event(env, loop, terminal=FAIL, step_name=frame.step.name))
        except Exception:
            loop.terminal_failure_handled = True
            raise
        return result

    def _terminal_run_result(
        self,
        loop: _RunLoopState,
        context: Context,
        *,
        terminal: str,
        checkpoint: Checkpoint | None,
    ) -> RunResult:
        assert loop.state is not None
        output, output_validation_error = self._build_workflow_output(context, loop.state)
        return RunResult(
            terminal=terminal,
            state=loop.state,
            history=tuple(loop.history),
            checkpoint=checkpoint,
            last_event=loop.last_event,
            last_outcome=loop.last_outcome,
            last_transition=loop.last_transition,
            output=output,
            output_validation_error=output_validation_error,
        )

    def _terminal_event(
        self,
        env: _RunEnvironment,
        loop: _RunLoopState,
        *,
        terminal: str,
        step_name: str | None,
    ) -> TerminalFinish:
        return TerminalFinish(
            binding=env.binding,
            terminal=terminal,
            step_name=step_name,
            state=self._clone_state(loop.state),
            event=self._clone_event(loop.last_event),
            outcome=self._clone_outcome(loop.last_outcome),
        )

    def _save_loop_checkpoint(
        self,
        loop: _RunLoopState,
        *,
        stage: str,
        pending_input: PendingInput | None,
        pending_answer: str | None,
        state: BaseModel | None = None,
        pending_handoffs: tuple[PendingHandoff, ...] | None = None,
        failure_context: FailureContext | Mapping[str, Any] | None = None,
    ) -> Checkpoint:
        current_state = state if state is not None else loop.state
        assert current_state is not None
        return self._save_checkpoint(
            stage=stage,
            state=current_state,
            values=loop.values,
            step_states=loop.step_states,
            item_states=loop.item_states,
            step_item_states=loop.step_item_states,
            worklist_selections=loop.selections,
            worklist_selection_snapshots=loop.selection_snapshots,
            pending_handoffs=loop.pending_handoffs if pending_handoffs is None else pending_handoffs,
            pending_input=pending_input,
            pending_answer=pending_answer,
            failure_context=failure_context,
        )

    def _handle_run_failure(
        self,
        env: _RunEnvironment,
        loop: _RunLoopState | None,
        exc: Exception,
    ) -> None:
        if loop is not None and loop.terminal_failure_handled:
            return
        fatal_event = TerminalFinish(
            binding=env.binding,
            terminal="fatal",
            step_name=None if loop is None else (loop.history[-1] if loop.history else loop.current_step_name),
            state=None if loop is None else self._clone_state(loop.state),
            event=None if loop is None else self._clone_event(loop.last_event),
            outcome=None if loop is None else self._clone_outcome(loop.last_outcome),
        )
        fatal_error = self._notify_fatal(env.extensions, fatal_event, exc)
        self._notify_terminal(env.extensions, fatal_event)
        if fatal_error is not None:
            raise fatal_error from exc

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
            worklist_selections=_snapshot_worklist_selections(
                self.compiled.worklists,
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
            _validate_json_schema_mapping(schema, label="pending input schema")
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
    def _state_for_failure(current_state: BaseModel | None, exc: Exception) -> BaseModel | None:
        return exception_checkpoint_state(exc, current_state=current_state)

    def _failure_context_for_exception(self, exc: Exception) -> FailureContext | None:
        return exception_failure_context(exc)

    @staticmethod
    def _failure_context_payload(
        failure_context: FailureContext | Mapping[str, Any] | None,
    ) -> dict[str, Any] | None:
        if isinstance(failure_context, FailureContext):
            return failure_context.to_payload()
        if isinstance(failure_context, Mapping):
            return dict(failure_context) or None
        return None

    def _clone_event(self, event: Event | None) -> Event | None:
        if event is None:
            return None
        return Event(tag=event.tag, reason=event.reason, question=event.question, handoff=event.handoff)

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

    def _clone_state(self, state: BaseModel | None) -> BaseModel | None:
        if state is None:
            return None
        state_cls = type(state)
        return state_cls.model_validate(deepcopy(state.model_dump(mode="python", warnings=False)))

    def _validate_resume_checkpoint_target(self, checkpoint: Checkpoint) -> None:
        stage = checkpoint.stage
        if not isinstance(stage, str) or not stage:
            raise WorkflowExecutionError("resume checkpoint does not declare the step to continue")
        if stage not in self.compiled.steps:
            raise WorkflowExecutionError(
                f"resume checkpoint refers to step {stage!r}, but the current workflow does not declare that step"
            )

    def _current_item_state_key(self, context: Context, step: StepPlan) -> str | None:
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
    def _update_item_runtime_state_on_entry(
        step: StepPlan,
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

    def _ensure_step_state_store(
        self,
        step_states: dict[str, BaseModel | dict[str, Any]],
        step: StepPlan,
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
        step: StepPlan,
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
        step: StepPlan,
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
        step: StepPlan,
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
        context._sync_item_state(item_state_store)
        context._sync_step_item_state(step_item_state_store)
        self._update_item_runtime_state_on_entry(step, context, item_state_store)

    @staticmethod
    def _current_step_scope_item(context: Context, step: StepPlan) -> tuple[str | None, str | None]:
        if step.scope_name is None:
            return None, None
        item = context.current(step.scope_name)
        item_id = getattr(item, "id", None)
        if not isinstance(item_id, str) or not item_id:
            return step.scope_name, None
        return step.scope_name, item_id

    def _step_execution_visit(
        self,
        step: StepPlan,
        step_state: BaseModel | dict[str, Any] | None,
        step_item_state: BaseModel | dict[str, Any] | None,
    ) -> int | None:
        if step.scope_name is not None and step_item_state is not None:
            return self._step_runtime_visits(step_item_state)
        return self._step_runtime_visits(step_state)

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
