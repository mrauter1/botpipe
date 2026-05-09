from __future__ import annotations

import inspect
from pathlib import Path
import re

import pytest
from pydantic import BaseModel, Field

import botlane
import botlane.simple as simple
import botlane.core as core
import botlane.core.steps as core_steps
import botlane.core.validation as core_validation
from botlane.core.branch_groups.models import BranchGroupDeclarationSpec
from botlane.core.compiler import compile_workflow
from botlane.core.context import ChildWorkflowResult, Context
from botlane.core.discovery import get_workflow_definition
from botlane.core.engine import Engine
from botlane.core.errors import WorkflowExecutionError, WorkflowValidationError
from botlane.core.providers.fake import ScriptedLLMProvider
from botlane.core.provider_policy import PermissionPolicy, ProviderPolicy, ProviderPolicyOverride
from botlane.core.route_contracts import route_target_value
from botlane.core.stores import InMemoryCheckpointStore, InMemorySessionStore


REMOVED_WORKFLOW_STEP = "Workflow" + "Step"
REMOVED_AFTER_HOOK_RESULT = "After" + "HookResult"
REMOVED_STATE_VAR = "State" + "Var"
REMOVED_PARAM = "Pa" + "ram"
REMOVED_LLM_STEP = "L" + "LMStep"
REMOVED_PAIR_STEP = "Pair" + "Step"
REMOVED_SYSTEM_STEP = "System" + "Step"
REMOVED_STRICT_WORKFLOW = "Strict" + "Workflow"
REMOVED_REVIEW_STEP = "review" + "_" + "step"
REMOVED_DO_REVIEW_STEP = "do" + "_" + "review" + "_" + "step"
REMOVED_SYSTEM_STEP_ALIAS = "system" + "_" + "step"
REMOVED_VERIFIER_WRITES = "review_" + "writes"


def _import_from(module_name: str, symbol: str) -> object:
    namespace: dict[str, object] = {}
    exec(f"from {module_name} import {symbol} as imported_symbol", namespace)
    return namespace["imported_symbol"]


def test_effect_exports_and_route_helpers_are_public() -> None:
    route = simple.Route.advance(simple.FINISH, status="completed", exhausted="done")
    assert isinstance(simple.Effects.advance(exhausted="done"), simple.Effects)
    assert isinstance(simple.WorklistEffect(set_current_status="completed"), simple.WorklistEffect)
    assert route.on_taken is not None
    returned = route.on_taken(object())
    assert isinstance(returned, simple.Effects)
    assert returned.worklists[0].advance is True
    assert returned.worklists[0].set_current_status == "completed"


def test_effect_helpers_and_additional_route_helpers_lower_to_effects() -> None:
    then_effect = simple.Effects.then("next")
    refresh_current_effect = simple.Effects.refresh()
    refresh_route = simple.Route.refresh(simple.FINISH, worklist="items")
    complete_route = simple.Route.complete_current(simple.FINISH, worklist="items")
    complete_and_advance_route = simple.Route.complete_and_advance(simple.FINISH, worklist="items", exhausted="done")

    assert then_effect.event == "next"
    assert refresh_current_effect.worklists == (simple.WorklistEffect(worklist=None, refresh=True),)
    assert simple.WorklistEffect.refresh_current(worklist="items") == simple.WorklistEffect(worklist="items", refresh=True)
    assert simple.WorklistEffect.complete_current(worklist="items") == simple.WorklistEffect(
        worklist="items",
        set_current_status="completed",
    )
    assert simple.WorklistEffect.advance_current(worklist="items", exhausted="done") == simple.WorklistEffect(
        worklist="items",
        advance=True,
        exhausted="done",
    )
    assert simple.WorklistEffect.complete_and_advance(worklist="items", exhausted="done") == simple.WorklistEffect(
        worklist="items",
        set_current_status="completed",
        advance=True,
        exhausted="done",
    )

    assert refresh_route.on_taken is not None
    refresh_effect = refresh_route.on_taken(object())
    assert isinstance(refresh_effect, simple.Effects)
    assert refresh_effect.worklists == (simple.WorklistEffect(worklist="items", refresh=True),)

    assert complete_route.on_taken is not None
    complete_effect = complete_route.on_taken(object())
    assert isinstance(complete_effect, simple.Effects)
    assert complete_effect.worklists == (
        simple.WorklistEffect(worklist="items", set_current_status="completed"),
    )

    assert complete_and_advance_route.on_taken is not None
    complete_and_advance_effect = complete_and_advance_route.on_taken(object())
    assert isinstance(complete_and_advance_effect, simple.Effects)
    assert complete_and_advance_effect.worklists == (
        simple.WorklistEffect(worklist="items", set_current_status="completed", advance=True, exhausted="done"),
    )


def test_effect_bundle_accepts_runtime_controls_as_event_overrides() -> None:
    request_effect = simple.Effects(event=simple.RequestInput("Need approval?"))
    goto_effect = simple.Effects(event=simple.Goto("publish", reason="Workflow policy redirected the run."))
    fail_effect = simple.Effects(event=simple.Fail("Stop the workflow."))

    assert simple.Effects.then("next") == simple.Effects(event="next")
    assert isinstance(request_effect.event, simple.RequestInput)
    assert request_effect.event.question == "Need approval?"
    assert isinstance(goto_effect.event, simple.Goto)
    assert goto_effect.event.target == "publish"
    assert isinstance(fail_effect.event, simple.Fail)
    assert fail_effect.event.reason == "Stop the workflow."


def test_validation_step_lowers_to_python_step_with_feedback_write_and_optional_failed_route() -> None:
    feedback = simple.Md("feedback")

    @simple.validation_step(
        name="validate_manifest",
        feedback=feedback,
        routes={"repair": simple.FINISH},
        failed=simple.FAIL,
    )
    def validate_manifest(_ctx):
        return simple.ValidationResult.valid()

    assert isinstance(validate_manifest, simple.PythonStepDeclaration)
    assert validate_manifest.writes == (feedback,)
    assert validate_manifest.routes == {"repair": simple.FINISH}
    assert getattr(validate_manifest, "implicit_routes") == {"failed": simple.FAIL}


def test_validation_result_helpers_render_expected_shape() -> None:
    valid = simple.ValidationResult.valid()
    invalid = simple.ValidationResult.invalid(
        "Fix the draft.",
        details=("Add references.", "Resolve TODOs."),
    )

    assert valid.ok is True
    assert valid.message is None
    assert invalid.ok is False
    assert invalid.message == "Fix the draft."
    assert invalid.details == ("Add references.", "Resolve TODOs.")


