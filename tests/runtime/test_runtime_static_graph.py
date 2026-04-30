from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from autoloop import FINISH, Prompt, Route, Workflow, produce_verify_step, python_step
from core import Artifact
from core.compiler import compile_workflow
from autoloop_v3.runtime.static_graph import (
    TOPOLOGY_FILENAME,
    write_static_step_graph,
    write_topology_artifacts,
    workflow_static_step_graph_payload,
    workflow_topology_payload,
)
from core.schema_registry import WORKFLOW_STATIC_STEP_GRAPH_SCHEMA


class _AssessmentPayload(BaseModel):
    summary: str


class _StaticGraphWorkflow(Workflow):
    name = "static_graph_demo"

    request = Artifact.text("{task_folder}/request.txt", name="request")
    note = Artifact.text("{run_folder}/note.txt", name="note")
    assessment = produce_verify_step(
        producer_prompt=Prompt.file("prompts/assessment_producer.md"),
        verifier_prompt=Prompt.file("prompts/assessment_verifier.md"),
        requires=[request],
        producer_writes=[note],
        control_schema=_AssessmentPayload,
        routes={"assessment_ready": Route.to("finish", summary="assessment completed")},
    )

    @python_step(name="finish", routes={"done": FINISH})
    def finish(ctx):
        return None


def test_static_step_graph_written_for_run(tmp_path: Path) -> None:
    run_dir = tmp_path / ".autoloop" / "tasks" / "task-1" / "wf_demo" / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    compiled = compile_workflow(_StaticGraphWorkflow)

    output_path = write_static_step_graph(run_dir, compiled)

    assert output_path == run_dir / "static_step_graph.json"
    assert output_path.exists()


def test_static_step_graph_includes_step_kind_prompts_routes_and_artifact_names() -> None:
    compiled = compile_workflow(_StaticGraphWorkflow)

    payload = workflow_static_step_graph_payload(compiled)
    assessment = next(step for step in payload["steps"] if step["name"] == "assessment")
    finish = next(step for step in payload["steps"] if step["name"] == "finish")

    assert payload["workflow_name"] == "static_graph_demo"
    assert assessment["kind"] == "produce_verify"
    assert assessment["prompt"] is None
    assert assessment["producer_prompt"] == "prompts/assessment_producer.md"
    assert assessment["verifier_prompt"] == "prompts/assessment_verifier.md"
    assert assessment["reads"] == []
    assert assessment["requires"] == ["request"]
    assert assessment["producer_writes"] == ["assessment.note"]
    assert assessment["writes"] == ["assessment.note"]
    assert assessment["log_artifacts"] == []
    assert "assessment_ready" in assessment["available_routes"]
    assert finish["kind"] == "python"
    assert finish["prompt"] is None
    assert finish["producer_prompt"] is None
    assert finish["verifier_prompt"] is None


def test_static_step_graph_includes_route_metadata_and_schema_presence(tmp_path: Path) -> None:
    compiled = compile_workflow(_StaticGraphWorkflow)
    write_static_step_graph(tmp_path, compiled)

    payload = json.loads((tmp_path / "static_step_graph.json").read_text(encoding="utf-8"))
    assessment = next(step for step in payload["steps"] if step["name"] == "assessment")

    assert assessment["routes"]["assessment_ready"]["summary"] == "assessment completed"
    assert assessment["routes"]["assessment_ready"]["required_writes"] == []
    assert assessment["has_expected_output_schema"] is True


def test_topology_artifacts_are_written_additively_with_canonical_finish_surface(tmp_path: Path) -> None:
    compiled = compile_workflow(_StaticGraphWorkflow)

    outputs = write_topology_artifacts(tmp_path, compiled)
    topology = json.loads((tmp_path / TOPOLOGY_FILENAME).read_text(encoding="utf-8"))

    assert TOPOLOGY_FILENAME in outputs
    assert (tmp_path / "topology.mmd").exists()
    assert (tmp_path / "route_table.md").exists()
    assert (tmp_path / "artifact_contracts.json").exists()
    assert (tmp_path / "prompt_refs.json").exists()
    assert (tmp_path / "state_contracts.json").exists()
    assert (tmp_path / "session_contracts.json").exists()
    assert (tmp_path / "compile_report.md").exists()
    assert topology["entry"] == "assessment"
    assert topology["source_hash"] == compiled.source_hash
    assert topology["topology_hash"] == compiled.topology_hash
    assert topology["terminals"] == ["FINISH", "PAUSE", "FAIL"]
    assert topology["steps"][1]["routes"][0]["target"] == "FINISH"
    assert topology["steps"][0]["hooks"]["before"] is None
    assert topology["steps"][0]["state_model"] is None
    assert topology["steps"][0]["state_fields"] == []


def test_topology_payload_exposes_canonical_writes_and_required_writes() -> None:
    compiled = compile_workflow(_StaticGraphWorkflow)

    payload = workflow_topology_payload(compiled)
    assessment = next(step for step in payload["steps"] if step["name"] == "assessment")
    finish = next(step for step in payload["steps"] if step["name"] == "finish")

    assert assessment["writes"] == ["assessment.note"]
    assert assessment["routes"][0]["required_writes"] == []
    assert finish["routes"][0]["target"] == "FINISH"
    assert payload["source_hash"] == compiled.source_hash
    assert payload["topology_hash"] == compiled.topology_hash


def test_static_graph_schema_uses_registry_constant() -> None:
    compiled = compile_workflow(_StaticGraphWorkflow)

    payload = workflow_static_step_graph_payload(compiled)

    assert payload["schema"] == WORKFLOW_STATIC_STEP_GRAPH_SCHEMA
