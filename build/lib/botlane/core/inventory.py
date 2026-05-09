"""Artifact inventory ownership for workflow discovery and compilation."""

from __future__ import annotations

from dataclasses import dataclass, field
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


@dataclass(slots=True)
class MutableArtifactRecord:
    artifact: Artifact
    name: str
    qualified_name: str
    owner_step: str | None
    workflow_level: bool = False
    producer_steps: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _ArtifactBinding:
    artifact_id: int
    name: str
    qualified_name: str
    allow_producer_rebind: bool


def collect_artifact_inventory(definition: Any) -> dict[str, ArtifactInventoryRecord]:
    """Collect artifact registry metadata keyed by canonical reference."""

    builder = _ArtifactInventoryBuilder(definition)

    for attr_name, artifact in definition.workflow_artifacts.items():
        builder.register_workflow_artifact(attr_name, artifact)
    for index, artifact in enumerate(definition.workflow_log_artifacts, start=1):
        builder.register_log_artifact(f"workflow__log_{index}", artifact)
    for step in definition.steps:
        for nested_step in _iter_inventory_steps(step):
            for write_name, artifact in nested_step.writes.items():
                builder.register_step_artifact(nested_step.name, write_name, artifact)
            for index, artifact in enumerate(nested_step.reads, start=1):
                if isinstance(artifact, Artifact):
                    builder.register_reference_artifact(f"{nested_step.name}__read_{index}", artifact)
            for index, artifact in enumerate(nested_step.requires, start=1):
                if isinstance(artifact, Artifact):
                    builder.register_reference_artifact(f"{nested_step.name}__require_{index}", artifact)
            for index, artifact in enumerate(nested_step.log_artifacts, start=1):
                builder.register_log_artifact(f"{nested_step.name}__log_{index}", artifact)

    return builder.build()


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