def test_simple_authoring_examples_preserve_route_sentinel_contracts() -> None:
    class AuthoringChildWorkflow(simple.Workflow):
        @simple.python_step(routes={"done": simple.FINISH})
        def capture(_ctx):
            return simple.Event("done")

    class PublicAuthoringWorkflow(simple.Workflow):
        draft = simple.step(
            "Draft the note.",
            name="draft",
            writes=[simple.Md("draft")],
        )
        review = simple.produce_verify_step(
            producer_prompt="Review {draft.draft}.",
            verifier_prompt="Decide whether it is ready.",
            name="review",
            producer_writes=[simple.Md("candidate")],
            verifier_writes=[simple.Md("decision")],
        )
        publish = simple.python_step(
            lambda _ctx: simple.Event("done"),
            name="publish",
            routes={
                "done": simple.FINISH,
                "question": simple.AWAIT_INPUT,
                "failed": simple.FAIL,
                "repair": simple.Route(target=simple.SELF, summary="retry once"),
            },
            control_routes=False,
        )
        child = simple.workflow_step(AuthoringChildWorkflow, name="child")

    compiled = compile_workflow(PublicAuthoringWorkflow)

    assert tuple(compiled.steps) == ("draft", "review", "publish", "child")
    assert compiled.routes["draft"]["done"].target == "review"
    assert compiled.routes["review"]["accepted"].target == "publish"
    assert compiled.routes["review"]["needs_rework"].target == "review"
    assert compiled.routes["publish"]["done"].target == "FINISH"
    assert compiled.routes["publish"]["question"].target == "AWAIT_INPUT"
    assert compiled.routes["publish"]["failed"].target == "FAIL"
    assert compiled.routes["publish"]["repair"].target == "publish"
    assert compiled.routes["publish"]["repair"].summary == "retry once"
    assert compiled.routes["child"]["done"].target == "FINISH"


def test_removed_root_public_symbols_fail_to_import() -> None:
    for symbol in (
        "PAUSE",
        "SU" + "CCESS",
        "Route" + "Info",
        REMOVED_STRICT_WORKFLOW,
        REMOVED_WORKFLOW_STEP,
        REMOVED_AFTER_HOOK_RESULT,
        "ResolvedArtifacts",
        "Checkpoint",
        "ChildWorkflowResult",
        "chain",
        REMOVED_REVIEW_STEP,
        REMOVED_DO_REVIEW_STEP,
        REMOVED_SYSTEM_STEP_ALIAS,
        REMOVED_PARAM,
    ):
        with pytest.raises(ImportError):
            _import_from("botlane", symbol)


def test_removed_simple_aliases_are_absent() -> None:
    for symbol in (
        REMOVED_STRICT_WORKFLOW,
        "chain",
        REMOVED_REVIEW_STEP,
        REMOVED_DO_REVIEW_STEP,
        REMOVED_SYSTEM_STEP_ALIAS,
        REMOVED_PARAM,
        REMOVED_AFTER_HOOK_RESULT,
        "Checkpoint",
        "ChildWorkflowResult",
        "ResolvedArtifacts",
        REMOVED_WORKFLOW_STEP,
    ):
        assert not hasattr(simple, symbol)
    assert not hasattr(simple.Route, "complete")


def test_removed_simple_symbols_fail_to_import() -> None:
    for symbol in (
        REMOVED_AFTER_HOOK_RESULT,
        "Checkpoint",
        "ChildWorkflowResult",
        "ResolvedArtifacts",
        REMOVED_WORKFLOW_STEP,
    ):
        with pytest.raises(ImportError):
            _import_from("botlane.simple", symbol)


def test_operation_surface_singletons_expose_public_runtime_types() -> None:
    assert repr(simple.llm) == "LLMOperation()"
    assert repr(simple.classify) == "ClassifyOperation()"
    assert isinstance(simple.llm, simple.LLMOperation)
    assert isinstance(simple.classify, simple.ClassifyOperation)


def test_runtime_control_exports_are_canonical_and_validate_basic_fields() -> None:
    assert botlane.RequestInput(question="What changed?").question == "What changed?"
    assert botlane.Goto(target="publish").target == "publish"
    assert botlane.Fail(reason="stop").reason == "stop"

    with pytest.raises(ValueError):
        botlane.RequestInput(question="  ")

    with pytest.raises(ValueError):
        botlane.Fail(reason="  ")


def test_child_workflow_result_keeps_positional_constructor_and_path_fields(tmp_path: Path) -> None:
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_demo"
    run_folder = workflow_folder / "runs" / "run-1"
    package_folder = tmp_path / "workflows" / "demo"
    request_file = run_folder / "request.md"
    run_meta_file = run_folder / "run.json"
    events_file = run_folder / "events.jsonl"
    checkpoint_file = run_folder / "checkpoint.json"
    sessions_dir = run_folder / "sessions"
    trace_file = run_folder / "trace.jsonl"
    raw_dir = run_folder / "raw"
    parent_file = run_folder / "parent.json"
    output_artifacts = {"report": run_folder / "report.md"}
    metadata = {"source": "child"}

    result = ChildWorkflowResult(
        "demo",
        "run-1",
        simple.FINISH,
        "success",
        simple.Event("done"),
        {"score": 1},
        output_artifacts,
        task_folder,
        workflow_folder,
        run_folder,
        package_folder,
        request_file,
        run_meta_file,
        events_file,
        checkpoint_file,
        sessions_dir,
        trace_file,
        raw_dir,
        parent_file,
        {"summary": "ok"},
        {},
        metadata,
        None,
    )

    assert result.workflow_name == "demo"
    assert result.task_folder == task_folder
    assert result.workflow_folder == workflow_folder
    assert result.run_folder == run_folder
    assert result.package_folder == package_folder
    assert result.request_file == request_file
    assert result.run_meta_file == run_meta_file
    assert result.events_file == events_file
    assert result.checkpoint_file == checkpoint_file
    assert result.sessions_dir == sessions_dir
    assert result.trace_file == trace_file
    assert result.raw_dir == raw_dir
    assert result.parent_file == parent_file
    assert dict(result.artifacts) == output_artifacts
    assert result.metadata == metadata


def test_core_top_level_surface_excludes_quarantined_legacy_names() -> None:
    for symbol in (
        REMOVED_AFTER_HOOK_RESULT,
        REMOVED_LLM_STEP,
        REMOVED_PAIR_STEP,
        REMOVED_PARAM,
        "PAUSE",
        "Route" + "Info",
        REMOVED_STATE_VAR,
        "SU" + "CCESS",
        REMOVED_SYSTEM_STEP,
        REMOVED_WORKFLOW_STEP,
    ):
        assert not hasattr(core, symbol)
        with pytest.raises(ImportError):
            _import_from("core", symbol)

    for symbol in (
        "Artifact",
        "AWAIT_INPUT",
        "Context",
        "FAIL",
        "FINISH",
        "GLOBAL",
        "Prompt",
        "Route",
        "Workflow",
    ):
        assert _import_from("botlane.core", symbol) is getattr(core, symbol)


def test_core_module_identity_remains_canonical() -> None:
    import botlane.core.workflow_capabilities as core_capabilities

    assert core.validation is core_validation
    assert core.steps is core_steps
    assert core_capabilities.__name__ == "botlane.core.workflow_capabilities"
    assert core.Workflow is _import_from("botlane.core", "Workflow")
    assert core_steps.Step is _import_from("botlane.core.steps", "Step")


def test_legacy_core_import_usage_is_absent_from_active_python_files() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    forbidden_patterns = (
        re.compile(r"\bfrom\s+core\._compat(?:\.|\s+import\b)"),
        re.compile(r"\bimport\s+core\._compat(?:\.|\b)"),
    )
    candidates = (
        "botlane",
        "core",
        "extensions",
        "stdlib",
        "runtime",
        "workflows",
        "tests/fixtures",
        "tests/runtime",
        "tests/unit",
        "tests/contract",
    )
    matches: list[str] = []

    for relative_root in candidates:
        root = repo_root / relative_root
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            if any(pattern.search(text) for pattern in forbidden_patterns):
                matches.append(path.relative_to(repo_root).as_posix())

    assert matches == []


