"""Workflow compilation."""

from __future__ import annotations

import hashlib
import inspect
import json
import re
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Mapping
from uuid import uuid4

from pydantic import BaseModel

from botlane.policy import Policy, PolicyInput

from .artifact_plan import ArtifactSpec
from .branch_groups.models import (
    BranchGroupDeclarationSpec,
    FanInHelperReference,
)
from .context import Context
from .discovery import (
    WorkflowDefinition,
    _SimpleStepSeed,
    _lower_simple_steps,
    _lower_simple_verifier_writes,
    _lower_simple_writes,
    get_workflow_definition,
)
from .errors import WorkflowCompilationError, WorkflowValidationError
from .inventory import ArtifactInventoryRecord, collect_artifact_inventory, public_artifact_inventory, resolve_artifact_reference
from .identifiers import ArtifactId
from .lowering import (
    ResolvedRouteSpec,
    _fallback_route_summary,
    compile_expected_output_contract,
    normalize_step_route_metadata,
    resolve_step_routes,
    step_authored_route_tags,
)
from .primitives import AWAIT_INPUT, FAIL, FINISH, GLOBAL, SELF
from .provider_policy import ProviderPolicy, ProviderPolicyOverride
from .providers.retries import ProviderRetryPolicy
from .placeholders import PlaceholderRef, parse_placeholders, validate_placeholder_ref
from .prompts import Prompt, resolve_prompt_reference
from .reference_graph import ReferenceGraph, ReferenceGraphBuilder
from .route_reporting import payload_contract_for_route, route_fields_contract_for_route
from .route_required_writes import route_required_write_payload
from .route_contracts import (
    PayloadContract,
    ProviderRoutePolicy,
    RequiredWriteContract,
    RouteContract,
    RouteFieldsContract,
    RouteTarget,
    available_route_tags,
    provider_visible_route_tags,
    route_target_value,
    runtime_control_route_tags,
)
from .routes import Route, _replace_route, normalize_route_spec
from .sessions import Continuity, DEFAULT_SESSION_NAME
from .step_plans import (
    BranchGroupPlan,
    BranchGroupStepPlan,
    BranchPlan,
    ChildWorkflowStepPlan,
    ExternalRead,
    FanInRead,
    ProduceVerifyStepPlan,
    PromptStepPlan,
    ProviderTurnPlan,
    PythonStepPlan,
    SingleStepPlan,
    StepHeader,
    StepHookSpec,
    StepIO,
    StepPlan,
    StepSource,
    StepStateSpec,
)
from .step_state import build_step_item_state_model, build_step_state_model
from .steps import BranchGroupStep, PromptStep, ProduceVerifyStep, Session, Step, PythonStep, ChildWorkflowStep
from .validation import PayloadValidator
from .workflow_plan import WorkflowPlan

SystemHandler = Callable[[Context], Any]

_WORKFLOW_PLAN_CACHE: dict[tuple[str, str, str], WorkflowPlan] = {}
_WORKFLOW_STEP_MESSAGE_UNKNOWN_FIELD_RE = re.compile(
    r"^(?P<prefix>workflow step '.*' message placeholder \{[^}]+\}) "
    r"references unknown (?:State|Input|Params) field (?P<field>'.*')$"
)


def compile_workflow(workflow_cls: type[Any]) -> WorkflowPlan:
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
        cached = _WORKFLOW_PLAN_CACHE.get(cache_key)
        if cached is not None:
            return cached
    inventory = collect_artifact_inventory(definition)
    routes = _compile_routes(definition, inventory)
    global_routes = _compile_global_routes(definition, inventory)
    compiled_steps = _compile_steps(definition, inventory, routes)
    plan = WorkflowPlan(
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
        steps=compiled_steps,
        routes=routes,
        global_routes=global_routes,
        artifacts=_compile_artifacts(inventory),
        public_artifacts=_compile_public_artifacts(inventory),
        artifacts_by_qualified_name=_compile_artifacts_by_qualified_name(inventory),
        extensions=definition.extensions,
        provider_policy=_validated_compiled_policy(definition.workflow_policy, owner="workflow"),
        source_hash=source_hash,
        topology_hash="",
        reference_graph=ReferenceGraph.empty(),
    )
    plan = replace(plan, reference_graph=_compile_reference_graph(plan, inventory))
    plan = _with_topology_hash(plan)
    if cache_key is not None:
        _WORKFLOW_PLAN_CACHE[cache_key] = plan
    return plan


def _compile_single_step_execution_plan(
    step_def: Step | object,
    *,
    input_model: type[BaseModel] | None,
    params_model: type[BaseModel] | None,
    routes: Mapping[str, object] | None,
    workflow_policy: PolicyInput = None,
) -> tuple[SingleStepPlan, WorkflowPlan]:
    workflow_plan = _compile_single_step_workflow_plan(
        step_def,
        input_model=input_model,
        params_model=params_model,
        routes=routes,
        workflow_policy=workflow_policy,
    )
    entry_step_name = workflow_plan.entry_step_name
    return (
        SingleStepPlan(
            step=workflow_plan.steps[entry_step_name],
            input_model=workflow_plan.input_model,
            params_model=workflow_plan.parameters_cls,
            routes=dict(workflow_plan.routes.get(entry_step_name, {})),
            workflow_policy=workflow_plan.provider_policy,
        ),
        workflow_plan,
    )


