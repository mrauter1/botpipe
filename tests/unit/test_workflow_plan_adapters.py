from __future__ import annotations

from copy import deepcopy

from pydantic import BaseModel

from botlane import AWAIT_INPUT, FAIL, FINISH, Route
from botlane.core import GLOBAL, Workflow
from botlane.core.artifacts import Artifact
from botlane.core.compiler import compile_workflow, compile_workflow_plan
from botlane.core.plan_adapters import compiled_workflow_from_plan, workflow_plan_from_compiled
from botlane.core.route_contracts import RouteContract
from botlane.core.steps import PromptStep, Session
from botlane.core.workflow_plan import WorkflowPlan


class RoutePayload(BaseModel):
    approved: bool


class _WorkflowPlanParityWorkflow(Workflow):
    class State(BaseModel):
        status: str = "new"

    session_main = Session.run(open=True)
    shared = Artifact("shared.md", name="shared")
    ask = PromptStep(
        name="ask",
        producer="ask.md",
        session=session_main,
        reads=[shared],
        requires=[shared],
        writes={"report": Artifact("{run_folder}/report.md")},
    )
    review = PromptStep(name="review", producer="review.md")
    entry = ask
    transitions = {
        ask: {
            "publish": Route.to(
                review,
                summary="publish the generated report",
                required_writes=("report",),
                handoff="Send the report to the user.",
                provider_visibility="interactive_only",
                payload_schema=RoutePayload,
            ),
            "failed": Route.disabled(),
        },
        review: {"done": FINISH},
        GLOBAL: {"abort": FAIL},
    }


def _route_signature(contract: RouteContract) -> dict[str, object]:
    return {
        "target": (contract.target.kind, contract.target.step_name),
        "visibility": contract.provider.visibility,
        "payload_schema": contract.payload.schema,
        "route_fields_schema": contract.route_fields.schema,
        "handoff": contract.handoff,
        "disabled": contract.disabled,
        "runtime_control": contract.is_runtime_control,
        "required_writes": tuple(artifact_id.qualified_name for artifact_id in contract.required_writes.declared),
    }


def test_compile_workflow_plan_returns_internal_workflow_plan_with_topology_hash_parity() -> None:
    compiled = compile_workflow(_WorkflowPlanParityWorkflow)
    plan = compile_workflow_plan(_WorkflowPlanParityWorkflow)

    assert isinstance(plan, WorkflowPlan)
    assert plan.topology_hash == compiled.topology_hash
    assert plan.workflow_name == compiled.workflow_name
    assert plan.default_session_name == compiled.default_session_name
    assert sorted(plan.sessions) == sorted(compiled.sessions)
    assert plan.worklists == compiled.worklists


def test_workflow_plan_adapter_round_trip_preserves_compiled_workflow_shape() -> None:
    compiled = compile_workflow(_WorkflowPlanParityWorkflow)
    plan = workflow_plan_from_compiled(compiled)
    rebuilt = compiled_workflow_from_plan(plan)

    assert rebuilt == compiled
    assert rebuilt.topology_hash == compiled.topology_hash
    assert plan.artifacts == compiled.artifacts
    assert plan.artifacts_by_qualified_name == compiled.artifacts_by_qualified_name
    assert {artifact_id.qualified_name for artifact_id in plan.artifacts_by_id} == set(
        compiled.artifacts_by_qualified_name
    )


def test_workflow_plan_routes_match_compiled_route_tables_and_globals() -> None:
    compiled = compile_workflow(_WorkflowPlanParityWorkflow)
    plan = workflow_plan_from_compiled(compiled)

    assert tuple(plan.routes["ask"]) == tuple(compiled.routes["ask"])
    assert tuple(plan.global_routes) == tuple(compiled.global_routes)

    for step_name, route_table in compiled.routes.items():
        for tag, compiled_route in route_table.items():
            assert _route_signature(plan.routes[step_name][tag]) == {
                "target": (
                    "disabled"
                    if compiled_route.disabled or compiled_route.target is None
                    else (
                        "finish"
                        if compiled_route.target == FINISH
                        else "await_input"
                        if compiled_route.target == AWAIT_INPUT
                        else "fail" if compiled_route.target == FAIL else "step"
                    ),
                    None
                    if compiled_route.target in {FINISH, AWAIT_INPUT, FAIL, None}
                    else compiled_route.target,
                ),
                "visibility": compiled_route.provider_visibility,
                "payload_schema": compiled_route.payload_schema,
                "route_fields_schema": compiled_route.route_fields_schema,
                "handoff": compiled_route.handoff,
                "disabled": compiled_route.disabled,
                "runtime_control": compiled_route.is_runtime_control,
                "required_writes": compiled_route.required_writes,
            }

    assert _route_signature(plan.global_routes["abort"])["target"] == ("fail", None)


def test_workflow_plan_adapters_copy_maps_instead_of_reusing_mutable_compiled_dicts() -> None:
    compiled = compile_workflow(_WorkflowPlanParityWorkflow)
    original_routes = deepcopy(compiled.routes["ask"])
    plan = workflow_plan_from_compiled(compiled)

    compiled.routes["ask"].clear()
    compiled.artifacts.clear()

    assert tuple(plan.routes["ask"]) == tuple(original_routes)
    assert "report" in plan.artifacts

    rebuilt = compiled_workflow_from_plan(plan)
    rebuilt.routes["ask"].clear()
    rebuilt.artifacts.clear()

    assert tuple(plan.routes["ask"]) == tuple(original_routes)
    assert "report" in plan.artifacts
