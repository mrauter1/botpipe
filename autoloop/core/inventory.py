"""Artifact inventory ownership for workflow discovery and compilation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .artifacts import Artifact
from .errors import WorkflowValidationError
from .steps import BranchGroupStep, Step


@dataclass(frozen=True, slots=True)
class ArtifactInventoryRecord:
    """Artifact registry candidate."""

    artifact: Artifact
    name: str
    qualified_name: str
    owner_step: str | None
    workflow_level: bool
    producer_steps: tuple[str, ...]


def collect_artifact_inventory(definition: Any) -> dict[str, ArtifactInventoryRecord]:
    """Collect artifact registry metadata keyed by canonical reference."""

    workflow_level_names_to_identity: dict[str, int] = {}
    qualified_names_to_identity: dict[str, int] = {}
    records_by_identity: dict[int, dict[str, Any]] = {}
    all_steps = tuple(nested_step for step in definition.steps for nested_step in _iter_inventory_steps(step))
    steps_by_name = {step.name: step for step in all_steps}

    def register(
        artifact: Artifact,
        *,
        fallback_name: str,
        workflow_level: bool = False,
        producer_step: str | None = None,
    ) -> None:
        if artifact.name is None:
            artifact.bind_name(fallback_name)
        artifact_id = id(artifact)
        name = artifact.name or fallback_name
        if name in definition.reserved_step_pseudo_fields:
            raise WorkflowValidationError(
                f"artifact name {name!r} is reserved because it collides with prompt pseudo-fields"
            )
        existing_record = records_by_identity.get(artifact_id)
        workflow_level_declared = bool(existing_record and existing_record["workflow_level"])
        allow_producer_rebind = bool(
            existing_record
            and not workflow_level_declared
            and not existing_record["producer_steps"]
            and existing_record["owner_step"] is None
            and producer_step is not None
        )

        if workflow_level or workflow_level_declared:
            artifact.owner_step = None
            artifact.owner = None
            artifact.qualified_name = name
        elif producer_step is not None and artifact.owner_step is None:
            artifact.bind_owner_step(producer_step)
            artifact.owner = steps_by_name[producer_step]
        elif artifact.qualified_name is None:
            artifact.qualified_name = name

        qualified_name = artifact.qualified_name or name
        if allow_producer_rebind and existing_record is not None and existing_record["qualified_name"] != qualified_name:
            old_qualified_name = existing_record["qualified_name"]
            if qualified_names_to_identity.get(old_qualified_name) == artifact_id:
                del qualified_names_to_identity[old_qualified_name]
        if workflow_level:
            existing_identity = workflow_level_names_to_identity.get(name)
            if existing_identity is not None and existing_identity != artifact_id:
                if producer_step is None:
                    raise WorkflowValidationError(f"duplicate artifact name {name!r}")
                _raise_workflow_level_artifact_conflict_error(
                    artifact_name=name,
                    workflow_level_record=records_by_identity.get(existing_identity),
                    conflicting_artifact=artifact,
                    conflicting_qualified_name=qualified_name,
                    producer_step=producer_step,
                )
            workflow_level_names_to_identity[name] = artifact_id
        elif producer_step is not None:
            existing_identity = workflow_level_names_to_identity.get(name)
            if existing_identity is not None and existing_identity != artifact_id:
                _raise_workflow_level_artifact_conflict_error(
                    artifact_name=name,
                    workflow_level_record=records_by_identity.get(existing_identity),
                    conflicting_artifact=artifact,
                    conflicting_qualified_name=qualified_name,
                    producer_step=producer_step,
                )
        existing_identity = qualified_names_to_identity.get(qualified_name)
        if existing_identity is not None and existing_identity != artifact_id:
            existing_duplicate = records_by_identity.get(existing_identity)
            if (
                existing_duplicate is not None
                and existing_duplicate.get("owner_step") == artifact.owner_step
                and _artifacts_equivalent(existing_duplicate["artifact"], artifact)
            ):
                if producer_step is not None and producer_step not in existing_duplicate["producer_steps"]:
                    existing_duplicate["producer_steps"].append(producer_step)
                return
            _raise_duplicate_qualified_artifact_name_error(
                qualified_name=qualified_name,
                existing_record=existing_duplicate,
                conflicting_artifact=artifact,
            )
        qualified_names_to_identity[qualified_name] = artifact_id
        record = records_by_identity.setdefault(
            artifact_id,
            {
                "artifact": artifact,
                "name": name,
                "qualified_name": qualified_name,
                "owner_step": artifact.owner_step,
                "workflow_level": False,
                "producer_steps": [],
            },
        )
        if record["name"] != name:
            raise WorkflowValidationError(f"artifact name drift detected for {artifact!r}")
        if record["qualified_name"] != qualified_name:
            if allow_producer_rebind:
                record["qualified_name"] = qualified_name
                record["owner_step"] = artifact.owner_step
            else:
                raise WorkflowValidationError(f"artifact qualified-name drift detected for {artifact!r}")
        if record["owner_step"] != artifact.owner_step:
            if allow_producer_rebind:
                record["owner_step"] = artifact.owner_step
            else:
                raise WorkflowValidationError(f"artifact owner-step drift detected for {artifact!r}")
        if workflow_level:
            record["workflow_level"] = True
        if producer_step is not None and producer_step not in record["producer_steps"]:
            record["producer_steps"].append(producer_step)

    for attr_name, artifact in definition.workflow_artifacts.items():
        register(artifact, fallback_name=attr_name, workflow_level=True)
    for index, artifact in enumerate(definition.workflow_log_artifacts, start=1):
        register(artifact, fallback_name=f"workflow__log_{index}")
    for step in definition.steps:
        for nested_step in _iter_inventory_steps(step):
            for write_name, artifact in nested_step.writes.items():
                register(artifact, fallback_name=write_name, producer_step=nested_step.name)
            for index, artifact in enumerate(nested_step.reads, start=1):
                if isinstance(artifact, Artifact):
                    register(artifact, fallback_name=f"{nested_step.name}__read_{index}")
            for index, artifact in enumerate(nested_step.requires, start=1):
                if isinstance(artifact, Artifact):
                    register(artifact, fallback_name=f"{nested_step.name}__require_{index}")
            for index, artifact in enumerate(nested_step.log_artifacts, start=1):
                register(artifact, fallback_name=f"{nested_step.name}__log_{index}")

    return {
        record["qualified_name"]: ArtifactInventoryRecord(
            artifact=record["artifact"],
            name=record["name"],
            qualified_name=record["qualified_name"],
            owner_step=record["owner_step"],
            workflow_level=record["workflow_level"],
            producer_steps=tuple(record["producer_steps"]),
        )
        for record in records_by_identity.values()
    }


def _iter_inventory_steps(step: Step) -> tuple[Step, ...]:
    if not isinstance(step, BranchGroupStep):
        return (step,)
    branch_group = getattr(step, "branch_group", None)
    nested: list[Step] = [step]
    if branch_group is None:
        return tuple(nested)
    nested.extend(branch.step for branch in getattr(branch_group, "branches", ()))
    fan_in_step = getattr(branch_group, "fan_in_step", None)
    if isinstance(fan_in_step, Step):
        nested.append(fan_in_step)
    return tuple(nested)

def _raise_workflow_level_artifact_conflict_error(
    *,
    artifact_name: str,
    workflow_level_record: dict[str, Any] | None,
    conflicting_artifact: Artifact,
    conflicting_qualified_name: str,
    producer_step: str | None,
) -> None:
    if workflow_level_record is None:
        raise WorkflowValidationError(f"duplicate artifact name {artifact_name!r}")
    workflow_artifact = workflow_level_record["artifact"]
    workflow_qualified_name = workflow_level_record.get("qualified_name", artifact_name)
    producer_suffix = (
        f" step output {conflicting_qualified_name!r} from step {producer_step!r}"
        if producer_step is not None
        else f" declaration {conflicting_qualified_name!r}"
    )
    raise WorkflowValidationError(
        f"artifact {artifact_name!r} is declared by multiple artifact objects with the same public name; "
        f"workflow-level declaration {workflow_qualified_name!r} uses "
        f"{_artifact_signature(workflow_artifact)}, while{producer_suffix} uses "
        f"{_artifact_signature(conflicting_artifact)}. Recommended fix: reuse the same Artifact object when a "
        "workflow-level artifact is intentionally written by steps, or rename one of the declarations."
    )


def _raise_duplicate_qualified_artifact_name_error(
    *,
    qualified_name: str,
    existing_record: dict[str, Any] | None,
    conflicting_artifact: Artifact,
) -> None:
    if existing_record is None:
        raise WorkflowValidationError(f"duplicate qualified artifact name {qualified_name!r}")
    raise WorkflowValidationError(
        f"artifact qualified name {qualified_name!r} is declared by multiple artifact objects; existing "
        f"declaration uses {_artifact_signature(existing_record['artifact'])}, while the conflicting declaration "
        f"uses {_artifact_signature(conflicting_artifact)}. Recommended fix: share one Artifact object for the "
        "same artifact identity or rename one declaration."
    )


def _artifact_signature(artifact: Artifact) -> str:
    parts = [f"template={artifact.template!r}", f"kind={artifact.kind!r}"]
    if artifact.schema is not None:
        schema_name = getattr(artifact.schema, "__name__", type(artifact.schema).__name__)
        parts.append(f"schema={schema_name!r}")
    return ", ".join(parts)


def _artifacts_equivalent(left: Artifact, right: Artifact) -> bool:
    return (
        left.template == right.template
        and left.kind == right.kind
        and left.required == right.required
        and left.name == right.name
        and left.owner_step == right.owner_step
        and left.qualified_name == right.qualified_name
        and left.schema == right.schema
    )


def public_artifact_inventory(inventory: dict[str, ArtifactInventoryRecord]) -> dict[str, ArtifactInventoryRecord]:
    """Return unqualified artifact aliases for globally unambiguous artifacts."""

    grouped: dict[str, list[ArtifactInventoryRecord]] = {}
    for record in inventory.values():
        grouped.setdefault(record.name, []).append(record)
    return {name: records[0] for name, records in grouped.items() if len(records) == 1}


def resolve_artifact_reference(
    reference: Artifact | str,
    inventory: dict[str, ArtifactInventoryRecord],
    *,
    step_name: str | None = None,
    prefer_step_local: bool = False,
) -> ArtifactInventoryRecord:
    """Resolve an artifact reference deterministically against inventory."""

    if isinstance(reference, Artifact):
        if reference.qualified_name:
            record = inventory.get(reference.qualified_name)
            if record is not None:
                return record
        if reference.name is None:
            raise WorkflowValidationError("artifact reference must have a bound name")
        raw_reference = reference.name
    else:
        raw_reference = reference

    if not isinstance(raw_reference, str) or not raw_reference.strip():
        raise WorkflowValidationError("artifact references must be non-empty strings or Artifact declarations")
    raw_reference = raw_reference.strip()

    if "." in raw_reference and raw_reference in inventory:
        return inventory[raw_reference]

    if prefer_step_local and step_name is not None:
        step_local_name = f"{step_name}.{raw_reference}"
        record = inventory.get(step_local_name)
        if record is not None:
            return record

    if raw_reference in inventory:
        return inventory[raw_reference]

    matches = [record for record in inventory.values() if record.name == raw_reference]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise WorkflowValidationError(f"unknown artifact reference {raw_reference!r}")
    candidates = ", ".join(sorted(record.qualified_name for record in matches))
    raise WorkflowValidationError(
        f"ambiguous artifact reference {raw_reference!r}; use one of: {candidates}"
    )


def resolve_optional_read_reference(
    reference: Artifact | str,
    inventory: dict[str, ArtifactInventoryRecord],
) -> str | None:
    """Resolve a declared artifact read when possible, preserving optional path reads."""

    try:
        return resolve_artifact_reference(reference, inventory).qualified_name
    except WorkflowValidationError as exc:
        if isinstance(reference, str) and str(exc).startswith("unknown artifact reference "):
            return None
        raise


__all__ = [
    "ArtifactInventoryRecord",
    "collect_artifact_inventory",
    "public_artifact_inventory",
    "resolve_artifact_reference",
    "resolve_optional_read_reference",
]
