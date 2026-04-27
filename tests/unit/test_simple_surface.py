from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from pydantic import BaseModel

from autoloop.simple import Json, Md, Prompt, Route, RouteInfo, StrictWorkflow, Workflow, chain, review_step, step, workflow_step
from autoloop_v3.core.compiler import compile_workflow
from autoloop_v3.core.primitives import Event
from autoloop_v3.core.errors import WorkflowValidationError
from autoloop_v3.core.prompts import PromptRegistry
from autoloop_v3.runtime.prompts import FilesystemPromptRegistry


REPO_ROOT = Path(__file__).resolve().parents[2]


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


def test_simple_workflow_step_compiles_and_generated_handler_invokes_child_workflow(tmp_path: Path) -> None:
    class ChildWorkflow(Workflow):
        note = step("Write the note.")

    class ParentState(BaseModel):
        done: bool = False

    class ParentWorkflow(Workflow):
        State = ParentState
        launch = workflow_step(
            ChildWorkflow,
            message="Run child workflow",
            out=Json("child_result"),
        )
        flow = chain(launch)

    compiled = compile_workflow(ParentWorkflow)

    assert compiled.entry_step_name == "launch"
    assert compiled.routes["launch"]["done"].target == "SUCCESS"
    assert compiled.routes["launch"]["failed"].target == "FAIL"
    assert compiled.routes["launch"]["blocked"].target == "PAUSE"
    assert compiled.steps["launch"].kind == "system"

    @dataclass
    class _FakeChildResult:
        workflow_name: str = "child_workflow"
        run_id: str = "run-child-1"
        terminal: str = "SUCCESS"
        status: str = "success"
        last_event: Event | None = Event("done")
        output_artifacts: dict[str, Path] | None = None
        output_metadata: dict[str, object] | None = None

    class _FakeContext:
        def __init__(self) -> None:
            self.workflow_folder = tmp_path / "parent"
            self.workflow_folder.mkdir(parents=True, exist_ok=True)
            self.invocations: list[tuple[object, str, dict[str, object], object]] = []

        def invoke_workflow(self, workflow, *, message, parameters=None, input=None):
            self.invocations.append((workflow, message, dict(parameters or {}), input))
            return _FakeChildResult(output_artifacts={"note": self.workflow_folder / "child-note.md"}, output_metadata={})

    ctx = _FakeContext()
    state = ParentState()
    next_state, event = ParentWorkflow.on_launch(state, ctx)
    payload = json.loads((ctx.workflow_folder / "launch" / "child_result.json").read_text(encoding="utf-8"))

    assert next_state == state
    assert event.tag == "done"
    assert ctx.invocations == [(ChildWorkflow, "Run child workflow", {}, None)]
    assert payload["workflow_name"] == "child_workflow"
    assert payload["terminal"] == "SUCCESS"
    assert payload["output_artifacts"]["note"].endswith("child-note.md")


def test_simple_workflow_step_message_from_reads_step_local_artifact_text(tmp_path: Path) -> None:
    class ChildWorkflow(Workflow):
        note = step("Write the note.")

    class ParentWorkflow(Workflow):
        draft = step("Draft the child launch message.", out=Md("brief"))
        launch = workflow_step(ChildWorkflow, message_from="brief")
        flow = chain(draft, launch)

    compiled = compile_workflow(ParentWorkflow)

    @dataclass
    class _FakeChildResult:
        workflow_name: str = "child_workflow"
        run_id: str = "run-child-2"
        terminal: str = "SUCCESS"
        status: str = "success"
        last_event: Event | None = Event("done")
        output_artifacts: dict[str, Path] | None = None
        output_metadata: dict[str, object] | None = None

    class _FakeContext:
        def __init__(self) -> None:
            self.workflow_folder = tmp_path / "parent"
            self.workflow_folder.mkdir(parents=True, exist_ok=True)
            self.invocations: list[str] = []

        def invoke_workflow(self, workflow, *, message, parameters=None, input=None):
            assert workflow is ChildWorkflow
            assert parameters == {}
            assert input is None
            self.invocations.append(message)
            return _FakeChildResult()

    ctx = _FakeContext()
    message_path = ctx.workflow_folder / "draft" / "brief.md"
    message_path.parent.mkdir(parents=True, exist_ok=True)
    message_path.write_text("Launch the child workflow with this brief.\n", encoding="utf-8")

    next_state, event = ParentWorkflow.on_launch(compiled.new_state(), ctx)

    assert next_state == compiled.new_state()
    assert event.tag == "done"
    assert ctx.invocations == ["Launch the child workflow with this brief.\n"]


