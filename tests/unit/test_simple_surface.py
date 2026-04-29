from __future__ import annotations

import inspect

import pytest
from pydantic import BaseModel, Field

import autoloop
import autoloop.simple as simple
from autoloop_v3.core.compiler import compile_workflow
from autoloop_v3.core.errors import WorkflowValidationError


def _import_from(module_name: str, symbol: str) -> object:
    namespace: dict[str, object] = {}
    exec(f"from {module_name} import {symbol} as imported_symbol", namespace)
    return namespace["imported_symbol"]


def test_autoloop_root_exports_only_the_canonical_public_surface() -> None:
    assert tuple(autoloop.__all__) == (
        "Workflow",
        "step",
        "produce_verify_step",
        "python_step",
        "workflow_step",
        "llm",
        "classify",
        "Prompt",
        "Md",
        "Json",
        "Text",
        "Raw",
        "Route",
        "Session",
        "Continuity",
        "Worklist",
        "Event",
        "Outcome",
        "FINISH",
        "PAUSE",
        "FAIL",
        "SELF",
    )

    for symbol in autoloop.__all__:
        assert _import_from("autoloop", symbol) is getattr(autoloop, symbol)


def test_removed_root_public_symbols_fail_to_import() -> None:
    for symbol in (
        "SUCCESS",
        "RouteInfo",
        "StrictWorkflow",
        "WorkflowStep",
        "AfterHookResult",
        "ResolvedArtifacts",
        "Checkpoint",
        "ChildWorkflowResult",
        "chain",
        "review_step",
        "do_review_step",
        "system_step",
        "StateVar",
        "Param",
    ):
        with pytest.raises(ImportError):
            _import_from("autoloop", symbol)


def test_removed_simple_aliases_are_absent() -> None:
    for symbol in ("StrictWorkflow", "chain", "review_step", "do_review_step", "system_step", "StateVar", "Param"):
        assert not hasattr(simple, symbol)
    assert not hasattr(simple.Route, "complete")


def test_canonical_simple_signatures_expose_only_canonical_argument_names() -> None:
    assert tuple(inspect.signature(simple.step).parameters) == (
        "prompt",
        "name",
        "reads",
        "requires",
        "writes",
        "routes",
        "before",
        "after",
        "on_route",
        "control_schema",
        "retry",
        "session",
        "control_routes",
    )
    assert tuple(inspect.signature(simple.produce_verify_step).parameters) == (
        "producer_prompt",
        "verifier_prompt",
        "name",
        "reads",
        "requires",
        "verifier_reads",
        "verifier_requires",
        "producer_writes",
        "verifier_writes",
        "routes",
        "state",
        "before_producer",
        "after_producer",
        "before_verifier",
        "after_verifier",
        "on_route",
        "control_schema",
        "retry",
        "session",
        "verifier_session",
        "control_routes",
    )
    assert tuple(inspect.signature(simple.python_step).parameters) == (
        "fn",
        "name",
        "reads",
        "requires",
        "writes",
        "routes",
        "before",
        "after",
        "on_route",
        "control_routes",
    )


def test_legacy_simple_keyword_arguments_fail_fast() -> None:
    with pytest.raises(TypeError):
        simple.step("Draft the note.", out=simple.Md("note"))

    with pytest.raises(TypeError):
        simple.step("Draft the note.", outputs=[simple.Md("note")])

    with pytest.raises(TypeError):
        simple.produce_verify_step(do="draft", review="verify")

    with pytest.raises(TypeError):
        simple.produce_verify_step(
            producer_prompt="draft",
            verifier_prompt="verify",
            review_writes=[simple.Md("report")],
        )

    with pytest.raises(TypeError):
        simple.Route.to(simple.FINISH, required_outputs=("note",))


def test_simple_workflow_compiles_with_pydantic_state_params_and_produce_verify_step() -> None:
    class ParamsModel(BaseModel):
        max_attempts: int = 3

    class WorkflowState(BaseModel):
        approved: bool = False

    class ReviewState(BaseModel):
        attempts: int = 0
        history: list[str] = Field(default_factory=list)

    class Decision(BaseModel):
        ok: bool = True

    class ReviewWorkflow(simple.Workflow):
        Params = ParamsModel
        State = WorkflowState

        prepare = simple.step(
            prompt=simple.Prompt.inline("Prepare using {params.max_attempts}."),
            writes=[simple.Md("brief", required=True)],
        )
        review = simple.produce_verify_step(
            producer_prompt=simple.Prompt.inline("Draft from {prepare.brief}."),
            verifier_prompt=simple.Prompt.inline("Verify with {review.state.attempts}."),
            requires=[prepare.brief],
            producer_writes=[simple.Md("draft", required=True)],
            verifier_writes=[simple.Json("decision", Decision, required=False)],
            state=ReviewState,
        )

    compiled = compile_workflow(ReviewWorkflow)

    assert compiled.entry_step_name == "prepare"
    assert compiled.parameters_cls is ParamsModel
    assert compiled.state_cls is WorkflowState
    assert compiled.default_session_name == "global"
    assert compiled.steps["prepare"].kind == "step"
    assert compiled.steps["review"].kind == "produce_verify"
    assert compiled.routes["prepare"]["done"].target == "review"
    assert compiled.routes["review"]["accepted"].target == "FINISH"
    assert compiled.routes["review"]["needs_rework"].target == "review"
    assert compiled.steps["prepare"].writes == ("prepare.brief",)
    assert compiled.steps["review"].producer_prompt is not None
    assert compiled.steps["review"].verifier_prompt is not None
    assert compiled.steps["review"].producer_writes == ("review.draft",)
    assert compiled.steps["review"].verifier_writes == ("review.decision",)
    assert compiled.steps["review"].step_state_fields == ("attempts", "history")


def test_simple_workflow_rejects_parameters_namespace_instead_of_params() -> None:
    class BadWorkflow(simple.Workflow):
        class Parameters(BaseModel):
            count: int = 1

        start = simple.step(prompt="Start.")

    with pytest.raises(WorkflowValidationError, match="Use Params, not Parameters"):
        compile_workflow(BadWorkflow)


def test_produce_verify_step_requires_pydantic_step_state_model() -> None:
    class BadWorkflow(simple.Workflow):
        review = simple.produce_verify_step(
            producer_prompt="Draft.",
            verifier_prompt="Verify.",
            state={"attempts": 0},
        )

    with pytest.raises(
        WorkflowValidationError,
        match="simple step 'review' state must be declared with a pydantic.BaseModel subclass",
    ):
        compile_workflow(BadWorkflow)


def test_simple_workflow_rejects_class_level_transitions_and_flow() -> None:
    class TransitionWorkflow(simple.Workflow):
        start = simple.step(prompt="Start.")
        transitions = {"start": {"done": "finish"}}

    with pytest.raises(
        WorkflowValidationError,
        match="step-local routes and optional entry, not transitions or flow",
    ):
        compile_workflow(TransitionWorkflow)


def test_simple_workflow_rejects_item_state_prompt_placeholders() -> None:
    class ItemStateWorkflow(simple.Workflow):
        start = simple.step(prompt=simple.Prompt.inline("Inspect {item.state.status}."))

    with pytest.raises(
        WorkflowValidationError,
        match="item.state, which is not part of the canonical simple-workflow surface",
    ):
        compile_workflow(ItemStateWorkflow)
