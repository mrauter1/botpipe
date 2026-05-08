"""Workflow compilation."""

from __future__ import annotations

import hashlib
import inspect
import json
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping

from pydantic import BaseModel

from autoloop.policy import Policy, PolicyInput

from .artifacts import CompiledArtifact
from .branch_groups.models import (
    BranchGroupDeclarationSpec,
    CompiledBranchGroupSpec,
    CompiledBranchStepSpec,
    FanInHelperReference,
)
from .context import Context
from .discovery import WorkflowDefinition, get_workflow_definition
from .extensions import WorkflowExtension
from .errors import RoutingError, WorkflowCompilationError, WorkflowValidationError
from .inventory import ArtifactInventoryRecord, collect_artifact_inventory, public_artifact_inventory, resolve_artifact_reference, resolve_optional_read_reference
from .lowering import (
    ResolvedRouteSpec,
    _fallback_route_summary,
    compile_expected_output_contract,
    normalize_step_route_metadata,
    resolve_step_routes,
    step_authored_route_tags,
)
from .primitives import AWAIT_INPUT, FAIL, FINISH, GLOBAL, SELF
from .prompts import PromptSpec
from .provider_policy import ProviderPolicy, ProviderPolicyOverride
from .providers.retries import ProviderRetryPolicy
from .route_reporting import payload_contract_for_route, route_fields_contract_for_route
from .route_required_writes import route_required_write_payload
from .routes import Route, _replace_route, normalize_route_spec
from .sessions import Continuity, DEFAULT_SESSION_NAME
from .step_state import build_step_item_state_model, build_step_state_model
from .steps import BranchGroupStep, PromptStep, ProduceVerifyStep, Session, Step, PythonStep, ChildWorkflowStep
from .validation import PayloadValidator
from .worklists import Worklist

SystemHandler = Callable[[Context], Any]

_COMPILED_WORKFLOW_CACHE: dict[tuple[str, str, str], "CompiledWorkflow"] = {}


@dataclass(frozen=True, slots=True)
class CompiledStep:
    """Normalized immutable step metadata."""

    name: str
    kind: str
    step: Step
    session_name: str | None
    scope_name: str | None
    reads: tuple[str, ...]
    requires: tuple[str, ...]
    writes: tuple[str, ...]
    log_artifacts: tuple[str, ...]
    available_routes: tuple[str, ...]
    authored_routes: tuple[str, ...]
    runtime_control_routes: tuple[str, ...]
    provider_visible_routes_interactive: tuple[str, ...]
    provider_visible_routes_full_auto: tuple[str, ...]
    expected_output_schema: dict[str, Any] | None
    retry_policy: ProviderRetryPolicy
    prompt: PromptSpec | None
    producer_prompt: PromptSpec | None
    verifier_prompt: PromptSpec | None
    producer_reads: tuple[str, ...]
    producer_requires: tuple[str, ...]
    producer_writes: tuple[str, ...]
    verifier_reads: tuple[str, ...]
    verifier_requires: tuple[str, ...]
    verifier_writes: tuple[str, ...]
    verifier_session_name: str | None
    expected_output_validator: PayloadValidator | None
    python_handler: SystemHandler | None
    before_hook: Callable[..., Any] | None
    after_hook: Callable[..., Any] | None
    before_producer_hook: Callable[..., Any] | None
    after_producer_hook: Callable[..., Any] | None
    before_verifier_hook: Callable[..., Any] | None
    after_verifier_hook: Callable[..., Any] | None
    step_state_model: type[BaseModel]
    step_state_fields: tuple[str, ...]
    step_item_state_model: type[BaseModel] | None
    step_item_state_fields: tuple[str, ...]
    provider_policy: PolicyInput = None
    branch_group: Any | None = None
    route_table: dict[str, "CompiledRoute"] | None = None


@dataclass(frozen=True, slots=True)
class CompiledRoute:
    """Normalized immutable route metadata."""

    source_step: str
    tag: str
    target: str | None
    summary: str | None = None
    required_writes: tuple[str, ...] = ()
    handoff: str | None = None
    on_taken: object | None = None
    provider_visibility: str = "always"
    provider_visible: bool = True
    provider_visible_interactive: bool = True
    provider_visible_full_auto: bool = True
    payload_schema_mode: str = "inherit"
    payload_schema: dict[str, Any] | None = None
    payload_validator: PayloadValidator | None = None
    route_fields_schema: dict[str, Any] | None = None
    route_fields_validator: PayloadValidator | None = None
    preset_kind: str = "custom"
    inheritance_source: str = "step_local"
    disabled: bool = False
    is_runtime_control: bool = False
    _required_writes_explicit: bool = False


@dataclass(frozen=True, slots=True)
class CompiledWorkflow:
    """Immutable compiled workflow."""

    workflow_cls: type[Any]
    workflow_name: str
    state_cls: type[BaseModel]
    input_model: type[BaseModel] | None
    output_model: type[BaseModel] | None
    output_builder: Callable[[BaseModel, Context], Any] | None
    parameters_cls: type[BaseModel] | None
    entry_step_name: str
    sessions: dict[str, Session]
    default_session_name: str
    default_session_open: bool
    worklists: dict[str, Worklist[Any]]
    steps: dict[str, CompiledStep]
    routes: dict[str, dict[str, CompiledRoute]]
    global_routes: dict[str, CompiledRoute]
    artifacts: dict[str, CompiledArtifact]
    artifacts_by_qualified_name: dict[str, CompiledArtifact]
    extensions: tuple[WorkflowExtension, ...]
    provider_policy: PolicyInput
    source_hash: str | None
    topology_hash: str

    def artifact_items(self, *, authoritative: bool = False) -> tuple[tuple[str, CompiledArtifact], ...]:
        """Return compiled artifact entries.

        ``authoritative=False`` returns the public short-name artifact view.
        ``authoritative=True`` returns the full canonical qualified inventory.
        """

        source = self.artifacts_by_qualified_name if authoritative else self.artifacts
        return tuple(source.items())

    def route(self, step_name: str, tag: str) -> CompiledRoute:
        compiled_route = self.routes.get(step_name, {}).get(tag)
        if compiled_route is not None:
            if compiled_route.disabled:
                raise RoutingError(f"no route for step {step_name!r} and tag {tag!r}")
            return compiled_route
        compiled_route = self.global_routes.get(tag)
        if compiled_route is None or compiled_route.disabled:
            raise RoutingError(f"no route for step {step_name!r} and tag {tag!r}")
        return compiled_route

    def new_state(self) -> BaseModel:
        try:
            return self.state_cls()
        except Exception as exc:
            raise WorkflowCompilationError(
                f"state model {self.state_cls.__qualname__} requires an explicit initial state"
            ) from exc