def test_simple_workflow_step_child_question_maps_to_reserved_question_route(tmp_path: Path) -> None:
    class ChildWorkflow(Workflow):
        note = step("Write the note.")

    class ParentWorkflow(Workflow):
        launch = workflow_step(ChildWorkflow, message="Run child workflow")
        flow = chain(launch)

    compiled = compile_workflow(ParentWorkflow)

    @dataclass
    class _FakeChildResult:
        workflow_name: str = "child_workflow"
        run_id: str = "run-child-3"
        terminal: str = "PAUSE"
        status: str = "paused"
        last_event: Event | None = Event("question", question="Need approval?")
        output_artifacts: dict[str, Path] | None = None
        output_metadata: dict[str, object] | None = None

    class _FakeContext:
        def __init__(self) -> None:
            self.workflow_folder = tmp_path / "parent"
            self.workflow_folder.mkdir(parents=True, exist_ok=True)

        def invoke_workflow(self, workflow, *, message, parameters=None, input=None):
            return _FakeChildResult()

    _, event = ParentWorkflow.on_launch(compiled.new_state(), _FakeContext())

    assert compiled.routes["launch"]["question"].target == "PAUSE"
    assert event.tag == "question"
    assert event.question == "Need approval?"


def test_simple_workflow_step_child_failure_maps_to_reserved_failed_route(tmp_path: Path) -> None:
    class ChildWorkflow(Workflow):
        note = step("Write the note.")

    class ParentWorkflow(Workflow):
        launch = workflow_step(ChildWorkflow, message="Run child workflow")
        flow = chain(launch)

    compiled = compile_workflow(ParentWorkflow)

    @dataclass
    class _FakeChildResult:
        workflow_name: str = "child_workflow"
        run_id: str = "run-child-4"
        terminal: str = "FAIL"
        status: str = "failed"
        last_event: Event | None = Event("failed")
        output_artifacts: dict[str, Path] | None = None
        output_metadata: dict[str, object] | None = None

    class _FakeContext:
        def __init__(self) -> None:
            self.workflow_folder = tmp_path / "parent"
            self.workflow_folder.mkdir(parents=True, exist_ok=True)

        def invoke_workflow(self, workflow, *, message, parameters=None, input=None):
            return _FakeChildResult()

    _, event = ParentWorkflow.on_launch(compiled.new_state(), _FakeContext())

    assert compiled.routes["launch"]["failed"].target == "FAIL"
    assert event.tag == "failed"


def test_simple_workflow_step_child_pause_without_question_maps_to_reserved_blocked_route(tmp_path: Path) -> None:
    class ChildWorkflow(Workflow):
        note = step("Write the note.")

    class ParentWorkflow(Workflow):
        launch = workflow_step(ChildWorkflow, message="Run child workflow")
        flow = chain(launch)

    compiled = compile_workflow(ParentWorkflow)

    @dataclass
    class _FakeChildResult:
        workflow_name: str = "child_workflow"
        run_id: str = "run-child-5"
        terminal: str = "PAUSE"
        status: str = "paused"
        last_event: Event | None = Event("blocked")
        output_artifacts: dict[str, Path] | None = None
        output_metadata: dict[str, object] | None = None

    class _FakeContext:
        def __init__(self) -> None:
            self.workflow_folder = tmp_path / "parent"
            self.workflow_folder.mkdir(parents=True, exist_ok=True)

        def invoke_workflow(self, workflow, *, message, parameters=None, input=None):
            return _FakeChildResult()

    _, event = ParentWorkflow.on_launch(compiled.new_state(), _FakeContext())

    assert compiled.routes["launch"]["blocked"].target == "PAUSE"
    assert event.tag == "blocked"


def test_simple_workflow_step_rejects_unknown_message_from_reference() -> None:
    class ChildWorkflow(Workflow):
        note = step("Write the note.")

    class BrokenParentWorkflow(Workflow):
        launch = workflow_step(ChildWorkflow, message_from="missing")
        flow = chain(launch)

    with pytest.raises(WorkflowValidationError, match="message_from 'missing' must reference a known artifact"):
        compile_workflow(BrokenParentWorkflow)


def test_strict_workflow_counterpart_preserves_import_time_validation() -> None:
    with pytest.raises(WorkflowValidationError, match="workflow must define nested State"):

        class BrokenStrictWorkflow(StrictWorkflow):
            note = step("Write a short note.")


def test_authoring_doc_mentions_additive_autoloop_simple_surface() -> None:
    text = (REPO_ROOT / "docs" / "authoring.md").read_text(encoding="utf-8")

    assert "autoloop.simple" in text
    assert "The root `workflow` shim remains the strict compatibility surface during the migration window." in text
