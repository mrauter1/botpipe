"""Internal compiled-plan adapters.

Not part of the public botlane authoring API.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .compiler import CompiledArtifact, CompiledRoute
from .identifiers import ArtifactId
from .inventory import ArtifactInventoryRecord, resolve_artifact_reference
from .primitives import AWAIT_INPUT, FAIL, FINISH, GLOBAL
from .route_contracts import (
    PayloadContract,
    ProviderRoutePolicy,
    RequiredWriteContract,
    RouteContract,
    RouteFieldsContract,
    RouteTarget,
)


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
    inventory: Mapping[str, ArtifactInventoryRecord] | None = None,
) -> RouteContract:
    if route.required_writes and inventory is None:
        raise ValueError("route required_writes adaptation requires artifact inventory")
    source_step = None if route.source_step == GLOBAL else route.source_step
    declared = tuple(
        artifact_id_for_reference(
            reference,
            inventory or {},
            step_name=source_step,
        )
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
    raise NotImplementedError("step-plan adapters land in the workflow-plan phase")


def compiled_step_from_step_plan(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError("step-plan adapters land in the workflow-plan phase")


def workflow_plan_from_compiled(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError("workflow-plan adapters land in the workflow-plan phase")


def compiled_workflow_from_plan(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError("workflow-plan adapters land in the workflow-plan phase")


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
