from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from autoloop import FINISH, Md, Prompt, Route, Workflow, produce_verify_step, python_step, step
from core import Artifact, FAIL, GLOBAL, Workflow as CoreWorkflow
from core.compiler import compile_workflow
from core.providers.retries import ProviderRetryPolicy
from core.steps import PromptStep
from runtime.static_graph import (
    ROUTE_TABLE_FILENAME,
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
    assert topology["steps"][0]["state_model"] == "ProduceVerifyRuntimeState"
    assert topology["steps"][0]["state_fields"] == [
        "visits",
        "last_route",
        "last_reason",
        "rework_count",
        "replan_count",
    ]


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


def test_topology_payload_and_route_table_preserve_explicit_vs_effective_required_writes(tmp_path: Path) -> None:
    class RequiredWritesWorkflow(Workflow):
        publish = step(
            prompt=Prompt.inline("Publish the report."),
            writes=[Md("report", required=True)],
            routes={
                "done": FINISH,
                "skip": Route.to(FINISH, required_writes=[]),
            },
        )

    compiled = compile_workflow(RequiredWritesWorkflow)

    payload = workflow_topology_payload(compiled)
    publish = next(step_payload for step_payload in payload["steps"] if step_payload["name"] == "publish")
    done = next(route for route in publish["routes"] if route["tag"] == "done")
    skip = next(route for route in publish["routes"] if route["tag"] == "skip")

    assert done["required_writes"] == []
    assert done["explicit_required_writes"] is None
    assert done["effective_required_writes"] == ["publish.report"]
    assert skip["required_writes"] == []
    assert skip["explicit_required_writes"] == []
    assert skip["effective_required_writes"] == []

    write_topology_artifacts(tmp_path, compiled)
    route_table = (tmp_path / ROUTE_TABLE_FILENAME).read_text(encoding="utf-8")

    assert "| publish | done | FINISH | inherit | publish.report |" in route_table
    assert "| publish | skip | FINISH | none (explicit) | - |" in route_table


def test_topology_payload_omits_unbound_effective_set_for_inherited_global_routes() -> None:
    class GlobalRouteWorkflow(CoreWorkflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"report": Artifact.md("report.md", required=True)},
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {
            ask: {"done": FINISH},
            GLOBAL: {"failed": FAIL},
        }

        @staticmethod
        def on_ask(state, outcome, artifacts):
            return state

    compiled = compile_workflow(GlobalRouteWorkflow)

    payload = workflow_topology_payload(compiled)
    ask = next(step_payload for step_payload in payload["steps"] if step_payload["name"] == "ask")
    failed_route = next(route for route in ask["routes"] if route["tag"] == "failed")

    assert failed_route["effective_required_writes"] == ["ask.report"]
    assert payload["global_routes"]["failed"]["required_writes"] == []
    assert payload["global_routes"]["failed"]["explicit_required_writes"] is None
    assert payload["global_routes"]["failed"]["effective_required_writes"] is None


def test_topology_payload_keeps_explicit_global_route_required_writes_concrete() -> None:
    class ExplicitGlobalRouteWorkflow(CoreWorkflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"report": Artifact.md("report.md", required=True)},
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {
            ask: {"done": FINISH},
            GLOBAL: {"failed": Route.to(FAIL, required_writes=("report",))},
        }

        @staticmethod
        def on_ask(state, outcome, artifacts):
            return state

    compiled = compile_workflow(ExplicitGlobalRouteWorkflow)

    payload = workflow_topology_payload(compiled)

    assert payload["global_routes"]["failed"]["required_writes"] == ["report"]
    assert payload["global_routes"]["failed"]["explicit_required_writes"] == ["report"]
    assert payload["global_routes"]["failed"]["effective_required_writes"] == ["report"]


def test_static_graph_schema_uses_registry_constant() -> None:
    compiled = compile_workflow(_StaticGraphWorkflow)

    payload = workflow_static_step_graph_payload(compiled)

    assert payload["schema"] == WORKFLOW_STATIC_STEP_GRAPH_SCHEMA