def _compile_single_step_workflow_plan(
    step_def: Step | object,
    *,
    input_model: type[BaseModel] | None,
    params_model: type[BaseModel] | None,
    routes: Mapping[str, object] | None,
    workflow_policy: PolicyInput = None,
) -> WorkflowPlan:
    workflow_name = _single_step_workflow_name(step_def)
    workflow_cls = _single_step_workflow_cls(
        workflow_name=workflow_name,
        input_model=input_model,
        params_model=params_model,
        workflow_policy=workflow_policy,
    )
    step = _materialize_single_step_definition(workflow_cls, step_def)
    base_definition = WorkflowDefinition(
        workflow_cls=workflow_cls,
        workflow_name=workflow_name,
        workflow_policy=workflow_policy,
        state_cls=_SingleStepWorkflowState,
        parameters_cls=params_model,
        entry=step,
        steps=(step,),
        steps_by_name={step.name: step},
        sessions_by_name={},
        default_session_name=DEFAULT_SESSION_NAME,
        worklists_by_name={},
        workflow_artifacts={},
        workflow_log_artifacts=(),
        extensions=(),
        authored_transitions={},
        transitions={},
        framework_default_transitions_by_step={},
        runtime_control_routes_by_step={},
    )
    authored_routes = (
        {
            route_name: _lower_internal_route_destination(
                destination,
                destination_names=_internal_branch_destination_names(base_definition, step),
                current_step_name=step.name,
            )
            for route_name, destination in dict(routes).items()
        }
        if routes is not None
        else _internal_single_step_authored_routes(base_definition, step)
    )
    definition = WorkflowDefinition(
        workflow_cls=workflow_cls,
        workflow_name=workflow_name,
        workflow_policy=workflow_policy,
        state_cls=_SingleStepWorkflowState,
        parameters_cls=params_model,
        entry=step,
        steps=(step,),
        steps_by_name={step.name: step},
        sessions_by_name={},
        default_session_name=DEFAULT_SESSION_NAME,
        worklists_by_name={},
        workflow_artifacts={},
        workflow_log_artifacts=(),
        extensions=(),
        authored_transitions={step: dict(authored_routes)},
        transitions={step: dict(authored_routes)},
        framework_default_transitions_by_step={step.name: _internal_step_framework_default_routes(step)},
        runtime_control_routes_by_step={step.name: _internal_step_runtime_control_routes(step)},
    )
    workflow_cls.__workflow_definition__ = definition
    inventory = collect_artifact_inventory(definition)
    compiled_routes = _compile_routes(definition, inventory)
    global_routes = _compile_global_routes(definition, inventory)
    compiled_steps = _compile_steps(definition, inventory, compiled_routes)
    workflow_plan = WorkflowPlan(
        workflow_cls=workflow_cls,
        workflow_name=workflow_name,
        state_cls=_SingleStepWorkflowState,
        input_model=input_model,
        output_model=None,
        output_builder=None,
        parameters_cls=params_model,
        entry_step_name=step.name,
        sessions=_compile_sessions(definition),
        default_session_name=DEFAULT_SESSION_NAME,
        default_session_open=False,
        worklists={},
        steps=compiled_steps,
        routes=compiled_routes,
        global_routes=global_routes,
        artifacts=_compile_artifacts(inventory),
        public_artifacts=_compile_public_artifacts(inventory),
        artifacts_by_qualified_name=_compile_artifacts_by_qualified_name(inventory),
        extensions=(),
        provider_policy=workflow_policy,
        source_hash=None,
        topology_hash="",
        reference_graph=ReferenceGraph.empty(),
    )
    workflow_plan = replace(workflow_plan, reference_graph=_compile_reference_graph(workflow_plan, inventory))
    return _with_topology_hash(workflow_plan)


def runtime_workflow_validation_message(exc: WorkflowValidationError) -> str | None:
    message = str(exc)
    match = _WORKFLOW_STEP_MESSAGE_UNKNOWN_FIELD_RE.match(message)
    if match is not None:
        return f"{match.group('prefix')} references unknown runtime field {match.group('field')}"
    if "workflow step " in message and " message placeholder {" in message:
        return message
    return None