def test_canonical_simple_signatures_expose_only_canonical_argument_names() -> None:
    assert tuple(inspect.signature(simple.step).parameters) == (
        "prompt",
        "name",
        "reads",
        "requires",
        "writes",
        "scope",
        "item_state",
        "routes",
        "before",
        "after",
        "control_schema",
        "retry",
        "session",
        "control_routes",
        "policy",
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
        "scope",
        "routes",
        "state",
        "item_state",
        "before_producer",
        "after_producer",
        "before_verifier",
        "after_verifier",
        "control_schema",
        "retry",
        "session",
        "verifier_session",
        "control_routes",
        "policy",
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
        "control_routes",
        "policy",
    )
    assert tuple(inspect.signature(simple.parallel).parameters) == (
        "branches",
        "name",
        "concurrency",
        "settle",
        "fan_in",
        "outcome",
        "success_routes",
        "routes",
    )
    assert tuple(inspect.signature(simple.fan_out).parameters) == (
        "step",
        "branches",
        "name",
        "concurrency",
        "settle",
        "fan_in",
        "outcome",
        "success_routes",
        "routes",
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
            **{REMOVED_VERIFIER_WRITES: [simple.Md("report")]},
        )

    with pytest.raises(TypeError):
        simple.Route.to(simple.FINISH, **{"required_" + "outputs": ("note",)})

    with pytest.raises(TypeError):
        simple.step("Draft the note.", on_route=lambda ctx: None)

    with pytest.raises(TypeError):
        simple.produce_verify_step(
            producer_prompt="draft",
            verifier_prompt="verify",
            on_route=lambda ctx: None,
        )

    with pytest.raises(TypeError):
        simple.python_step(lambda ctx: None, on_route=lambda ctx: None)


def test_core_step_constructors_reject_removed_on_route_keyword() -> None:
    with pytest.raises(TypeError):
        core_steps.PromptStep(name="ask", producer="ask.md", on_route=lambda ctx: None)

    with pytest.raises(TypeError):
        core_steps.ProduceVerifyStep(
            name="review",
            producer="draft.md",
            verifier="verify.md",
            on_route=lambda ctx: None,
        )

    with pytest.raises(TypeError):
        core_steps.PythonStep(name="publish", on_route=lambda ctx: None)


def test_core_pair_step_constructor_rejects_removed_legacy_hook_keywords() -> None:
    with pytest.raises(TypeError):
        core_steps.ProduceVerifyStep(
            name="review",
            producer="draft.md",
            verifier="verify.md",
            before_do=lambda ctx: None,
        )

    with pytest.raises(TypeError):
        core_steps.ProduceVerifyStep(
            name="review",
            producer="draft.md",
            verifier="verify.md",
            review_session=core_steps.Session.run(),
        )


def test_simple_python_step_does_not_install_legacy_on_step_alias() -> None:
    class PublicWorkflow(simple.Workflow):
        @simple.python_step(name="inspect")
        def inspect(ctx):
            return None

    assert "on_inspect" not in PublicWorkflow.__dict__


def test_simple_workflow_rejects_legacy_class_level_handler_methods() -> None:
    with pytest.raises(
        WorkflowValidationError,
        match="simple workflows must declare lifecycle and step behavior on explicit step declarations",
    ):

        class LegacyHandlersWorkflow(simple.Workflow):
            ask = simple.step("Ask the model.")

            @staticmethod
            def on_ask(state, outcome, artifacts):
                return state

            @staticmethod
            def on_start(ctx):
                return None

            @staticmethod
            def on_outcome(state, outcome):
                return None

        compile_workflow(LegacyHandlersWorkflow)


def test_simple_declarations_store_only_canonical_write_fields() -> None:
    step_decl = simple.step("Draft the note.", writes=[simple.Md("note")])
    pair_decl = simple.produce_verify_step(
        producer_prompt="Draft.",
        verifier_prompt="Verify.",
        producer_writes=[simple.Md("draft")],
        verifier_writes=[simple.Md("decision")],
    )

    assert "outputs" not in vars(step_decl)
    assert "outputs" not in vars(pair_decl)
    assert "review_outputs" not in vars(pair_decl)
    assert hasattr(step_decl, "writes")
    assert hasattr(pair_decl, "writes")
    assert hasattr(pair_decl, "verifier_writes")


def test_simple_policy_authoring_surfaces_preserve_policy_objects_on_declarations_and_lowered_steps() -> None:
    workflow_policy = simple.Policy(permission_mode=simple.PermissionMode.FULL_AUTO_SANDBOXED)
    step_policy = simple.Policy(permission_mode=simple.PermissionMode.ASK)

    class PolicyWorkflow(simple.Workflow):
        policy = workflow_policy
        draft = simple.step("Draft the note.", policy=step_policy)

        @simple.python_step(policy=step_policy)
        def publish(_ctx):
            return simple.Event("done")

    definition = get_workflow_definition(PolicyWorkflow)

    assert PolicyWorkflow.policy is workflow_policy
    assert definition.workflow_policy is workflow_policy
    assert definition.steps_by_name["draft"].provider_policy is step_policy
    assert definition.steps_by_name["publish"].provider_policy is step_policy


def test_simple_workflow_policy_must_be_a_provider_policy() -> None:
    class InvalidPolicyWorkflow(simple.Workflow):
        policy = "ask"
        draft = simple.step("Draft the note.")

    with pytest.raises(
        WorkflowValidationError,
        match=r"InvalidPolicyWorkflow\.policy must be a Policy or core provider policy object",
    ):
        get_workflow_definition(InvalidPolicyWorkflow)


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
            verifier_prompt=simple.Prompt.inline("Verify with {review.state.visits} and {review.state.attempts}."),
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
    assert not hasattr(compiled.steps["review"], "on_route_hook")
    assert compiled.steps["prepare"].step_state_fields == ("visits", "last_route", "last_reason")
    assert set(compiled.steps["review"].step_state_fields) == {
        "visits",
        "last_route",
        "last_reason",
        "rework_count",
        "replan_count",
        "attempts",
        "history",
    }


def test_parallel_branch_group_compiles_as_one_external_step_with_ordered_internal_specs() -> None:
    class BranchGroupWorkflow(simple.Workflow):
        class State(BaseModel):
            approved: bool = False

        reviews = simple.parallel(
            branches={
                "security": simple.step("Review {branch.name}.", name="security_review", session=simple.Session.fresh()),
                "cost": simple.step("Review {branch.group}.", name="cost_review", session=simple.Session.fresh()),
            },
            fan_in=simple.python_step(lambda ctx: simple.Event("done"), name="combine_reviews"),
        )
        publish = simple.python_step(lambda ctx: simple.Event("done"))

    compiled = compile_workflow(BranchGroupWorkflow)
    definition = get_workflow_definition(BranchGroupWorkflow)

    assert compiled.entry_step_name == "reviews"
    assert tuple(compiled.steps) == ("reviews", "publish")
    assert compiled.steps["reviews"].kind == "branch_group"
    assert isinstance(definition.steps_by_name["reviews"].branch_group, BranchGroupDeclarationSpec)
    assert compiled.steps["reviews"].branch_group is not None
    assert "security_review" not in compiled.steps
    assert "cost_review" not in compiled.steps
    assert "security_review" not in compiled.routes
    assert "cost_review" not in compiled.routes
    assert route_target_value(compiled.routes["reviews"]["done"].target) == "publish"
    branch_group = compiled.steps["reviews"].branch_group
    assert branch_group is not None
    assert branch_group.kind == "parallel"
    assert branch_group.composite_route_tags == ("done",)
    assert tuple(branch.name for branch in branch_group.branches) == ("security", "cost")
    assert tuple(branch.index for branch in branch_group.branches) == (0, 1)
    assert tuple(branch.step.name for branch in branch_group.branches) == ("security_review", "cost_review")
    assert branch_group.fan_in_step is not None
    assert branch_group.fan_in_step.name == "combine_reviews"


