from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from pydantic import BaseModel, Field

import autoloop
import autoloop.simple as simple
import autoloop_v3.core as strict_core
import autoloop_v3.core._compat as strict_compat
import autoloop_v3.core.steps as strict_steps
import autoloop_v3.core.validation as strict_validation
import core
import core.steps as core_steps
import core.validation as core_validation
from autoloop_v3.core.compiler import compile_workflow
from autoloop_v3.core.context import Context
from autoloop_v3.core.engine import Engine
from autoloop_v3.core.errors import WorkflowExecutionError, WorkflowValidationError
from autoloop_v3.core.providers.fake import ScriptedLLMProvider
from autoloop_v3.core.stores import InMemoryCheckpointStore, InMemorySessionStore


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
        "SU" + "CCESS",
        "Route" + "Info",
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
    for symbol in (
        "StrictWorkflow",
        "chain",
        "review_step",
        "do_review_step",
        "system_step",
        "StateVar",
        "Param",
        "AfterHookResult",
        "Checkpoint",
        "ChildWorkflowResult",
        "ResolvedArtifacts",
        "WorkflowStep",
    ):
        assert not hasattr(simple, symbol)
    assert not hasattr(simple.Route, "complete")


def test_removed_simple_symbols_fail_to_import() -> None:
    for symbol in ("AfterHookResult", "Checkpoint", "ChildWorkflowResult", "ResolvedArtifacts", "WorkflowStep"):
        with pytest.raises(ImportError):
            _import_from("autoloop.simple", symbol)


def test_core_top_level_surface_excludes_quarantined_legacy_names() -> None:
    for symbol in (
        "AfterHookResult",
        "LLMStep",
        "PairStep",
        "Param",
        "Route" + "Info",
        "StateVar",
        "SU" + "CCESS",
        "SystemStep",
        "WorkflowStep",
    ):
        assert not hasattr(strict_core, symbol)
        with pytest.raises(ImportError):
            _import_from("autoloop_v3.core", symbol)

    for symbol in ("Artifact", "Context", "FAIL", "FINISH", "GLOBAL", "PAUSE", "Prompt", "Route", "Workflow"):
        assert _import_from("autoloop_v3.core", symbol) is getattr(strict_core, symbol)


def test_core_compat_surface_excludes_removed_route_runtime_helpers() -> None:
    for symbol in ("SU" + "CCESS", "Route" + "Info", "LLMStep", "PairStep", "SystemStep", "WorkflowStep"):
        assert not hasattr(strict_compat, symbol)
        with pytest.raises(ImportError):
            _import_from("autoloop_v3.core._compat", symbol)


def test_autoloop_v3_core_bridge_preserves_shared_module_identity() -> None:
    assert strict_core is core
    assert strict_validation is core_validation
    assert strict_steps is core_steps
    assert strict_core.Workflow is core.Workflow
    assert strict_steps.Step is core_steps.Step


def test_core_compat_usage_stays_quarantined_to_explicit_compatibility_files() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    allowed = {
        "tests/runtime/test_compatibility_runtime.py",
        "tests/fixtures/toy_runtime_workflow.py",
    }
    compat_tokens = ("core" "._compat", "autoloop_v3.core" "._compat")
    candidates = (
        "autoloop",
        "core",
        "stdlib",
        "runtime",
        "workflows",
        "tests/unit",
        "tests/contract",
    )
    matches: list[str] = []

    for relative_root in candidates:
        root = repo_root / relative_root
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            rel = path.relative_to(repo_root).as_posix()
            if rel in allowed:
                continue
            text = path.read_text(encoding="utf-8")
            if any(token in text for token in compat_tokens):
                matches.append(rel)

    assert matches == []


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
        simple.Route.to(simple.FINISH, **{"required_" + "outputs": ("note",)})


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


def test_simple_workflow_injects_canonical_default_routes_by_step_kind() -> None:
    class ChildWorkflow(simple.Workflow):
        finish = simple.step(prompt="Finish child.")

    class RouteMatrixWorkflow(simple.Workflow):
        start = simple.step(prompt="Start.")
        review = simple.produce_verify_step(
            producer_prompt="Draft.",
            verifier_prompt="Verify.",
        )

        @simple.python_step()
        def decide(ctx):
            return None

        child = simple.workflow_step(ChildWorkflow)
        verdict = simple.classify.step(prompt="Classify.", choices=["ship", "rework"])

    compiled = compile_workflow(RouteMatrixWorkflow)

    assert set(compiled.routes["start"]) == {"done", "question", "blocked", "failed"}
    assert compiled.routes["start"]["done"].target == "review"
    assert set(compiled.routes["review"]) == {"accepted", "needs_rework", "question", "blocked", "failed"}
    assert compiled.routes["review"]["accepted"].target == "decide"
    assert compiled.routes["review"]["needs_rework"].target == "review"
    assert set(compiled.routes["decide"]) == {"done", "failed"}
    assert compiled.routes["decide"]["done"].target == "child"
    assert set(compiled.routes["child"]) == {"done", "failed"}
    assert compiled.routes["child"]["done"].target == "verdict"
    assert set(compiled.routes["verdict"]) == {"done"}
    assert compiled.routes["verdict"]["done"].target == "FINISH"


