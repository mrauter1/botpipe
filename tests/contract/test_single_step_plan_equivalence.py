from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import BaseModel

import botlane.simple as simple
import botlane.sdk as sdk_module
from botlane import AWAIT_INPUT, FAIL, FINISH, SELF, Botlane, Policy, StaticInput
from botlane.core.compiler import compile_workflow_plan
from botlane.core.primitives import Event, Outcome
from botlane.core.prompts import Prompt
from botlane.core.providers.fake import ScriptedLLMProvider
from botlane.core.step_plans import (
    ChildWorkflowStepPlan,
    ProduceVerifyStepPlan,
    PromptStepPlan,
    PythonStepPlan,
    SingleStepPlan,
)
from botlane.core.steps import ChildWorkflowStep, ProduceVerifyStep, PromptStep, PythonStep
from botlane.policy import ModelEffort
from botlane.runtime.config import GitTrackingRuntimeConfig, RuntimeConfig


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
        return Event("done")


def _sdk_client(tmp_path: Path, provider: object) -> Botlane:
    return Botlane(
        workspace=tmp_path,
        provider=provider,
        state_dir=tmp_path / ".botlane",
        runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False, commit_policy="off")),
    )


def _step_plan_signature(plan: object) -> dict[str, object]:
    header = plan.header
    signature = {
        "plan_type": type(plan),
        "name": header.name,
        "kind": header.kind,
        "session_name": header.session_name,
        "scope_name": header.scope_name,
        "io": header.io,
        "step_state_model": header.state.step_state_model,
        "step_state_fields": header.state.step_state_fields,
        "step_item_state_model": header.state.step_item_state_model,
        "step_item_state_fields": header.state.step_item_state_fields,
    }
    if isinstance(plan, PromptStepPlan):
        signature["turn_kind"] = plan.turn.kind
        signature["turn_session_name"] = plan.turn.session_name
    elif isinstance(plan, ProduceVerifyStepPlan):
        signature["producer_kind"] = plan.producer.kind
        signature["verifier_kind"] = plan.verifier.kind
        signature["verifier_session_name"] = plan.verifier_session_name
    elif isinstance(plan, ChildWorkflowStepPlan):
        signature["workflow"] = plan.workflow
        signature["message"] = plan.message
    return signature


@pytest.mark.parametrize(
    ("factory", "expected_plan_type", "expected_routes"),
    [
        (
            lambda: simple.step("Draft {input.topic}.", name="draft"),
            PromptStepPlan,
            ("done", "question"),
        ),
        (
            lambda: simple.produce_verify_step(
                producer_prompt="Draft {input.topic}.",
                verifier_prompt="Review {input.topic}.",
                name="review",
            ),
            ProduceVerifyStepPlan,
            ("accepted", "needs_rework", "question"),
        ),
        (
            lambda: simple.python_step(lambda _ctx: Event("done"), name="python"),
            PythonStepPlan,
            ("done",),
        ),
        (
            lambda: simple.workflow_step(_SingleStepChildWorkflow, name="child"),
            ChildWorkflowStepPlan,
            ("done",),
        ),
        (
            lambda: simple.llm.step(prompt="Summarize {input.topic}.", name="summarize"),
            PythonStepPlan,
            ("done",),
        ),
        (
            lambda: simple.classify.step(
                prompt="Classify {input.topic}.",
                choices=["ship", "rework"],
                name="classify",
            ),
            PythonStepPlan,
            ("done",),
        ),
        (
            lambda: PromptStep(name="prompt_core", producer=Prompt.inline("Prompt {input.topic}.")),
            PromptStepPlan,
            ("done", "question"),
        ),
        (
            lambda: ProduceVerifyStep(
                name="pair_core",
                producer=Prompt.inline("Draft {input.topic}."),
                verifier=Prompt.inline("Review {input.topic}."),
            ),
            ProduceVerifyStepPlan,
            ("accepted", "needs_rework", "question"),
        ),
        (
            lambda: PythonStep(name="python_core", handler=lambda _ctx: Event("done")),
            PythonStepPlan,
            ("done",),
        ),
        (
            lambda: ChildWorkflowStep(
                name="child_core",
                workflow=_SingleStepChildWorkflow,
                message="{ctx.message}",
            ),
            ChildWorkflowStepPlan,
            ("done",),
        ),
    ],
)
def test_single_step_plan_matches_compiled_synthetic_workflow_for_supported_steps(
    tmp_path: Path,
    factory: Callable[[], object],
    expected_plan_type: type[object],
    expected_routes: tuple[str, ...],
) -> None:
    step_def = factory()
    typed_input = _SingleStepTypedInput(topic="release")
    params = _SingleStepParams(mode="focused")

    single_step_plan = sdk_module._build_single_step_plan(
        tmp_path,
        step_def,
        typed_input,
        params,
        routes=None,
    )
    workflow_cls = sdk_module._build_synthetic_step_workflow(
        tmp_path,
        step_def,
        typed_input,
        params,
        routes=None,
    )
    workflow_plan = compile_workflow_plan(workflow_cls)
    entry_step_name = workflow_plan.entry_step_name

    assert isinstance(single_step_plan, SingleStepPlan)
    assert isinstance(single_step_plan.step, expected_plan_type)
    assert _step_plan_signature(single_step_plan.step) == _step_plan_signature(workflow_plan.steps[entry_step_name])
    assert single_step_plan.input_model is workflow_plan.input_model
    assert single_step_plan.params_model is workflow_plan.parameters_cls
    assert tuple(single_step_plan.routes) == expected_routes
    assert single_step_plan.routes == workflow_plan.routes[entry_step_name]
    assert single_step_plan.workflow_policy == workflow_plan.provider_policy


