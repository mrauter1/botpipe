from __future__ import annotations

import botlane.simple as simple
from pydantic import BaseModel

from botlane import FINISH
from botlane.core import Workflow
from botlane.core.artifacts import Artifact
from botlane.core.compiler import compile_workflow
from botlane.core.identifiers import ArtifactId
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


def test_compile_workflow_emits_typed_step_plan_variants() -> None:
    compiled = compile_workflow(_PlanWorkflow)

    prompt_plan = compiled.steps["prompt"]
    pair_plan = compiled.steps["pair"]
    python_plan = compiled.steps["run_python"]
    child_plan = compiled.steps["launch"]

    assert isinstance(prompt_plan, PromptStepPlan)
    assert prompt_plan.header.source is not None
    assert prompt_plan.header.source.declaration_name == "prompt"
    assert prompt_plan.header.source.authoring_kind == "PromptStep"
    assert prompt_plan.turn.kind == "llm"
    assert isinstance(prompt_plan.reads[0], ArtifactId)
    assert isinstance(prompt_plan.reads[1], ExternalRead)
    assert prompt_plan.available_routes == ("done", "question")
    assert not hasattr(prompt_plan.header, "original_step")

    assert isinstance(pair_plan, ProduceVerifyStepPlan)
    assert pair_plan.header.source is not None
    assert pair_plan.header.source.declaration_name == "pair"
    assert pair_plan.producer.kind == "producer"
    assert pair_plan.verifier.kind == "verifier"
    assert pair_plan.verifier_session_name == compiled.steps["pair"].verifier_session_name

    assert isinstance(python_plan, PythonStepPlan)
    assert python_plan.header.source is not None
    assert python_plan.header.source.declaration_name == "run_python"
    assert python_plan.handler is compiled.steps["run_python"].handler

    assert isinstance(child_plan, ChildWorkflowStepPlan)
    assert child_plan.header.source is not None
    assert child_plan.header.source.declaration_name == "launch"
    assert child_plan.workflow == "child_workflow"
    assert child_plan.message == "Run child workflow."
    assert child_plan.params == {"mode": "fast"}
    assert child_plan.input == {"attempt": 1}


def test_branch_group_step_plan_keeps_nested_plan_shapes_and_fan_in_helpers() -> None:
    compiled = compile_workflow(_BranchPlanWorkflow)
    plan = compiled.steps["reviews"]

    assert isinstance(plan, BranchGroupStepPlan)
    assert plan.header.source is not None
    assert plan.header.source.declaration_name == "reviews"
    assert [branch.name for branch in plan.branch_group.branches] == ["security", "cost"]
    assert isinstance(plan.branch_group.branches[0].step, PromptStepPlan)
    assert isinstance(plan.branch_group.fan_in_step, PromptStepPlan)
    assert isinstance(plan.branch_group.fan_in_step.reads[0], FanInRead)
    assert plan.branch_group.fan_in_step.reads[0].helper == "results"
    assert isinstance(plan.branch_group.fan_in_step.requires[0], FanInRead)
    assert plan.branch_group.fan_in_step.requires[0].helper == "context"