def test_parallel_branch_group_propagates_explicit_fan_in_routes_to_outer_routes() -> None:
    class FanInRoutesWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        assess = simple.parallel(
            branches={
                "security": simple.step("Review {branch.name}.", name="security_review", session=simple.Session.fresh()),
            },
            fan_in=simple.step(
                "Summarize {fan_in.context_text}.",
                name="synthesize_reviews",
                routes={"approved": simple.FINISH, "needs_revision": simple.SELF},
            ),
        )

    compiled = compile_workflow(FanInRoutesWorkflow)

    assert compiled.steps["assess"].available_routes == ("approved", "needs_revision")
    assert compiled.routes["assess"]["approved"].target == "FINISH"
    assert compiled.routes["assess"]["needs_revision"].target == "assess"


def test_parallel_branch_group_without_fan_in_materializes_mechanical_outcome_routes() -> None:
    class MechanicalOutcomeWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        assess = simple.parallel(
            branches={
                "security": simple.python_step(lambda ctx: simple.Event("done"), name="security_review"),
            },
        )
        publish = simple.python_step(lambda ctx: simple.Event("done"))

    compiled = compile_workflow(MechanicalOutcomeWorkflow)

    assert compiled.steps["assess"].available_routes == ("done", "partial", "question", "failed")
    assert compiled.routes["assess"]["done"].target == "publish"
    assert compiled.routes["assess"]["partial"].target == "publish"
    assert compiled.routes["assess"]["question"].target == "AWAIT_INPUT"
    assert compiled.routes["assess"]["failed"].target == "FAIL"


def test_fan_out_branch_group_preserves_branch_inputs_and_order() -> None:
    class FanOutWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        assess = simple.fan_out(
            step=simple.step(
                "Assess {branch.input.area}.",
                name="assess_one",
                session=simple.Session.fresh(),
            ),
            branches={
                "security": {"area": "security"},
                "performance": {"area": "performance"},
            },
        )

    compiled = compile_workflow(FanOutWorkflow)

    branch_group = compiled.steps["assess"].branch_group
    assert branch_group is not None
    assert branch_group.kind == "fan_out"
    assert tuple(branch.name for branch in branch_group.branches) == ("security", "performance")
    assert tuple(branch.index for branch in branch_group.branches) == (0, 1)
    assert tuple(branch.input for branch in branch_group.branches) == (
        {"area": "security"},
        {"area": "performance"},
    )
    assert tuple(branch.step.name for branch in branch_group.branches) == ("assess_one", "assess_one")


@pytest.mark.parametrize(
    "fan_in_factory",
    [
        lambda: simple.step("Summarize {fan_in.context_text}.", name="fan_in_prompt"),
        lambda: simple.produce_verify_step(
            producer_prompt="Draft from {fan_in.results_path}.",
            verifier_prompt="Verify from {fan_in.context_path}.",
            name="fan_in_pair",
        ),
        lambda: simple.python_step(lambda ctx: simple.Event("done"), name="fan_in_python"),
    ],
)
def test_branch_group_fan_in_accepts_supported_step_kinds(fan_in_factory) -> None:
    class FanInWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        assess = simple.parallel(
            branches={
                "a": simple.python_step(lambda ctx: simple.Event("done"), name="branch_a"),
            },
            fan_in=fan_in_factory(),
        )

    compiled = compile_workflow(FanInWorkflow)

    assert compiled.steps["assess"].kind == "branch_group"
    assert compiled.steps["assess"].branch_group is not None
    assert compiled.steps["assess"].branch_group.fan_in_step is not None


@pytest.mark.parametrize(
    "fan_in_factory",
    [
        lambda: simple.llm.step(prompt="Classify {fan_in.branch_count}.", name="fan_in_llm_operation"),
        lambda: simple.classify.step(
            prompt="Choose one from {fan_in.branch_count}.",
            choices=("yes", "no"),
            name="fan_in_classify_operation",
        ),
    ],
)
def test_branch_group_rejects_operation_fan_in_steps(fan_in_factory) -> None:
    with pytest.raises(WorkflowValidationError, match="unsupported fan-in step .* kind 'operation'"):

        class InvalidOperationFanInWorkflow(simple.Workflow):
            class State(BaseModel):
                pass

            assess = simple.parallel(
                branches={
                    "a": simple.python_step(lambda ctx: simple.Event("done"), name="branch_a"),
                },
                fan_in=fan_in_factory(),
            )

        compile_workflow(InvalidOperationFanInWorkflow)


def test_branch_group_fan_in_helpers_are_rejected_outside_fan_in() -> None:
    with pytest.raises(WorkflowValidationError, match="only valid inside fan-in"):

        class InvalidHelperWorkflow(simple.Workflow):
            class State(BaseModel):
                pass

            ask = simple.step("Draft.", reads=[simple.FanIn.results()])

        compile_workflow(InvalidHelperWorkflow)


def test_branch_group_fan_in_context_helper_is_rejected_outside_fan_in() -> None:
    with pytest.raises(WorkflowValidationError, match="only valid inside fan-in"):

        class InvalidContextHelperWorkflow(simple.Workflow):
            class State(BaseModel):
                pass

            ask = simple.step("Draft.", requires=[simple.FanIn.context()])

        compile_workflow(InvalidContextHelperWorkflow)


def test_branch_placeholder_is_rejected_outside_branch_steps() -> None:
    with pytest.raises(WorkflowValidationError, match="only valid inside branch steps"):

        class InvalidBranchPlaceholderWorkflow(simple.Workflow):
            class State(BaseModel):
                pass

            ask = simple.step("Draft {branch.name}.")

        compile_workflow(InvalidBranchPlaceholderWorkflow)


def test_fan_in_placeholder_is_rejected_outside_fan_in_steps() -> None:
    with pytest.raises(WorkflowValidationError, match="only valid inside fan-in steps"):

        class InvalidFanInPlaceholderWorkflow(simple.Workflow):
            class State(BaseModel):
                pass

            ask = simple.step("Draft {fan_in.context_text}.")

        compile_workflow(InvalidFanInPlaceholderWorkflow)


def test_simple_workflow_accepts_supported_ctx_prompt_bindings() -> None:
    class CtxWorkflow(simple.Workflow):
        class Input(BaseModel):
            topic: str

        class Params(BaseModel):
            mode: str = "brief"

        class State(BaseModel):
            status: str = "draft"

        review = simple.step(
            "Message={ctx.message}; Request={ctx.request.text}; File={ctx.request.file}; "
            "TaskFile={ctx.request.task_file}; RequestFile={ctx.request_file}; Topic={ctx.input.topic}; "
            "Status={ctx.state.status}; Mode={ctx.params.mode}; Run={ctx.run.id}; Workflow={ctx.workflow.folder}"
        )

    compiled = compile_workflow(CtxWorkflow)

    assert compiled.steps["review"].name == "review"


def test_simple_workflow_accepts_input_message_prompt_binding() -> None:
    class InputMessageWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        review = simple.step("Message={input.message}")

    compiled = compile_workflow(InputMessageWorkflow)

    assert compiled.steps["review"].name == "review"


