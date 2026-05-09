from __future__ import annotations

import botlane.simple as simple
from pydantic import BaseModel

from botlane import FINISH
from botlane.core import Workflow
from botlane.core.artifacts import Artifact
from botlane.core.compiler import compile_workflow
from botlane.core.plan_adapters import compiled_step_from_step_plan, route_contract_from_compiled_route, step_plan_from_compiled_step
from botlane.core.step_plans import (
    BranchGroupStepPlan,
    ChildWorkflowStepPlan,
    ExternalRead,
    FanInRead,
    ProduceVerifyStepPlan,
    PromptStepPlan,
    PythonStepPlan,
)
from botlane.core.steps import ChildWorkflowStep, ProduceVerifyStep, PromptStep, PythonStep, Session


class _ChildWorkflow(Workflow):
    class State(BaseModel):
        status: str = "new"

    done = PromptStep(name="done", producer="child.md")
    entry = done
    transitions = {done: {"done": FINISH}}


class _PlanWorkflow(Workflow):
    class State(BaseModel):
        status: str = "new"

    producer_session = Session.fresh()
    verifier_session_slot = Session.fresh()
    shared = Artifact("shared.md", name="shared")
    prompt = PromptStep(
        name="prompt",
        producer="prompt.md",
        reads=[shared, "notes.txt"],
        requires=[shared],
        writes={"draft": Artifact("draft.md")},
    )
    pair = ProduceVerifyStep(
        name="pair",
        producer="producer.md",
        verifier="verifier.md",
        reads=[shared],
        requires=[shared],
        verifier_requires=[shared],
        producer_writes={"draft": Artifact("pair_draft.md")},
        verifier_writes={"review": Artifact("pair_review.md")},
        session=producer_session,
        verifier_session=verifier_session_slot,
    )
    run_python = PythonStep(
        name="run_python",
        reads=[shared],
        requires=[shared],
        writes={"result": Artifact("result.json", kind="json")},
        handler=lambda ctx: None,
    )
    launch = ChildWorkflowStep(
        name="launch",
        workflow="child_workflow",
        message="Run child workflow.",
        params={"mode": "fast"},
        input={"attempt": 1},
        reads=[shared],
        requires=[shared],
        writes={"child_report": Artifact("child_report.md")},
    )
    entry = prompt
    transitions = {
        prompt: {"done": pair},
        pair: {"accepted": run_python, "needs_rework": prompt},
        run_python: {"done": launch},
        launch: {"done": FINISH},
    }


class _BranchPlanWorkflow(Workflow):
    class State(BaseModel):
        status: str = "new"

    reviews = simple.parallel(
        branches={
            "security": simple.step(
                "Review security findings.",
                name="security_review",
                session=simple.Session.fresh(),
            ),
            "cost": simple.step(
                "Review cost findings.",
                name="cost_review",
                session=simple.Session.fresh(),
            ),
        },
        fan_in=simple.step(
            "Summarize branch outputs.",
            name="combine_reviews",
            reads=[simple.FanIn.results()],
            requires=[simple.FanIn.context()],
            routes={"done": FINISH},
        ),
    )


