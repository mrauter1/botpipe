from __future__ import annotations

import importlib
import inspect
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import BaseModel

from autoloop import Checkpoint, ChildWorkflowResult, Event, Outcome, ResolvedArtifacts
from autoloop.simple import (
    AfterHookResult,
    FINISH,
    Json,
    Md,
    Param,
    Prompt,
    Route,
    RouteInfo,
    SELF,
    Session,
    StateVar,
    StrictWorkflow,
    Workflow,
    chain,
    do_review_step,
    python_step,
    review_step,
    step,
    system_step,
    workflow_step,
)
from autoloop.simple import Checkpoint as SimpleCheckpoint
from autoloop.simple import ChildWorkflowResult as SimpleChildWorkflowResult
from autoloop.simple import Event as SimpleEvent
from autoloop.simple import Outcome as SimpleOutcome
from autoloop.simple import ResolvedArtifacts as SimpleResolvedArtifacts
from autoloop_v3.core.compiler import compile_workflow
from autoloop_v3.core.errors import WorkflowValidationError
from autoloop_v3.core.prompts import PromptRegistry
from autoloop_v3.runtime.prompts import FilesystemPromptRegistry
from autoloop_v3.core.steps import SystemStep, WorkflowStep


REPO_ROOT = Path(__file__).resolve().parents[2]


class _SystemWorkflowState(BaseModel):
    notes: int = 0


