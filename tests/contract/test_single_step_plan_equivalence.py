from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import BaseModel

import botpipe.simple as simple
import botpipe.sdk as sdk_module
from botpipe import AWAIT_INPUT, FAIL, FINISH, SELF, Policy
from botpipe.core.prompts import Prompt
from botpipe.core.step_plans import (
    ChildWorkflowStepPlan,
    ProduceVerifyStepPlan,
    PromptStepPlan,
    PythonStepPlan,
    SingleStepPlan,
)
from botpipe.core.steps import ChildWorkflowStep, ProduceVerifyStep, PromptStep, PythonStep
from botpipe.policy import ModelEffort


class _SingleStepTypedInput(BaseModel):
    topic: str


class _SingleStepParams(BaseModel):
    mode: str


class _SingleStepChildWorkflow(simple.Workflow):
    class State(BaseModel):
        seen_message: str | None = None

    @simple.python_step(routes={"done": FINISH})
    def capture(ctx):
        ctx.state = ctx.state.model_copy(update={"seen_message": ctx.message})
        return simple.Event("done")


@pytest.mark.parametrize(
    ("factory", "expected_plan_type", "expected_routes"),
    [
        (
            lambda: simple.step("Draft {{ input.topic }}.", name="draft"),
            PromptStepPlan,
            ("done", "question"),
        ),
        (
            lambda: simple.produce_verify_step(
                producer_prompt="Draft {{ input.topic }}.",
                verifier_prompt="Review {{ input.topic }}.",
                name="review",
            ),
            ProduceVerifyStepPlan,
            ("accepted", "needs_rework", "question"),
        ),
        (
            lambda: simple.python_step(lambda _ctx: simple.Event("done"), name="python"),
            PythonStepPlan,
            ("done",),
        ),
        (
            lambda: simple.workflow_step(_SingleStepChildWorkflow, name="child"),
            ChildWorkflowStepPlan,
            ("done",),
        ),
        (
            lambda: simple.llm.step(prompt="Summarize {{ input.topic }}.", name="summarize"),
            PythonStepPlan,
            ("done",),
        ),
        (
            lambda: simple.classify.step(
                prompt="Classify {{ input.topic }}.",
                choices=["ship", "rework"],
                name="classify",
            ),
            PythonStepPlan,
            ("done",),
        ),
        (
            lambda: PromptStep(name="prompt_core", producer=Prompt.inline("Prompt {{ input.topic }}.")),
            PromptStepPlan,
            ("done", "question"),
        ),
        (
            lambda: ProduceVerifyStep(
                name="pair_core",
                producer=Prompt.inline("Draft {{ input.topic }}."),
                verifier=Prompt.inline("Review {{ input.topic }}."),
            ),
            ProduceVerifyStepPlan,
            ("accepted", "needs_rework", "question"),
        ),
        (
            lambda: PythonStep(name="python_core", handler=lambda _ctx: simple.Event("done")),
            PythonStepPlan,
            ("done",),
        ),
        (
            lambda: ChildWorkflowStep(
                name="child_core",
                workflow=_SingleStepChildWorkflow,
                message="{{ message }}",
            ),
            ChildWorkflowStepPlan,
            ("done",),
        ),
    ],
)
def test_single_step_plan_builds_direct_step_plans(
    tmp_path: Path,
    factory: Callable[[], object],
    expected_plan_type: type[object],
    expected_routes: tuple[str, ...],
) -> None:
    single_step_plan, _workflow_plan = sdk_module._build_single_step_execution_plan(
        tmp_path,
        factory(),
        _SingleStepTypedInput(topic="release"),
        _SingleStepParams(mode="focused"),
        routes=None,
    )

    assert isinstance(single_step_plan, SingleStepPlan)
    assert isinstance(single_step_plan.step, expected_plan_type)
    assert tuple(single_step_plan.routes) == expected_routes
    assert single_step_plan.input_model is _SingleStepTypedInput
    assert single_step_plan.params_model is _SingleStepParams


def test_single_step_workflow_plan_uses_single_step_as_entry(tmp_path: Path) -> None:
    _single_step_plan, workflow_plan = sdk_module._build_single_step_execution_plan(
        tmp_path,
        simple.step("Draft {{ input.topic }}.", name="draft"),
        _SingleStepTypedInput(topic="release"),
        _SingleStepParams(mode="focused"),
        routes=None,
    )

    assert workflow_plan.workflow_name == "sdk_step_draft"
    assert workflow_plan.entry_step_name == "draft"
    assert tuple(workflow_plan.steps) == ("draft",)
    assert isinstance(workflow_plan.steps["draft"], PromptStepPlan)
    assert tuple(workflow_plan.routes["draft"]) == ("done", "question")


def test_single_step_workflow_plan_lowers_simple_pair_rework_to_current_step(tmp_path: Path) -> None:
    _single_step_plan, workflow_plan = sdk_module._build_single_step_execution_plan(
        tmp_path,
        simple.produce_verify_step(
            producer_prompt="Draft {{ input.topic }}.",
            verifier_prompt="Review {{ input.topic }}.",
            name="review",
        ),
        _SingleStepTypedInput(topic="release"),
        _SingleStepParams(mode="focused"),
        routes=None,
    )

    assert workflow_plan.routes["review"]["accepted"].target == FINISH
    assert workflow_plan.routes["review"]["needs_rework"].target.step_name == "review"


def test_single_step_plan_preserves_policy_layering_and_explicit_routes(tmp_path: Path) -> None:
    authored_policy = Policy(effort=ModelEffort.LOW)
    invocation_policy = Policy(effort=ModelEffort.HIGH)
    authored_step = PromptStep(
        name="draft",
        producer=Prompt.inline("Draft {{ input.topic }}."),
        provider_policy=authored_policy,
    )
    effective_step, workflow_policy = sdk_module._sdk_step_invocation_layer(authored_step, invocation_policy)

    single_step_plan, _workflow_plan = sdk_module._build_single_step_execution_plan(
        tmp_path,
        effective_step,
        _SingleStepTypedInput(topic="release"),
        _SingleStepParams(mode="focused"),
        routes={
            "done": FINISH,
            "question": AWAIT_INPUT,
            "failed": FAIL,
            "repair": simple.Route(target=SELF, summary="retry once"),
        },
        workflow_policy=workflow_policy,
    )

    assert workflow_policy is authored_policy
    assert authored_step.provider_policy is authored_policy
    assert single_step_plan.workflow_policy is authored_policy
    assert single_step_plan.step.header.provider_policy is invocation_policy
    assert tuple(single_step_plan.routes) == ("done", "question", "failed", "repair")


def test_sdk_module_no_longer_exposes_synthetic_step_workflow_builder() -> None:
    assert not hasattr(sdk_module, "_build_synthetic_step_workflow")
