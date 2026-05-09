from __future__ import annotations

import pytest

from botlane.core.artifacts import Artifact, CompiledArtifact
from botlane.core.identifiers import ArtifactId
from botlane.core.inventory import ArtifactInventoryRecord
from botlane.core.plan_adapters import (
    artifact_id_for_reference,
    artifact_id_from_compiled_artifact,
    artifact_id_from_inventory_record,
)


def _inventory_record(
    *,
    name: str,
    qualified_name: str,
    owner_step: str | None,
    workflow_level: bool,
) -> ArtifactInventoryRecord:
    artifact = Artifact(
        f"{qualified_name}.txt",
        name=name,
        kind="text",
        owner_step=owner_step,
        qualified_name=qualified_name,
    )
    return ArtifactInventoryRecord(
        artifact=artifact,
        name=name,
        qualified_name=qualified_name,
        owner_step=owner_step,
        workflow_level=workflow_level,
        producer_steps=() if owner_step is None else (owner_step,),
    )


def test_artifact_id_accepts_workflow_and_step_variants() -> None:
    workflow = ArtifactId("workflow", name="report")
    step = ArtifactId("step", name="result.json", step="draft")

    assert workflow.qualified_name == "report"
    assert workflow.display == "report"
    assert step.qualified_name == "draft.result.json"
    assert step.display == "draft.result.json"


def test_artifact_id_validates_namespace_invariants() -> None:
    with pytest.raises(ValueError, match="step ArtifactId requires step"):
        ArtifactId("step", name="report")

    with pytest.raises(ValueError, match="workflow ArtifactId must not include step"):
        ArtifactId("workflow", name="report", step="draft")

    with pytest.raises(ValueError, match="ArtifactId.name must be non-empty"):
        ArtifactId("workflow", name=" ")


def test_artifact_id_adapters_preserve_dotted_step_artifact_names() -> None:
    record = _inventory_record(
        name="result.v2.json",
        qualified_name="draft.result.v2.json",
        owner_step="draft",
        workflow_level=False,
    )
    compiled = CompiledArtifact(
        name=record.qualified_name,
        template=record.artifact.template,
        kind=record.artifact.kind,
        schema=record.artifact.schema,
        required=record.artifact.required,
        owner_step=record.owner_step,
        qualified_name=record.qualified_name,
        workflow_level=record.workflow_level,
        producer_steps=record.producer_steps,
    )

    expected = ArtifactId("step", name="result.v2.json", step="draft")

    assert artifact_id_from_inventory_record(key=record.qualified_name, record=record) == expected
    assert artifact_id_from_compiled_artifact(key=record.qualified_name, artifact=compiled) == expected


def test_artifact_id_for_reference_uses_inventory_resolution_instead_of_dot_splitting() -> None:
    workflow_record = _inventory_record(
        name="report.v1",
        qualified_name="report.v1",
        owner_step=None,
        workflow_level=True,
    )
    step_record = _inventory_record(
        name="result.v2.json",
        qualified_name="draft.result.v2.json",
        owner_step="draft",
        workflow_level=False,
    )
    inventory = {
        workflow_record.qualified_name: workflow_record,
        step_record.qualified_name: step_record,
    }

    assert artifact_id_for_reference("report.v1", inventory) == ArtifactId("workflow", name="report.v1")
    assert artifact_id_for_reference(
        "result.v2.json",
        inventory,
        step_name="draft",
        prefer_step_local=True,
    ) == ArtifactId("step", name="result.v2.json", step="draft")
