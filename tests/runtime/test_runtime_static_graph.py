from __future__ import annotations

import json
from pathlib import Path

import botpipe.simple as simple
import botpipe.core.route_reporting as route_reporting_helpers
from pydantic import BaseModel

from botpipe import AWAIT_INPUT, FINISH, Md, Prompt, Route, StateVar, Workflow, Worklist, produce_verify_step, python_step, step
from botpipe.core import Artifact, FAIL, GLOBAL, Workflow as CoreWorkflow
from botpipe.core.compiler import compile_workflow
from botpipe.core.outcome_contract import NATIVE_SCHEMA_HAS_OPEN_OBJECT, ProviderOutcomeContract
from botpipe.core.providers.retries import ProviderRetryPolicy
from botpipe.core.steps import PromptStep
from botpipe.runtime.static_graph import (
    ROUTE_TABLE_FILENAME,
    TOPOLOGY_FILENAME,
    write_static_step_graph,
    write_topology_artifacts,
    workflow_static_step_graph_payload,
    workflow_topology_payload,
)
from botpipe.core.schema_registry import WORKFLOW_STATIC_STEP_GRAPH_SCHEMA

STATE_DIRNAME = ".botpipe"


class _AssessmentPayload(BaseModel):
    summary: str


class _RouteReasonPayload(BaseModel):
    reason: str | None = None


class _StaticGraphWorkflow(Workflow):
    name = "static_graph_demo"

    request = Artifact.text("{{ task.folder }}/request.txt", name="request")
    assessment = produce_verify_step(
        producer_prompt=Prompt.file("prompts/assessment_producer.md"),
        verifier_prompt=Prompt.file("prompts/assessment_verifier.md"),
        requires=[request],
        producer_writes=[Artifact.text("{{ run.folder }}/note.txt", name="note")],
        control_schema=_AssessmentPayload,
        routes={"assessment_ready": Route.to("finish", summary="assessment completed")},
    )

    @python_step(name="finish", routes={"done": FINISH})
    def finish(ctx):
        return None


def test_static_step_graph_written_for_run(tmp_path: Path) -> None:
    run_dir = tmp_path / STATE_DIRNAME / "tasks" / "task-1" / "wf_demo" / "runs" / "run-1"
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
    assert assessment["compiled_route_tags"] == ["assessment_ready", "question"]
    assert assessment["suppressed_route_tags"] == []
    assert assessment["runtime_control_routes"] == ["question"]
    assert assessment["provider_visible_routes_interactive"] == ["assessment_ready", "question"]
    assert assessment["provider_visible_routes_full_auto"] == ["assessment_ready"]
    assert assessment["provider_response_contracts"]["interactive"]["schema_delivery_mode"] == "prompt_only"
    assert assessment["provider_response_contracts"]["interactive"]["native_skip_reason"] == NATIVE_SCHEMA_HAS_OPEN_OBJECT
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
    assert assessment["routes"]["question"]["payload_contract"]["mode"] == "inherit"
    assert assessment["routes"]["question"]["route_fields_contract"]["source"] == "route"
    assert assessment["compiled_routes"]["question"]["available"] is True
    assert assessment["has_expected_output_schema"] is True
    assert payload["terminals"] == ["FINISH", "AWAIT_INPUT", "FAIL"]
    assert assessment["runtime_control_hook_locations"] == []
    assert assessment["route_hook_locations"] == []