class _ArtifactInventoryBuilder:
    def __init__(self, definition: Any) -> None:
        self._definition = definition
        self._workflow_level_names_to_identity: dict[str, int] = {}
        self._qualified_names_to_identity: dict[str, int] = {}
        self._records_by_identity: dict[int, MutableArtifactRecord] = {}
        all_steps = tuple(nested_step for step in definition.steps for nested_step in _iter_inventory_steps(step))
        self._steps_by_name = {step.name: step for step in all_steps}

    def register_workflow_artifact(self, name: str, artifact: Artifact) -> None:
        self._register(artifact, fallback_name=name, workflow_level=True)

    def register_step_artifact(self, step_name: str, name: str, artifact: Artifact) -> None:
        self._register(artifact, fallback_name=name, producer_step=step_name)

    def register_reference_artifact(self, fallback_name: str, artifact: Artifact) -> None:
        self._register(artifact, fallback_name=fallback_name)

    def register_log_artifact(self, fallback_name: str, artifact: Artifact) -> None:
        self._register(artifact, fallback_name=fallback_name)

    def build(self) -> dict[str, ArtifactInventoryRecord]:
        return {
            record.qualified_name: ArtifactInventoryRecord(
                artifact=record.artifact,
                name=record.name,
                qualified_name=record.qualified_name,
                owner_step=record.owner_step,
                workflow_level=record.workflow_level,
                producer_steps=tuple(record.producer_steps),
            )
            for record in self._records_by_identity.values()
        }

    def _register(
        self,
        artifact: Artifact,
        *,
        fallback_name: str,
        workflow_level: bool = False,
        producer_step: str | None = None,
    ) -> None:
        binding = self._bind_artifact_identity(
            artifact,
            fallback_name=fallback_name,
            workflow_level=workflow_level,
            producer_step=producer_step,
        )
        if binding.allow_producer_rebind:
            self._drop_rebound_qualified_name(binding.artifact_id, binding.qualified_name)
        self._check_workflow_name_conflict(
            artifact=artifact,
            artifact_id=binding.artifact_id,
            name=binding.name,
            qualified_name=binding.qualified_name,
            workflow_level=workflow_level,
            producer_step=producer_step,
        )
        if self._check_qualified_name_conflict(
            artifact=artifact,
            artifact_id=binding.artifact_id,
            qualified_name=binding.qualified_name,
            producer_step=producer_step,
        ):
            return
        self._qualified_names_to_identity[binding.qualified_name] = binding.artifact_id
        record = self._upsert_record(
            artifact=artifact,
            artifact_id=binding.artifact_id,
            name=binding.name,
            qualified_name=binding.qualified_name,
            allow_producer_rebind=binding.allow_producer_rebind,
        )
        if workflow_level:
            record.workflow_level = True
        self._record_producer_step(record, producer_step)

    def _bind_artifact_identity(
        self,
        artifact: Artifact,
        *,
        fallback_name: str,
        workflow_level: bool,
        producer_step: str | None,
    ) -> _ArtifactBinding:
        if artifact.name is None:
            artifact.bind_name(fallback_name)
        artifact_id = id(artifact)
        name = artifact.name or fallback_name
        self._check_reserved_name(name)
        existing_record = self._records_by_identity.get(artifact_id)
        workflow_level_declared = bool(existing_record and existing_record.workflow_level)
        allow_producer_rebind = bool(
            existing_record
            and not workflow_level_declared
            and not existing_record.producer_steps
            and existing_record.owner_step is None
            and producer_step is not None
        )

        if workflow_level or workflow_level_declared:
            artifact.owner_step = None
            artifact.owner = None
            artifact.qualified_name = name
        elif producer_step is not None and artifact.owner_step is None:
            artifact.bind_owner_step(producer_step)
            artifact.owner = self._steps_by_name[producer_step]
        elif artifact.qualified_name is None:
            artifact.qualified_name = name

        return _ArtifactBinding(
            artifact_id=artifact_id,
            name=name,
            qualified_name=artifact.qualified_name or name,
            allow_producer_rebind=allow_producer_rebind,
        )

    def _check_reserved_name(self, name: str) -> None:
        if name in self._definition.reserved_step_pseudo_fields:
            raise WorkflowValidationError(
                f"artifact name {name!r} is reserved because it collides with prompt pseudo-fields"
            )

    def _drop_rebound_qualified_name(self, artifact_id: int, qualified_name: str) -> None:
        existing_record = self._records_by_identity.get(artifact_id)
        if existing_record is None or existing_record.qualified_name == qualified_name:
            return
        old_qualified_name = existing_record.qualified_name
        if self._qualified_names_to_identity.get(old_qualified_name) == artifact_id:
            del self._qualified_names_to_identity[old_qualified_name]

    def _check_workflow_name_conflict(
        self,
        *,
        artifact: Artifact,
        artifact_id: int,
        name: str,
        qualified_name: str,
        workflow_level: bool,
        producer_step: str | None,
    ) -> None:
        if workflow_level:
            existing_identity = self._workflow_level_names_to_identity.get(name)
            if existing_identity is not None and existing_identity != artifact_id:
                if producer_step is None:
                    raise WorkflowValidationError(f"duplicate artifact name {name!r}")
                _raise_workflow_level_artifact_conflict_error(
                    artifact_name=name,
                    workflow_level_record=self._records_by_identity.get(existing_identity),
                    conflicting_artifact=artifact,
                    conflicting_qualified_name=qualified_name,
                    producer_step=producer_step,
                )
            self._workflow_level_names_to_identity[name] = artifact_id
            return
        if producer_step is None:
            return
        existing_identity = self._workflow_level_names_to_identity.get(name)
        if existing_identity is not None and existing_identity != artifact_id:
            _raise_workflow_level_artifact_conflict_error(
                artifact_name=name,
                workflow_level_record=self._records_by_identity.get(existing_identity),
                conflicting_artifact=artifact,
                conflicting_qualified_name=qualified_name,
                producer_step=producer_step,
            )

    def _check_qualified_name_conflict(
        self,
        *,
        artifact: Artifact,
        artifact_id: int,
        qualified_name: str,
        producer_step: str | None,
    ) -> bool:
        existing_identity = self._qualified_names_to_identity.get(qualified_name)
        if existing_identity is None or existing_identity == artifact_id:
            return False
        existing_record = self._records_by_identity.get(existing_identity)
        if (
            existing_record is not None
            and existing_record.owner_step == artifact.owner_step
            and _artifacts_equivalent(existing_record.artifact, artifact)
        ):
            self._record_producer_step(existing_record, producer_step)
            return True
        _raise_duplicate_qualified_artifact_name_error(
            qualified_name=qualified_name,
            existing_record=existing_record,
            conflicting_artifact=artifact,
        )

    def _upsert_record(
        self,
        *,
        artifact: Artifact,
        artifact_id: int,
        name: str,
        qualified_name: str,
        allow_producer_rebind: bool,
    ) -> MutableArtifactRecord:
        record = self._records_by_identity.setdefault(
            artifact_id,
            MutableArtifactRecord(
                artifact=artifact,
                name=name,
                qualified_name=qualified_name,
                owner_step=artifact.owner_step,
            ),
        )
        if record.name != name:
            raise WorkflowValidationError(f"artifact name drift detected for {artifact!r}")
        if record.qualified_name != qualified_name:
            if allow_producer_rebind:
                record.qualified_name = qualified_name
                record.owner_step = artifact.owner_step
            else:
                raise WorkflowValidationError(f"artifact qualified-name drift detected for {artifact!r}")
        if record.owner_step != artifact.owner_step:
            if allow_producer_rebind:
                record.owner_step = artifact.owner_step
            else:
                raise WorkflowValidationError(f"artifact owner-step drift detected for {artifact!r}")
        return record

    def _record_producer_step(self, record: MutableArtifactRecord, producer_step: str | None) -> None:
        if producer_step is not None and producer_step not in record.producer_steps:
            record.producer_steps.append(producer_step)

def _raise_workflow_level_artifact_conflict_error(
    *,
    artifact_name: str,
    workflow_level_record: MutableArtifactRecord | None,
    conflicting_artifact: Artifact,
    conflicting_qualified_name: str,
    producer_step: str | None,
) -> None:
    if workflow_level_record is None:
        raise WorkflowValidationError(f"duplicate artifact name {artifact_name!r}")
    workflow_artifact = workflow_level_record.artifact
    workflow_qualified_name = workflow_level_record.qualified_name or artifact_name
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
    existing_record: MutableArtifactRecord | None,
    conflicting_artifact: Artifact,
) -> None:
    if existing_record is None:
        raise WorkflowValidationError(f"duplicate qualified artifact name {qualified_name!r}")
    raise WorkflowValidationError(
        f"artifact qualified name {qualified_name!r} is declared by multiple artifact objects; existing "
        f"declaration uses {_artifact_signature(existing_record.artifact)}, while the conflicting declaration "
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
