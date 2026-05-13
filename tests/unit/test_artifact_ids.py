from __future__ import annotations

import botpipe.simple as simple
import pytest

from botpipe.core.artifact_plan import ArtifactSpec
from botpipe.core.compiler import compile_workflow
from botpipe.core.identifiers import ArtifactId
from botpipe.core.step_plans import ExternalRead, FanInRead


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


def test_compiler_keeps_dotted_artifact_names_without_dot_splitting() -> None:
    class ArtifactWorkflow(simple.Workflow):
        prepare = simple.step(
            "Prepare the artifact.",
            name="prepare",
            reads=["notes.txt"],
            writes=[simple.Json("result.v2.json")],
        )

    compiled = compile_workflow(ArtifactWorkflow)
    step_id = ArtifactId("step", name="result.v2.json", step="prepare")

    assert step_id in compiled.artifacts
    assert compiled.artifacts_by_qualified_name["prepare.result.v2.json"] == step_id
    assert compiled.steps["prepare"].writes == (step_id,)
    assert isinstance(compiled.steps["prepare"].reads[0], ExternalRead)
    assert compiled.steps["prepare"].requires == ()


def test_artifact_spec_uses_explicit_artifact_ids() -> None:
    artifact_id = ArtifactId("step", name="result.v2.json", step="draft")
    spec = ArtifactSpec(
        id=artifact_id,
        name="result.v2.json",
        template="draft/result.v2.json",
        kind="json",
        schema=None,
        required=True,
        owner_step="draft",
        workflow_level=False,
        producer_steps=("draft",),
    )

    assert spec.id is artifact_id
    assert spec.name == "result.v2.json"
    assert spec.qualified_name == "draft.result.v2.json"


def test_step_io_reference_types_use_artifact_ids_and_fan_in_helpers() -> None:
    class FanInWorkflow(simple.Workflow):
        review = simple.parallel(
            branches={"security": simple.step("Review.", name="security_review", session=simple.Session.fresh())},
            fan_in=simple.step(
                "Summarize {{ fan_in.context_text }}.",
                name="combine_reviews",
                reads=[simple.FanIn.results()],
                requires=[simple.FanIn.context()],
            ),
        )

    compiled = compile_workflow(FanInWorkflow)
    fan_in_step = compiled.steps["review"].branch_group.fan_in_step

    assert isinstance(fan_in_step.reads[0], FanInRead)
    assert isinstance(fan_in_step.requires[0], FanInRead)