def compile_workflow(workflow_cls: type[Any]) -> CompiledWorkflow:
    """Compile a validated workflow class."""

    definition = get_workflow_definition(workflow_cls)
    source_hash = _workflow_source_hash(workflow_cls)
    cache_key: tuple[str, str, str] | None = None
    if not _definition_contains_branch_groups(definition):
        cache_key = _workflow_compile_cache_key(
            workflow_cls,
            definition=definition,
            source_hash=source_hash,
        )
        cached = _COMPILED_WORKFLOW_CACHE.get(cache_key)
        if cached is not None:
            return cached
    inventory = collect_artifact_inventory(definition)
    compiled_routes = _compile_routes(definition)
    compiled_global_routes = _compile_global_routes(definition)
    compiled = CompiledWorkflow(
        workflow_cls=workflow_cls,
        workflow_name=definition.workflow_name,
        state_cls=definition.state_cls,
        input_model=_compile_optional_model(workflow_cls, "Input"),
        output_model=_compile_optional_model(workflow_cls, "Output"),
        output_builder=_compile_output_builder(workflow_cls),
        parameters_cls=definition.parameters_cls,
        entry_step_name=definition.entry.name,
        sessions=_compile_sessions(definition),
        default_session_name=definition.default_session_name,
        default_session_open=definition.sessions_by_name.get(definition.default_session_name).open
        if definition.default_session_name in definition.sessions_by_name
        else False,
        worklists=dict(definition.worklists_by_name),
        steps=_compile_steps(definition, inventory, compiled_routes),
        routes=compiled_routes,
        global_routes=compiled_global_routes,
        artifacts=_compile_public_artifacts(inventory),
        artifacts_by_qualified_name=_compile_artifacts_by_qualified_name(inventory),
        extensions=definition.extensions,
        provider_policy=_validated_compiled_policy(definition.workflow_policy, owner="workflow"),
        source_hash=source_hash,
        topology_hash="",
    )
    compiled = _with_topology_hash(compiled)
    if cache_key is not None:
        _COMPILED_WORKFLOW_CACHE[cache_key] = compiled
    return compiled