def test_branch_group_payloads_are_additive_in_static_graph_and_topology(tmp_path: Path) -> None:
    class BranchGroupTopologyWorkflow(Workflow):
        class State(BaseModel):
            pass

        reviews = simple.parallel(
            branches={
                "security": simple.step("Review security.", name="security_review", session=simple.Session.fresh()),
                "cost": simple.step("Review cost.", name="cost_review", session=simple.Session.fresh()),
            },
            fan_in=simple.step(
                "Summarize reviews.",
                name="combine_reviews",
                routes={"approved": FINISH, "needs_revision": "publish"},
            ),
        )
        publish = python_step(routes={"done": FINISH})(lambda ctx: None)

    compiled = compile_workflow(BranchGroupTopologyWorkflow)

    static_payload = workflow_static_step_graph_payload(compiled)
    topology_payload = workflow_topology_payload(compiled)
    write_topology_artifacts(tmp_path, compiled)
    route_table = (tmp_path / ROUTE_TABLE_FILENAME).read_text(encoding="utf-8")
    static_reviews = next(step_payload for step_payload in static_payload["steps"] if step_payload["name"] == "reviews")
    topology_reviews = next(step_payload for step_payload in topology_payload["steps"] if step_payload["name"] == "reviews")

    assert static_reviews["kind"] == "branch_group"
    assert static_reviews["branch_group"]["kind"] == "parallel"
    assert static_reviews["branch_group"]["branch_count"] == 2
    assert static_reviews["branch_group"]["outcome_policy"] == "all_done"
    assert static_reviews["branch_group"]["has_fan_in"] is True
    assert static_reviews["branch_group"]["default_chain_route"] == "done"
    assert static_reviews["branch_group"]["rework_chain_route"] is None
    assert [branch["name"] for branch in static_reviews["branch_group"]["branches"]] == ["security", "cost"]
    assert static_reviews["branch_group"]["branches"][0]["step"]["name"] == "security_review"
    assert static_reviews["branch_group"]["branches"][1]["step"]["name"] == "cost_review"
    assert static_reviews["branch_group"]["fan_in_step"]["name"] == "combine_reviews"
    assert static_reviews["branch_group"]["fan_in_step"]["routes"]["approved"]["target"] == "FINISH"
    assert set(static_payload["transitions"]["steps"]) == {"reviews", "publish"}

    assert topology_reviews["branch_group"]["kind"] == "parallel"
    assert topology_reviews["branch_group"]["outcome_policy"] == "all_done"
    assert topology_reviews["branch_group"]["has_fan_in"] is True
    assert topology_reviews["branch_group"]["default_chain_route"] == "done"
    assert topology_reviews["branch_group"]["rework_chain_route"] is None
    assert topology_reviews["branch_group"]["exposed_routes"] == ["approved", "needs_revision"]
    assert topology_reviews["branch_group"]["branches"][0]["step"]["routes"][0]["tag"] == "done"
    assert topology_reviews["branch_group"]["fan_in_step"]["routes"][0]["tag"] == "approved"
    assert "| security_review |" not in route_table
    assert "| cost_review |" not in route_table
    assert "| combine_reviews |" not in route_table


def test_branch_group_surface_payloads_expose_mechanical_outcome_metadata() -> None:
    class BranchOutcomeSurfaceWorkflow(Workflow):
        class State(BaseModel):
            pass

        reviews = simple.parallel(
            outcome="all_settled",
            branches={
                "security": simple.python_step(lambda ctx: simple.Event("done"), name="security_review"),
                "cost": simple.python_step(lambda ctx: simple.Event("done"), name="cost_review"),
            },
            routes={"done": FINISH, "partial": FINISH},
        )

    compiled = compile_workflow(BranchOutcomeSurfaceWorkflow)

    static_payload = workflow_static_step_graph_payload(compiled)
    topology_payload = workflow_topology_payload(compiled)
    static_reviews = next(step_payload for step_payload in static_payload["steps"] if step_payload["name"] == "reviews")
    topology_reviews = next(step_payload for step_payload in topology_payload["steps"] if step_payload["name"] == "reviews")

    assert static_reviews["branch_group"]["outcome_policy"] == "all_settled"
    assert static_reviews["branch_group"]["has_fan_in"] is False
    assert static_reviews["branch_group"]["default_chain_route"] == "done"
    assert static_reviews["branch_group"]["rework_chain_route"] is None

    assert topology_reviews["branch_group"]["outcome_policy"] == "all_settled"
    assert topology_reviews["branch_group"]["has_fan_in"] is False
    assert topology_reviews["branch_group"]["default_chain_route"] == "done"
    assert topology_reviews["branch_group"]["rework_chain_route"] is None


def test_branch_group_internal_shape_changes_topology_hash() -> None:
    class BranchHashWorkflowA(Workflow):
        name = "branch_hash_demo"

        class State(BaseModel):
            pass

        assess = simple.fan_out(
            step=simple.step("Assess {{ branch.input.area }}.", name="assess_one", session=simple.Session.fresh()),
            branches={"security": {"area": "security"}},
        )

    class BranchHashWorkflowB(Workflow):
        name = "branch_hash_demo"

        class State(BaseModel):
            pass

        assess = simple.fan_out(
            step=simple.step("Assess {{ branch.input.area }}.", name="assess_one", session=simple.Session.fresh()),
            branches={"security": {"area": "performance"}},
        )

    compiled_a = compile_workflow(BranchHashWorkflowA)
    compiled_b = compile_workflow(BranchHashWorkflowB)

    assert compiled_a.workflow_name == compiled_b.workflow_name == "branch_hash_demo"
    assert compiled_a.topology_hash != compiled_b.topology_hash