def _compile_steps(
    definition: WorkflowDefinition,
    inventory: dict[str, ArtifactInventoryRecord],
    routes: dict[str, dict[str, RouteContract]],
) -> dict[str, StepPlan]:
    compiled_steps: dict[str, StepPlan] = {}
    for step in definition.steps:
        route_table = dict(routes.get(step.name, {}))
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
            _artifact_id_from_record(resolve_artifact_reference(artifact, inventory))
            for artifact in step.writes.values()
        )
        producer_writes = tuple(
            _artifact_id_from_record(resolve_artifact_reference(step.writes[name], inventory))
            for name in getattr(step, "producer_writes", tuple(step.writes.keys()))
        )
        verifier_writes = tuple(
            _artifact_id_from_record(resolve_artifact_reference(step.writes[name], inventory))
            for name in getattr(step, "verifier_writes", ())
        )
        step_log_artifacts = tuple(
            _artifact_id_from_record(resolve_artifact_reference(artifact, inventory))
            for artifact in step.log_artifacts
        )
        workflow_log_artifact_names = tuple(
            _artifact_id_from_record(resolve_artifact_reference(artifact, inventory))
            for artifact in definition.workflow_log_artifacts
        )
        log_names = tuple(dict.fromkeys((*workflow_log_artifact_names, *step_log_artifacts)))
        before_hook = getattr(step, "before", None)
        after_hook = getattr(step, "after", None)
        before_producer_hook = getattr(step, "before_producer", None)
        after_producer_hook = getattr(step, "after_producer", None)
        before_verifier_hook = getattr(step, "before_verifier", None)
        after_verifier_hook = getattr(step, "after_verifier", None)
        step_kind = _step_kind(step)
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
            _step_session_name(step, step.session, default_session_name=definition.default_session_name)
            if step.session is not None
            else definition.default_session_name
        )
        if isinstance(step, (PythonStep, ChildWorkflowStep)):
            compiled_session_name = (
                _step_session_name(step, step.session, default_session_name=definition.default_session_name)
                if step.session is not None
                else None
            )
        if isinstance(step, BranchGroupStep):
            compiled_session_name = None
        producer_reads = tuple(
            _compile_read_reference(artifact_reference, inventory, step=step)
            for artifact_reference in getattr(step, "producer_reads", step.reads)
        )
        producer_requires = tuple(
            _compile_required_reference(artifact_reference, inventory, step=step)
            for artifact_reference in getattr(step, "producer_requires", step.requires)
        )
        verifier_requires = tuple(
            _compile_required_reference(artifact_reference, inventory, step=step)
            for artifact_reference in getattr(step, "verifier_requires", ())
        )
        verifier_read_refs = getattr(step, "verifier_reads", None)
        if verifier_read_refs is None:
            verifier_reads = tuple(dict.fromkeys((*reads, *producer_writes, *verifier_requires)))
        else:
            verifier_reads = tuple(
                _compile_read_reference(artifact_reference, inventory, step=step)
                for artifact_reference in verifier_read_refs
            )
        header = StepHeader(
            name=step.name,
            kind=step_kind,
            source=_step_source(step),
            session_name=compiled_session_name,
            scope_name=None if isinstance(step, PythonStep) else _compile_scope_name(step.scope),
            io=StepIO(
                reads=reads,
                requires=requires,
                writes=writes,
                log_artifacts=log_names,
            ),
            state=StepStateSpec(
                step_state_model=step_state_model,
                step_state_fields=step_state_fields,
                step_item_state_model=step_item_state_model,
                step_item_state_fields=step_item_state_fields,
            ),
            hooks=StepHookSpec(
                before=before_hook,
                after=after_hook,
                before_producer=before_producer_hook,
                after_producer=after_producer_hook,
                before_verifier=before_verifier_hook,
                after_verifier=after_verifier_hook,
            ),
            provider_policy=_validated_compiled_policy(step.provider_policy, owner=f"step {step.name!r}"),
        )
        if isinstance(step, ProduceVerifyStep):
            compiled_steps[step.name] = ProduceVerifyStepPlan(
                header=header,
                producer=ProviderTurnPlan(
                    kind="producer",
                    prompt=step.producer,
                    session_name=compiled_session_name,
                    io=StepIO(
                        reads=producer_reads,
                        requires=producer_requires,
                        writes=producer_writes,
                        log_artifacts=log_names,
                    ),
                    retry_policy=step.retry_policy,
                    expected_output_schema=None,
                    expected_output_validator=None,
                ),
                verifier=ProviderTurnPlan(
                    kind="verifier",
                    prompt=step.verifier,
                    session_name=(
                        _step_session_name(
                            step,
                            step.verifier_session,
                            default_session_name=definition.default_session_name,
                            role="verifier_session",
                        )
                        if getattr(step, "verifier_session", None) is not None
                        else None
                    ),
                    io=StepIO(
                        reads=verifier_reads,
                        requires=verifier_requires,
                        writes=verifier_writes or writes,
                        log_artifacts=log_names,
                    ),
                    retry_policy=step.retry_policy,
                    expected_output_schema=expected_output_schema,
                    expected_output_validator=expected_output_validator,
                ),
                verifier_session_name=(
                    _step_session_name(
                        step,
                        step.verifier_session,
                        default_session_name=definition.default_session_name,
                        role="verifier_session",
                    )
                    if getattr(step, "verifier_session", None) is not None
                    else None
                ),
                _route_table=route_table,
            )
        elif isinstance(step, PromptStep):
            compiled_steps[step.name] = PromptStepPlan(
                header=header,
                turn=ProviderTurnPlan(
                    kind="llm",
                    prompt=step.producer,
                    session_name=compiled_session_name,
                    io=StepIO(
                        reads=producer_reads,
                        requires=producer_requires,
                        writes=writes,
                        log_artifacts=log_names,
                    ),
                    retry_policy=step.retry_policy,
                    expected_output_schema=expected_output_schema,
                    expected_output_validator=expected_output_validator,
                ),
                _route_table=route_table,
            )
        elif isinstance(step, PythonStep):
            compiled_steps[step.name] = PythonStepPlan(
                header=header,
                handler=_compile_system_handler(step),
                _route_table=route_table,
            )
        elif isinstance(step, ChildWorkflowStep):
            compiled_steps[step.name] = ChildWorkflowStepPlan(
                header=header,
                workflow=step.workflow,
                message=step.message,
                message_from=step.message_from,
                params=dict(step.params),
                input=step.input,
                _route_table=route_table,
            )
        elif isinstance(step, BranchGroupStep):
            compiled_branch_group = _compile_branch_group_internal_steps(
                definition,
                step.branch_group,
                inventory=inventory,
            )
            compiled_steps[step.name] = BranchGroupStepPlan(
                header=header,
                branch_group=compiled_branch_group,
                _route_table=route_table,
            )
        else:
            raise WorkflowCompilationError(f"unsupported step type {type(step)!r}")
    return compiled_steps