def _compile_steps(
    definition: WorkflowDefinition,
    inventory: dict[str, ArtifactInventoryRecord],
    compiled_routes: dict[str, dict[str, CompiledRoute]],
) -> dict[str, CompiledStep]:
    compiled_steps: dict[str, CompiledStep] = {}
    for step in definition.steps:
        route_table = compiled_routes.get(step.name, {})
        available_routes = _compiled_available_route_tags(step, route_table)
        authored_routes = step_authored_route_tags(definition, step)
        runtime_control_routes = _compiled_runtime_control_route_tags(
            available_routes,
            route_table=route_table,
        )
        provider_visible_routes_interactive = _provider_visible_route_tags(
            available_routes,
            route_table=route_table,
            policy="interactive",
        )
        provider_visible_routes_full_auto = _provider_visible_route_tags(
            available_routes,
            route_table=route_table,
            policy="full_auto",
        )
        expected_output_schema, expected_output_validator = _compile_expected_output_contract(step)
        reads = tuple(
            _compile_read_reference(artifact_reference, inventory, step=step)
            for artifact_reference in step.reads
        )
        requires = tuple(
            _compile_required_reference(artifact_reference, inventory, step=step)
            for artifact_reference in step.requires
        )
        verifier_requires = tuple(
            _compile_required_reference(
                artifact_reference,
                inventory,
                step=step,
            )
            for artifact_reference in getattr(step, "verifier_requires", ())
        )
        writes = tuple(
            resolve_artifact_reference(artifact, inventory).qualified_name
            for artifact in step.writes.values()
        )
        producer_writes = tuple(
            resolve_artifact_reference(step.writes[name], inventory).qualified_name
            for name in getattr(step, "producer_writes", tuple(step.writes.keys()))
        )
        verifier_writes = tuple(
            resolve_artifact_reference(step.writes[name], inventory).qualified_name
            for name in getattr(step, "verifier_writes", ())
        )
        step_log_artifacts = tuple(
            resolve_artifact_reference(artifact, inventory).qualified_name
            for artifact in step.log_artifacts
        )
        workflow_log_artifact_names = tuple(
            resolve_artifact_reference(artifact, inventory).qualified_name
            for artifact in definition.workflow_log_artifacts
        )
        log_names = tuple(dict.fromkeys((*workflow_log_artifact_names, *step_log_artifacts)))
        step_kind = step.kind
        before_hook = getattr(step, "before", None)
        after_hook = getattr(step, "after", None)
        before_producer_hook = getattr(step, "before_producer", None)
        after_producer_hook = getattr(step, "after_producer", None)
        before_verifier_hook = getattr(step, "before_verifier", None)
        after_verifier_hook = getattr(step, "after_verifier", None)
        step_kind = _compiled_step_kind(step)
        step_state_model = getattr(step, "state_model", None)
        if step_state_model is None:
            step_state_model = build_step_state_model(
                None,
                step_name=step.name,
                step_kind=step_kind,
                module_name=definition.workflow_cls.__module__,
            )
        step_state_fields = tuple(dict.fromkeys(step_state_model.model_fields.keys()))
        step_item_state_model = None
        step_item_state_fields: tuple[str, ...] = ()
        if step.scope is not None:
            step_item_state_model = getattr(step, "step_item_state_model", None)
            if step_item_state_model is None:
                step_item_state_model = build_step_item_state_model(
                    getattr(step, "item_state", None),
                    step_name=step.name,
                    step_kind=step_kind,
                    module_name=definition.workflow_cls.__module__,
                )
            step_item_state_fields = tuple(dict.fromkeys(step_item_state_model.model_fields.keys()))
        compiled_session_name = (
            _compiled_step_session_name(step, step.session, default_session_name=definition.default_session_name)
            if step.session is not None
            else definition.default_session_name
        )
        if isinstance(step, BranchGroupStep):
            compiled_session_name = None
        producer_reads = tuple(getattr(step, "producer_reads", reads))
        producer_requires = tuple(getattr(step, "producer_requires", requires))
        verifier_requires = tuple(getattr(step, "verifier_requires", verifier_requires))
        verifier_reads = tuple(
            getattr(step, "verifier_reads", tuple(dict.fromkeys((*reads, *producer_writes, *verifier_requires))))
        )
        if isinstance(step, ProduceVerifyStep):
            compiled_steps[step.name] = CompiledStep(
                name=step.name,
                kind=step_kind,
                step=step,
                session_name=compiled_session_name,
                scope_name=_compile_scope_name(step.scope),
                reads=reads,
                requires=requires,
                writes=writes,
                log_artifacts=log_names,
                available_routes=available_routes,
                authored_routes=authored_routes,
                runtime_control_routes=runtime_control_routes,
                provider_visible_routes_interactive=provider_visible_routes_interactive,
                provider_visible_routes_full_auto=provider_visible_routes_full_auto,
                expected_output_schema=expected_output_schema,
                retry_policy=step.retry_policy,
                prompt=None,
                producer_prompt=step.producer,
                verifier_prompt=step.verifier,
                producer_reads=producer_reads,
                producer_requires=producer_requires,
                producer_writes=producer_writes,
                verifier_reads=verifier_reads,
                verifier_requires=verifier_requires,
                verifier_writes=verifier_writes or writes,
                verifier_session_name=(
                    _compiled_step_session_name(
                        step,
                        step.verifier_session,
                        default_session_name=definition.default_session_name,
                        role="verifier_session",
                    )
                    if getattr(step, "verifier_session", None) is not None
                    else None
                ),
                expected_output_validator=expected_output_validator,
                python_handler=None,
                before_hook=before_hook,
                after_hook=after_hook,
                before_producer_hook=before_producer_hook,
                after_producer_hook=after_producer_hook,
                before_verifier_hook=before_verifier_hook,
                after_verifier_hook=after_verifier_hook,
                step_state_model=step_state_model,
                step_state_fields=step_state_fields,
                step_item_state_model=step_item_state_model,
                step_item_state_fields=step_item_state_fields,
                provider_policy=_validated_compiled_policy(step.provider_policy, owner=f"step {step.name!r}"),
                route_table=dict(route_table),
            )
        elif isinstance(step, PromptStep):
            compiled_steps[step.name] = CompiledStep(
                name=step.name,
                kind=step_kind,
                step=step,
                session_name=compiled_session_name,
                scope_name=_compile_scope_name(step.scope),
                reads=reads,
                requires=requires,
                writes=writes,
                log_artifacts=log_names,
                available_routes=available_routes,
                authored_routes=authored_routes,
                runtime_control_routes=runtime_control_routes,
                provider_visible_routes_interactive=provider_visible_routes_interactive,
                provider_visible_routes_full_auto=provider_visible_routes_full_auto,
                expected_output_schema=expected_output_schema,
                retry_policy=step.retry_policy,
                prompt=step.producer,
                producer_prompt=step.producer,
                verifier_prompt=None,
                producer_reads=producer_reads,
                producer_requires=producer_requires,
                producer_writes=writes,
                verifier_reads=(),
                verifier_requires=(),
                verifier_writes=(),
                verifier_session_name=None,
                expected_output_validator=expected_output_validator,
                python_handler=None,
                before_hook=before_hook,
                after_hook=after_hook,
                before_producer_hook=None,
                after_producer_hook=None,
                before_verifier_hook=None,
                after_verifier_hook=None,
                step_state_model=step_state_model,
                step_state_fields=step_state_fields,
                step_item_state_model=step_item_state_model,
                step_item_state_fields=step_item_state_fields,
                provider_policy=_validated_compiled_policy(step.provider_policy, owner=f"step {step.name!r}"),
                route_table=dict(route_table),
            )
        elif isinstance(step, PythonStep):
            compiled_steps[step.name] = CompiledStep(
                name=step.name,
                kind=step_kind,
                step=step,
                session_name=(
                    _compiled_step_session_name(step, step.session, default_session_name=definition.default_session_name)
                    if step.session is not None
                    else None
                ),
                scope_name=None,
                reads=reads,
                requires=requires,
                writes=writes,
                log_artifacts=log_names,
                available_routes=available_routes,
                authored_routes=authored_routes,
                runtime_control_routes=runtime_control_routes,
                provider_visible_routes_interactive=provider_visible_routes_interactive,
                provider_visible_routes_full_auto=provider_visible_routes_full_auto,
                expected_output_schema=None,
                retry_policy=ProviderRetryPolicy(max_attempts=1),
                prompt=None,
                producer_prompt=None,
                verifier_prompt=None,
                producer_reads=producer_reads,
                producer_requires=producer_requires,
                producer_writes=writes,
                verifier_reads=(),
                verifier_requires=(),
                verifier_writes=(),
                verifier_session_name=None,
                expected_output_validator=None,
                python_handler=_compile_system_handler(step),
                before_hook=before_hook,
                after_hook=after_hook,
                before_producer_hook=None,
                after_producer_hook=None,
                before_verifier_hook=None,
                after_verifier_hook=None,
                step_state_model=step_state_model,
                step_state_fields=step_state_fields,
                step_item_state_model=step_item_state_model,
                step_item_state_fields=step_item_state_fields,
                provider_policy=_validated_compiled_policy(step.provider_policy, owner=f"step {step.name!r}"),
                route_table=dict(route_table),
            )
        elif isinstance(step, ChildWorkflowStep):
            compiled_steps[step.name] = CompiledStep(
                name=step.name,
                kind=step_kind,
                step=step,
                session_name=(
                    _compiled_step_session_name(step, step.session, default_session_name=definition.default_session_name)
                    if step.session is not None
                    else None
                ),
                scope_name=_compile_scope_name(step.scope),
                reads=reads,
                requires=requires,
                writes=writes,
                log_artifacts=log_names,
                available_routes=available_routes,
                authored_routes=authored_routes,
                runtime_control_routes=runtime_control_routes,
                provider_visible_routes_interactive=provider_visible_routes_interactive,
                provider_visible_routes_full_auto=provider_visible_routes_full_auto,
                expected_output_schema=None,
                retry_policy=ProviderRetryPolicy(max_attempts=1),
                prompt=None,
                producer_prompt=None,
                verifier_prompt=None,
                producer_reads=producer_reads,
                producer_requires=producer_requires,
                producer_writes=writes,
                verifier_reads=(),
                verifier_requires=(),
                verifier_writes=(),
                verifier_session_name=None,
                expected_output_validator=None,
                python_handler=None,
                before_hook=before_hook,
                after_hook=after_hook,
                before_producer_hook=None,
                after_producer_hook=None,
                before_verifier_hook=None,
                after_verifier_hook=None,
                step_state_model=step_state_model,
                step_state_fields=step_state_fields,
                step_item_state_model=step_item_state_model,
                step_item_state_fields=step_item_state_fields,
                provider_policy=_validated_compiled_policy(step.provider_policy, owner=f"step {step.name!r}"),
                route_table=dict(route_table),
            )
        elif isinstance(step, BranchGroupStep):
            compiled_branch_group = _compile_branch_group_internal_steps(
                definition,
                step.branch_group,
                inventory=inventory,
            )
            compiled_steps[step.name] = CompiledStep(
                name=step.name,
                kind="branch_group",
                step=step,
                session_name=None,
                scope_name=None,
                reads=(),
                requires=(),
                writes=(),
                log_artifacts=(),
                available_routes=available_routes,
                authored_routes=authored_routes,
                runtime_control_routes=runtime_control_routes,
                provider_visible_routes_interactive=provider_visible_routes_interactive,
                provider_visible_routes_full_auto=provider_visible_routes_full_auto,
                expected_output_schema=None,
                retry_policy=ProviderRetryPolicy(),
                prompt=None,
                producer_prompt=None,
                verifier_prompt=None,
                producer_reads=(),
                producer_requires=(),
                producer_writes=(),
                verifier_reads=(),
                verifier_requires=(),
                verifier_writes=(),
                verifier_session_name=None,
                expected_output_validator=None,
                python_handler=None,
                before_hook=None,
                after_hook=None,
                before_producer_hook=None,
                after_producer_hook=None,
                before_verifier_hook=None,
                after_verifier_hook=None,
                step_state_model=step_state_model,
                step_state_fields=step_state_fields,
                step_item_state_model=None,
                step_item_state_fields=(),
                provider_policy=_validated_compiled_policy(step.provider_policy, owner=f"step {step.name!r}"),
                branch_group=compiled_branch_group,
                route_table=dict(route_table),
            )
        else:
            raise WorkflowCompilationError(f"unsupported step type {type(step)!r}")
    return compiled_steps