def test_route_visibility_and_route_schema_changes_change_topology_hash() -> None:
    class VisibilityHashWorkflowA(Workflow):
        name = "route_hash_demo"

        review = step(
            prompt=Prompt.inline("Review the draft."),
            routes={
                "done": FINISH,
                "audit": Route.to(FINISH, provider_visibility="always"),
            },
        )

    class VisibilityHashWorkflowB(Workflow):
        name = "route_hash_demo"

        review = step(
            prompt=Prompt.inline("Review the draft."),
            routes={
                "done": FINISH,
                "audit": Route.to(FINISH, provider_visibility="hidden"),
            },
        )

    class SchemaHashWorkflow(Workflow):
        name = "route_hash_demo"

        review = step(
            prompt=Prompt.inline("Review the draft."),
            routes={
                "done": FINISH,
                "audit": Route.to(
                    FINISH,
                    provider_visibility="always",
                    route_fields_schema=_RouteReasonPayload,
                ),
            },
        )

    compiled_visibility_a = compile_workflow(VisibilityHashWorkflowA)
    compiled_visibility_b = compile_workflow(VisibilityHashWorkflowB)
    compiled_schema = compile_workflow(SchemaHashWorkflow)

    assert compiled_visibility_a.workflow_name == compiled_visibility_b.workflow_name == compiled_schema.workflow_name
    assert compiled_visibility_a.topology_hash != compiled_visibility_b.topology_hash
    assert compiled_visibility_a.topology_hash != compiled_schema.topology_hash


def test_branch_group_payloads_preserve_structured_fan_out_inputs(tmp_path: Path) -> None:
    class BranchInputTopologyWorkflow(Workflow):
        name = "branch_input_topology_demo"

        class State(BaseModel):
            pass

        assess = simple.fan_out(
            step=simple.step("Assess {{ branch.input.area }}.", name="assess_one", session=simple.Session.fresh()),
            branches={
                "security": {
                    "area": "security",
                    "checks": ["deps", "secrets"],
                    "critical": True,
                }
            },
        )

    compiled = compile_workflow(BranchInputTopologyWorkflow)

    static_payload = workflow_static_step_graph_payload(compiled)
    topology_payload = workflow_topology_payload(compiled)
    write_static_step_graph(tmp_path, compiled)
    write_topology_artifacts(tmp_path, compiled)

    static_assess = next(step_payload for step_payload in static_payload["steps"] if step_payload["name"] == "assess")
    topology_assess = next(step_payload for step_payload in topology_payload["steps"] if step_payload["name"] == "assess")
    persisted_static = json.loads((tmp_path / "static_step_graph.json").read_text(encoding="utf-8"))
    persisted_topology = json.loads((tmp_path / TOPOLOGY_FILENAME).read_text(encoding="utf-8"))
    expected_input = {
        "area": "security",
        "checks": ["deps", "secrets"],
        "critical": True,
    }

    assert static_assess["branch_group"]["branches"][0]["input"] == expected_input
    assert topology_assess["branch_group"]["branches"][0]["input"] == expected_input
    assert persisted_static["steps"][0]["branch_group"]["branches"][0]["input"] == expected_input
    assert persisted_topology["steps"][0]["branch_group"]["branches"][0]["input"] == expected_input


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
    assert any(route["tag"] == "question" and route["route_fields_contract"]["source"] == "route" for route in assessment["compiled_routes"])
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

    assert "| publish | done | custom | step_local | FINISH | always | available |" in route_table
    assert "| publish | skip | custom | step_local | FINISH | always | available |" in route_table
    assert "inherit | publish.report |" in route_table
    assert "none (explicit) | - |" in route_table


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

    assert "| publish | human_escalation | custom | step_local | FINISH | hidden | available |" in route_table
    assert "publish -- human_escalation [custom, step_local, hidden] --> FINISH" in mermaid


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
    assert review_topology["route_hook_locations"] == review_topology["runtime_control_hook_locations"]

    write_topology_artifacts(tmp_path, compiled)
    compile_report = (tmp_path / "compile_report.md").read_text(encoding="utf-8")
    route_table = (tmp_path / ROUTE_TABLE_FILENAME).read_text(encoding="utf-8")

    assert "- terminals: `FINISH`, `AWAIT_INPUT`, `FAIL`" in compile_report
    assert "## Step Route Views" in compile_report
    assert (
        "- `review`: compiled=`done`, `human_escalation`, `question`; available=`done`, `human_escalation`, `question`; "
        "suppressed=none; provider_visible_interactive=`done`, `question`; "
        "provider_visible_full_auto=`done`; provider_schema_delivery(interactive/full_auto)=`native`/`native`; "
        "legacy_authored=`done`, `human_escalation`; legacy_runtime_control=`question`"
    ) in compile_report
    assert "## Route Contracts" in compile_report
    assert "## Route Hook Locations" in compile_report
    assert "`review`: before:before_review, after:after_review, on_taken:human_escalation" in compile_report
    assert "| review | human_escalation | custom | step_local | FINISH | hidden | available |" in route_table
    assert "| - | on_hidden_taken |" in route_table


