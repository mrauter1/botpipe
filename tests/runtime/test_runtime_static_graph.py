from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from autoloop_v3.core.compiler import compile_workflow
from autoloop_v3.runtime.static_graph import write_static_step_graph, workflow_static_step_graph_payload
from core import Artifact, PairStep, RouteInfo, SUCCESS, SystemStep, Workflow
from core.primitives import Event, Outcome


class _AssessmentPayload(BaseModel):
    summary: str


class _StaticGraphWorkflow(Workflow):
    name = "static_graph_demo"

    class State(BaseModel):
        note: str = ""

    request = Artifact("{task_folder}/request.txt")
    note = Artifact("{run_folder}/note.txt")
    transcript = Artifact("{run_folder}/transcript.log")
    assessment = PairStep(
        name="assessment",
        producer="prompts/assessment_producer.md",
        verifier="prompts/assessment_verifier.md",
        requires=[request],
        produces={"note": note},
        log_artifacts=[transcript],
        expected_output_schema=_AssessmentPayload,
        route_infos={"assessment_ready": RouteInfo(summary="assessment completed")},
    )
    finish = SystemStep(name="finish")
    entry = assessment
    transitions = {
        assessment: {"assessment_ready": finish},
        finish: {"done": SUCCESS},
    }

    @staticmethod
    def on_assessment(state: State, outcome: Outcome, artifacts):
        return state.model_copy(update={"note": outcome.payload.get("summary", "")})

    @staticmethod
    def on_finish(state: State, ctx):
        return state, Event("done")


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
    assert assessment["kind"] == "pair"
    assert assessment["producer_prompt"] == "prompts/assessment_producer.md"
    assert assessment["verifier_prompt"] == "prompts/assessment_verifier.md"
    assert assessment["reads"] == []
    assert assessment["requires"] == ["request"]
    assert assessment["produces"] == ["assessment.note"]
    assert assessment["log_artifacts"] == ["transcript"]
    assert "assessment_ready" in assessment["available_routes"]
    assert finish["producer_prompt"] is None
    assert finish["verifier_prompt"] is None


def test_static_step_graph_includes_route_infos_and_schema_presence(tmp_path: Path) -> None:
    compiled = compile_workflow(_StaticGraphWorkflow)
    write_static_step_graph(tmp_path, compiled)

    payload = json.loads((tmp_path / "static_step_graph.json").read_text(encoding="utf-8"))
    assessment = next(step for step in payload["steps"] if step["name"] == "assessment")

    assert assessment["route_infos"]["assessment_ready"]["summary"] == "assessment completed"
    assert assessment["route_required_outputs"]["assessment_ready"] == []
    assert assessment["route_infos"]["assessment_ready"]["summary"] == "assessment completed"
    assert assessment["has_expected_output_schema"] is True
    assert payload["transitions"]["steps"]["assessment"]["assessment_ready"] == "finish"
    assert payload["transitions"]["steps"]["finish"]["done"] == "SUCCESS"
    assert payload["transitions"]["global"] == {}