def _provider_visible_route_tags(
    available_routes: tuple[str, ...],
    *,
    route_table: Mapping[str, CompiledRoute],
    policy: str,
) -> tuple[str, ...]:
    visible: list[str] = []
    for route_tag in available_routes:
        route = route_table.get(route_tag)
        if route is None:
            continue
        if _compiled_route_visible_for_policy(route, policy=policy):
            visible.append(route_tag)
    return tuple(visible)


def _compiled_available_route_tags(
    step: Step,
    route_table: Mapping[str, CompiledRoute],
) -> tuple[str, ...]:
    resolved = tuple(tag for tag, route in route_table.items() if not route.disabled)
    composite_tags = getattr(step, "composite_route_tags", None)
    if composite_tags:
        composite_order = [tag for tag in composite_tags if tag in resolved]
        extras = [tag for tag in resolved if tag not in composite_tags]
        return tuple((*composite_order, *extras))
    return resolved


def _compiled_runtime_control_route_tags(
    available_routes: tuple[str, ...],
    *,
    route_table: Mapping[str, CompiledRoute],
) -> tuple[str, ...]:
    return tuple(
        route_tag
        for route_tag in available_routes
        if route_table.get(route_tag) is not None and route_table[route_tag].is_runtime_control
    )


def _compiled_route_visible_for_policy(route: CompiledRoute, *, policy: str) -> bool:
    if policy == "interactive":
        return route.provider_visible_interactive
    if policy == "full_auto":
        return route.provider_visible_full_auto
    raise WorkflowCompilationError(f"unsupported provider-visibility policy {policy!r}")


def _compile_branch_group_internal_steps(
    definition: WorkflowDefinition,
    branch_group: BranchGroupDeclarationSpec,
    *,
    inventory: dict[str, ArtifactInventoryRecord],
) -> CompiledBranchGroupSpec:
    compiled_branches = tuple(
        CompiledBranchStepSpec(
            name=branch.name,
            index=branch.index,
            input=branch.input,
            step=_compile_branch_group_internal_step(
                definition,
                branch.step,
                inventory=inventory,
            ),
        )
        for branch in branch_group.branches
    )
    compiled_fan_in_step = (
        None
        if branch_group.fan_in_step is None
        else _compile_branch_group_internal_step(
            definition,
            branch_group.fan_in_step,
            inventory=inventory,
        )
    )
    return CompiledBranchGroupSpec(
        name=branch_group.name,
        kind=branch_group.kind,
        branches=compiled_branches,
        concurrency=branch_group.concurrency,
        settle=branch_group.settle,
        success_routes=branch_group.success_routes,
        outcome=branch_group.outcome,
        fan_in_step=compiled_fan_in_step,
        composite_route_tags=branch_group.composite_route_tags,
        default_chain_route=branch_group.default_chain_route,
        rework_chain_route=branch_group.rework_chain_route,
    )


def _compile_branch_group_internal_step(
    definition: WorkflowDefinition,
    step: Step,
    *,
    inventory: dict[str, ArtifactInventoryRecord],
) -> CompiledStep:
    internal_definition = WorkflowDefinition(
        workflow_cls=definition.workflow_cls,
        workflow_name=definition.workflow_name,
        workflow_policy=definition.workflow_policy,
        state_cls=definition.state_cls,
        parameters_cls=definition.parameters_cls,
        entry=step,
        steps=(step,),
        steps_by_name={step.name: step},
        sessions_by_name=dict(definition.sessions_by_name),
        default_session_name=definition.default_session_name,
        worklists_by_name=dict(definition.worklists_by_name),
        workflow_artifacts=dict(definition.workflow_artifacts),
        workflow_log_artifacts=tuple(definition.workflow_log_artifacts),
        extensions=(),
        authored_transitions={step: _internal_step_authored_routes(definition, step)},
        transitions={step: _internal_step_authored_routes(definition, step)},
        framework_default_transitions_by_step={step.name: _internal_step_framework_default_routes(step)},
        runtime_control_routes_by_step={step.name: _internal_step_runtime_control_routes(step)},
    )
    compiled_routes = _compile_routes(internal_definition)
    compiled_step = _compile_steps(
        internal_definition,
        inventory,
        compiled_routes,
    )[step.name]
    return replace(compiled_step, route_table=dict(compiled_routes.get(step.name, {})))


def _internal_step_authored_routes(
    definition: WorkflowDefinition,
    step: Step,
) -> dict[str, object]:
    authored = _lower_internal_step_route_map(definition, step)
    if authored:
        return authored
    if isinstance(step, ProduceVerifyStep):
        return {"accepted": FINISH, "needs_rework": step.name}
    if isinstance(step, ChildWorkflowStep):
        return {"done": FINISH}
    return {"done": FINISH}


def _internal_step_framework_default_routes(step: Step) -> dict[str, object]:
    question_mode = getattr(getattr(step, "control_routes", None), "question", "never")
    if question_mode == "never":
        return {}
    provider_visibility = "always" if question_mode == "always" else "interactive_only"
    return {"question": Route.question(provider_visibility=provider_visibility)}


def _internal_step_runtime_control_routes(step: Step) -> tuple[str, ...]:
    runtime_routes: list[str] = []
    question_mode = getattr(getattr(step, "control_routes", None), "question", "never")
    if question_mode != "never":
        runtime_routes.append("question")
    return tuple(runtime_routes)


def _lower_internal_step_route_map(
    definition: WorkflowDefinition,
    step: Step,
) -> dict[str, object]:
    declaration = getattr(step, "simple_declaration", None)
    raw_routes = getattr(declaration, "routes", None)
    implicit_routes = getattr(declaration, "implicit_routes", None)
    merged: dict[str, object] = {}
    if isinstance(raw_routes, Mapping):
        merged.update(raw_routes)
    if isinstance(implicit_routes, Mapping):
        merged.update(implicit_routes)
    if not merged:
        return {}
    destination_names = _internal_branch_destination_names(definition, step)
    return {
        route_name: _lower_internal_route_destination(
            destination,
            destination_names=destination_names,
            current_step_name=step.name,
        )
        for route_name, destination in merged.items()
    }


def _internal_branch_destination_names(
    definition: WorkflowDefinition,
    step: Step,
) -> dict[int, str]:
    names: dict[int, str] = {id(step): step.name}
    declaration = getattr(step, "simple_declaration", None)
    if declaration is not None:
        names[id(declaration)] = step.name
    for candidate in definition.steps:
        names[id(candidate)] = candidate.name
        candidate_declaration = getattr(candidate, "simple_declaration", None)
        if candidate_declaration is not None:
            names[id(candidate_declaration)] = candidate.name
    return names


def _lower_internal_route_destination(
    destination: object,
    *,
    destination_names: Mapping[int, str],
    current_step_name: str,
) -> object:
    if isinstance(destination, Route):
        if destination.is_disabled:
            return destination
        lowered_target = _lower_internal_route_target(
            destination.target,
            destination_names=destination_names,
            current_step_name=current_step_name,
        )
        return _replace_route(destination, target=lowered_target)
    return _lower_internal_route_target(
        destination,
        destination_names=destination_names,
        current_step_name=current_step_name,
    )


