from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from autoloop import AWAIT_INPUT, FINISH, Md, Prompt, Route, StateVar, Workflow, Worklist, produce_verify_step, python_step, step
from autoloop.core import Artifact, FAIL, GLOBAL, Workflow as CoreWorkflow
from autoloop.core.compiler import compile_workflow
from autoloop.core.providers.retries import ProviderRetryPolicy
from autoloop.core.steps import PromptStep
from autoloop.runtime.static_graph import (
    ROUTE_TABLE_FILENAME,
    TOPOLOGY_FILENAME,
    write_static_step_graph,
    write_topology_artifacts,
    workflow_static_step_graph_payload,
    workflow_topology_payload,
)
from autoloop.core.schema_registry import WORKFLOW_STATIC_STEP_GRAPH_SCHEMA


class _AssessmentPayload(BaseModel):
    summary: str


class _StaticGraphWorkflow(Workflow):
    name = "static_graph_demo"

    request = Artifact.text("{task_folder}/request.txt", name="request")
    assessment = produce_verify_step(
        producer_prompt=Prompt.file("prompts/assessment_producer.md"),
        verifier_prompt=Prompt.file("prompts/assessment_verifier.md"),
        requires=[request],
        producer_writes=[Artifact.text("{run_folder}/note.txt", name="note")],
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
    assert assessment["authored_routes"] == ["assessment_ready"]
    assert assessment["runtime_control_routes"] == ["question", "blocked", "failed"]
    assert assessment["provider_visible_routes_interactive"] == [
        "assessment_ready",
        "question",
        "blocked",
        "failed",
    ]
    assert assessment["provider_visible_routes_full_auto"] == ["assessment_ready", "blocked", "failed"]
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
    assert assessment["routes"]["question"]["is_runtime_control"] is True
    assert assessment["routes"]["question"]["provider_visible_interactive"] is True
    assert assessment["routes"]["question"]["provider_visible_full_auto"] is False
    assert assessment["has_expected_output_schema"] is True
    assert payload["terminals"] == ["FINISH", "AWAIT_INPUT", "FAIL"]
    assert assessment["runtime_control_hook_locations"] == []


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
    assert topology["terminals"] == ["FINISH", "AWAIT_INPUT", "FAIL"]
    assert topology["steps"][1]["routes"][0]["target"] == "FINISH"
    assert topology["steps"][0]["hooks"]["before"] is None
    assert "on_route" not in topology["steps"][0]["hooks"]
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
    assert assessment["routes"][0]["provider_visible"] is True
    assert any(route["tag"] == "question" and route["is_runtime_control"] for route in assessment["routes"])
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

    assert "| publish | done | authored | FINISH | true | true | inherit | publish.report |" in route_table
    assert "| publish | skip | authored | FINISH | true | true | none (explicit) | - |" in route_table


def test_topology_payload_marks_hidden_routes_and_mermaid_route_table_keep_them(tmp_path: Path) -> None:
    class HiddenRouteWorkflow(Workflow):
        publish = step(
            prompt=Prompt.inline("Publish the report."),
            routes={
                "done": FINISH,
                "human_escalation": Route.to(FINISH, provider_visible=False),
            },
        )

    compiled = compile_workflow(HiddenRouteWorkflow)

    payload = workflow_topology_payload(compiled)
    publish = next(step_payload for step_payload in payload["steps"] if step_payload["name"] == "publish")
    hidden = next(route for route in publish["routes"] if route["tag"] == "human_escalation")

    assert hidden["provider_visible"] is False

    write_topology_artifacts(tmp_path, compiled)
    route_table = (tmp_path / ROUTE_TABLE_FILENAME).read_text(encoding="utf-8")
    mermaid = (tmp_path / "topology.mmd").read_text(encoding="utf-8")

    assert "| publish | human_escalation | authored | FINISH | false | false | inherit | - |" in route_table
    assert "publish -- human_escalation [authored, hidden] --> FINISH" in mermaid


def test_topology_artifacts_include_state_surfaces_runtime_control_hook_locations_and_compile_report_details(
    tmp_path: Path,
) -> None:
    class WorkItemState(BaseModel):
        severity: str = "medium"

    def before_review(ctx):
        return None

    def after_review(ctx):
        return None

    def on_hidden_taken(ctx):
        return None

    class RichTopologyWorkflow(Workflow):
        gates = Worklist.from_items(
            "gate",
            items=({"id": "alpha", "title": "Alpha"},),
            item_state=WorkItemState,
        )
        review = step(
            prompt=Prompt.inline("Review the selected gate."),
            scope=gates,
            item_state={"attempts": StateVar(0)},
            before=before_review,
            after=after_review,
            routes={
                "done": FINISH,
                "human_escalation": Route.to(FINISH, provider_visible=False, on_taken=on_hidden_taken),
            },
        )

    compiled = compile_workflow(RichTopologyWorkflow)

    static_payload = workflow_static_step_graph_payload(compiled)
    topology_payload = workflow_topology_payload(compiled)
    review_static = next(step_payload for step_payload in static_payload["steps"] if step_payload["name"] == "review")
    review_topology = next(step_payload for step_payload in topology_payload["steps"] if step_payload["name"] == "review")

    assert static_payload["worklists"]["gate"] == {
        "item_state_model": "GateWorkItemState",
        "item_state_fields": ["last_route", "last_step", "severity", "status"],
        "item_state_runtime_fields": ["status", "last_step", "last_route"],
        "item_state_custom_fields": ["severity"],
        "source_type": "static",
        "source_descriptor": "static",
        "missing_policy": None,
        "materialization_state": "declared",
    }
    assert review_static["step_item_state_fields"] == ["visits", "last_route", "last_reason", "attempts"]
    assert review_topology["step_item_state_surface"] == {
        "model": "ReviewStepItemState",
        "fields": ["visits", "last_route", "last_reason", "attempts"],
        "runtime_fields": ["visits", "last_route", "last_reason"],
        "custom_fields": ["attempts"],
    }
    assert topology_payload["worklists"]["gate"]["materialization_state"] == "declared"
    assert topology_payload["worklists"]["gate"]["source_descriptor"] == "static"
    assert review_topology["runtime_control_hook_locations"] == [
        {"hook": "before", "callable": "before_review"},
        {"hook": "after", "callable": "after_review"},
        {"hook": "on_taken", "callable": "on_hidden_taken", "route": "human_escalation", "source_step": "review"},
    ]

    write_topology_artifacts(tmp_path, compiled)
    compile_report = (tmp_path / "compile_report.md").read_text(encoding="utf-8")
    route_table = (tmp_path / ROUTE_TABLE_FILENAME).read_text(encoding="utf-8")

    assert "- terminals: `FINISH`, `AWAIT_INPUT`, `FAIL`" in compile_report
    assert "## Step Route Views" in compile_report
    assert (
        "- `review`: authored=`done`, `human_escalation`; runtime_control=`question`, `blocked`, `failed`; "
        "provider_visible_interactive=`done`, `question`, `blocked`, `failed`; "
        "provider_visible_full_auto=`done`, `blocked`, `failed`"
    ) in compile_report
    assert "## Runtime-Control Hook Locations" in compile_report
    assert "`review`: before:before_review, after:after_review, on_taken:human_escalation" in compile_report
    assert "| review | human_escalation | authored | FINISH | false | false | inherit | - | - | on_hidden_taken |" in route_table


def test_route_table_mermaid_and_compile_report_distinguish_runtime_control_routes(tmp_path: Path) -> None:
    compiled = compile_workflow(_StaticGraphWorkflow)

    write_topology_artifacts(tmp_path, compiled)
    route_table = (tmp_path / ROUTE_TABLE_FILENAME).read_text(encoding="utf-8")
    mermaid = (tmp_path / "topology.mmd").read_text(encoding="utf-8")
    compile_report = (tmp_path / "compile_report.md").read_text(encoding="utf-8")

    assert "| assessment | question | runtime-control | AWAIT_INPUT | true | false | inherit | - | - | - |" in route_table
    assert "assessment -- question [runtime-control, interactive-only] --> AWAIT_INPUT" in mermaid
    assert (
        "- `assessment`: authored=`assessment_ready`; runtime_control=`question`, `blocked`, `failed`; "
        "provider_visible_interactive=`assessment_ready`, `question`, `blocked`, `failed`; "
        "provider_visible_full_auto=`assessment_ready`, `blocked`, `failed`"
    ) in compile_report


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

    compiled = compile_workflow(ExplicitGlobalRouteWorkflow)

    payload = workflow_topology_payload(compiled)

    assert payload["global_routes"]["failed"]["required_writes"] == ["report"]
    assert payload["global_routes"]["failed"]["explicit_required_writes"] == ["report"]
    assert payload["global_routes"]["failed"]["effective_required_writes"] == ["report"]


def test_route_table_and_compile_report_include_hidden_global_routes(tmp_path: Path) -> None:
    class HiddenGlobalRouteWorkflow(CoreWorkflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {
            ask: {"done": FINISH},
            GLOBAL: {"blocked": Route.to(AWAIT_INPUT, provider_visible=False)},
        }

    compiled = compile_workflow(HiddenGlobalRouteWorkflow)

    payload = workflow_topology_payload(compiled)

    assert payload["global_routes"]["blocked"]["provider_visible"] is False

    write_topology_artifacts(tmp_path, compiled)
    route_table = (tmp_path / ROUTE_TABLE_FILENAME).read_text(encoding="utf-8")
    compile_report = (tmp_path / "compile_report.md").read_text(encoding="utf-8")

    assert "| GLOBAL | blocked | authored | AWAIT_INPUT | false | false | inherit | - | - | - |" in route_table
    assert "- hidden routes: `1`" in compile_report


def test_static_graph_schema_uses_registry_constant() -> None:
    compiled = compile_workflow(_StaticGraphWorkflow)

    payload = workflow_static_step_graph_payload(compiled)

    assert payload["schema"] == WORKFLOW_STATIC_STEP_GRAPH_SCHEMA