def _compile_reference_graph(
    plan: WorkflowPlan,
    inventory: dict[str, ArtifactInventoryRecord],
) -> ReferenceGraph:
    step_entries = tuple(_iter_reference_graph_steps(plan.steps.values()))
    step_plans = {step.name: step for step, _, _ in step_entries}
    builder = ReferenceGraphBuilder(step_names=frozenset(step_plans))
    state_fields = frozenset(getattr(plan.state_cls, "model_fields", {}).keys())
    parameter_fields = (
        frozenset(getattr(plan.parameters_cls, "model_fields", {}).keys())
        if plan.parameters_cls is not None
        else frozenset()
    )
    input_fields = (
        frozenset(getattr(plan.input_model, "model_fields", {}).keys())
        if plan.input_model is not None
        else frozenset()
    )
    worklist_item_state_fields = {
        name: frozenset(worklist.runtime_item_state_model.model_fields.keys())
        for name, worklist in plan.worklists.items()
    }
    step_state_fields = {name: frozenset(step.step_state_fields) for name, step in step_plans.items()}
    step_item_state_fields = {name: frozenset(step.step_item_state_fields) for name, step in step_plans.items()}
    step_output_names = {name: frozenset(artifact_id.name for artifact_id in step.writes) for name, step in step_plans.items()}
    artifact_name_counts = _artifact_name_counts(plan.artifacts.values())
    step_symbol_contexts = {
        step.name: {
            "step_name": step.name,
            "own_outputs": frozenset(artifact_id.name for artifact_id in step.writes),
            "state_fields": state_fields,
            "parameter_fields": parameter_fields,
            "input_fields": input_fields,
            "scope_name": step.scope_name,
            "worklist_item_state_fields": worklist_item_state_fields,
            "step_state_fields": step_state_fields,
            "step_item_state_fields": step_item_state_fields,
            "step_output_names": step_output_names,
            "artifact_name_counts": artifact_name_counts,
            "allow_branch_placeholders": allow_branch_placeholders,
            "allow_fan_in_placeholders": allow_fan_in_placeholders,
        }
        for step, allow_branch_placeholders, allow_fan_in_placeholders in step_entries
    }

    for step, _, _ in step_entries:
        prompt_refs: list[PlaceholderRef] = []
        inferred_reads: list[ArtifactId] = []
        prompt_symbols = _placeholder_symbols(step_symbol_contexts[step.name], kind="simple_prompt")
        for prompt_text in _step_prompt_texts(step, workflow_cls=plan.workflow_cls):
            refs = tuple(ref for ref in parse_placeholders(prompt_text, source="prompt") if ref.raw)
            prompt_refs.extend(ref for ref in refs if ref not in prompt_refs)
            inferred_reads.extend(
                artifact_id
                for artifact_id in _infer_prompt_artifact_reads(
                    refs,
                    symbols=prompt_symbols,
                    inventory=inventory,
                    step_name=step.name,
                )
                if artifact_id not in inferred_reads
            )
        if isinstance(step, ChildWorkflowStepPlan) and isinstance(step.message, str):
            refs = tuple(ref for ref in parse_placeholders(step.message, source="workflow_step_message") if ref.raw)
            if refs:
                _validate_placeholder_refs(
                    refs,
                    surface=f"workflow step {step.name!r} message placeholder",
                    symbol_candidates=(
                        _placeholder_symbols(step_symbol_contexts[step.name], kind="workflow_step_message"),
                    ),
                )
                builder.add_prompt_refs(step.name, refs)
        if prompt_refs:
            builder.add_prompt_refs(step.name, tuple(prompt_refs))
        if inferred_reads:
            builder.add_inferred_artifact_reads(step.name, tuple(inferred_reads))

    for artifact_id, artifact_spec in plan.artifacts.items():
        refs = tuple(ref for ref in parse_placeholders(artifact_spec.template, source="artifact_template") if ref.raw)
        if not refs:
            continue
        builder.add_artifact_template_refs(artifact_id.qualified_name, refs)
        _validate_placeholder_refs(
            refs,
            surface=f"artifact template {artifact_id.qualified_name!r} placeholder",
            symbol_candidates=_artifact_template_symbol_candidates(
                artifact_spec,
                step_symbol_contexts=step_symbol_contexts,
                state_fields=state_fields,
                parameter_fields=parameter_fields,
                input_fields=input_fields,
                worklist_item_state_fields=worklist_item_state_fields,
                step_state_fields=step_state_fields,
                step_item_state_fields=step_item_state_fields,
                step_output_names=step_output_names,
                artifact_name_counts=artifact_name_counts,
            ),
        )
    return builder.build()


def _placeholder_symbols(symbol_context: Mapping[str, Any], *, kind: str) -> dict[str, Any]:
    return {"kind": kind, **symbol_context}


def _validate_placeholder_refs(
    refs: tuple[PlaceholderRef, ...],
    *,
    surface: str,
    symbol_candidates: tuple[Mapping[str, Any], ...],
) -> None:
    for ref in refs:
        errors: list[WorkflowValidationError] = []
        for symbols in symbol_candidates:
            try:
                validate_placeholder_ref(ref, surface=surface, symbols=symbols)
                break
            except WorkflowValidationError as exc:
                errors.append(exc)
        else:
            raise errors[0]


