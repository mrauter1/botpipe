"""Internal compiled-plan adapters.

Not part of the public botlane authoring API.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypeAlias, cast

from .branch_groups.models import CompiledBranchGroupSpec, CompiledBranchStepSpec
from .compiler import CompiledArtifact, CompiledRoute, CompiledStep, CompiledWorkflow
from .identifiers import ArtifactId
from .inventory import ArtifactInventoryRecord, resolve_artifact_reference
from .primitives import AWAIT_INPUT, FAIL, FINISH, GLOBAL
from .providers.retries import ProviderRetryPolicy
from .route_contracts import (
    PayloadContract,
    ProviderRoutePolicy,
    RequiredWriteContract,
    RouteContract,
    RouteFieldsContract,
    RouteTarget,
)
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
    ReadRef,
    RequireRef,
    StepHeader,
    StepHookSpec,
    StepIO,
    StepPlan,
    StepStateSpec,
    WriteRef,
)
from .workflow_plan import WorkflowPlan


CompiledInventoryEntry: TypeAlias = CompiledArtifact | ArtifactInventoryRecord


def artifact_id_from_compiled_artifact(
    *,
    key: str,
    artifact: CompiledArtifact,
) -> ArtifactId:
    qualified_name = artifact.qualified_name or key
    if artifact.workflow_level:
        workflow_name = artifact.name
        if workflow_name == qualified_name:
            workflow_name = qualified_name
        return ArtifactId("workflow", name=workflow_name)
    step_name = artifact.owner_step
    if not isinstance(step_name, str) or not step_name.strip():
        raise ValueError("step-scoped compiled artifact requires owner_step")
    step_prefix = f"{step_name}."
    if isinstance(artifact.name, str) and artifact.name and artifact.name != qualified_name:
        artifact_name = artifact.name
    elif qualified_name.startswith(step_prefix):
        artifact_name = qualified_name[len(step_prefix) :]
    else:
        raise ValueError(
            f"step-scoped compiled artifact {qualified_name!r} does not match owner step {step_name!r}"
        )
    return ArtifactId("step", name=artifact_name, step=step_name)


def artifact_id_from_inventory_record(
    *,
    key: str,
    record: ArtifactInventoryRecord,
) -> ArtifactId:
    if record.workflow_level:
        return ArtifactId("workflow", name=record.name)
    if not isinstance(record.owner_step, str) or not record.owner_step.strip():
        raise ValueError(f"step-scoped inventory record {key!r} requires owner_step")
    return ArtifactId("step", name=record.name, step=record.owner_step)


def artifact_id_for_reference(
    reference: object,
    inventory: Mapping[str, ArtifactInventoryRecord],
    *,
    step_name: str | None = None,
    prefer_step_local: bool = False,
) -> ArtifactId:
    resolved = resolve_artifact_reference(
        reference,
        dict(inventory),
        step_name=step_name,
        prefer_step_local=prefer_step_local,
    )
    return artifact_id_from_inventory_record(key=resolved.qualified_name, record=resolved)


def route_contract_from_compiled_route(
    route: CompiledRoute,
    *,
    inventory: Mapping[str, CompiledInventoryEntry] | None = None,
) -> RouteContract:
    if route.required_writes and inventory is None:
        raise ValueError("route required_writes adaptation requires artifact inventory")
    declared = tuple(
        _artifact_id_from_compiled_reference(reference, inventory or {})
        for reference in route.required_writes
    )
    explicit = declared if route._required_writes_explicit else None
    return RouteContract(
        source_step=route.source_step,
        tag=route.tag,
        target=_route_target_from_compiled(route),
        summary=route.summary,
        required_writes=RequiredWriteContract(
            declared=declared,
            explicit=explicit,
            effective=explicit,
        ),
        handoff=route.handoff,
        on_taken=route.on_taken,
        provider=ProviderRoutePolicy(
            visibility=route.provider_visibility,
            visible=route.provider_visible,
            visible_interactive=route.provider_visible_interactive,
            visible_full_auto=route.provider_visible_full_auto,
        ),
        payload=PayloadContract(
            schema_mode=route.payload_schema_mode,
            schema=route.payload_schema,
            validator=route.payload_validator,
        ),
        route_fields=RouteFieldsContract(
            schema=route.route_fields_schema,
            validator=route.route_fields_validator,
        ),
        preset_kind=route.preset_kind,
        inheritance_source=route.inheritance_source,
        disabled=route.disabled,
        is_runtime_control=route.is_runtime_control,
    )


def compiled_route_from_route_contract(contract: RouteContract) -> CompiledRoute:
    declared = tuple(artifact_id.qualified_name for artifact_id in contract.required_writes.declared)
    return CompiledRoute(
        source_step=contract.source_step,
        tag=contract.tag,
        target=_compiled_target_from_route_target(contract.target),
        summary=contract.summary,
        required_writes=declared,
        handoff=contract.handoff,
        on_taken=contract.on_taken,
        provider_visibility=contract.provider.visibility,
        provider_visible=contract.provider.visible,
        provider_visible_interactive=contract.provider.visible_interactive,
        provider_visible_full_auto=contract.provider.visible_full_auto,
        payload_schema_mode=contract.payload.schema_mode,
        payload_schema=contract.payload.schema,
        payload_validator=contract.payload.validator,
        route_fields_schema=contract.route_fields.schema,
        route_fields_validator=contract.route_fields.validator,
        preset_kind=contract.preset_kind,
        inheritance_source=contract.inheritance_source,
        disabled=contract.disabled,
        is_runtime_control=contract.is_runtime_control,
        _required_writes_explicit=contract.required_writes.explicit is not None,
    )


def step_plan_from_compiled_step(*args: Any, **kwargs: Any) -> Any:
    step = cast(CompiledStep, kwargs.pop("step", args[0] if args else None))
    routes = cast(Mapping[str, RouteContract], kwargs.pop("routes"))
    inventory = cast(Mapping[str, CompiledArtifact], kwargs.pop("inventory"))
    if kwargs:
        unexpected = ", ".join(sorted(kwargs))
        raise TypeError(f"unexpected keyword arguments: {unexpected}")
    if step is None:
        raise TypeError("step is required")

    original_step = step.step
    source_reads = _step_source_refs(original_step, "reads")
    source_requires = _step_source_refs(original_step, "requires")
    source_producer_reads = _step_source_refs(original_step, "producer_reads", default=source_reads)
    source_producer_requires = _step_source_refs(original_step, "producer_requires", default=source_requires)
    source_verifier_reads = _step_source_refs(original_step, "verifier_reads", default=source_reads)
    source_verifier_requires = _step_source_refs(original_step, "verifier_requires", default=source_requires)

    header = _step_header_from_compiled_step(step, inventory)
    if step.kind == "step":
        return PromptStepPlan(
            header=header,
            turn=ProviderTurnPlan(
                kind="llm",
                prompt=step.prompt,
                session_name=step.session_name,
                io=_step_io_from_compiled_fields(
                    reads=step.producer_reads,
                    requires=step.producer_requires,
                    writes=step.producer_writes,
                    log_artifacts=step.log_artifacts,
                    inventory=inventory,
                    fallback_reads=source_producer_reads,
                    fallback_requires=source_producer_requires,
                ),
                retry_policy=step.retry_policy,
                expected_output_schema=step.expected_output_schema,
                expected_output_validator=step.expected_output_validator,
            ),
            _compiled_step=step,
        )
    if step.kind == "produce_verify":
        return ProduceVerifyStepPlan(
            header=header,
            producer=ProviderTurnPlan(
                kind="producer",
                prompt=step.producer_prompt,
                session_name=step.session_name,
                io=_step_io_from_compiled_fields(
                    reads=step.producer_reads,
                    requires=step.producer_requires,
                    writes=step.producer_writes,
                    log_artifacts=step.log_artifacts,
                    inventory=inventory,
                    fallback_reads=source_producer_reads,
                    fallback_requires=source_producer_requires,
                ),
                retry_policy=step.retry_policy,
                expected_output_schema=None,
                expected_output_validator=None,
            ),
            verifier=ProviderTurnPlan(
                kind="verifier",
                prompt=step.verifier_prompt,
                session_name=step.verifier_session_name,
                io=_step_io_from_compiled_fields(
                    reads=step.verifier_reads,
                    requires=step.verifier_requires,
                    writes=step.verifier_writes,
                    log_artifacts=step.log_artifacts,
                    inventory=inventory,
                    fallback_reads=source_verifier_reads,
                    fallback_requires=source_verifier_requires,
                ),
                retry_policy=step.retry_policy,
                expected_output_schema=step.expected_output_schema,
                expected_output_validator=step.expected_output_validator,
            ),
            verifier_session_name=step.verifier_session_name,
            _compiled_step=step,
        )
    if step.kind in {"python", "operation"}:
        return PythonStepPlan(
            header=header,
            handler=step.python_handler,
            _compiled_step=step,
        )
    if step.kind == "workflow":
        original_step = step.step
        return ChildWorkflowStepPlan(
            header=header,
            workflow=getattr(original_step, "workflow", None),
            message=getattr(original_step, "message", None),
            message_from=getattr(original_step, "message_from", None),
            params=dict(getattr(original_step, "params", {})),
            input=getattr(original_step, "input", None),
            _compiled_step=step,
        )
    if step.kind == "branch_group":
        branch_group = step.branch_group
        if branch_group is None:
            raise ValueError(f"branch-group compiled step {step.name!r} is missing branch_group metadata")
        return BranchGroupStepPlan(
            header=header,
            branch_group=BranchGroupPlan(
                name=branch_group.name,
                kind=branch_group.kind,
                branches=tuple(
                    BranchPlan(
                        name=branch.name,
                        index=branch.index,
                        input=branch.input,
                        step=step_plan_from_compiled_step(
                            branch.step,
                            routes=_route_contracts_from_compiled_route_table(
                                branch.step.route_table or {},
                                inventory,
                            ),
                            inventory=inventory,
                        ),
                    )
                    for branch in branch_group.branches
                ),
                concurrency=branch_group.concurrency,
                settle=branch_group.settle,
                success_routes=tuple(branch_group.success_routes),
                outcome=branch_group.outcome,
                fan_in_step=(
                    None
                    if branch_group.fan_in_step is None
                    else step_plan_from_compiled_step(
                        branch_group.fan_in_step,
                        routes=_route_contracts_from_compiled_route_table(
                            branch_group.fan_in_step.route_table or {},
                            inventory,
                        ),
                        inventory=inventory,
                    )
                ),
                composite_route_tags=tuple(branch_group.composite_route_tags),
                default_chain_route=branch_group.default_chain_route,
                rework_chain_route=branch_group.rework_chain_route,
            ),
            _compiled_step=step,
        )
    raise ValueError(f"unsupported compiled step kind {step.kind!r}")


def compiled_step_from_step_plan(*args: Any, **kwargs: Any) -> Any:
    plan, routes = _parse_compiled_step_from_step_plan_args(args, kwargs)
    original_compiled = _compiled_step_parity(plan)
    common_kwargs = _compiled_step_common_kwargs(plan, routes, original_compiled=original_compiled)
    return _compiled_step_builder_for_plan(plan)(plan, common_kwargs, original_compiled)


def _parse_compiled_step_from_step_plan_args(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> tuple[StepPlan, Mapping[str, RouteContract]]:
    plan = cast(StepPlan, kwargs.pop("plan", args[0] if args else None))
    routes = cast(Mapping[str, RouteContract], kwargs.pop("routes"))
    if kwargs:
        unexpected = ", ".join(sorted(kwargs))
        raise TypeError(f"unexpected keyword arguments: {unexpected}")
    if plan is None:
        raise TypeError("plan is required")
    return plan, routes


def _compiled_step_common_kwargs(
    plan: StepPlan,
    routes: Mapping[str, RouteContract],
    *,
    original_compiled: CompiledStep | None,
) -> dict[str, Any]:
    header = plan.header
    route_table = {tag: compiled_route_from_route_contract(route) for tag, route in routes.items()}
    return dict(
        name=header.name,
        kind=header.kind,
        step=original_compiled.step if original_compiled is not None else header.original_step,
        session_name=header.session_name,
        scope_name=header.scope_name,
        reads=_compiled_reads_from_step_io(header.io),
        requires=_compiled_requires_from_step_io(header.io),
        writes=_compiled_writes_from_step_io(header.io),
        log_artifacts=_compiled_log_artifacts_from_step_io(header.io),
        available_routes=tuple(tag for tag, route in routes.items() if not route.disabled),
        authored_routes=tuple(
            tag for tag, route in routes.items() if route.inheritance_source != "framework_default"
        ),
        runtime_control_routes=tuple(
            tag for tag, route in routes.items() if not route.disabled and route.is_runtime_control
        ),
        provider_visible_routes_interactive=tuple(
            tag for tag, route in routes.items() if not route.disabled and route.provider.visible_interactive
        ),
        provider_visible_routes_full_auto=tuple(
            tag for tag, route in routes.items() if not route.disabled and route.provider.visible_full_auto
        ),
        before_hook=header.hooks.before,
        after_hook=header.hooks.after,
        before_producer_hook=header.hooks.before_producer,
        after_producer_hook=header.hooks.after_producer,
        before_verifier_hook=header.hooks.before_verifier,
        after_verifier_hook=header.hooks.after_verifier,
        step_state_model=header.state.step_state_model,
        step_state_fields=header.state.step_state_fields,
        step_item_state_model=header.state.step_item_state_model,
        step_item_state_fields=header.state.step_item_state_fields,
        provider_policy=header.provider_policy,
        route_table=route_table,
    )


def _compiled_step_builder_for_plan(
    plan: StepPlan,
) -> Any:
    builder = _COMPILED_STEP_PLAN_BUILDERS.get(type(plan))
    if builder is None:
        raise TypeError(f"unsupported step plan {type(plan)!r}")
    return builder


def _build_prompt_compiled_step(
    plan: PromptStepPlan,
    common_kwargs: dict[str, Any],
    original_compiled: CompiledStep | None,
) -> CompiledStep:
    return CompiledStep(
        **common_kwargs,
        expected_output_schema=plan.turn.expected_output_schema,
        retry_policy=plan.turn.retry_policy,
        prompt=plan.turn.prompt,
        producer_prompt=plan.turn.prompt,
        verifier_prompt=None,
        producer_reads=_producer_reads(original_compiled, plan.turn.io),
        producer_requires=_producer_requires(original_compiled, plan.turn.io),
        producer_writes=_compiled_writes_from_step_io(plan.turn.io),
        verifier_reads=(),
        verifier_requires=(),
        verifier_writes=(),
        verifier_session_name=None,
        expected_output_validator=plan.turn.expected_output_validator,
        python_handler=None,
        branch_group=None,
    )


def _build_produce_verify_compiled_step(
    plan: ProduceVerifyStepPlan,
    common_kwargs: dict[str, Any],
    original_compiled: CompiledStep | None,
) -> CompiledStep:
    return CompiledStep(
        **common_kwargs,
        expected_output_schema=plan.producer.expected_output_schema,
        retry_policy=plan.producer.retry_policy,
        prompt=None,
        producer_prompt=plan.producer.prompt,
        verifier_prompt=plan.verifier.prompt,
        producer_reads=_producer_reads(original_compiled, plan.producer.io),
        producer_requires=_producer_requires(original_compiled, plan.producer.io),
        producer_writes=_compiled_writes_from_step_io(plan.producer.io),
        verifier_reads=_verifier_reads(original_compiled, plan.verifier.io),
        verifier_requires=_verifier_requires(original_compiled, plan.verifier.io),
        verifier_writes=_compiled_writes_from_step_io(plan.verifier.io),
        verifier_session_name=plan.verifier_session_name,
        expected_output_validator=plan.producer.expected_output_validator,
        python_handler=None,
        branch_group=None,
    )


def _build_python_compiled_step(
    plan: PythonStepPlan,
    common_kwargs: dict[str, Any],
    original_compiled: CompiledStep | None,
) -> CompiledStep:
    return CompiledStep(
        **common_kwargs,
        expected_output_schema=None,
        retry_policy=_compiled_retry_policy(original_compiled, default=ProviderRetryPolicy(max_attempts=1)),
        prompt=None,
        producer_prompt=None,
        verifier_prompt=None,
        producer_reads=_producer_reads(original_compiled, plan.header.io),
        producer_requires=_producer_requires(original_compiled, plan.header.io),
        producer_writes=_compiled_writes_from_step_io(plan.header.io),
        verifier_reads=(),
        verifier_requires=(),
        verifier_writes=(),
        verifier_session_name=None,
        expected_output_validator=None,
        python_handler=plan.handler,
        branch_group=None,
    )


def _build_child_workflow_compiled_step(
    plan: ChildWorkflowStepPlan,
    common_kwargs: dict[str, Any],
    original_compiled: CompiledStep | None,
) -> CompiledStep:
    return CompiledStep(
        **common_kwargs,
        expected_output_schema=None,
        retry_policy=_compiled_retry_policy(original_compiled, default=ProviderRetryPolicy(max_attempts=1)),
        prompt=None,
        producer_prompt=None,
        verifier_prompt=None,
        producer_reads=_producer_reads(original_compiled, plan.header.io),
        producer_requires=_producer_requires(original_compiled, plan.header.io),
        producer_writes=_compiled_writes_from_step_io(plan.header.io),
        verifier_reads=(),
        verifier_requires=(),
        verifier_writes=(),
        verifier_session_name=None,
        expected_output_validator=None,
        python_handler=None,
        branch_group=None,
    )


def _build_branch_group_compiled_step(
    plan: BranchGroupStepPlan,
    common_kwargs: dict[str, Any],
    original_compiled: CompiledStep | None,
) -> CompiledStep:
    return CompiledStep(
        **common_kwargs,
        expected_output_schema=None,
        retry_policy=_compiled_retry_policy(original_compiled, default=ProviderRetryPolicy()),
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
        branch_group=_compiled_branch_group_for_plan(plan, original_compiled),
    )


def _compiled_branch_group_for_plan(
    plan: BranchGroupStepPlan,
    original_compiled: CompiledStep | None,
) -> CompiledBranchGroupSpec:
    if original_compiled is not None and original_compiled.branch_group is not None:
        return original_compiled.branch_group
    return _compiled_branch_group_from_plan(plan.branch_group)


def _producer_reads(original_compiled: CompiledStep | None, io: StepIO) -> tuple[str, ...]:
    return (
        original_compiled.producer_reads
        if original_compiled is not None
        else _compiled_reads_from_step_io(io)
    )


def _producer_requires(original_compiled: CompiledStep | None, io: StepIO) -> tuple[str, ...]:
    return (
        original_compiled.producer_requires
        if original_compiled is not None
        else _compiled_requires_from_step_io(io)
    )


def _verifier_reads(original_compiled: CompiledStep | None, io: StepIO) -> tuple[str, ...]:
    return (
        original_compiled.verifier_reads
        if original_compiled is not None
        else _compiled_reads_from_step_io(io)
    )


def _verifier_requires(original_compiled: CompiledStep | None, io: StepIO) -> tuple[str, ...]:
    return (
        original_compiled.verifier_requires
        if original_compiled is not None
        else _compiled_requires_from_step_io(io)
    )


def _compiled_retry_policy(
    original_compiled: CompiledStep | None,
    *,
    default: ProviderRetryPolicy,
) -> ProviderRetryPolicy:
    return original_compiled.retry_policy if original_compiled is not None else default


_COMPILED_STEP_PLAN_BUILDERS = {
    PromptStepPlan: _build_prompt_compiled_step,
    ProduceVerifyStepPlan: _build_produce_verify_compiled_step,
    PythonStepPlan: _build_python_compiled_step,
    ChildWorkflowStepPlan: _build_child_workflow_compiled_step,
    BranchGroupStepPlan: _build_branch_group_compiled_step,
}


def workflow_plan_from_compiled(*args: Any, **kwargs: Any) -> Any:
    compiled = cast(CompiledWorkflow, kwargs.pop("compiled", args[0] if args else None))
    if kwargs:
        unexpected = ", ".join(sorted(kwargs))
        raise TypeError(f"unexpected keyword arguments: {unexpected}")
    if compiled is None:
        raise TypeError("compiled workflow is required")

    inventory = dict(compiled.artifacts_by_qualified_name)
    routes = {
        step_name: _route_contracts_from_compiled_route_table(route_table, inventory)
        for step_name, route_table in compiled.routes.items()
    }
    global_routes = _route_contracts_from_compiled_route_table(compiled.global_routes, inventory)
    return WorkflowPlan(
        workflow_cls=compiled.workflow_cls,
        workflow_name=compiled.workflow_name,
        state_cls=compiled.state_cls,
        input_model=compiled.input_model,
        output_model=compiled.output_model,
        output_builder=compiled.output_builder,
        parameters_cls=compiled.parameters_cls,
        entry_step_name=compiled.entry_step_name,
        sessions=dict(compiled.sessions),
        default_session_name=compiled.default_session_name,
        default_session_open=compiled.default_session_open,
        worklists=dict(compiled.worklists),
        steps={
            step_name: step_plan_from_compiled_step(step, routes=routes[step_name], inventory=inventory)
            for step_name, step in compiled.steps.items()
        },
        routes={step_name: dict(route_table) for step_name, route_table in routes.items()},
        global_routes=dict(global_routes),
        artifacts=dict(compiled.artifacts),
        artifacts_by_id={
            artifact_id_from_compiled_artifact(key=key, artifact=artifact): artifact
            for key, artifact in compiled.artifacts_by_qualified_name.items()
        },
        artifacts_by_qualified_name=dict(compiled.artifacts_by_qualified_name),
        extensions=tuple(compiled.extensions),
        provider_policy=compiled.provider_policy,
        source_hash=compiled.source_hash,
        topology_hash=compiled.topology_hash,
    )


def compiled_workflow_from_plan(*args: Any, **kwargs: Any) -> Any:
    plan = cast(WorkflowPlan, kwargs.pop("plan", args[0] if args else None))
    if kwargs:
        unexpected = ", ".join(sorted(kwargs))
        raise TypeError(f"unexpected keyword arguments: {unexpected}")
    if plan is None:
        raise TypeError("workflow plan is required")

    routes = {
        step_name: {tag: compiled_route_from_route_contract(route) for tag, route in route_table.items()}
        for step_name, route_table in plan.routes.items()
    }
    return CompiledWorkflow(
        workflow_cls=plan.workflow_cls,
        workflow_name=plan.workflow_name,
        state_cls=plan.state_cls,
        input_model=plan.input_model,
        output_model=plan.output_model,
        output_builder=plan.output_builder,
        parameters_cls=plan.parameters_cls,
        entry_step_name=plan.entry_step_name,
        sessions=dict(plan.sessions),
        default_session_name=plan.default_session_name,
        default_session_open=plan.default_session_open,
        worklists=dict(plan.worklists),
        steps={
            step_name: compiled_step_from_step_plan(step_plan, routes=plan.routes.get(step_name, {}))
            for step_name, step_plan in plan.steps.items()
        },
        routes=routes,
        global_routes={tag: compiled_route_from_route_contract(route) for tag, route in plan.global_routes.items()},
        artifacts=dict(plan.artifacts),
        artifacts_by_qualified_name=dict(plan.artifacts_by_qualified_name),
        extensions=tuple(plan.extensions),
        provider_policy=plan.provider_policy,
        source_hash=plan.source_hash,
        topology_hash=plan.topology_hash,
    )


def _route_target_from_compiled(route: CompiledRoute) -> RouteTarget:
    if route.disabled:
        return RouteTarget("disabled")
    if route.target == FINISH:
        return RouteTarget("finish")
    if route.target == AWAIT_INPUT:
        return RouteTarget("await_input")
    if route.target == FAIL:
        return RouteTarget("fail")
    if route.target is None:
        return RouteTarget("disabled")
    return RouteTarget("step", step_name=route.target)


def _compiled_target_from_route_target(target: RouteTarget) -> str | None:
    if target.kind == "step":
        return target.step_name
    if target.kind == "finish":
        return FINISH
    if target.kind == "await_input":
        return AWAIT_INPUT
    if target.kind == "fail":
        return FAIL
    return None


def _artifact_id_from_compiled_reference(
    reference: object,
    inventory: Mapping[str, CompiledInventoryEntry],
) -> ArtifactId:
    if not isinstance(reference, str):
        raise ValueError(f"compiled artifact reference must be a string, got {type(reference)!r}")
    entry = inventory.get(reference)
    if entry is not None:
        return _artifact_id_from_inventory_entry(key=reference, entry=entry)
    first_entry = next(iter(inventory.values()), None)
    if isinstance(first_entry, ArtifactInventoryRecord):
        return artifact_id_for_reference(reference, cast(Mapping[str, ArtifactInventoryRecord], inventory))
    raise ValueError(f"unknown compiled artifact reference {reference!r}")


def _artifact_id_from_inventory_entry(
    *,
    key: str,
    entry: CompiledInventoryEntry,
) -> ArtifactId:
    if isinstance(entry, CompiledArtifact):
        return artifact_id_from_compiled_artifact(key=key, artifact=entry)
    return artifact_id_from_inventory_record(key=key, record=entry)


def _step_header_from_compiled_step(
    step: CompiledStep,
    inventory: Mapping[str, CompiledArtifact],
) -> StepHeader:
    source_reads = _step_source_refs(step.step, "reads")
    source_requires = _step_source_refs(step.step, "requires")
    return StepHeader(
        name=step.name,
        kind=step.kind,
        original_step=step.step,
        session_name=step.session_name,
        scope_name=step.scope_name,
        io=_step_io_from_compiled_fields(
            reads=step.reads,
            requires=step.requires,
            writes=step.writes,
            log_artifacts=step.log_artifacts,
            inventory=inventory,
            fallback_reads=source_reads,
            fallback_requires=source_requires,
        ),
        state=StepStateSpec(
            step_state_model=step.step_state_model,
            step_state_fields=tuple(step.step_state_fields),
            step_item_state_model=step.step_item_state_model,
            step_item_state_fields=tuple(step.step_item_state_fields),
        ),
        hooks=StepHookSpec(
            before=step.before_hook,
            after=step.after_hook,
            before_producer=step.before_producer_hook,
            after_producer=step.after_producer_hook,
            before_verifier=step.before_verifier_hook,
            after_verifier=step.after_verifier_hook,
        ),
        provider_policy=step.provider_policy,
    )


def _compiled_step_parity(plan: StepPlan) -> CompiledStep | None:
    compiled = getattr(plan, "_compiled_step", None)
    return compiled if isinstance(compiled, CompiledStep) else None


def _compiled_branch_group_from_plan(plan: BranchGroupPlan) -> CompiledBranchGroupSpec:
    return CompiledBranchGroupSpec(
        name=plan.name,
        kind=plan.kind,
        branches=tuple(
            CompiledBranchStepSpec(
                name=branch.name,
                index=branch.index,
                input=branch.input,
                step=_compiled_step_from_branch_plan(branch.step),
            )
            for branch in plan.branches
        ),
        concurrency=plan.concurrency,
        settle=plan.settle,
        success_routes=tuple(plan.success_routes),
        outcome=plan.outcome,
        fan_in_step=(
            None
            if plan.fan_in_step is None
            else _compiled_step_from_branch_plan(plan.fan_in_step)
        ),
        composite_route_tags=tuple(plan.composite_route_tags),
        default_chain_route=plan.default_chain_route,
        rework_chain_route=plan.rework_chain_route,
    )


def _compiled_step_from_branch_plan(plan: StepPlan) -> CompiledStep:
    compiled = _compiled_step_parity(plan)
    if compiled is None:
        raise ValueError(
            "branch-group nested compiled-step reconstruction requires adapter parity metadata"
        )
    return compiled


def _step_io_from_compiled_fields(
    *,
    reads: tuple[object, ...],
    requires: tuple[object, ...],
    writes: tuple[object, ...],
    log_artifacts: tuple[object, ...],
    inventory: Mapping[str, CompiledArtifact],
    fallback_reads: tuple[object, ...] = (),
    fallback_requires: tuple[object, ...] = (),
) -> StepIO:
    return StepIO(
        reads=tuple(
            _read_ref_from_compiled(
                value,
                inventory,
                fallback=fallback_reads[index] if index < len(fallback_reads) else None,
            )
            for index, value in enumerate(reads)
        ),
        requires=tuple(
            _require_ref_from_compiled(
                value,
                inventory,
                fallback=fallback_requires[index] if index < len(fallback_requires) else None,
            )
            for index, value in enumerate(requires)
        ),
        writes=tuple(_write_ref_from_compiled(value, inventory) for value in writes),
        log_artifacts=tuple(_write_ref_from_compiled(value, inventory) for value in log_artifacts),
    )


def _step_source_refs(step: object, attr: str, *, default: tuple[object, ...] = ()) -> tuple[object, ...]:
    value = getattr(step, attr, None)
    if value is None:
        return default
    return tuple(cast(Any, value))


def _read_ref_from_compiled(
    value: object,
    inventory: Mapping[str, CompiledArtifact],
    *,
    fallback: object | None = None,
) -> ReadRef:
    fan_in_read = _fan_in_read_from_path(value)
    if fan_in_read is not None:
        return fan_in_read
    if not isinstance(value, str):
        if fallback is not None:
            return _read_ref_from_compiled(fallback, inventory)
        artifact_id = _artifact_id_from_object_reference(value, inventory)
        if artifact_id is not None:
            return artifact_id
        if isinstance(value, Path):
            return ExternalRead(value=value)
        return ExternalRead(value=str(value))
    artifact = inventory.get(value)
    if artifact is not None:
        return artifact_id_from_compiled_artifact(key=value, artifact=artifact)
    if fallback is not None:
        return _read_ref_from_compiled(fallback, inventory)
    return ExternalRead(value=value)


def _require_ref_from_compiled(
    value: object,
    inventory: Mapping[str, CompiledArtifact],
    *,
    fallback: object | None = None,
) -> RequireRef:
    fan_in_read = _fan_in_read_from_path(value)
    if fan_in_read is not None:
        return fan_in_read
    if not isinstance(value, str):
        if fallback is not None:
            return _require_ref_from_compiled(fallback, inventory)
        artifact_id = _artifact_id_from_object_reference(value, inventory)
        if artifact_id is not None:
            return artifact_id
        raise ValueError(f"unknown compiled required reference {value!r}")
    artifact = inventory.get(value)
    if artifact is None and fallback is not None:
        return _require_ref_from_compiled(fallback, inventory)
    if artifact is None:
        raise ValueError(f"unknown compiled required reference {value!r}")
    return artifact_id_from_compiled_artifact(key=value, artifact=artifact)


def _write_ref_from_compiled(value: object, inventory: Mapping[str, CompiledArtifact]) -> WriteRef:
    if not isinstance(value, str):
        artifact_id = _artifact_id_from_object_reference(value, inventory)
        if artifact_id is not None:
            return artifact_id
        raise ValueError(f"unknown compiled write reference {value!r}")
    artifact = inventory.get(value)
    if artifact is None:
        raise ValueError(f"unknown compiled write reference {value!r}")
    return artifact_id_from_compiled_artifact(key=value, artifact=artifact)


def _fan_in_read_from_path(value: object) -> FanInRead | None:
    helper = getattr(value, "helper", None)
    if helper in {"results", "context"}:
        return FanInRead(helper=helper, path=str(value))
    return None


def _artifact_id_from_object_reference(
    value: object,
    inventory: Mapping[str, CompiledArtifact],
) -> ArtifactId | None:
    qualified_name = getattr(value, "qualified_name", None)
    if isinstance(qualified_name, str) and qualified_name in inventory:
        return artifact_id_from_compiled_artifact(key=qualified_name, artifact=inventory[qualified_name])
    name = getattr(value, "name", None)
    if not isinstance(name, str):
        return None
    if name in inventory:
        return artifact_id_from_compiled_artifact(key=name, artifact=inventory[name])
    matches = [key for key, artifact in inventory.items() if artifact.name == name]
    if len(matches) == 1:
        key = matches[0]
        return artifact_id_from_compiled_artifact(key=key, artifact=inventory[key])
    return None


def _compiled_reads_from_step_io(io: StepIO) -> tuple[str, ...]:
    return tuple(_compiled_read_ref(value) for value in io.reads)


def _compiled_requires_from_step_io(io: StepIO) -> tuple[str, ...]:
    return tuple(_compiled_require_ref(value) for value in io.requires)


def _compiled_writes_from_step_io(io: StepIO) -> tuple[str, ...]:
    return tuple(_compiled_write_ref(value) for value in io.writes)


def _compiled_log_artifacts_from_step_io(io: StepIO) -> tuple[str, ...]:
    return tuple(_compiled_write_ref(value) for value in io.log_artifacts)


def _compiled_read_ref(value: ReadRef) -> str:
    if isinstance(value, ArtifactId):
        return value.qualified_name
    if isinstance(value, FanInRead):
        return value.path
    if isinstance(value.value, Path):
        return str(value.value)
    return value.value


def _compiled_require_ref(value: RequireRef) -> str:
    if isinstance(value, ArtifactId):
        return value.qualified_name
    return value.path


def _compiled_write_ref(value: WriteRef) -> str:
    return value.qualified_name


def _route_contracts_from_compiled_route_table(
    route_table: Mapping[str, CompiledRoute],
    inventory: Mapping[str, CompiledArtifact],
) -> dict[str, RouteContract]:
    return {
        tag: route_contract_from_compiled_route(route, inventory=inventory)
        for tag, route in route_table.items()
    }


def _compiled_step_retry_policy(plan: StepPlan) -> ProviderRetryPolicy:
    if isinstance(plan, PromptStepPlan):
        return plan.turn.retry_policy
    if isinstance(plan, ProduceVerifyStepPlan):
        return plan.producer.retry_policy
    if isinstance(plan, BranchGroupStepPlan):
        return ProviderRetryPolicy()
    return ProviderRetryPolicy(max_attempts=1)