def test_simple_workflow_accepts_ctx_input_message_prompt_binding() -> None:
    class CtxInputMessageWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        review = simple.step("Message={ctx.input.message}")

    compiled = compile_workflow(CtxInputMessageWorkflow)

    assert compiled.steps["review"].name == "review"


@pytest.mark.parametrize(
    ("placeholder", "message"),
    [
        ("{message}", r"simple step 'review' prompt placeholder \{message\} is unknown; use \{ctx\.message\}"),
        ("{ctx}", r"simple step 'review' prompt placeholder \{ctx\} must qualify a runtime context field"),
        ("{ctx.request}", r"simple step 'review' prompt placeholder \{ctx\.request\} must qualify a request field"),
        ("{ctx.input}", r"simple step 'review' prompt placeholder \{ctx\.input\} must qualify a input field"),
        ("{ctx.state}", r"simple step 'review' prompt placeholder \{ctx\.state\} must qualify a state field"),
        ("{ctx.params}", r"simple step 'review' prompt placeholder \{ctx\.params\} must qualify a params field"),
        ("{ctx.input.missing}", r"simple step 'review' prompt placeholder \{ctx\.input\.missing\} references unknown Input field 'missing'"),
        ("{ctx.state.missing}", r"simple step 'review' prompt placeholder \{ctx\.state\.missing\} references unknown State field 'missing'"),
        ("{ctx.params.missing}", r"simple step 'review' prompt placeholder \{ctx\.params\.missing\} references unknown Params field 'missing'"),
        ("{ctx.__dict__}", r"simple step 'review' prompt placeholder \{ctx\.__dict__\} is not a supported safe dotted path"),
        ("{ctx.message.upper()}", r"simple step 'review' prompt placeholder \{ctx\.message\.upper\(\)\} is not a supported safe dotted path"),
        ("{ctx.request.file.read_text()}", r"simple step 'review' prompt placeholder \{ctx\.request\.file\.read_text\(\)\} is not a supported safe dotted path"),
        ("{ctx.values.foo}", r"simple step 'review' prompt placeholder \{ctx\.values\.foo\} is not a supported safe dotted path"),
        ("{ctx.artifacts.foo}", r"simple step 'review' prompt placeholder \{ctx\.artifacts\.foo\} is not a supported safe dotted path"),
    ],
)
def test_simple_workflow_rejects_invalid_ctx_prompt_bindings(placeholder: str, message: str) -> None:
    class InvalidCtxWorkflow(simple.Workflow):
        class Input(BaseModel):
            topic: str

        class Params(BaseModel):
            mode: str = "brief"

        class State(BaseModel):
            status: str = "draft"

        review = simple.step(placeholder)

    with pytest.raises(WorkflowValidationError, match=message):
        compile_workflow(InvalidCtxWorkflow)


def test_provider_backed_branch_steps_require_explicit_fresh_sessions_only_inside_branch_groups() -> None:
    class TopLevelWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        ask = simple.step("Draft without explicit session.")

    assert compile_workflow(TopLevelWorkflow).steps["ask"].session_name == "global"

    with pytest.raises(WorkflowValidationError, match="without explicit session=Session\\.fresh\\(\\)"):

        class MissingFreshSessionWorkflow(simple.Workflow):
            class State(BaseModel):
                pass

            assess = simple.parallel(
                branches={
                    "a": simple.step("Draft branch.", name="branch_prompt"),
                }
            )

        compile_workflow(MissingFreshSessionWorkflow)

    with pytest.raises(WorkflowValidationError, match="non-fresh session continuity 'run'"):

        class NonFreshSessionWorkflow(simple.Workflow):
            class State(BaseModel):
                pass

            assess = simple.parallel(
                branches={
                    "a": simple.step("Draft branch.", name="branch_prompt", session=simple.Session.run()),
                }
            )

        compile_workflow(NonFreshSessionWorkflow)


def test_branch_group_rejects_non_fresh_verifier_sessions_inside_branch_groups() -> None:
    with pytest.raises(WorkflowValidationError, match="non-fresh verifier_session continuity 'run'"):

        class InvalidVerifierSessionWorkflow(simple.Workflow):
            class State(BaseModel):
                pass

            assess = simple.parallel(
                branches={
                    "a": simple.produce_verify_step(
                        producer_prompt="Draft branch.",
                        verifier_prompt="Verify branch.",
                        name="branch_pair",
                        session=simple.Session.fresh(),
                        verifier_session=simple.Session.run(),
                    ),
                }
            )

        compile_workflow(InvalidVerifierSessionWorkflow)


def test_branch_group_rejects_unsafe_names_child_workflow_fan_in_and_non_serializable_fan_out_inputs() -> None:
    with pytest.raises(WorkflowValidationError, match="branch group name .* must be path-safe"):

        class InvalidBranchGroupNameWorkflow(simple.Workflow):
            class State(BaseModel):
                pass

            assess = simple.parallel(
                name="../unsafe",
                branches={"a": simple.python_step(lambda ctx: simple.Event("done"), name="branch_a")},
            )

        compile_workflow(InvalidBranchGroupNameWorkflow)

    with pytest.raises(WorkflowValidationError, match="branch name .* must be path-safe"):

        class InvalidBranchNameWorkflow(simple.Workflow):
            class State(BaseModel):
                pass

            assess = simple.parallel(
                branches={"../unsafe": simple.python_step(lambda ctx: simple.Event("done"), name="branch_a")},
            )

        compile_workflow(InvalidBranchNameWorkflow)

    class Child(simple.Workflow):
        class State(BaseModel):
            pass

        finish = simple.python_step(lambda ctx: simple.Event("done"))

    with pytest.raises(WorkflowValidationError, match="child workflow branch step"):

        class InvalidBranchStepWorkflow(simple.Workflow):
            class State(BaseModel):
                pass

            assess = simple.parallel(
                branches={"a": simple.workflow_step(Child, name="child_branch")},
            )

        compile_workflow(InvalidBranchStepWorkflow)

    with pytest.raises(WorkflowValidationError, match="scoped branch step"):

        class InvalidScopedBranchStepWorkflow(simple.Workflow):
            class State(BaseModel):
                pass

            queue = simple.Worklist.from_items(
                name="queue",
                items=["a"],
                item_id=lambda item: item,
                title=lambda item: item,
            )
            assess = simple.parallel(
                branches={
                    "a": simple.step(
                        "Draft branch.",
                        name="scoped_branch",
                        session=simple.Session.fresh(),
                        scope=queue,
                    ),
                }
            )

        compile_workflow(InvalidScopedBranchStepWorkflow)

    with pytest.raises(WorkflowValidationError, match="operation branch step"):

        class InvalidOperationBranchStepWorkflow(simple.Workflow):
            class State(BaseModel):
                pass

            assess = simple.parallel(
                branches={
                    "a": simple.classify.step(
                        prompt="Choose one.",
                        choices=("yes", "no"),
                        name="branch_operation",
                    ),
                }
            )

        compile_workflow(InvalidOperationBranchStepWorkflow)

    with pytest.raises(WorkflowValidationError, match="child workflow fan-in step"):

        class InvalidFanInWorkflow(simple.Workflow):
            class State(BaseModel):
                pass

            assess = simple.parallel(
                branches={"a": simple.python_step(lambda ctx: simple.Event("done"), name="branch_a")},
                fan_in=simple.workflow_step(Child, name="join_child"),
            )

        compile_workflow(InvalidFanInWorkflow)

    with pytest.raises(WorkflowValidationError, match="must be JSON-serializable"):

        class InvalidFanOutInputWorkflow(simple.Workflow):
            class State(BaseModel):
                pass

            assess = simple.fan_out(
                step=simple.python_step(lambda ctx: simple.Event("done"), name="branch_a"),
                branches={"a": {1, 2, 3}},
            )

        compile_workflow(InvalidFanOutInputWorkflow)