def test_single_step_plan_preserves_policy_layering_and_explicit_routes(tmp_path: Path) -> None:
    authored_policy = Policy(effort=ModelEffort.LOW)
    invocation_policy = Policy(effort=ModelEffort.HIGH)
    original_step = PromptStep(
        name="draft",
        producer=Prompt.inline("Draft {input.topic}."),
        provider_policy=authored_policy,
    )
    effective_step, workflow_policy = sdk_module._sdk_step_invocation_layer(original_step, invocation_policy)

    single_step_plan = sdk_module._build_single_step_plan(
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
    assert original_step.provider_policy is authored_policy
    assert single_step_plan.workflow_policy is authored_policy
    assert single_step_plan.step.header.provider_policy is invocation_policy
    assert tuple(single_step_plan.routes) == ("done", "question", "failed", "repair")


def test_sdk_step_matches_direct_synthetic_workflow_run_for_typed_input_and_params(tmp_path: Path) -> None:
    snapshot = simple.Json("snapshot")

    @simple.python_step(writes=[snapshot], routes={"done": FINISH})
    def capture(ctx):
        ctx.artifacts.snapshot.write_json(
            {
                "message": ctx.message,
                "params": ctx.params.model_dump(mode="python"),
                "input": ctx.input.model_dump(mode="python"),
            }
        )
        return Event("done")

    client = _sdk_client(tmp_path, ScriptedLLMProvider())
    typed_input = _SingleStepTypedInput(topic="release")
    params = _SingleStepParams(mode="focused")
    workflow_cls = sdk_module._build_synthetic_step_workflow(
        tmp_path,
        capture,
        typed_input,
        params,
        routes=None,
    )

    step_result = client.step(
        capture,
        message="Handle the release.",
        input=typed_input,
        params=params,
    )
    workflow_result = client.run(
        workflow_cls,
        message="Handle the release.",
        input=typed_input,
        params=params,
    )

    assert step_result.ok is workflow_result.ok
    assert step_result.status == workflow_result.status
    assert step_result.route == sdk_module._step_result_route(workflow_result)
    assert step_result.value is None
    assert step_result.artifacts.snapshot.read_json() == workflow_result.artifacts.snapshot.read_json()
    assert step_result.workflow_result.status == workflow_result.status


def test_sdk_step_matches_direct_synthetic_workflow_run_for_provider_question_flow(tmp_path: Path) -> None:
    provider_step = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="Need approval", tag="question", question="Proceed?"),
            Outcome(raw_output="Approved", tag="done"),
        ]
    )
    provider_run = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="Need approval", tag="question", question="Proceed?"),
            Outcome(raw_output="Approved", tag="done"),
        ]
    )
    step_client = _sdk_client(tmp_path / "step", provider_step)
    run_client = _sdk_client(tmp_path / "run", provider_run)
    declaration = simple.step(
        "Review the request.",
        name="review",
        routes={"done": FINISH, "question": AWAIT_INPUT},
    )
    workflow_cls = sdk_module._build_synthetic_step_workflow(
        tmp_path,
        declaration,
        None,
        None,
        routes=None,
    )

    step_result = step_client.step(
        declaration,
        "Review the rollout.",
        on_input=StaticInput("yes"),
    )
    workflow_result = run_client.run(
        workflow_cls,
        "Review the rollout.",
        on_input=StaticInput("yes"),
    )

    assert step_result.status == workflow_result.status == "completed"
    assert step_result.route == sdk_module._step_result_route(workflow_result) == "done"
    assert len(step_result.workflow_result.handled_inputs) == len(workflow_result.handled_inputs) == 1