def _lower_internal_route_target(
    target: object,
    *,
    destination_names: Mapping[int, str],
    current_step_name: str,
) -> object:
    if isinstance(target, Step):
        return target.name
    if target is SELF:
        return current_step_name
    mapped = destination_names.get(id(target))
    if mapped is not None:
        return mapped
    return target


def _compile_optional_model(workflow_cls: type[Any], attribute: str) -> type[BaseModel] | None:
    raw = getattr(workflow_cls, attribute, None)
    if raw is None:
        return None
    if not isinstance(raw, type) or not issubclass(raw, BaseModel):
        raise WorkflowCompilationError(
            f"{workflow_cls.__name__}.{attribute} must inherit from pydantic.BaseModel"
        )
    if attribute == "Input" and "message" in getattr(raw, "model_fields", {}):
        raise WorkflowCompilationError(
            f"{workflow_cls.__name__}.Input must not declare field 'message'; "
            "message is provided by client.run(..., message)."
        )
    return raw


def _compile_output_builder(workflow_cls: type[Any]) -> Callable[[BaseModel, Context], Any] | None:
    raw_builder = getattr(workflow_cls, "build_output", None)
    if raw_builder is None:
        return None
    if _callable_arity(raw_builder) != 2:
        raise WorkflowCompilationError("build_output must accept exactly 2 positional arguments")
    return raw_builder


def _compile_sessions(definition: WorkflowDefinition) -> dict[str, Session]:
    compiled: dict[str, Session] = {}
    for name, session in definition.sessions_by_name.items():
        compiled[name] = _compiled_session_copy(name, session)
    for step in definition.steps:
        _register_inline_step_sessions(compiled, step)
    if definition.default_session_name not in compiled:
        compiled[definition.default_session_name] = _compiled_session_copy(
            definition.default_session_name,
            definition.sessions_by_name.get(definition.default_session_name),
        )
    if DEFAULT_SESSION_NAME not in compiled:
        compiled[DEFAULT_SESSION_NAME] = _compiled_session_copy(DEFAULT_SESSION_NAME, None)
    return compiled


def _compiled_session_copy(name: str, session: Session | None) -> Session:
    continuity = session.continuity if isinstance(session, Session) else Continuity.run()
    compiled = Session(continuity=continuity, open=session.open if isinstance(session, Session) else False)
    compiled.bind_name(name)
    return compiled


def _register_inline_step_sessions(compiled: dict[str, Session], step: Step) -> None:
    if isinstance(step, BranchGroupStep):
        branch_group = getattr(step, "branch_group", None)
        if branch_group is not None:
            for branch in getattr(branch_group, "branches", ()):
                _register_inline_step_sessions(compiled, branch.step)
            fan_in_step = getattr(branch_group, "fan_in_step", None)
            if isinstance(fan_in_step, Step):
                _register_inline_step_sessions(compiled, fan_in_step)
        return
    if step.session is not None:
        compiled.setdefault(
            _compiled_step_session_name(step, step.session, default_session_name=DEFAULT_SESSION_NAME),
            _compiled_session_copy(
                _compiled_step_session_name(step, step.session, default_session_name=DEFAULT_SESSION_NAME),
                step.session,
            ),
        )
    verifier_session = getattr(step, "verifier_session", None)
    if verifier_session is not None:
        compiled.setdefault(
            _compiled_step_session_name(step, verifier_session, default_session_name=DEFAULT_SESSION_NAME, role="verifier_session"),
            _compiled_session_copy(
                _compiled_step_session_name(step, verifier_session, default_session_name=DEFAULT_SESSION_NAME, role="verifier_session"),
                verifier_session,
            ),
        )


def _compiled_step_session_name(
    step: Step,
    session: Session,
    *,
    default_session_name: str,
    role: str = "session",
) -> str:
    if session.name is not None:
        return session.name
    if role == "session" and isinstance(step, PromptStep):
        return f"{step.name}__session"
    if role == "session" and isinstance(step, ProduceVerifyStep):
        return f"{step.name}__producer_session"
    if role == "verifier_session":
        return f"{step.name}__verifier_session"
    return f"{step.name}__{role}"


def _compile_system_handler(step: PythonStep) -> SystemHandler:
    raw_handler = step.handler
    step_name = step.name
    if raw_handler is None:
        raise WorkflowCompilationError(f"python_step {step_name!r} is missing a handler")

    arity = _callable_arity(raw_handler)
    if arity not in {1, 2}:
        raise WorkflowCompilationError(
            f"handler for python_step {step_name!r} must accept exactly 1 or 2 positional arguments"
        )

    def handler(ctx: Context) -> Any:
        if arity == 1:
            return raw_handler(ctx)
        return raw_handler(ctx.state, ctx)

    return handler


def _compile_routes(definition: WorkflowDefinition) -> dict[str, dict[str, CompiledRoute]]:
    inventory = collect_artifact_inventory(definition)
    route_metadata = {
        step.name: normalize_step_route_metadata(definition, step, inventory)
        for step in definition.steps
    }
    routes: dict[str, dict[str, CompiledRoute]] = {}
    for step in definition.steps:
        compiled_step_routes: dict[str, CompiledRoute] = {}
        for resolved in resolve_step_routes(definition, step):
            normalized_route = route_metadata[step.name].get(resolved.tag, resolved.route)
            compiled_step_routes[resolved.tag] = _compile_route(
                step,
                GLOBAL if resolved.inheritance_source == "global" else step.name,
                resolved.tag,
                normalized_route,
                inheritance_source=resolved.inheritance_source,
                is_runtime_control=resolved.legacy_runtime_control,
            )
        routes[step.name] = compiled_step_routes
    return routes


def _compile_global_routes(definition: WorkflowDefinition) -> dict[str, CompiledRoute]:
    source_routes = definition.transitions.get(GLOBAL, {})
    return {
        tag: _compile_route(
            None,
            GLOBAL,
            tag,
            destination,
            summary=_fallback_route_summary(GLOBAL, tag, normalize_route_spec(destination).target),
            inheritance_source="global",
        )
        for tag, destination in source_routes.items()
    }


