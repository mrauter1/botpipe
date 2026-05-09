from __future__ import annotations

from types import SimpleNamespace

from pydantic import BaseModel

from botlane import Route
from botlane.core import Workflow
from botlane.core.artifacts import Artifact
from botlane.core.compiler import compile_workflow
from botlane.core.identifiers import ArtifactId
from botlane.core.primitives import AWAIT_INPUT, FAIL, FINISH, GLOBAL
from botlane.core.route_contracts import (
    AwaitInput,
    Continue,
    FailAction,
    Finish,
    available_route_tags,
    provider_visible_route_tags,
    route_action_for_contract,
    route_target_value,
    runtime_control_route_tags,
)
from botlane.core.steps import PromptStep


class RoutePayload(BaseModel):
    approved: bool


class _RouteWorkflow(Workflow):
    class State(BaseModel):
        pass

    ask = PromptStep(
        name="ask",
        producer="ask.md",
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
        GLOBAL: {"question": Route.question()},
    }


def test_route_contract_targets_map_to_internal_route_actions() -> None:
    compiled = compile_workflow(_RouteWorkflow)
    publish = compiled.routes["ask"]["publish"]
    question = compiled.routes["ask"]["question"]
    failed = compiled.routes["ask"]["failed"]

    assert publish.target.kind == "step"
    assert publish.target.step_name == "review"
    assert question.target.kind == "await_input"
    assert failed.target.kind == "disabled"

    assert route_action_for_contract(compiled.routes["review"]["done"]) == Finish()
    assert route_action_for_contract(question, pending_input={"question": "Need approval"}) == AwaitInput(
        pending_input={"question": "Need approval"}
    )
    fail_contract = Route.to(FAIL)
    class _FailWorkflow(Workflow):
        class State(BaseModel):
            pass
        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"failed": fail_contract}}
    compiled_fail = compile_workflow(_FailWorkflow)
    assert route_action_for_contract(
        compiled_fail.routes["ask"]["failed"],
        reason="runtime failure",
        failure_context={"kind": "runtime_control_validation"},
    ) == FailAction(reason="runtime failure", failure_context={"kind": "runtime_control_validation"})
    assert route_action_for_contract(publish) == Continue(target_step="review")


def test_compiled_route_contract_preserves_metadata_and_required_writes() -> None:
    compiled = compile_workflow(_RouteWorkflow)
    publish = compiled.routes["ask"]["publish"]
    question = compiled.routes["ask"]["question"]
    failed = compiled.routes["ask"]["failed"]

    assert publish.required_writes.declared == (ArtifactId("step", name="report", step="ask"),)
    assert publish.required_writes.explicit == publish.required_writes.declared
    assert publish.required_writes.effective is None
    assert publish.provider.visibility == "interactive_only"
    assert publish.payload.schema == {"properties": {"approved": {"title": "Approved", "type": "boolean"}}, "required": ["approved"], "title": "RoutePayload", "type": "object"}
    assert publish.handoff == "Send the report to the user."
    assert publish.disabled is False
    assert publish.is_runtime_control is False

    assert question.is_runtime_control is False
    assert route_target_value(question.target) == AWAIT_INPUT
    assert failed.disabled is True
    assert route_target_value(failed.target) is None


def test_route_view_helpers_derive_tags_from_plan_route_tables() -> None:
    compiled = compile_workflow(_RouteWorkflow)
    plan = SimpleNamespace(routes={"ask": compiled.routes["ask"]})

    assert available_route_tags(plan, "ask") == ("publish", "question")
    assert runtime_control_route_tags(plan, "ask") == ()
    assert provider_visible_route_tags(plan, "ask", mode="interactive") == ("publish", "question")
    assert provider_visible_route_tags(plan, "ask", mode="full_auto") == ()