def _artifact_template_symbol_candidates(
    artifact_spec: ArtifactSpec,
    *,
    step_symbol_contexts: Mapping[str, Mapping[str, Any]],
    state_fields: frozenset[str],
    parameter_fields: frozenset[str],
    input_fields: frozenset[str],
    worklist_item_state_fields: Mapping[str, frozenset[str]],
    step_state_fields: Mapping[str, frozenset[str]],
    step_item_state_fields: Mapping[str, frozenset[str]],
    step_output_names: Mapping[str, frozenset[str]],
    artifact_name_counts: Mapping[str, int],
) -> tuple[Mapping[str, Any], ...]:
    if artifact_spec.owner_step is not None and artifact_spec.owner_step in step_symbol_contexts:
        return (_placeholder_symbols(step_symbol_contexts[artifact_spec.owner_step], kind="artifact_template"),)
    if artifact_spec.producer_steps:
        return tuple(
            _placeholder_symbols(step_symbol_contexts[step_name], kind="artifact_template")
            for step_name in artifact_spec.producer_steps
            if step_name in step_symbol_contexts
        ) or (
            {
                "kind": "artifact_template",
                "step_name": "",
                "own_outputs": frozenset(),
                "state_fields": state_fields,
                "parameter_fields": parameter_fields,
                "input_fields": input_fields,
                "scope_name": None,
                "worklist_item_state_fields": worklist_item_state_fields,
                "step_state_fields": step_state_fields,
                "step_item_state_fields": step_item_state_fields,
                "step_output_names": step_output_names,
                "artifact_name_counts": artifact_name_counts,
                "allow_branch_placeholders": False,
                "allow_fan_in_placeholders": False,
            },
        )
    return (
        {
            "kind": "artifact_template",
            "step_name": "",
            "own_outputs": frozenset(),
            "state_fields": state_fields,
            "parameter_fields": parameter_fields,
            "input_fields": input_fields,
            "scope_name": None,
            "worklist_item_state_fields": worklist_item_state_fields,
            "step_state_fields": step_state_fields,
            "step_item_state_fields": step_item_state_fields,
            "step_output_names": step_output_names,
            "artifact_name_counts": artifact_name_counts,
            "allow_branch_placeholders": False,
            "allow_fan_in_placeholders": False,
        },
    )


def _iter_reference_graph_steps(
    steps: Any,
    *,
    allow_branch_placeholders: bool = False,
    allow_fan_in_placeholders: bool = False,
):
    for step in steps:
        yield step, allow_branch_placeholders, allow_fan_in_placeholders
        if not isinstance(step, BranchGroupStepPlan):
            continue
        for branch in step.branch_group.branches:
            yield from _iter_reference_graph_steps(
                (branch.step,),
                allow_branch_placeholders=True,
                allow_fan_in_placeholders=False,
            )
        if step.branch_group.fan_in_step is not None:
            yield from _iter_reference_graph_steps(
                (step.branch_group.fan_in_step,),
                allow_branch_placeholders=False,
                allow_fan_in_placeholders=True,
            )