def _compile_route(
    step: Step | None,
    source_step: str,
    tag: str,
    destination: Step | str | Route,
    *,
    summary: str | None = None,
    inheritance_source: str,
    is_runtime_control: bool = False,
) -> CompiledRoute:
    route = normalize_route_spec(destination)
    compiled_target: str | None
    if route.is_disabled:
        compiled_target = None
    else:
        target = route.target
        if isinstance(target, Step):
            compiled_target = target.name
        elif isinstance(target, str):
            compiled_target = target
        else:  # pragma: no cover - validation guards this before compilation
            raise WorkflowCompilationError(f"route {tag!r} from {source_step!r} is missing a target")
    required_writes_explicit = route.required_writes is not None
    compiled_required_writes = tuple(route.required_writes or ())
    payload_schema, payload_validator = _compile_route_contract(
        route.payload_schema if route.payload_schema_mode == "explicit" else None,
        owner=f"route {tag!r} from {source_step!r} payload_schema",
    )
    route_fields_schema, route_fields_validator = _compile_route_contract(
        route.route_fields_schema,
        owner=f"route {tag!r} from {source_step!r} route_fields_schema",
        allow_missing_jsonschema_fallback=route._handwritten_route_fields_validation_equivalent,
    )
    provider_visibility = _effective_provider_visibility(
        step,
        route=route,
        tag=tag,
        is_runtime_control=is_runtime_control,
    )
    provider_visible_interactive, provider_visible_full_auto = _compiled_provider_visibility(
        step,
        provider_visibility=provider_visibility,
    )
    preset_kind = _effective_preset_kind(route, tag=tag)
    return CompiledRoute(
        source_step=source_step,
        tag=tag,
        target=compiled_target,
        summary=route.summary or summary,
        required_writes=compiled_required_writes,
        handoff=route.handoff,
        on_taken=route.on_taken,
        provider_visibility=provider_visibility,
        provider_visible=provider_visibility != "hidden",
        provider_visible_interactive=provider_visible_interactive,
        provider_visible_full_auto=provider_visible_full_auto,
        payload_schema_mode=route.payload_schema_mode,
        payload_schema=payload_schema,
        payload_validator=payload_validator,
        route_fields_schema=route_fields_schema,
        route_fields_validator=route_fields_validator,
        preset_kind=preset_kind,
        inheritance_source=inheritance_source,
        disabled=route.is_disabled,
        is_runtime_control=is_runtime_control,
        _required_writes_explicit=required_writes_explicit,
    )


def _compiled_provider_visibility(
    step: Step | None,
    *,
    provider_visibility: str,
) -> tuple[bool, bool]:
    if provider_visibility == "hidden":
        return False, False
    if not isinstance(step, (PromptStep, ProduceVerifyStep)):
        return (True, False) if step is None and provider_visibility == "interactive_only" else (
            False,
            False,
        )
    if provider_visibility == "always":
        return True, True
    return True, False


def _effective_provider_visibility(
    step: Step | None,
    *,
    route: Route,
    tag: str,
    is_runtime_control: bool,
) -> str:
    provider_visibility = route.provider_visibility or ("hidden" if not route.provider_visible else "always")
    if provider_visibility == "hidden":
        return "hidden"
    if route.preset_kind == "question":
        return provider_visibility
    if tag == "question":
        if step is None:
            return "interactive_only"
        question_mode = getattr(getattr(step, "control_routes", None), "question", "never")
        if question_mode == "always":
            return "always"
        if is_runtime_control:
            return "interactive_only"
        return "interactive_only"
    return provider_visibility


def _effective_preset_kind(route: Route, *, tag: str) -> str:
    if route.preset_kind != "custom":
        return route.preset_kind
    if tag == "question":
        return "question"
    return route.preset_kind


def _compile_route_contract(
    spec: Any | None,
    *,
    owner: str,
    allow_missing_jsonschema_fallback: bool = False,
) -> tuple[dict[str, Any] | None, PayloadValidator | None]:
    if spec is None:
        return None, None
    if isinstance(spec, Mapping):
        schema = deepcopy(dict(spec))
        try:
            return compile_expected_output_contract(schema)
        except WorkflowValidationError as exc:
            if allow_missing_jsonschema_fallback and "optional jsonschema dependency" in str(exc):
                return schema, None
            raise WorkflowCompilationError(f"{owner} is invalid: {exc}") from exc
    try:
        return compile_expected_output_contract(spec)
    except WorkflowValidationError as exc:
        raise WorkflowCompilationError(f"{owner} is invalid: {exc}") from exc


def _compiled_step_kind(step: Step) -> str:
    if isinstance(step, ProduceVerifyStep):
        return "produce_verify"
    if isinstance(step, PromptStep):
        return "step"
    if isinstance(step, BranchGroupStep):
        return "branch_group"
    if isinstance(step, ChildWorkflowStep):
        return "workflow"
    if isinstance(step, PythonStep):
        declaration = getattr(step, "simple_declaration", None)
        if getattr(declaration, "kind", None) == "operation":
            return "operation"
        return "python"
    return step.kind


def _compile_artifact(record: ArtifactInventoryRecord, *, name: str) -> CompiledArtifact:
    return CompiledArtifact(
        name=name,
        template=record.artifact.template,
        kind=record.artifact.kind,
        schema=record.artifact.schema,
        required=record.artifact.required,
        owner_step=record.artifact.owner_step,
        qualified_name=record.artifact.qualified_name,
        workflow_level=record.workflow_level,
        producer_steps=record.producer_steps,
    )


def _compile_public_artifacts(inventory: dict[str, ArtifactInventoryRecord]) -> dict[str, CompiledArtifact]:
    return {
        name: _compile_artifact(record, name=name)
        for name, record in public_artifact_inventory(inventory).items()
    }


def _compile_artifacts_by_qualified_name(
    inventory: dict[str, ArtifactInventoryRecord],
) -> dict[str, CompiledArtifact]:
    return {
        name: _compile_artifact(record, name=name)
        for name, record in inventory.items()
    }


def _compile_expected_output_contract(step: Step) -> tuple[dict[str, Any] | None, PayloadValidator | None]:
    if step.expected_output_schema is None:
        return None, None
    return compile_expected_output_contract(step.expected_output_schema)


def _compile_read_reference(
    reference: object,
    inventory: dict[str, ArtifactInventoryRecord],
    *,
    step: Step | None = None,
) -> str:
    helper_path = _fan_in_helper_runtime_path(reference, step=step)
    if helper_path is not None:
        return helper_path
    resolved = resolve_optional_read_reference(reference, inventory)
    if resolved is not None:
        return resolved
    if isinstance(reference, Path):
        return str(reference)
    if isinstance(reference, str):
        return reference
    raise WorkflowCompilationError(f"unsupported read reference {reference!r}")


def _compile_required_reference(
    reference: object,
    inventory: dict[str, ArtifactInventoryRecord],
    *,
    step: Step | None = None,
) -> str:
    helper_path = _fan_in_helper_runtime_path(reference, step=step)
    if helper_path is not None:
        return helper_path
    return resolve_artifact_reference(
        reference,
        inventory,
        step_name=None if step is None else step.name,
        prefer_step_local=step is not None,
    ).qualified_name


def _fan_in_helper_runtime_path(reference: object, *, step: Step | None) -> str | None:
    if not isinstance(reference, FanInHelperReference):
        return None
    group_name = getattr(step, "_branch_group_name", None) if step is not None else None
    if not isinstance(group_name, str) or not group_name:
        raise WorkflowCompilationError(f"{reference} requires an internal fan-in step with a branch-group owner")
    filename = "results.json" if reference.helper == "results" else "context.md"
    return f"_branch_groups/{group_name}/{filename}"


def _compile_scope_name(scope: object | None) -> str | None:
    if scope is None:
        return None
    if isinstance(scope, str):
        return scope
    name = getattr(scope, "name", None)
    if isinstance(name, str) and name:
        return name
    raise WorkflowCompilationError("scoped steps require a named worklist")


def _callable_arity(func: Callable[..., Any]) -> int:
    signature = inspect.signature(func)
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    return len(positional)


