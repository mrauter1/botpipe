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

from autoloop.simple import AfterHookResult, Json, Md, Prompt, Route, RouteInfo, StrictWorkflow, Workflow, chain, review_step, step, system_step, workflow_step
from autoloop_v3.core.compiler import compile_workflow
from autoloop_v3.core.errors import WorkflowValidationError
from autoloop_v3.core.primitives import Event
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
from autoloop.simple import Json, RouteInfo, StrictWorkflow, Workflow

print(json.dumps({
    "workflow_module": Workflow.__module__,
    "strict_module": StrictWorkflow.__module__,
    "artifact_name": Json("note").name,
    "route_info_module": RouteInfo.__module__,
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


def test_autoloop_simple_imports_with_repo_root_fallback_only() -> None:
    payload = _probe_simple_surface(REPO_ROOT, cwd=REPO_ROOT)

    assert payload["workflow_module"] == "autoloop.simple"
    assert payload["strict_module"] == "autoloop.simple"
    assert payload["artifact_name"] == "note"
    assert payload["route_info_module"] == "core.routes"


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


def test_simple_single_step_workflow_compiles_with_inferred_entry_and_success_route() -> None:
    class LightweightWorkflow(Workflow):
        note = step("Write a short note.", out=Md("note"))

    compiled = compile_workflow(LightweightWorkflow)

    assert compiled.entry_step_name == "note"
    assert compiled.routes["note"]["done"].target == "SUCCESS"
    assert compiled.steps["note"].expected_output_schema is None
    assert compiled.new_state().model_dump(mode="python") == {}


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
    assert compiled.routes["email"]["accepted"].target == "SUCCESS"
    assert compiled.routes["email"]["needs_rework"].target == "email"
    assert compiled.steps["analysis"].expected_output_schema is None
    assert compiled.steps["email"].reads == ("analysis.analysis",)
    assert compiled.steps["email"].requires == ()


def test_simple_placeholder_inference_is_conservative_about_bare_name_ambiguity() -> None:
    class Analysis(BaseModel):
        summary: str

    class AmbiguousPromptWorkflow(Workflow):
        class State(BaseModel):
            analysis: str = ""

        analysis = step("Produce the analysis.", out=Json("analysis", Analysis))
        publish = step("Publish a short summary of {analysis}.")
        flow = chain(analysis, publish)

    compiled = compile_workflow(AmbiguousPromptWorkflow)

    assert compiled.steps["publish"].reads == ()
    assert compiled.steps["publish"].requires == ()


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
    assert compiled.routes["launch"]["done"].target == "SUCCESS"
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
        run = system_step(handler, out=Md("note"))
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


def test_strict_workflow_counterpart_preserves_import_time_validation() -> None:
    with pytest.raises(WorkflowValidationError, match="workflow must define nested State"):

        class BrokenStrictWorkflow(StrictWorkflow):
            note = step("Write a short note.")


def test_autoloop_simple_exports_requested_public_authoring_surface() -> None:
    autoloop_surface = importlib.import_module("autoloop")

    for exported in (
        "AfterHookResult",
        "Json",
        "Md",
        "Prompt",
        "Raw",
        "Route",
        "RouteInfo",
        "StrictWorkflow",
        "Text",
        "Workflow",
        "WorkflowStep",
        "chain",
        "review_step",
        "step",
        "system_step",
        "workflow_step",
    ):
        assert hasattr(autoloop_surface, exported)

    assert not hasattr(autoloop_surface, "RouteContract")


def test_autoloop_simple_helper_signatures_are_explicit() -> None:
    simple_surface = importlib.import_module("autoloop.simple")

    assert tuple(inspect.signature(simple_surface.step).parameters) == (
        "prompt",
        "name",
        "reads",
        "requires",
        "out",
        "outputs",
        "routes",
        "route_infos",
        "route_summaries",
        "before",
        "after",
        "control_schema",
        "retry",
        "session",
    )
    assert tuple(inspect.signature(simple_surface.review_step).parameters) == (
        "producer",
        "verifier",
        "name",
        "reads",
        "requires",
        "out",
        "outputs",
        "accepted",
        "rework",
        "route_infos",
        "route_summaries",
        "before",
        "after",
        "control_schema",
        "retry",
        "session",
    )
    assert tuple(inspect.signature(simple_surface.system_step).parameters) == (
        "fn",
        "name",
        "reads",
        "requires",
        "out",
        "outputs",
        "routes",
        "route_infos",
        "route_summaries",
        "before",
        "after",
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
        "out",
        "outputs",
        "routes",
        "route_infos",
        "route_summaries",
        "before",
        "after",
    )


def test_autoloop_simple_does_not_export_route_contract() -> None:
    simple_surface = importlib.import_module("autoloop.simple")

    assert not hasattr(simple_surface, "RouteContract")


def test_autoloop_simple_exports_after_hook_result() -> None:
    simple_surface = importlib.import_module("autoloop.simple")

    assert simple_surface.AfterHookResult is AfterHookResult