def _artifact_name_counts(artifacts: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for artifact in artifacts:
        counts[artifact.name] = counts.get(artifact.name, 0) + 1
    return counts


def _step_prompt_texts(step: StepPlan, *, workflow_cls: type[Any]) -> tuple[str, ...]:
    texts: list[str] = []
    if isinstance(step, PromptStepPlan):
        text = _prompt_text(step.turn.prompt, workflow_cls=workflow_cls)
        if text:
            texts.append(text)
    elif isinstance(step, ProduceVerifyStepPlan):
        producer_text = _prompt_text(step.producer.prompt, workflow_cls=workflow_cls)
        verifier_text = _prompt_text(step.verifier.prompt, workflow_cls=workflow_cls)
        if producer_text:
            texts.append(producer_text)
        if verifier_text:
            texts.append(verifier_text)
    return tuple(texts)


def _prompt_text(prompt: Any, *, workflow_cls: type[Any]) -> str | None:
    if prompt is None:
        return None
    if isinstance(prompt, str):
        return prompt
    if isinstance(prompt, Prompt):
        if isinstance(prompt.text, str) and prompt.text:
            return prompt.text
        if not isinstance(prompt.path, str) or not prompt.path or prompt.source == "registry":
            return None
        return resolve_prompt_reference(
            prompt.path,
            source=prompt.source,
            search_roots=_workflow_prompt_search_roots(workflow_cls),
        ).text
    prompt_text = getattr(prompt, "text", None)
    if isinstance(prompt_text, str) and prompt_text:
        return prompt_text
    return None


def _workflow_prompt_search_roots(workflow_cls: type[Any]) -> tuple[Path, ...]:
    module = inspect.getmodule(workflow_cls)
    module_file = getattr(module, "__file__", None)
    if not isinstance(module_file, str) or not module_file:
        return ()
    return (Path(module_file).resolve().parent,)


def _infer_prompt_artifact_reads(
    refs: tuple[PlaceholderRef, ...],
    *,
    symbols: Mapping[str, Any],
    inventory: dict[str, ArtifactInventoryRecord],
    step_name: str,
) -> tuple[ArtifactId, ...]:
    inferred: list[ArtifactId] = []
    for ref in refs:
        inferred_artifact = validate_placeholder_ref(
            ref,
            surface=f"step {step_name!r} prompt placeholder",
            symbols=symbols,
        )
        if inferred_artifact is None:
            continue
        record = resolve_artifact_reference(
            inferred_artifact,
            inventory,
            step_name=step_name,
            prefer_step_local=True,
        )
        artifact_id = _artifact_id_from_record(record)
        if artifact_id not in inferred:
            inferred.append(artifact_id)
    return tuple(inferred)


def _compile_branch_group_internal_steps(
    definition: WorkflowDefinition,
    branch_group: BranchGroupDeclarationSpec,
    *,
    inventory: dict[str, ArtifactInventoryRecord],
) -> BranchGroupPlan:
    compiled_branches = tuple(
        BranchPlan(
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
    return BranchGroupPlan(
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
) -> StepPlan:
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
    compiled_routes = _compile_routes(internal_definition, inventory)
    compiled_step = _compile_steps(
        internal_definition,
        inventory,
        compiled_routes,
    )[step.name]
    return compiled_step


def _internal_single_step_authored_routes(
    definition: WorkflowDefinition,
    step: Step,
) -> dict[str, object]:
    authored = _lower_internal_step_route_map(definition, step)
    if authored:
        return authored
    return {
        route_name: _lower_internal_route_destination(
            destination,
            destination_names=_internal_branch_destination_names(definition, step),
            current_step_name=step.name,
        )
        for route_name, destination in _default_single_step_routes(step).items()
    }


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


def _default_single_step_routes(step_def: Step) -> dict[str, object]:
    if step_def.route_metadata:
        transitions: dict[str, object] = {}
        for route_name in step_def.route_metadata:
            if route_name in {"question", "blocked"}:
                transitions[route_name] = AWAIT_INPUT
            elif route_name == "failed":
                transitions[route_name] = FAIL
            elif isinstance(step_def, ProduceVerifyStep) and route_name == "needs_rework":
                transitions[route_name] = SELF
            else:
                transitions[route_name] = FINISH
        return transitions
    if isinstance(step_def, ProduceVerifyStep):
        return {"accepted": FINISH, "needs_rework": SELF}
    if isinstance(step_def, (PromptStep, PythonStep, ChildWorkflowStep)):
        return {"done": FINISH}
    return {"done": FINISH}


def _materialize_single_step_definition(workflow_cls: type[object], step_def: Step | object) -> Step:
    if isinstance(step_def, Step):
        return step_def
    simple_name = getattr(step_def, "name", None) or "step"
    writes = _lower_single_step_writes(step_def, simple_name)
    verifier_writes = _lower_single_step_verifier_writes(step_def, simple_name)
    seed = _single_step_seed(
        declaration=step_def,
        name=simple_name,
        writes=writes,
        verifier_writes=verifier_writes,
    )
    lowered = _lower_simple_steps(
        workflow_cls,
        simple_seeds=(seed,),
        workflow_artifacts={},
        existing_steps=(),
    )
    return lowered[0][1]


def _single_step_seed(
    *,
    declaration: object,
    name: str,
    writes: dict[str, Any],
    verifier_writes: dict[str, Any],
) -> _SimpleStepSeed:
    return _SimpleStepSeed(
        order=0,
        attr_name=name,
        declaration=declaration,
        name=name,
        kind=str(getattr(declaration, "kind", "")),
        writes=writes,
        verifier_writes=verifier_writes,
        output_order=tuple((*writes.keys(), *verifier_writes.keys())),
    )


def _lower_single_step_writes(step_def: object, step_name: str) -> dict[str, Any]:
    if isinstance(step_def, Step):
        return dict(step_def.writes)
    return _lower_simple_writes(step_def, step_name)


def _lower_single_step_verifier_writes(step_def: object, step_name: str) -> dict[str, Any]:
    if isinstance(step_def, Step):
        verifier_write_names = tuple(getattr(step_def, "verifier_writes", ()))
        if not verifier_write_names:
            return {}
        return {
            name: artifact
            for name, artifact in step_def.writes.items()
            if name in verifier_write_names
        }
    return _lower_simple_verifier_writes(step_def, step_name)


def _single_step_workflow_name(step_def: Step | object) -> str:
    safe_name = re.sub(r"[^a-z0-9]+", "_", (getattr(step_def, "name", None) or "step").strip().lower()).strip("_")
    return f"sdk_step_{safe_name or 'step'}"


def _single_step_workflow_cls(
    *,
    workflow_name: str,
    input_model: type[BaseModel] | None,
    params_model: type[BaseModel] | None,
    workflow_policy: PolicyInput,
) -> type[object]:
    attrs: dict[str, Any] = {
        "__module__": __name__,
        "State": _SingleStepWorkflowState,
        "name": workflow_name,
    }
    if input_model is not None:
        attrs["Input"] = input_model
    if params_model is not None:
        attrs["Params"] = params_model
    if workflow_policy is not None:
        attrs["policy"] = workflow_policy
    return type(f"SDKSingleStepWorkflow_{uuid4().hex[:8]}", (), attrs)


class _SingleStepWorkflowState(BaseModel):
    pass


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
    if target == SELF:
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
            _step_session_name(step, step.session, default_session_name=DEFAULT_SESSION_NAME),
            _compiled_session_copy(
                _step_session_name(step, step.session, default_session_name=DEFAULT_SESSION_NAME),
                step.session,
            ),
        )
    verifier_session = getattr(step, "verifier_session", None)
    if verifier_session is not None:
        compiled.setdefault(
            _step_session_name(step, verifier_session, default_session_name=DEFAULT_SESSION_NAME, role="verifier_session"),
            _compiled_session_copy(
                _step_session_name(step, verifier_session, default_session_name=DEFAULT_SESSION_NAME, role="verifier_session"),
                verifier_session,
            ),
        )


def _step_session_name(
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


def _compile_routes(
    definition: WorkflowDefinition,
    inventory: dict[str, ArtifactInventoryRecord],
) -> dict[str, dict[str, RouteContract]]:
    route_metadata = {
        step.name: normalize_step_route_metadata(definition, step, inventory)
        for step in definition.steps
    }
    routes: dict[str, dict[str, RouteContract]] = {}
    for step in definition.steps:
        compiled_step_routes: dict[str, RouteContract] = {}
        for resolved in resolve_step_routes(definition, step):
            normalized_route = route_metadata[step.name].get(resolved.tag, resolved.route)
            compiled_step_routes[resolved.tag] = _compile_route(
                step,
                GLOBAL if resolved.inheritance_source == "global" else step.name,
                resolved.tag,
                normalized_route,
                inventory=inventory,
                inheritance_source=resolved.inheritance_source,
                is_runtime_control=resolved.legacy_runtime_control,
            )
        routes[step.name] = compiled_step_routes
    return routes


def _compile_global_routes(
    definition: WorkflowDefinition,
    inventory: dict[str, ArtifactInventoryRecord],
) -> dict[str, RouteContract]:
    source_routes = definition.transitions.get(GLOBAL, {})
    return {
        tag: _compile_route(
            None,
            GLOBAL,
            tag,
            destination,
            inventory=inventory,
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
    inventory: dict[str, ArtifactInventoryRecord],
    summary: str | None = None,
    inheritance_source: str,
    is_runtime_control: bool = False,
) -> RouteContract:
    route = normalize_route_spec(destination)
    compiled_target: RouteTarget
    if route.is_disabled:
        compiled_target = RouteTarget("disabled")
    else:
        target = route.target
        if isinstance(target, Step):
            compiled_target = RouteTarget("step", step_name=target.name)
        elif isinstance(target, str):
            if target == FINISH:
                compiled_target = RouteTarget("finish")
            elif target == AWAIT_INPUT:
                compiled_target = RouteTarget("await_input")
            elif target == FAIL:
                compiled_target = RouteTarget("fail")
            else:
                compiled_target = RouteTarget("step", step_name=target)
        else:  # pragma: no cover - validation guards this before compilation
            raise WorkflowCompilationError(f"route {tag!r} from {source_step!r} is missing a target")
    explicit_required_writes = (
        None
        if route.required_writes is None
        else tuple(
            _artifact_id_from_record(
                resolve_artifact_reference(
                    reference,
                    inventory,
                    step_name=source_step if source_step != GLOBAL else None,
                    prefer_step_local=source_step != GLOBAL,
                )
            )
            for reference in route.required_writes
        )
    )
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
    return RouteContract(
        source_step=source_step,
        tag=tag,
        target=compiled_target,
        summary=route.summary or summary,
        required_writes=RequiredWriteContract(
            declared=() if explicit_required_writes is None else explicit_required_writes,
            explicit=explicit_required_writes,
        ),
        handoff=route.handoff,
        on_taken=route.on_taken,
        provider=ProviderRoutePolicy(
            visibility=provider_visibility,
            visible=provider_visibility != "hidden",
            visible_interactive=provider_visible_interactive,
            visible_full_auto=provider_visible_full_auto,
        ),
        payload=PayloadContract(
            schema_mode=route.payload_schema_mode,
            schema=payload_schema,
            validator=payload_validator,
        ),
        route_fields=RouteFieldsContract(
            schema=route_fields_schema,
            validator=route_fields_validator,
        ),
        preset_kind=preset_kind,
        inheritance_source=inheritance_source,
        disabled=route.is_disabled,
        is_runtime_control=is_runtime_control,
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


def _step_kind(step: Step) -> str:
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


def _compile_artifact(record: ArtifactInventoryRecord, *, artifact_id: ArtifactId) -> ArtifactSpec:
    return ArtifactSpec(
        id=artifact_id,
        name=record.name,
        template=record.artifact.template,
        kind=record.artifact.kind,
        schema=record.artifact.schema,
        required=record.artifact.required,
        owner_step=record.artifact.owner_step,
        workflow_level=record.workflow_level,
        producer_steps=record.producer_steps,
    )


def _compile_artifacts(inventory: dict[str, ArtifactInventoryRecord]) -> dict[ArtifactId, ArtifactSpec]:
    return {
        _artifact_id_from_record(record): _compile_artifact(
            record,
            artifact_id=_artifact_id_from_record(record),
        )
        for record in inventory.values()
    }


def _compile_public_artifacts(inventory: dict[str, ArtifactInventoryRecord]) -> dict[str, ArtifactId]:
    return {
        name: _artifact_id_from_record(record)
        for name, record in public_artifact_inventory(inventory).items()
    }


def _compile_artifacts_by_qualified_name(
    inventory: dict[str, ArtifactInventoryRecord],
) -> dict[str, ArtifactId]:
    return {
        name: _artifact_id_from_record(record)
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
) -> ArtifactId | ExternalRead | FanInRead:
    helper_path = _fan_in_helper_runtime_path(reference, step=step)
    if helper_path is not None:
        return helper_path
    try:
        return _artifact_id_from_record(resolve_artifact_reference(reference, inventory))
    except WorkflowValidationError as exc:
        if not isinstance(reference, str) or not str(exc).startswith("unknown artifact reference "):
            raise
    if isinstance(reference, Path):
        return ExternalRead(reference)
    if isinstance(reference, str):
        return ExternalRead(reference)
    raise WorkflowCompilationError(f"unsupported read reference {reference!r}")


def _compile_required_reference(
    reference: object,
    inventory: dict[str, ArtifactInventoryRecord],
    *,
    step: Step | None = None,
) -> ArtifactId | FanInRead:
    helper_path = _fan_in_helper_runtime_path(reference, step=step)
    if helper_path is not None:
        return helper_path
    return _artifact_id_from_record(resolve_artifact_reference(
        reference,
        inventory,
        step_name=None if step is None else step.name,
        prefer_step_local=step is not None,
    ))


def _fan_in_helper_runtime_path(reference: object, *, step: Step | None) -> FanInRead | None:
    if not isinstance(reference, FanInHelperReference):
        return None
    group_name = getattr(step, "_branch_group_name", None) if step is not None else None
    if not isinstance(group_name, str) or not group_name:
        raise WorkflowCompilationError(f"{reference} requires an internal fan-in step with a branch-group owner")
    filename = "results.json" if reference.helper == "results" else "context.md"
    return FanInRead(helper=reference.helper, path=f"_branch_groups/{group_name}/{filename}")


def _compile_scope_name(scope: object | None) -> str | None:
    if scope is None:
        return None
    if isinstance(scope, str):
        return scope
    name = getattr(scope, "name", None)
    if isinstance(name, str) and name:
        return name
    raise WorkflowCompilationError("scoped steps require a named worklist")


def _artifact_id_from_record(record: ArtifactInventoryRecord) -> ArtifactId:
    if record.workflow_level:
        return ArtifactId(namespace="workflow", name=record.name)
    if record.owner_step is None:
        raise WorkflowCompilationError(f"artifact {record.qualified_name!r} is missing owner_step metadata")
    return ArtifactId(namespace="step", step=record.owner_step, name=record.name)


def _step_source(step: Step) -> StepSource:
    return StepSource(
        authoring_kind=type(step).__name__,
        declaration_name=step.name,
        source_module=type(step).__module__,
        source_qualname=type(step).__qualname__,
    )


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


def _topology_hash_payload(compiled: WorkflowPlan) -> dict[str, Any]:
    definition = get_workflow_definition(compiled.workflow_cls)
    steps_by_name = {step.name: step for step in definition.steps}
    return {
        "workflow_name": compiled.workflow_name,
        "entry_step_name": compiled.entry_step_name,
        "global_session": compiled.default_session_name,
        "workflow_policy_fingerprint": _policy_input_fingerprint(compiled.provider_policy),
        "steps": [
            _topology_hash_step_payload(
                compiled,
                step,
                authored_step=steps_by_name.get(step.name),
            )
            for step in compiled.steps.values()
        ],
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


def _topology_hash_step_payload(
    compiled: WorkflowPlan,
    step: StepPlan,
    *,
    authored_step: Step | None,
) -> dict[str, Any]:
    step_routes = compiled.routes.get(step.name, {})
    available_routes = available_route_tags(compiled, step.name)
    definition = get_workflow_definition(compiled.workflow_cls)
    payload = {
        "name": step.name,
        "kind": step.kind,
        "scope_name": step.scope_name,
        "reads": [_topology_json_value(value) for value in step.reads],
        "requires": [_topology_json_value(value) for value in step.requires],
        "writes": [_topology_json_value(value) for value in step.writes],
        "producer_reads": [_topology_json_value(value) for value in step.producer_reads],
        "producer_requires": [_topology_json_value(value) for value in step.producer_requires],
        "producer_writes": [_topology_json_value(value) for value in step.producer_writes],
        "verifier_reads": [_topology_json_value(value) for value in step.verifier_reads],
        "verifier_requires": [_topology_json_value(value) for value in step.verifier_requires],
        "verifier_writes": [_topology_json_value(value) for value in step.verifier_writes],
        "available_routes": list(available_routes),
        "authored_routes": list(step_authored_route_tags(definition, authored_step) if authored_step is not None else ()),
        "runtime_control_routes": list(runtime_control_route_tags(compiled, step.name)),
        "provider_visible_routes_interactive": list(provider_visible_route_tags(compiled, step.name, mode="interactive")),
        "provider_visible_routes_full_auto": list(provider_visible_route_tags(compiled, step.name, mode="full_auto")),
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
            for reference in compiled.reference_graph.prompt_refs.get(step.name, ())
        ],
    }
    if step_routes:
        payload["route_table"] = {
            tag: _topology_hash_route_payload(
                None,
                step_name=step.name,
                route_tag=tag,
                route=route,
                expected_output_schema=step.expected_output_schema,
                use_effective_required_writes=False,
            )
            for tag, route in step_routes.items()
        }
    if step.branch_group is not None:
        payload["branch_group"] = _topology_hash_branch_group_payload(step.branch_group)
    return payload


def _topology_hash_route_payload(
    compiled: WorkflowPlan | None,
    *,
    step_name: str | None,
    route_tag: str,
    route: RouteContract,
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
            "required_writes": list(artifact_id.qualified_name for artifact_id in route.required_writes.declared),
            "explicit_required_writes": (
                list(artifact_id.qualified_name for artifact_id in route.required_writes.explicit)
                if route.required_writes.explicit is not None
                else None
            ),
            "effective_required_writes": None,
        }
    return {
        "target": route_target_value(route.target),
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
                "step": {
                    "name": branch.step.name,
                    "kind": branch.step.kind,
                },
            }
            for branch in spec.branches
        ],
        "fan_in_step": None
        if spec.fan_in_step is None
        else {
            "name": spec.fan_in_step.name,
            "kind": spec.fan_in_step.kind,
        },
    }


def _with_topology_hash(compiled: WorkflowPlan) -> WorkflowPlan:
    payload = _topology_hash_payload(compiled)
    topology_hash = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=_topology_json_value,
        ).encode("utf-8")
    ).hexdigest()
    return replace(compiled, topology_hash=topology_hash)


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