def _workflow_source_hash(workflow_cls: type[Any]) -> str | None:
    module = inspect.getmodule(workflow_cls)
    module_file = getattr(module, "__file__", None)
    if not isinstance(module_file, str) or not module_file:
        return None
    path = Path(module_file)
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _definition_contains_branch_groups(definition: WorkflowDefinition) -> bool:
    return any(isinstance(step, BranchGroupStep) for step in definition.steps)


def _workflow_compile_cache_key(
    workflow_cls: type[Any],
    *,
    definition: WorkflowDefinition,
    source_hash: str | None,
) -> tuple[str, str, str]:
    payload = {
        "module": workflow_cls.__module__,
        "qualname": workflow_cls.__qualname__,
        "source_hash": source_hash,
        "workflow_name": definition.workflow_name,
        "entry_step_name": definition.entry.name,
        "default_session_name": definition.default_session_name,
        "state_fields": sorted(getattr(definition.state_cls, "model_fields", {}).keys()),
        "parameter_fields": sorted(getattr(definition.parameters_cls, "model_fields", {}).keys())
        if definition.parameters_cls is not None
        else [],
        "workflow_policy_fingerprint": _policy_input_fingerprint(definition.workflow_policy),
        "steps": [
            {
                "name": step.name,
                "type": type(step).__name__,
                "kind": getattr(step, "kind", None),
                "scope_name": _cache_scope_name(getattr(step, "scope", None)),
                "session_name": _cache_session_name(getattr(step, "session", None)),
                "verifier_session_name": _cache_session_name(getattr(step, "verifier_session", None)),
                "before_hook": _callable_name(getattr(step, "before", None)),
                "after_hook": _callable_name(getattr(step, "after", None)),
                "before_producer_hook": _callable_name(getattr(step, "before_producer", None)),
                "after_producer_hook": _callable_name(getattr(step, "after_producer", None)),
                "before_verifier_hook": _callable_name(getattr(step, "before_verifier", None)),
                "after_verifier_hook": _callable_name(getattr(step, "after_verifier", None)),
                "control_routes": {
                    "question": getattr(getattr(step, "control_routes", None), "question", None),
                },
                "provider_policy_fingerprint": _policy_input_fingerprint(getattr(step, "provider_policy", None)),
            }
            for step in definition.steps
        ],
        "transitions": _workflow_definition_transition_payload(definition),
        "worklists": {
            name: {
                "item_state_model": worklist.runtime_item_state_model.__name__,
                "item_state_fields": sorted(worklist.runtime_item_state_model.model_fields.keys()),
                "source_type": worklist.source_type,
                "missing_policy": worklist.missing_policy,
                "source_descriptor": worklist.source_descriptor(),
            }
            for name, worklist in definition.worklists_by_name.items()
        },
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=_topology_json_value,
        ).encode("utf-8")
    ).hexdigest()
    return (
        workflow_cls.__module__,
        workflow_cls.__qualname__,
        fingerprint,
    )


def _workflow_definition_transition_payload(definition: WorkflowDefinition) -> dict[str, dict[str, dict[str, Any]]]:
    payload: dict[str, dict[str, dict[str, Any]]] = {}
    for source, routes in definition.transitions.items():
        source_name = source if isinstance(source, str) else source.name
        payload[source_name] = {}
        for tag, destination in routes.items():
            route = normalize_route_spec(destination)
            target = route.target
            if hasattr(target, "name"):
                target = getattr(target, "name")
            payload[source_name][tag] = {
                "target": target,
                "summary": route.summary,
                "required_writes": list(route.required_writes or ()),
                "handoff": route.handoff,
                "on_taken": _callable_name(route.on_taken),
                "provider_visible": route.provider_visible,
                "provider_visibility": route.provider_visibility,
                "payload_schema_mode": route.payload_schema_mode,
                "route_fields_schema": route.route_fields_schema,
                "preset_kind": route.preset_kind,
                "disabled": route.disabled,
            }
    if getattr(definition, "framework_default_transitions_by_step", None):
        for step_name, routes in definition.framework_default_transitions_by_step.items():
            source_name = f"{step_name}::__framework_default__"
            payload[source_name] = {}
            for tag, destination in routes.items():
                route = normalize_route_spec(destination)
                target = route.target
                if hasattr(target, "name"):
                    target = getattr(target, "name")
                payload[source_name][tag] = {
                    "target": target,
                    "summary": route.summary,
                    "required_writes": list(route.required_writes or ()),
                    "handoff": route.handoff,
                    "on_taken": _callable_name(route.on_taken),
                    "provider_visible": route.provider_visible,
                    "provider_visibility": route.provider_visibility,
                    "payload_schema_mode": route.payload_schema_mode,
                    "route_fields_schema": route.route_fields_schema,
                    "preset_kind": route.preset_kind,
                    "disabled": route.disabled,
                }
    return payload


def _cache_scope_name(scope: object | None) -> str | None:
    if scope is None:
        return None
    if isinstance(scope, str):
        return scope
    name = getattr(scope, "name", None)
    return name if isinstance(name, str) and name else None


def _cache_session_name(session: object | None) -> str | None:
    name = getattr(session, "name", None)
    return name if isinstance(name, str) and name else None


def _topology_hash_payload(compiled: CompiledWorkflow) -> dict[str, Any]:
    return {
        "workflow_name": compiled.workflow_name,
        "entry_step_name": compiled.entry_step_name,
        "global_session": compiled.default_session_name,
        "workflow_policy_fingerprint": _policy_input_fingerprint(compiled.provider_policy),
        "steps": [_topology_hash_step_payload(step) for step in compiled.steps.values()],
        "worklists": {
            name: {
                "item_state_model": worklist.runtime_item_state_model.__name__,
                "item_state_fields": list(worklist.runtime_item_state_model.model_fields.keys()),
                "source_type": worklist.source_type,
                "missing_policy": worklist.missing_policy,
                "source_descriptor": worklist.source_descriptor(),
            }
            for name, worklist in compiled.worklists.items()
        },
        "routes": {
            step_name: {
                tag: _topology_hash_route_payload(
                    compiled,
                    step_name=step_name,
                    route_tag=tag,
                    route=route,
                    expected_output_schema=compiled.steps[step_name].expected_output_schema,
                )
                for tag, route in routes.items()
            }
            for step_name, routes in compiled.routes.items()
        },
        "global_routes": {
            tag: _topology_hash_route_payload(
                compiled,
                step_name=None,
                route_tag=tag,
                route=route,
                expected_output_schema=None,
            )
            for tag, route in compiled.global_routes.items()
        },
        "workflow_state_fields": sorted(getattr(compiled.state_cls, "model_fields", {}).keys()),
        "parameter_fields": sorted(getattr(compiled.parameters_cls, "model_fields", {}).keys())
        if compiled.parameters_cls is not None
        else [],
    }


