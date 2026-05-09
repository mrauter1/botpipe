"""Internal compiled-plan adapters.

Not part of the public botlane authoring API.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .compiler import CompiledArtifact
from .identifiers import ArtifactId
from .inventory import ArtifactInventoryRecord, resolve_artifact_reference


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


def route_contract_from_compiled_route(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError("routing adapters land in the routing phase")


def compiled_route_from_route_contract(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError("routing adapters land in the routing phase")


def step_plan_from_compiled_step(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError("step-plan adapters land in the workflow-plan phase")


def compiled_step_from_step_plan(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError("step-plan adapters land in the workflow-plan phase")


def workflow_plan_from_compiled(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError("workflow-plan adapters land in the workflow-plan phase")


def compiled_workflow_from_plan(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError("workflow-plan adapters land in the workflow-plan phase")