def test_branch_group_compile_cache_is_bypassed() -> None:
    class BranchGroupCacheWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        reviews = simple.parallel(
            branches={
                "security": simple.step("Review security.", name="security_review", session=simple.Session.fresh()),
            }
        )

    first = compile_workflow(BranchGroupCacheWorkflow)
    second = compile_workflow(BranchGroupCacheWorkflow)

    assert first is not second
    assert first.topology_hash == second.topology_hash


def test_branch_group_placeholder_root_matching_is_exact() -> None:
    with pytest.raises(WorkflowValidationError, match="references unknown step 'branching'"):

        class InvalidExactRootWorkflow(simple.Workflow):
            class State(BaseModel):
                pass

            ask = simple.step("Draft {branching.name}.")

        compile_workflow(InvalidExactRootWorkflow)


def test_fan_in_placeholder_root_matching_is_exact() -> None:
    with pytest.raises(WorkflowValidationError, match="references unknown step 'fan_inish'"):

        class InvalidFanInExactRootWorkflow(simple.Workflow):
            class State(BaseModel):
                pass

            ask = simple.step("Draft {fan_inish.context_text}.")

        compile_workflow(InvalidFanInExactRootWorkflow)


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

    assert set(compiled.routes["start"]) == {"done", "question"}
    assert compiled.routes["start"]["done"].target == "review"
    assert set(compiled.routes["review"]) == {"accepted", "needs_rework", "question"}
    assert compiled.routes["review"]["accepted"].target == "decide"
    assert compiled.routes["review"]["needs_rework"].target == "review"
    assert set(compiled.routes["decide"]) == {"done"}
    assert compiled.routes["decide"]["done"].target == "child"
    assert set(compiled.routes["child"]) == {"done"}
    assert compiled.routes["child"]["done"].target == "verdict"
    assert set(compiled.routes["verdict"]) == {"done"}
    assert compiled.routes["verdict"]["done"].target == "FINISH"
    assert compiled.steps["start"].runtime_control_routes == ("question",)
    assert compiled.steps["review"].runtime_control_routes == ("question",)
    assert compiled.steps["decide"].runtime_control_routes == ()
    assert compiled.steps["child"].runtime_control_routes == ()


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


def test_produce_verify_step_accepts_statevar_mapping_sugar() -> None:
    class ReviewWorkflow(simple.Workflow):
        review = simple.produce_verify_step(
            producer_prompt="Draft.",
            verifier_prompt="Verify with {review.state.attempts} and {review.state.selected_risk}.",
            state={
                "attempts": simple.StateVar(0),
                "selected_risk": simple.StateVar[str | None](None),
            },
        )

    compiled = compile_workflow(ReviewWorkflow)

    assert set(compiled.steps["review"].step_state_fields) == {
        "visits",
        "last_route",
        "last_reason",
        "rework_count",
        "replan_count",
        "attempts",
        "selected_risk",
    }


def test_produce_verify_step_rejects_non_statevar_mappings() -> None:
    class BadWorkflow(simple.Workflow):
        review = simple.produce_verify_step(
            producer_prompt="Draft.",
            verifier_prompt="Verify.",
            state={"attempts": 0},
        )

    with pytest.raises(
        WorkflowValidationError,
        match="state field 'attempts' must be declared with StateVar",
    ):
        compile_workflow(BadWorkflow)


def test_produce_verify_step_rejects_ambiguous_statevar_none_defaults() -> None:
    with pytest.raises(ValueError, match="StateVar\\(None\\) is ambiguous"):
        simple.StateVar(None)


def test_produce_verify_step_rejects_mutable_statevar_defaults_without_factory() -> None:
    with pytest.raises(ValueError, match="mutable defaults must use default_factory"):
        simple.StateVar([])


def test_produce_verify_step_accepts_typed_statevar_default_factories() -> None:
    class ReviewWorkflow(simple.Workflow):
        review = simple.produce_verify_step(
            producer_prompt="Draft.",
            verifier_prompt="Verify with {review.state.history}.",
            state={"history": simple.StateVar[list[str]](default_factory=list)},
        )

    compiled = compile_workflow(ReviewWorkflow)

    assert set(compiled.steps["review"].step_state_fields) == {
        "visits",
        "last_route",
        "last_reason",
        "rework_count",
        "replan_count",
        "history",
    }


def test_produce_verify_step_rejects_reserved_custom_state_field_names() -> None:
    class ReviewState(BaseModel):
        last_route: str | None = None

    class BadModelWorkflow(simple.Workflow):
        review = simple.produce_verify_step(
            producer_prompt="Draft.",
            verifier_prompt="Verify.",
            state=ReviewState,
        )

    with pytest.raises(
        WorkflowValidationError,
        match="custom state field 'last_route' conflicts with built-in runtime state",
    ):
        compile_workflow(BadModelWorkflow)

    class BadSugarWorkflow(simple.Workflow):
        review = simple.produce_verify_step(
            producer_prompt="Draft.",
            verifier_prompt="Verify.",
            state={"rework_count": simple.StateVar(0)},
        )

    with pytest.raises(
        WorkflowValidationError,
        match="custom state field 'rework_count' conflicts with built-in runtime state",
    ):
        compile_workflow(BadSugarWorkflow)


def test_simple_workflow_rejects_class_level_transitions_and_flow() -> None:
    class TransitionWorkflow(simple.Workflow):
        start = simple.step(prompt="Start.")
        transitions = {"start": {"done": "finish"}}

    with pytest.raises(
        WorkflowValidationError,
        match="step-local routes and optional entry, not transitions or flow",
    ):
        compile_workflow(TransitionWorkflow)


def test_simple_workflow_accepts_scoped_item_state_prompt_placeholders() -> None:
    class ItemState(BaseModel):
        severity: str = "medium"

    class ItemStateWorkflow(simple.Workflow):
        gates = simple.Worklist.from_items(
            "gate",
            items=({"id": "alpha", "title": "Alpha"},),
            item_state=ItemState,
        )
        start = simple.step(
            prompt=simple.Prompt.inline("Inspect {item.state.status} and {item.state.severity}."),
            scope=gates,
        )

    compiled = compile_workflow(ItemStateWorkflow)

    assert compiled.worklists["gate"].item_state_model is ItemState


def test_simple_workflow_accepts_scoped_runtime_item_prompt_placeholders() -> None:
    class RuntimeItemPromptWorkflow(simple.Workflow):
        gates = simple.Worklist.from_items(
            "gate",
            items=({"id": "alpha", "title": "Alpha", "payload": {"foo": "bar"}},),
        )
        start = simple.step(
            prompt=simple.Prompt.inline("Inspect {item.id}, {item.dir_key}, and {item.payload.foo}."),
            scope=gates,
        )

    compiled = compile_workflow(RuntimeItemPromptWorkflow)

    assert "start" in compiled.steps


def test_simple_workflow_rejects_runtime_item_prompt_placeholders_without_scope() -> None:
    class BadRuntimeItemPromptWorkflow(simple.Workflow):
        start = simple.step(
            prompt=simple.Prompt.inline("Inspect {item.id}."),
        )

    with pytest.raises(
        WorkflowValidationError,
        match="requires scope=... on the same step",
    ):
        compile_workflow(BadRuntimeItemPromptWorkflow)