def _topology_hash_step_payload(step: CompiledStep) -> dict[str, Any]:
    payload = {
        "name": step.name,
        "kind": step.kind,
        "scope_name": step.scope_name,
        "reads": list(step.reads),
        "requires": list(step.requires),
        "writes": list(step.writes),
        "producer_reads": list(step.producer_reads),
        "producer_requires": list(step.producer_requires),
        "producer_writes": list(step.producer_writes),
        "verifier_reads": list(step.verifier_reads),
        "verifier_requires": list(step.verifier_requires),
        "verifier_writes": list(step.verifier_writes),
        "available_routes": list(step.available_routes),
        "authored_routes": list(step.authored_routes),
        "runtime_control_routes": list(step.runtime_control_routes),
        "provider_visible_routes_interactive": list(step.provider_visible_routes_interactive),
        "provider_visible_routes_full_auto": list(step.provider_visible_routes_full_auto),
        "session_name": step.session_name,
        "verifier_session_name": step.verifier_session_name,
        "state_fields": list(step.step_state_fields),
        "state_model": step.step_state_model.__name__,
        "item_state_fields": list(step.step_item_state_fields),
        "item_state_model": step.step_item_state_model.__name__ if step.step_item_state_model is not None else None,
        "before_hook": _callable_name(step.before_hook),
        "after_hook": _callable_name(step.after_hook),
        "before_producer_hook": _callable_name(step.before_producer_hook),
        "after_producer_hook": _callable_name(step.after_producer_hook),
        "before_verifier_hook": _callable_name(step.before_verifier_hook),
        "after_verifier_hook": _callable_name(step.after_verifier_hook),
        "provider_policy_fingerprint": _policy_input_fingerprint(step.provider_policy),
        "prompt_refs": [
            _topology_json_value(reference)
            for reference in getattr(step.step, "simple_prompt_references", ())
        ],
    }
    if step.route_table:
        payload["route_table"] = {
            tag: _topology_hash_route_payload(
                None,
                step_name=step.name,
                route_tag=tag,
                route=route,
                expected_output_schema=step.expected_output_schema,
                use_effective_required_writes=False,
            )
            for tag, route in step.route_table.items()
        }
    if step.branch_group is not None:
        payload["branch_group"] = _topology_hash_branch_group_payload(step.branch_group)
    return payload


def _topology_hash_route_payload(
    compiled: CompiledWorkflow | None,
    *,
    step_name: str | None,
    route_tag: str,
    route: CompiledRoute,
    expected_output_schema: Mapping[str, Any] | None,
    use_effective_required_writes: bool = True,
) -> dict[str, Any]:
    payload_contract = payload_contract_for_route(
        route,
        expected_output_schema=expected_output_schema,
    )
    route_fields_contract = route_fields_contract_for_route(route)
    if use_effective_required_writes:
        required_write_payload = route_required_write_payload(
            compiled,
            step_name=step_name,
            route_tag=route_tag,
            route=route,
        )
    else:
        required_write_payload = {
            "required_writes": list(route.required_writes),
            "explicit_required_writes": list(route.required_writes) if route._required_writes_explicit else None,
            "effective_required_writes": None,
        }
    return {
        "target": route.target,
        "summary": route.summary,
        **required_write_payload,
        "handoff": route.handoff,
        "on_taken": _callable_name(route.on_taken),
        "provider_visibility": route.provider_visibility,
        "provider_visible": route.provider_visible,
        "provider_visible_interactive": route.provider_visible_interactive,
        "provider_visible_full_auto": route.provider_visible_full_auto,
        "payload_schema_mode": route.payload_schema_mode,
        "payload_schema": route.payload_schema,
        "payload_schema_source": payload_contract["source"],
        "payload_schema_name": payload_contract["name"],
        "payload_schema_fingerprint": payload_contract["fingerprint"],
        "route_fields_schema": route.route_fields_schema,
        "route_fields_schema_source": route_fields_contract["source"],
        "route_fields_schema_name": route_fields_contract["name"],
        "route_fields_schema_fingerprint": route_fields_contract["fingerprint"],
        "preset_kind": route.preset_kind,
        "inheritance_source": route.inheritance_source,
        "disabled": route.disabled,
        "is_runtime_control": route.is_runtime_control,
    }


def _topology_hash_branch_group_payload(spec: Any) -> dict[str, Any]:
    return {
        "name": spec.name,
        "kind": spec.kind,
        "concurrency": spec.concurrency,
        "settle": spec.settle,
        "success_routes": list(spec.success_routes),
        "exposed_routes": list(spec.composite_route_tags),
        "branches": [
            {
                "name": branch.name,
                "index": branch.index,
                "input": branch.input,
                "step": _topology_hash_step_payload(branch.step),
            }
            for branch in spec.branches
        ],
        "fan_in_step": None if spec.fan_in_step is None else _topology_hash_step_payload(spec.fan_in_step),
    }


def _with_topology_hash(compiled: CompiledWorkflow) -> CompiledWorkflow:
    payload = _topology_hash_payload(compiled)
    topology_hash = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=_topology_json_value,
        ).encode("utf-8")
    ).hexdigest()
    return CompiledWorkflow(
        workflow_cls=compiled.workflow_cls,
        workflow_name=compiled.workflow_name,
        state_cls=compiled.state_cls,
        input_model=compiled.input_model,
        output_model=compiled.output_model,
        output_builder=compiled.output_builder,
        parameters_cls=compiled.parameters_cls,
        entry_step_name=compiled.entry_step_name,
        sessions=compiled.sessions,
        default_session_name=compiled.default_session_name,
        default_session_open=compiled.default_session_open,
        worklists=compiled.worklists,
        steps=compiled.steps,
        routes=compiled.routes,
        global_routes=compiled.global_routes,
        artifacts=compiled.artifacts,
        artifacts_by_qualified_name=compiled.artifacts_by_qualified_name,
        extensions=compiled.extensions,
        provider_policy=compiled.provider_policy,
        source_hash=compiled.source_hash,
        topology_hash=topology_hash,
    )


def _callable_name(value: object | None) -> str | None:
    if value is None:
        return None
    return getattr(value, "__name__", type(value).__name__)


def _policy_input_payload(
    policy: PolicyInput,
) -> dict[str, Any] | None:
    if policy is None:
        return None
    if isinstance(policy, Policy):
        return {
            "kind": "policy_layer",
            "payload": policy.to_layer_payload(),
        }
    return {
        "kind": "provider_policy" if isinstance(policy, ProviderPolicy) else "provider_policy_override",
        "payload": policy.model_dump(mode="json", warnings=False),
    }


def _policy_input_fingerprint(policy: PolicyInput) -> str | None:
    if policy is None:
        return None
    payload = _policy_input_payload(policy)
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=_topology_json_value,
        ).encode("utf-8")
    ).hexdigest()


def _validated_compiled_policy(
    policy: PolicyInput,
    *,
    owner: str,
) -> PolicyInput:
    payload = _policy_input_payload(policy)
    if payload is None:
        return None
    try:
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=_topology_json_value,
        )
    except TypeError as exc:
        raise WorkflowCompilationError(f"{owner} provider policy must be JSON-serializable: {exc}") from exc
    return policy


def _topology_json_value(value: object) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Path):
        return str(value)
    qualified_name = getattr(value, "qualified_name", None)
    if isinstance(qualified_name, str) and qualified_name:
        return qualified_name
    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name
    return repr(value)