def test_step_plans_cover_prompt_pair_python_and_child_variants() -> None:
    compiled = compile_workflow(_PlanWorkflow)

    prompt_plan = step_plan_from_compiled_step(
        compiled.steps["prompt"],
        routes={
            tag: route_contract_from_compiled_route(route, inventory=compiled.artifacts_by_qualified_name)
            for tag, route in compiled.routes["prompt"].items()
        },
        inventory=compiled.artifacts_by_qualified_name,
    )
    pair_plan = step_plan_from_compiled_step(
        compiled.steps["pair"],
        routes={
            tag: route_contract_from_compiled_route(route, inventory=compiled.artifacts_by_qualified_name)
            for tag, route in compiled.routes["pair"].items()
        },
        inventory=compiled.artifacts_by_qualified_name,
    )
    python_plan = step_plan_from_compiled_step(
        compiled.steps["run_python"],
        routes={
            tag: route_contract_from_compiled_route(route, inventory=compiled.artifacts_by_qualified_name)
            for tag, route in compiled.routes["run_python"].items()
        },
        inventory=compiled.artifacts_by_qualified_name,
    )
    child_plan = step_plan_from_compiled_step(
        compiled.steps["launch"],
        routes={
            tag: route_contract_from_compiled_route(route, inventory=compiled.artifacts_by_qualified_name)
            for tag, route in compiled.routes["launch"].items()
        },
        inventory=compiled.artifacts_by_qualified_name,
    )

    assert isinstance(prompt_plan, PromptStepPlan)
    assert isinstance(prompt_plan.header.io.reads[0], type(prompt_plan.header.io.writes[0]))
    assert isinstance(prompt_plan.header.io.reads[1], ExternalRead)
    assert prompt_plan.turn.kind == "llm"
    assert not hasattr(prompt_plan.header, "available_routes")

    assert isinstance(pair_plan, ProduceVerifyStepPlan)
    assert pair_plan.producer.kind == "producer"
    assert pair_plan.verifier.kind == "verifier"
    assert pair_plan.verifier_session_name == compiled.steps["pair"].verifier_session_name

    assert isinstance(python_plan, PythonStepPlan)
    assert python_plan.handler is compiled.steps["run_python"].python_handler

    assert isinstance(child_plan, ChildWorkflowStepPlan)
    assert child_plan.workflow == "child_workflow"
    assert child_plan.message == "Run child workflow."
    assert child_plan.params == {"mode": "fast"}
    assert child_plan.input == {"attempt": 1}

    assert compiled_step_from_step_plan(prompt_plan, routes={
        tag: route_contract_from_compiled_route(route, inventory=compiled.artifacts_by_qualified_name)
        for tag, route in compiled.routes["prompt"].items()
    }) == compiled.steps["prompt"]
    assert compiled_step_from_step_plan(pair_plan, routes={
        tag: route_contract_from_compiled_route(route, inventory=compiled.artifacts_by_qualified_name)
        for tag, route in compiled.routes["pair"].items()
    }) == compiled.steps["pair"]
    assert compiled_step_from_step_plan(python_plan, routes={
        tag: route_contract_from_compiled_route(route, inventory=compiled.artifacts_by_qualified_name)
        for tag, route in compiled.routes["run_python"].items()
    }) == compiled.steps["run_python"]
    assert compiled_step_from_step_plan(child_plan, routes={
        tag: route_contract_from_compiled_route(route, inventory=compiled.artifacts_by_qualified_name)
        for tag, route in compiled.routes["launch"].items()
    }) == compiled.steps["launch"]


def test_branch_group_step_plan_keeps_nested_plan_shapes_and_fan_in_helpers() -> None:
    compiled = compile_workflow(_BranchPlanWorkflow)
    branch_step = compiled.steps["reviews"]

    plan = step_plan_from_compiled_step(
        branch_step,
        routes={
            tag: route_contract_from_compiled_route(route, inventory=compiled.artifacts_by_qualified_name)
            for tag, route in compiled.routes["reviews"].items()
        },
        inventory=compiled.artifacts_by_qualified_name,
    )

    assert isinstance(plan, BranchGroupStepPlan)
    assert [branch.name for branch in plan.branch_group.branches] == ["security", "cost"]
    assert isinstance(plan.branch_group.branches[0].step, PromptStepPlan)
    assert isinstance(plan.branch_group.fan_in_step, PromptStepPlan)
    assert isinstance(plan.branch_group.fan_in_step.header.io.reads[0], FanInRead)
    assert plan.branch_group.fan_in_step.header.io.reads[0].helper == "results"
    assert isinstance(plan.branch_group.fan_in_step.header.io.requires[0], FanInRead)
    assert plan.branch_group.fan_in_step.header.io.requires[0].helper == "context"

    round_trip = compiled_step_from_step_plan(
        plan,
        routes={
            tag: route_contract_from_compiled_route(route, inventory=compiled.artifacts_by_qualified_name)
            for tag, route in compiled.routes["reviews"].items()
        },
    )
    assert round_trip == branch_step