def test_simple_workflow_accepts_late_bound_worklist_prompt_placeholders() -> None:
    class WorklistPromptWorkflow(simple.Workflow):
        gates = simple.Worklist.from_items(
            "gate",
            items=({"id": "alpha", "title": "Alpha"},),
        )
        start = simple.step(
            prompt=simple.Prompt.inline(
                "Inspect {worklist.gate.current.id}, {worklist.gate.item_ids}, and {worklist.gate.is_exhausted}."
            ),
        )

    compiled = compile_workflow(WorklistPromptWorkflow)

    assert "gate" in compiled.worklists


def test_simple_workflow_rejects_unknown_worklist_prompt_placeholders() -> None:
    class BadWorklistPromptWorkflow(simple.Workflow):
        gates = simple.Worklist.from_items(
            "gate",
            items=({"id": "alpha", "title": "Alpha"},),
        )
        start = simple.step(
            prompt=simple.Prompt.inline("Inspect {worklist.missing.current.id}."),
        )

    with pytest.raises(
        WorkflowValidationError,
        match="references unknown worklist 'missing'",
    ):
        compile_workflow(BadWorklistPromptWorkflow)


def test_simple_workflow_rejects_unknown_scoped_item_state_prompt_fields() -> None:
    class ItemState(BaseModel):
        severity: str = "medium"

    class BadItemStateWorkflow(simple.Workflow):
        gates = simple.Worklist.from_items(
            "gate",
            items=({"id": "alpha", "title": "Alpha"},),
            item_state=ItemState,
        )
        start = simple.step(
            prompt=simple.Prompt.inline("Inspect {item.state.missing}."),
            scope=gates,
        )

    with pytest.raises(
        WorkflowValidationError,
        match="unknown item state field 'missing' on worklist 'gate'",
    ):
        compile_workflow(BadItemStateWorkflow)


def test_simple_workflow_rejects_unknown_scoped_step_item_state_prompt_fields() -> None:
    class BadStepItemStateWorkflow(simple.Workflow):
        gates = simple.Worklist.from_items(
            "gate",
            items=({"id": "alpha", "title": "Alpha"},),
        )
        review = simple.step(
            prompt=simple.Prompt.inline("Inspect {review.item_state.missing}."),
            scope=gates,
            item_state={"attempts": simple.StateVar(0)},
        )

    with pytest.raises(
        WorkflowValidationError,
        match="unknown item_state field 'missing' on step 'review'",
    ):
        compile_workflow(BadStepItemStateWorkflow)


def test_simple_workflow_accepts_scoped_step_item_state_prompt_placeholders() -> None:
    class StepItemStateWorkflow(simple.Workflow):
        gates = simple.Worklist.from_items(
            "gate",
            items=({"id": "alpha", "title": "Alpha"},),
        )
        review = simple.step(
            prompt=simple.Prompt.inline("Inspect {review.item_state.attempts} and {review.item_state.visits}."),
            scope=gates,
            item_state={"attempts": simple.StateVar(0)},
        )

    compiled = compile_workflow(StepItemStateWorkflow)

    assert set(compiled.steps["review"].step_item_state_fields) == {
        "visits",
        "last_route",
        "last_reason",
        "attempts",
    }


def test_simple_produce_verify_workflow_step_item_state_includes_producer_verifier_builtins() -> None:
    class StepItemStateWorkflow(simple.Workflow):
        gates = simple.Worklist.from_items(
            "gate",
            items=({"id": "alpha", "title": "Alpha"},),
        )
        review = simple.produce_verify_step(
            producer_prompt="Draft.",
            verifier_prompt=simple.Prompt.inline("Inspect {review.item_state.attempts} and {review.item_state.visits}."),
            scope=gates,
            item_state={"attempts": simple.StateVar(0)},
        )

    compiled = compile_workflow(StepItemStateWorkflow)

    assert set(compiled.steps["review"].step_item_state_fields) == {
        "visits",
        "last_route",
        "last_reason",
        "rework_count",
        "replan_count",
        "attempts",
    }


def test_simple_workflow_rejects_item_state_without_scope() -> None:
    class UnscopedItemStateWorkflow(simple.Workflow):
        review = simple.step(
            prompt="Verify.",
            item_state={"attempts": simple.StateVar(0)},
        )

    with pytest.raises(
        WorkflowValidationError,
        match="item_state requires scope=... on the same step",
    ):
        compile_workflow(UnscopedItemStateWorkflow)


def test_simple_produce_verify_workflow_rejects_item_state_without_scope() -> None:
    class UnscopedItemStateWorkflow(simple.Workflow):
        review = simple.produce_verify_step(
            producer_prompt="Draft.",
            verifier_prompt="Verify.",
            item_state={"attempts": simple.StateVar(0)},
        )

    with pytest.raises(
        WorkflowValidationError,
        match="item_state requires scope=... on the same step",
    ):
        compile_workflow(UnscopedItemStateWorkflow)


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
    assert store.visits == 0
    assert store.last_route is None
    assert store.rework_count == 0
    assert store.replan_count == 0
    assert step_states["review"] is store

    store.visits += 1
    store.last_route = "accepted"
    store.last_reason = "looks good"
    store.rework_count += 1
    store.attempts += 1
    store.history.append("accepted")

    serialized = engine._serialize_step_states(step_states)

    assert serialized == {
        "review": {
            "visits": 1,
            "last_route": "accepted",
            "last_reason": "looks good",
            "rework_count": 1,
            "replan_count": 0,
            "attempts": 1,
            "history": ["accepted"],
        }
    }

    restored_states: dict[str, BaseModel | dict[str, object]] = {"review": serialized["review"]}
    restored = engine._ensure_step_state_store(restored_states, step)

    assert isinstance(restored, ReviewState)
    assert restored.visits == 1
    assert restored.last_route == "accepted"
    assert restored.last_reason == "looks good"
    assert restored.rework_count == 1
    assert restored.replan_count == 0
    assert restored.attempts == 1
    assert restored.history == ["accepted"]
    assert restored_states["review"] is restored


