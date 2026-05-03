"""Artifact inventory ownership for workflow discovery and compilation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .artifacts import Artifact
from .errors import WorkflowValidationError
from .steps import Step


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
            and not existing_record["producer_steps"]
            and existing_record["owner_step"] is None
            and producer_step is not None
        )

        if producer_step is not None and artifact.owner_step is None and (
            not workflow_level_declared or allow_producer_rebind
        ):
            artifact.bind_owner_step(producer_step)
            artifact.owner = next(step for step in definition.steps if step.name == producer_step)
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
                raise WorkflowValidationError(f"duplicate artifact name {name!r}")
            workflow_level_names_to_identity[name] = artifact_id
        existing_identity = qualified_names_to_identity.get(qualified_name)
        if existing_identity is not None and existing_identity != artifact_id:
            raise WorkflowValidationError(f"duplicate qualified artifact name {qualified_name!r}")
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
        if (
            record["workflow_level"]
            and record["producer_steps"]
            and getattr(record["artifact"], "role", None) != "managed"
        ):
            _raise_dual_role_artifact_error(record)

    for attr_name, artifact in definition.workflow_artifacts.items():
        register(artifact, fallback_name=attr_name, workflow_level=True)
    for index, artifact in enumerate(definition.workflow_log_artifacts, start=1):
        register(artifact, fallback_name=f"workflow__log_{index}")
    for step in definition.steps:
        for write_name, artifact in step.writes.items():
            register(artifact, fallback_name=write_name, producer_step=step.name)
        for index, artifact in enumerate(step.reads, start=1):
            if isinstance(artifact, Artifact):
                register(artifact, fallback_name=f"{step.name}__read_{index}")
        for index, artifact in enumerate(step.requires, start=1):
            if isinstance(artifact, Artifact):
                register(artifact, fallback_name=f"{step.name}__require_{index}")
        for index, artifact in enumerate(step.log_artifacts, start=1):
            register(artifact, fallback_name=f"{step.name}__log_{index}")

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


def _raise_dual_role_artifact_error(record: dict[str, Any]) -> None:
    producer_steps = tuple(record["producer_steps"])
    producers = ", ".join(repr(step_name) for step_name in producer_steps) or "<none>"
    raise WorkflowValidationError(
        f"artifact {record['name']!r} (qualified name {record['qualified_name']!r}) is declared both as a "
        f"workflow-level artifact and as a produced step artifact; workflow-level declaration: workflow class "
        f"attribute {record['name']!r}; producer step names: {producers}. Recommended fix: For external/input "
        f"artifacts: keep as workflow class attribute and remove from step writes. For produced artifacts: keep as "
        f"step writes only and do not assign as workflow class attribute. For managed artifacts: use the explicit "
        f"managed-artifact role once implemented."
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