def _probe_simple_surface(*pythonpath: Path, cwd: Path) -> dict[str, object]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(str(path) for path in pythonpath)
    probe = """
import json
from autoloop import Checkpoint, ChildWorkflowResult, Event, Outcome, ResolvedArtifacts
from autoloop.simple import Checkpoint as SimpleCheckpoint
from autoloop.simple import ChildWorkflowResult as SimpleChildWorkflowResult
from autoloop.simple import Event as SimpleEvent
from autoloop.simple import Json, Outcome as SimpleOutcome, ResolvedArtifacts as SimpleResolvedArtifacts
from autoloop.simple import RouteInfo, StrictWorkflow, Workflow

print(json.dumps({
    "workflow_module": Workflow.__module__,
    "strict_module": StrictWorkflow.__module__,
    "artifact_name": Json("note").name,
    "route_info_module": RouteInfo.__module__,
    "checkpoint_identity": Checkpoint is SimpleCheckpoint,
    "child_workflow_result_identity": ChildWorkflowResult is SimpleChildWorkflowResult,
    "event_identity": Event is SimpleEvent,
    "outcome_identity": Outcome is SimpleOutcome,
    "resolved_artifacts_identity": ResolvedArtifacts is SimpleResolvedArtifacts,
}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        check=True,
        capture_output=True,
        cwd=cwd,
        env=env,
        text=True,
    )
    return json.loads(completed.stdout)


def test_autoloop_simple_imports_in_installed_package_mode(tmp_path: Path) -> None:
    target = tmp_path / "site"
    target.mkdir()
    shutil.copytree(REPO_ROOT / "autoloop", target / "autoloop")
    shutil.copytree(REPO_ROOT / "core", target / "core")
    payload = _probe_simple_surface(target, cwd=tmp_path)

    assert payload["workflow_module"] == "autoloop.simple"
    assert payload["strict_module"] == "autoloop.simple"
    assert payload["artifact_name"] == "note"
    assert payload["route_info_module"] == "core.routes"
    assert payload["checkpoint_identity"] is True
    assert payload["child_workflow_result_identity"] is True
    assert payload["event_identity"] is True
    assert payload["outcome_identity"] is True
    assert payload["resolved_artifacts_identity"] is True


def test_autoloop_simple_imports_with_repo_root_fallback_only() -> None:
    payload = _probe_simple_surface(REPO_ROOT, cwd=REPO_ROOT)

    assert payload["workflow_module"] == "autoloop.simple"
    assert payload["strict_module"] == "autoloop.simple"
    assert payload["artifact_name"] == "note"
    assert payload["route_info_module"] == "core.routes"
    assert payload["checkpoint_identity"] is True
    assert payload["child_workflow_result_identity"] is True
    assert payload["event_identity"] is True
    assert payload["outcome_identity"] is True
    assert payload["resolved_artifacts_identity"] is True


def test_prompt_inline_and_file_primitives_preserve_origin_metadata(tmp_path: Path) -> None:
    prompt_path = tmp_path / "incident.md"
    prompt_path.write_text("Investigate the incident.\n", encoding="utf-8")

    inline = Prompt.inline("Summarize the incident.")
    inline_resolved = PromptRegistry().resolve(inline)
    file_resolved = FilesystemPromptRegistry(tmp_path).resolve(Prompt.file(prompt_path.name))

    assert inline.source == "inline"
    assert inline.path is None
    assert inline_resolved.text == "Summarize the incident."
    assert inline_resolved.source == "inline"
    assert file_resolved.text == "Investigate the incident.\n"
    assert file_resolved.source == "file"
    assert file_resolved.path == str(prompt_path)


def test_prompt_ref_preserves_registry_origin_metadata() -> None:
    prompt = Prompt.ref("review")
    resolved = PromptRegistry({"review": "Registry prompt.\n"}).resolve(prompt)

    assert prompt.source == "registry"
    assert prompt.path == "review"
    assert resolved.source == "registry"
    assert resolved.text == "Registry prompt.\n"


def test_prompt_ref_compile_time_analysis_does_not_read_same_named_filesystem_prompt(tmp_path: Path) -> None:
    prompt_path = tmp_path / "review.md"
    prompt_path.write_text("Use {missing_artifact}.", encoding="utf-8")
    module_path = tmp_path / "registry_prompt_workflow.py"
    module_path.write_text(
        "\n".join(
            [
                "from autoloop.simple import Prompt, Workflow, step",
                "",
                "class RegistryPromptWorkflow(Workflow):",
                "    note = step(Prompt.ref('review.md'))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    module_name = "test_registry_prompt_workflow"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        compiled = compile_workflow(module.RegistryPromptWorkflow)
    finally:
        sys.modules.pop(module_name, None)

    assert compiled.steps["note"].reads == ()


def test_route_primitives_accept_optional_metadata_without_changing_target_or_effects() -> None:
    route = Route.complete(
        summary="Step completed cleanly.",
        required_outputs=("report",),
        handoff="Share the report with the next step.",
    )
    info = RouteInfo(summary="Verifier accepted the output.", required_outputs=("email",), handoff="Escalate if needed.")

    assert route.target == "SUCCESS"
    assert route.summary == "Step completed cleanly."
    assert route.required_outputs == ("report",)
    assert route.handoff == "Share the report with the next step."
    assert info.summary == "Verifier accepted the output."
    assert info.required_outputs == ("email",)
    assert info.handoff == "Escalate if needed."


def test_simple_workflow_declarations_bind_names_and_infer_step_local_artifact_paths() -> None:
    class Analysis(BaseModel):
        summary: str

    class IncidentBrief(Workflow):
        analysis = step(
            "Analyze the incident request and produce a structured summary.",
            out=Json("analysis", Analysis),
        )
        email = review_step(
            producer="Draft an executive email from {analysis}.",
            verifier="Accept if the email is accurate and concise.",
            out=Md("email"),
        )
        flow = chain(analysis, email)

    analysis_output = IncidentBrief.analysis.outputs[0]
    email_output = IncidentBrief.email.outputs[0]

    assert IncidentBrief.analysis.name == "analysis"
    assert IncidentBrief.email.name == "email"
    assert IncidentBrief.analysis.prompt.source == "inline"
    assert IncidentBrief.email.producer.source == "inline"
    assert analysis_output.path_template("analysis") == "{workflow_folder}/analysis/analysis.json"
    assert email_output.path_template("email") == "{workflow_folder}/email/email.md"
    assert IncidentBrief.flow.items == (IncidentBrief.analysis, IncidentBrief.email)


def test_simple_artifact_specs_materialize_preserving_schema_requiredness_and_explicit_paths() -> None:
    class Analysis(BaseModel):
        summary: str

    inferred = Json("analysis", Analysis, required=True).materialize("draft")
    explicit = Md("email", path="custom/email.md").materialize("review")

    assert inferred.template == "{workflow_folder}/draft/analysis.json"
    assert inferred.kind == "json"
    assert inferred.schema is Analysis
    assert inferred.required is True
    assert inferred.name == "analysis"
    assert explicit.template == "custom/email.md"
    assert explicit.kind == "markdown"
    assert explicit.required is False
    assert explicit.name == "email"


def test_simple_workflow_base_does_not_trigger_strict_class_definition_validation() -> None:
    class LightweightWorkflow(Workflow):
        note = step("Write a short note.")

    assert LightweightWorkflow.note.name == "note"
    assert LightweightWorkflow.__strict_workflow__ is False


def test_simple_single_step_workflow_compiles_with_inferred_entry_and_finish_route() -> None:
    class LightweightWorkflow(Workflow):
        note = step("Write a short note.", writes=[Md("note")])

    compiled = compile_workflow(LightweightWorkflow)

    assert compiled.entry_step_name == "note"
    assert compiled.routes["note"]["done"].target == "FINISH"
    assert compiled.steps["note"].expected_output_schema is None


def test_statevar_and_param_descriptors_extend_compiled_models_and_prompt_namespaces() -> None:
    class DescriptorWorkflow(Workflow):
        attempts = StateVar(0)
        labels = StateVar(default_factory=list)
        mode = Param("strict")

        note = step(
            "Mode: {params.mode}. Attempts: {state.attempts}.",
            writes=[Md("note")],
        )

    compiled = compile_workflow(DescriptorWorkflow)
    state = compiled.new_state()
    params = compiled.parameters_cls.model_validate({}) if compiled.parameters_cls is not None else None

    assert state.attempts == 0
    assert state.labels == []
    assert params is not None
    assert params.mode == "strict"
    assert compiled.steps["note"].reads == ()


def test_do_review_step_state_descriptors_compile_to_step_state_fields() -> None:
    class ReviewWorkflow(Workflow):
        review = do_review_step(
            do="Draft with {state.global_attempts}.",
            review="Inspect {review.state.attempts}.",
            state={"attempts": StateVar(0)},
        )
        global_attempts = StateVar(0)

    compiled = compile_workflow(ReviewWorkflow)

    assert compiled.steps["review"].step_state_fields == ("attempts",)
    assert compiled.new_state().model_dump(mode="python") == {"global_attempts": 0}


def test_inherited_simple_workflow_declarations_remain_discoverable_and_compilable() -> None:
    class BaseWorkflow(Workflow):
        note = step("Write a short note.", out=Md("note"))
        flow = chain(note)

    class ChildWorkflow(BaseWorkflow):
        pass

    compiled = compile_workflow(ChildWorkflow)

    assert compiled.entry_step_name == "note"
    assert tuple(compiled.steps) == ("note",)


def test_simple_chain_and_review_step_lower_into_existing_compiled_workflow_model() -> None:
    class Analysis(BaseModel):
        summary: str

    class IncidentBrief(Workflow):
        analysis = step(
            "Analyze the incident request and produce a structured summary.",
            out=Json("analysis", Analysis),
        )
        email = review_step(
            producer="Draft an executive email from {analysis}.",
            verifier="Accept if the email is accurate and concise.",
            out=Md("email"),
        )
        flow = chain(analysis, email)

    compiled = compile_workflow(IncidentBrief)

    assert compiled.entry_step_name == "analysis"
    assert compiled.routes["analysis"]["done"].target == "email"
    assert compiled.routes["email"]["accepted"].target == "FINISH"
    assert compiled.routes["email"]["needs_rework"].target == "email"
    assert compiled.steps["analysis"].expected_output_schema is None
    assert compiled.steps["email"].reads == ("analysis.analysis",)
    assert compiled.steps["email"].requires == ()


def test_simple_placeholder_inference_rejects_bare_name_ambiguity() -> None:
    class Analysis(BaseModel):
        summary: str

    class AmbiguousPromptWorkflow(Workflow):
        class State(BaseModel):
            analysis: str = ""

        analysis = step("Produce the analysis.", out=Json("analysis", Analysis))
        publish = step("Publish a short summary of {analysis}.")
        flow = chain(analysis, publish)

    with pytest.raises(WorkflowValidationError, match="is ambiguous"):
        compile_workflow(AmbiguousPromptWorkflow)


def test_simple_file_prompt_infers_reads_from_unambiguous_placeholders(tmp_path: Path) -> None:
    class Analysis(BaseModel):
        summary: str

    prompt_path = tmp_path / "publish.md"
    prompt_path.write_text("Publish a short summary of {analysis}.", encoding="utf-8")

    class FilePromptWorkflow(Workflow):
        analysis = step("Produce the analysis.", out=Json("analysis", Analysis))
        publish = step(prompt_path)
        flow = chain(analysis, publish)

    compiled = compile_workflow(FilePromptWorkflow)

    assert compiled.steps["publish"].reads == ("analysis.analysis",)
    assert compiled.steps["publish"].requires == ()


def test_simple_prompt_references_support_self_step_value_and_params_namespaces() -> None:
    class AnalysisWorkflow(Workflow):
        class Parameters(BaseModel):
            mode: str = "strict"

        draft = step(
            "Write {self.report} using {params.mode} and reflect on {draft.value}.",
            writes=[Md("report")],
        )

    compiled = compile_workflow(AnalysisWorkflow)

    assert compiled.steps["draft"].reads == ()


def test_simple_prompt_references_reject_unknown_placeholders() -> None:
    class UnknownPlaceholderWorkflow(Workflow):
        note = step("Write {missing_artifact}.")

    with pytest.raises(WorkflowValidationError, match="is unknown"):
        compile_workflow(UnknownPlaceholderWorkflow)


def test_simple_entry_defaults_to_first_declared_step_without_flow() -> None:
    class OrderedWorkflow(Workflow):
        first = step("First.")
        second = step("Second.")

    compiled = compile_workflow(OrderedWorkflow)

    assert compiled.entry_step_name == "first"
    assert compiled.routes["first"]["done"].target == "second"
    assert compiled.routes["second"]["done"].target == "FINISH"


def test_simple_routes_support_string_forward_refs_and_self() -> None:
    class RoutedWorkflow(Workflow):
        prepare = step(
            "Prepare.",
            routes={
                "retry": SELF,
                "next": "publish",
                "finish": FINISH,
            },
        )
        publish = step("Publish.")

    compiled = compile_workflow(RoutedWorkflow)

    assert compiled.routes["prepare"]["retry"].target == "prepare"
    assert compiled.routes["prepare"]["next"].target == "publish"
    assert compiled.routes["prepare"]["finish"].target == "FINISH"


def test_python_step_decorator_lowers_to_core_system_handler() -> None:
    class PythonWorkflow(Workflow):
        State = _SystemWorkflowState

        @python_step(writes=[Md("note")])
        def run(ctx):
            return "done"

    compiled = compile_workflow(PythonWorkflow)

    assert isinstance(compiled.steps["run"].step, SystemStep)


def test_do_review_step_accepts_canonical_prompt_names() -> None:
    class ReviewWorkflow(Workflow):
        assess = do_review_step(
            do=Prompt.inline("Assess."),
            review=Prompt.inline("Review."),
            writes=[Md("report")],
        )

    compiled = compile_workflow(ReviewWorkflow)

    assert compiled.entry_step_name == "assess"
    assert compiled.routes["assess"]["accepted"].target == "FINISH"
    assert compiled.routes["assess"]["needs_rework"].target == "assess"


def test_do_review_step_supports_separate_review_contracts_and_custom_routes() -> None:
    class ReviewWorkflow(Workflow):
        main = Session()
        reviewer = Session()

        assess = do_review_step(
            do=Prompt.inline("Assess."),
            review=Prompt.inline("Review."),
            writes=[Md("draft")],
            review_requires=["draft"],
            review_writes=[Json("decision")],
            routes={
                "approved": Route.to(FINISH, required_writes=["draft", "decision"]),
                "rejected": Route.to(FINISH, required_writes=["decision"]),
            },
            session=main,
            review_session=reviewer,
        )

    compiled = compile_workflow(ReviewWorkflow)
    step = compiled.steps["assess"]

    assert step.available_routes == ("approved", "rejected", "question", "blocked", "failed")
    assert step.do_writes == ("assess.draft",)
    assert step.review_writes == ("assess.decision",)
    assert step.review_requires == ("assess.draft",)
    assert step.review_session_name == "reviewer"
    assert compiled.routes["assess"]["approved"].target == "FINISH"
    assert compiled.routes["assess"]["rejected"].target == "FINISH"


def test_control_routes_can_be_disabled_for_simple_steps() -> None:
    class MinimalWorkflow(Workflow):
        note = step("Write a note.", control_routes=False)

    compiled = compile_workflow(MinimalWorkflow)

    assert tuple(compiled.steps["note"].available_routes) == ("done",)


def test_simple_workflow_step_compiles_as_core_workflow_step_without_generated_handler() -> None:
    class ChildWorkflow(Workflow):
        note = step("Write the note.")

    class ParentWorkflow(Workflow):
        launch = workflow_step(
            ChildWorkflow,
            message="Run child workflow",
            out=Json("child_result"),
        )
        flow = chain(launch)

    compiled = compile_workflow(ParentWorkflow)

    assert compiled.entry_step_name == "launch"
    assert compiled.routes["launch"]["done"].target == "FINISH"
    assert compiled.routes["launch"]["question"].target == "PAUSE"
    assert compiled.routes["launch"]["failed"].target == "FAIL"
    assert compiled.routes["launch"]["blocked"].target == "PAUSE"
    assert compiled.steps["launch"].kind == "workflow"
    assert isinstance(compiled.steps["launch"].step, WorkflowStep)
    assert compiled.steps["launch"].system_handler is None
    assert "on_launch" not in ParentWorkflow.__dict__


def test_simple_workflow_step_preserves_message_metadata_on_core_step() -> None:
    class ChildWorkflow(Workflow):
        note = step("Write the note.")

    class ParentWorkflow(Workflow):
        draft = step("Draft the child launch message.", out=Md("brief"))
        launch = workflow_step(ChildWorkflow, message_from="brief")
        flow = chain(draft, launch)

    compiled = compile_workflow(ParentWorkflow)
    step_model = compiled.steps["launch"].step

    assert isinstance(step_model, WorkflowStep)
    assert step_model.workflow is ChildWorkflow
    assert step_model.message is None
    assert step_model.message_from == "brief"


def test_simple_system_step_lowers_to_core_system_handler_without_on_step_method() -> None:
    def handler(state: _SystemWorkflowState, ctx: object) -> tuple[_SystemWorkflowState, str]:
        return _SystemWorkflowState(notes=state.notes + 1), "done"

    class SystemWorkflow(Workflow):
        State = _SystemWorkflowState
        run = python_step(handler, writes=[Md("note")])
        flow = chain(run)

    compiled = compile_workflow(SystemWorkflow)

    assert isinstance(compiled.steps["run"].step, SystemStep)
    assert "on_run" not in SystemWorkflow.__dict__

    next_state, event = compiled.steps["run"].system_handler(_SystemWorkflowState(), object())

    assert next_state.notes == 1
    assert event.tag == "done"


@pytest.mark.parametrize(
    ("handler_fn", "initial_notes", "expected_notes", "expected_tag"),
    [
        (lambda ctx: None, 3, 3, "done"),
        (lambda ctx: _SystemWorkflowState(notes=7), 3, 7, "done"),
        (lambda ctx: "question", 3, 3, "question"),
        (lambda ctx: Event("blocked"), 3, 3, "blocked"),
        (lambda state, ctx: (_SystemWorkflowState(notes=state.notes + 1), "done"), 1, 2, "done"),
        (lambda state, ctx: (_SystemWorkflowState(notes=state.notes + 2), Event("failed")), 1, 3, "failed"),
    ],
)
def test_simple_system_step_normalizes_supported_handler_signatures_and_return_shapes(
    handler_fn,
    initial_notes: int,
    expected_notes: int,
    expected_tag: str,
) -> None:
    class SystemWorkflow(Workflow):
        State = _SystemWorkflowState
        run = system_step(handler_fn, out=Md("note"))
        flow = chain(run)

    compiled = compile_workflow(SystemWorkflow)

    next_state, event = compiled.steps["run"].system_handler(_SystemWorkflowState(notes=initial_notes), object())

    assert next_state.notes == expected_notes
    assert event.tag == expected_tag


def test_strict_workflow_counterpart_remains_a_distinct_strict_surface() -> None:
    class BrokenStrictWorkflow(StrictWorkflow):
        note = step("Write a short note.")

    assert BrokenStrictWorkflow.__strict_workflow__ is True
    assert BrokenStrictWorkflow is not Workflow


def test_autoloop_simple_exports_requested_public_authoring_surface() -> None:
    autoloop_surface = importlib.import_module("autoloop")

    for exported in (
        "AfterHookResult",
        "Checkpoint",
        "ChildWorkflowResult",
        "Continuity",
        "Event",
        "FINISH",
        "Json",
        "Md",
        "Outcome",
        "Prompt",
        "Raw",
        "ResolvedArtifacts",
        "Route",
        "RouteInfo",
        "SELF",
        "SUCCESS",
        "Session",
        "StrictWorkflow",
        "Text",
        "Workflow",
        "WorkflowStep",
        "chain",
        "do_review_step",
        "python_step",
        "review_step",
        "step",
        "system_step",
        "workflow_step",
    ):
        assert hasattr(autoloop_surface, exported)

    assert not hasattr(autoloop_surface, "Route" "Contract")
    assert autoloop_surface.Checkpoint is SimpleCheckpoint
    assert autoloop_surface.ChildWorkflowResult is SimpleChildWorkflowResult


def test_autoloop_public_primitives_match_autoloop_simple_surface() -> None:
    assert Event is SimpleEvent
    assert Outcome is SimpleOutcome
    assert Checkpoint is SimpleCheckpoint
    assert ResolvedArtifacts is SimpleResolvedArtifacts
    assert ChildWorkflowResult is SimpleChildWorkflowResult


def test_autoloop_simple_helper_signatures_are_explicit() -> None:
    simple_surface = importlib.import_module("autoloop.simple")

    assert tuple(inspect.signature(simple_surface.step).parameters) == (
        "prompt",
        "name",
        "reads",
        "requires",
        "writes",
        "out",
        "outputs",
        "routes",
        "route_infos",
        "route_summaries",
        "before",
        "after",
        "on_route",
        "control_schema",
        "retry",
        "session",
        "control_routes",
    )
    assert tuple(inspect.signature(simple_surface.do_review_step).parameters) == (
        "do",
        "review",
        "producer",
        "verifier",
        "name",
        "reads",
        "requires",
        "review_requires",
        "writes",
        "review_writes",
        "out",
        "outputs",
        "accepted",
        "rework",
        "routes",
        "route_infos",
        "route_summaries",
        "before",
        "after",
        "state",
        "before_do",
        "after_do",
        "before_review",
        "after_review",
        "on_route",
        "control_schema",
        "retry",
        "session",
        "review_session",
        "control_routes",
    )
    assert tuple(inspect.signature(simple_surface.review_step).parameters) == (
        "producer",
        "verifier",
        "name",
        "reads",
        "requires",
        "review_requires",
        "writes",
        "review_writes",
        "out",
        "outputs",
        "accepted",
        "rework",
        "routes",
        "route_infos",
        "route_summaries",
        "before",
        "after",
        "state",
        "before_do",
        "after_do",
        "before_review",
        "after_review",
        "on_route",
        "control_schema",
        "retry",
        "session",
        "review_session",
        "control_routes",
    )
    assert tuple(inspect.signature(simple_surface.python_step).parameters) == (
        "fn",
        "name",
        "reads",
        "requires",
        "writes",
        "out",
        "outputs",
        "routes",
        "route_infos",
        "route_summaries",
        "before",
        "after",
        "on_route",
        "control_routes",
    )
    assert tuple(inspect.signature(simple_surface.system_step).parameters) == (
        "fn",
        "name",
        "reads",
        "requires",
        "writes",
        "out",
        "outputs",
        "routes",
        "route_infos",
        "route_summaries",
        "before",
        "after",
        "on_route",
        "control_routes",
    )
    assert tuple(inspect.signature(simple_surface.workflow_step).parameters) == (
        "workflow",
        "name",
        "message",
        "message_from",
        "params",
        "input",
        "reads",
        "requires",
        "writes",
        "out",
        "outputs",
        "routes",
        "route_infos",
        "route_summaries",
        "before",
        "after",
        "on_route",
        "control_routes",
    )


def test_autoloop_simple_does_not_export_route_contract() -> None:
    simple_surface = importlib.import_module("autoloop.simple")

    assert not hasattr(simple_surface, "Route" "Contract")


def test_autoloop_simple_exports_after_hook_result() -> None:
    simple_surface = importlib.import_module("autoloop.simple")

    assert simple_surface.AfterHookResult is AfterHookResult