def test_static_graph_and_compile_report_surface_prompt_only_provider_schema_delivery(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fallback_schema = {
        "type": "object",
        "properties": {
            "outcome": {
                "type": "object",
                "properties": {
                    "tag": {"type": "string"},
                    "payload": {"type": "object", "additionalProperties": True},
                    "route_fields": {"type": "object", "additionalProperties": True},
                },
                "required": ["tag", "payload", "route_fields"],
                "additionalProperties": False,
            }
        },
        "required": ["outcome"],
        "additionalProperties": False,
    }

    def _force_prompt_only_contract(*, routes, expected_output_schema, max_chars=12_000):
        return ProviderOutcomeContract(
            prompt_schema=fallback_schema,
            native_schema=None,
            native_skip_reason=NATIVE_SCHEMA_HAS_OPEN_OBJECT,
        )

    monkeypatch.setattr(route_reporting_helpers, "build_provider_outcome_contract", _force_prompt_only_contract)

    compiled = compile_workflow(_StaticGraphWorkflow)

    static_payload = workflow_static_step_graph_payload(compiled)
    assessment = next(step_payload for step_payload in static_payload["steps"] if step_payload["name"] == "assessment")

    assert assessment["provider_response_contracts"]["interactive"]["schema_delivery_mode"] == "prompt_only"
    assert assessment["provider_response_contracts"]["interactive"]["native_skip_reason"] == NATIVE_SCHEMA_HAS_OPEN_OBJECT
    assert assessment["provider_response_contracts"]["interactive"]["schema_fingerprint"] is not None
    assert assessment["provider_response_contracts"]["interactive"]["schema_chars"] > 0
    assert assessment["provider_response_contracts"]["full_auto"]["schema_delivery_mode"] == "prompt_only"

    write_topology_artifacts(tmp_path, compiled)
    compile_report = (tmp_path / "compile_report.md").read_text(encoding="utf-8")

    assert (
        "provider_schema_delivery(interactive/full_auto)="
        "`prompt_only:provider_response_schema_has_open_object`/`prompt_only:provider_response_schema_has_open_object`"
    ) in compile_report


def test_route_table_mermaid_and_compile_report_distinguish_runtime_control_routes(tmp_path: Path) -> None:
    compiled = compile_workflow(_StaticGraphWorkflow)

    write_topology_artifacts(tmp_path, compiled)
    route_table = (tmp_path / ROUTE_TABLE_FILENAME).read_text(encoding="utf-8")
    mermaid = (tmp_path / "topology.mmd").read_text(encoding="utf-8")
    compile_report = (tmp_path / "compile_report.md").read_text(encoding="utf-8")

    assert "| assessment | question | question | framework_default | AWAIT_INPUT | interactive_only | available |" in route_table
    assert "assessment -- question [question, framework_default, interactive_only] --> AWAIT_INPUT" in mermaid
    assert (
        "- `assessment`: compiled=`assessment_ready`, `question`; available=`assessment_ready`, `question`; "
        "suppressed=none; provider_visible_interactive=`assessment_ready`, `question`; "
        "provider_visible_full_auto=`assessment_ready`; provider_schema_delivery(interactive/full_auto)=`prompt_only:provider_response_schema_has_open_object`/`prompt_only:provider_response_schema_has_open_object`; "
        "legacy_authored=`assessment_ready`; legacy_runtime_control=`question`"
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

    assert "| GLOBAL | blocked | custom | global | AWAIT_INPUT | hidden | available |" in route_table
    assert "- routes: `3`" in compile_report
    assert "- hidden routes: `1`" in compile_report
    assert "- suppressed routes: `0`" in compile_report


def test_static_graph_schema_uses_registry_constant() -> None:
    compiled = compile_workflow(_StaticGraphWorkflow)

    payload = workflow_static_step_graph_payload(compiled)

    assert payload["schema"] == WORKFLOW_STATIC_STEP_GRAPH_SCHEMA