def test_runtime_built_in_step_state_updates_and_checkpoints_for_simple_steps(tmp_path) -> None:
    class PauseWorkflow(simple.Workflow):
        review = simple.produce_verify_step(
            producer_prompt="Draft.",
            verifier_prompt="Verify.",
            routes={"needs_rework": simple.AWAIT_INPUT},
            control_routes=False,
        )

    task_folder = tmp_path / "task"
    run_folder = tmp_path / "run"
    task_folder.mkdir()
    run_folder.mkdir()

    result = Engine(
        compile_workflow(PauseWorkflow),
        provider=ScriptedLLMProvider(
            producer_turns=["draft\n"],
            verifier_turns=[simple.Outcome(raw_output="repair\n", tag="needs_rework", reason="needs repair")],
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == simple.AWAIT_INPUT
    assert result.checkpoint is not None
    assert result.checkpoint.step_states == {
        "review": {
            "visits": 1,
            "last_route": "needs_rework",
            "last_reason": "needs repair",
            "rework_count": 1,
            "replan_count": 0,
        }
    }


def test_runtime_step_state_restores_built_ins_and_custom_fields_on_resume(tmp_path) -> None:
    class ReviewState(BaseModel):
        attempts: int = 0

    def record_attempt(ctx):
        ctx.step_state.attempts += 1

    class ResumeWorkflow(simple.Workflow):
        review = simple.produce_verify_step(
            producer_prompt="Draft.",
            verifier_prompt="Verify.",
            state=ReviewState,
            after_verifier=record_attempt,
            routes={"needs_replan": simple.AWAIT_INPUT},
            control_routes=False,
        )

    task_folder = tmp_path / "task"
    run_folder = tmp_path / "run"
    task_folder.mkdir()
    run_folder.mkdir()

    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        compile_workflow(ResumeWorkflow),
        provider=ScriptedLLMProvider(
            producer_turns=["draft-1\n", "draft-2\n"],
            verifier_turns=[
                simple.Outcome(raw_output="replan-1\n", tag="needs_replan", reason="needs replanning"),
                simple.Outcome(raw_output="replan-2\n", tag="needs_replan", reason="needs more replanning"),
            ],
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    first = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )
    second = engine.resume(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert first.terminal == simple.AWAIT_INPUT
    assert first.checkpoint is not None
    assert first.checkpoint.step_states == {
        "review": {
            "visits": 1,
            "last_route": "needs_replan",
            "last_reason": "needs replanning",
            "rework_count": 0,
            "replan_count": 1,
            "attempts": 1,
        }
    }

    assert second.terminal == simple.AWAIT_INPUT
    assert second.checkpoint is not None
    assert second.checkpoint.step_states == {
        "review": {
            "visits": 2,
            "last_route": "needs_replan",
            "last_reason": "needs more replanning",
            "rework_count": 0,
            "replan_count": 2,
            "attempts": 2,
        }
    }


def test_simple_scoped_item_state_and_step_item_state_restore_on_resume(tmp_path) -> None:
    class ItemState(BaseModel):
        attempts: int = 0

    def record_scoped_state(ctx):
        if ctx.item_state.attempts == 0:
            assert ctx.step_item_state.visits == 1
            assert ctx.step_item_state.last_route is None
            assert ctx.item_state.status == "pending"
            ctx.current_worklist.set_current_status("checkpointed")
        else:
            assert ctx.item_state.status == "checkpointed"
            assert ctx.step_item_state.visits == 2
            assert ctx.step_item_state.last_route == "done"
            ctx.current_worklist.set_current_status("resumed")
        ctx.item_state.attempts += 1
        ctx.step_item_state.attempts += 1

    class ResumeWorkflow(simple.Workflow):
        gates = simple.Worklist.from_items(
            "gate",
            items=({"id": "alpha", "title": "Alpha", "status": "pending"},),
            status="status",
            item_state=ItemState,
        )
        review = simple.step(
            prompt="Review.",
            scope=gates,
            item_state={"attempts": simple.StateVar(0)},
            after=record_scoped_state,
            routes={"done": simple.AWAIT_INPUT},
            control_routes=False,
        )

    task_folder = tmp_path / "task"
    run_folder = tmp_path / "run"
    task_folder.mkdir()
    run_folder.mkdir()

    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        compile_workflow(ResumeWorkflow),
        provider=ScriptedLLMProvider(
            llm_turns=[
                simple.Outcome(raw_output="ok-1\n", tag="done", reason="first pause"),
                simple.Outcome(raw_output="ok-2\n", tag="done", reason="second pause"),
            ]
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    first = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )
    second = engine.resume(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert first.terminal == simple.AWAIT_INPUT
    assert first.checkpoint is not None
    assert first.checkpoint.item_states == {
        "gate:alpha": {
            "status": "checkpointed",
            "last_step": "review",
            "last_route": "done",
            "attempts": 1,
        }
    }
    assert first.checkpoint.step_item_states == {
        "review": {
            "gate:alpha": {
                "visits": 1,
                "last_route": "done",
                "last_reason": "first pause",
                "attempts": 1,
            }
        }
    }

    assert second.terminal == simple.AWAIT_INPUT
    assert second.checkpoint is not None
    assert second.checkpoint.item_states == {
        "gate:alpha": {
            "status": "resumed",
            "last_step": "review",
            "last_route": "done",
            "attempts": 2,
        }
    }
    assert second.checkpoint.step_item_states == {
        "review": {
            "gate:alpha": {
                "visits": 2,
                "last_route": "done",
                "last_reason": "second pause",
                "attempts": 2,
            }
        }
    }


def test_runtime_built_in_step_state_is_available_on_core_steps(tmp_path) -> None:
    class WorkflowState(BaseModel):
        seen_visits: int = 0
        seen_last_route: str | None = None

    class CoreRuntimeWorkflow(core.Workflow):
        State = WorkflowState

        @staticmethod
        def inspect_handler(ctx: Context):
            assert ctx.step_state.visits == 1
            assert ctx.step_state.last_route is None
            assert ctx.step_state.last_reason is None
            ctx.state.seen_visits = ctx.step_state.visits
            ctx.state.seen_last_route = ctx.step_state.last_route
            return simple.Event("done", reason="inspected")

        inspect = core_steps.PythonStep(name="inspect", handler=inspect_handler)
        entry = inspect
        transitions = {inspect: {"done": core.AWAIT_INPUT}}

    task_folder = tmp_path / "task"
    run_folder = tmp_path / "run"
    task_folder.mkdir()
    run_folder.mkdir()

    result = Engine(
        compile_workflow(CoreRuntimeWorkflow),
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == core.AWAIT_INPUT
    assert result.state.seen_visits == 1
    assert result.state.seen_last_route is None
    assert result.checkpoint is not None
    assert result.checkpoint.step_states == {
        "inspect": {
            "visits": 1,
            "last_route": "done",
            "last_reason": "inspected",
        }
    }


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

    assert ctx.step_state.attempts == 0
    with pytest.raises(AttributeError, match="visits is runtime-owned and read-only"):
        ctx.step_state.visits = 2

    with pytest.raises(
        WorkflowExecutionError,
        match="item_state is only available when there is an active scoped worklist item",
    ):
        _ = ctx.item_state

    with pytest.raises(
        WorkflowExecutionError,
        match="step_item_state is only available when there is an active scoped worklist item",
    ):
        _ = ctx.step_item_state


def test_simple_context_exposes_modeled_item_state_surfaces(tmp_path) -> None:
    class WorkflowState(BaseModel):
        approved: bool = False

    class ItemState(BaseModel):
        attempts: int = 0

    class StepItemState(BaseModel):
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
        item_state_store=ItemState(attempts=2),
        step_item_state_store=StepItemState(attempts=2),
    )

    assert ctx.item_state.attempts == 2
    assert ctx.step_item_state.attempts == 2


def test_simple_context_item_state_runtime_fields_are_read_only(tmp_path) -> None:
    class WorkflowState(BaseModel):
        approved: bool = False

    class ItemState(BaseModel):
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
        item_state_store={"status": "active", "last_step": "review", "last_route": "done", "attempts": 2},
    )

    ctx.item_state.attempts = 3
    assert ctx.item_state.attempts == 3
    with pytest.raises(AttributeError, match="status is runtime-owned and read-only"):
        ctx.item_state.status = "completed"


def test_simple_context_step_item_state_runtime_fields_are_read_only(tmp_path) -> None:
    class WorkflowState(BaseModel):
        approved: bool = False

    class StepItemState(BaseModel):
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
        step_item_state_store=StepItemState(attempts=2),
    )

    ctx.step_item_state.attempts = 3
    assert ctx.step_item_state.attempts == 3
    with pytest.raises(AttributeError, match="last_route is runtime-owned and read-only"):
        ctx.step_item_state.last_route = "done"