def test_simple_workflow_respects_control_routes_false_and_custom_semantic_routes() -> None:
    class CustomRoutesWorkflow(simple.Workflow):
        class ChildWorkflow(simple.Workflow):
            finish = simple.step(prompt="Finish child.")

        start = simple.step(
            prompt="Start.",
            routes={"ready": "review"},
            control_routes=False,
        )
        review = simple.produce_verify_step(
            producer_prompt="Draft.",
            verifier_prompt="Verify.",
            routes={"approved": simple.FINISH},
            control_routes=False,
        )
        publish = simple.python_step(
            lambda ctx: None,
            routes={"published": "handoff"},
            control_routes=False,
        )
        handoff = simple.workflow_step(
            ChildWorkflow,
            routes={"done_with_child": simple.FINISH},
            control_routes=False,
        )

    compiled = compile_workflow(CustomRoutesWorkflow)

    assert set(compiled.routes["start"]) == {"ready"}
    assert compiled.routes["start"]["ready"].target == "review"
    assert set(compiled.routes["review"]) == {"approved"}
    assert compiled.routes["review"]["approved"].target == "FINISH"
    assert set(compiled.routes["publish"]) == {"published"}
    assert compiled.routes["publish"]["published"].target == "handoff"
    assert set(compiled.routes["handoff"]) == {"done_with_child"}
    assert compiled.routes["handoff"]["done_with_child"].target == "FINISH"


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


def test_simple_workflow_rejects_step_item_state_prompt_placeholders() -> None:
    class StepItemStateWorkflow(simple.Workflow):
        review = simple.produce_verify_step(
            producer_prompt="Draft.",
            verifier_prompt=simple.Prompt.inline("Inspect {review.item_state.attempts}."),
        )

    with pytest.raises(
        WorkflowValidationError,
        match="step item_state, which is not part of the canonical simple-workflow surface",
    ):
        compile_workflow(StepItemStateWorkflow)


def test_simple_runtime_step_state_uses_pydantic_models_and_serializes_for_checkpoints() -> None:
    class ReviewState(BaseModel):
        attempts: int = 0
        history: list[str] = Field(default_factory=list)

    class RuntimeStateWorkflow(simple.Workflow):
        review = simple.produce_verify_step(
            producer_prompt="Draft.",
            verifier_prompt="Verify.",
            state=ReviewState,
        )

    compiled = compile_workflow(RuntimeStateWorkflow)
    engine = Engine(
        compiled,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )
    step = compiled.steps["review"]
    step_states: dict[str, BaseModel | dict[str, object]] = {}

    store = engine._ensure_step_state_store(step_states, step)

    assert isinstance(store, ReviewState)
    assert step_states["review"] is store

    store.attempts += 1
    store.history.append("accepted")

    serialized = engine._serialize_step_states(step_states)

    assert serialized == {"review": {"attempts": 1, "history": ["accepted"]}}

    restored_states: dict[str, BaseModel | dict[str, object]] = {"review": serialized["review"]}
    restored = engine._ensure_step_state_store(restored_states, step)

    assert isinstance(restored, ReviewState)
    assert restored.attempts == 1
    assert restored.history == ["accepted"]
    assert restored_states["review"] is restored


def test_simple_context_suppresses_unmodeled_item_state_surfaces(tmp_path) -> None:
    class WorkflowState(BaseModel):
        approved: bool = False

    class ReviewState(BaseModel):
        attempts: int = 0

    ctx = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="simple-demo",
        task_folder=tmp_path,
        workflow_folder=tmp_path,
        run_folder=tmp_path,
        package_folder=tmp_path,
        state=WorkflowState(),
        session_store=InMemorySessionStore(),
        step_state_store=ReviewState(),
    )

    assert isinstance(ctx.step_state, ReviewState)
    assert ctx.step_state.attempts == 0

    with pytest.raises(
        WorkflowExecutionError,
        match="item_state is not part of the canonical public surface",
    ):
        _ = ctx.item_state

    with pytest.raises(
        WorkflowExecutionError,
        match="step_item_state is not part of the canonical public surface",
    ):
        _ = ctx.step_item_state
