from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import BaseModel

from autoloop.simple import Json, Md, Prompt, Route, RouteInfo, StrictWorkflow, Workflow, chain, review_step, step
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


def test_simple_workflow_base_does_not_trigger_strict_class_definition_validation() -> None:
    class LightweightWorkflow(Workflow):
        note = step("Write a short note.")

    assert LightweightWorkflow.note.name == "note"
    assert LightweightWorkflow.__strict_workflow__ is False


def test_strict_workflow_counterpart_preserves_import_time_validation() -> None:
    with pytest.raises(WorkflowValidationError, match="workflow must define nested State"):

        class BrokenStrictWorkflow(StrictWorkflow):
            note = step("Write a short note.")


def test_authoring_doc_mentions_additive_autoloop_simple_surface() -> None:
    text = (REPO_ROOT / "docs" / "authoring.md").read_text(encoding="utf-8")

    assert "autoloop.simple" in text
    assert "The root `workflow` shim remains the strict compatibility surface during the migration window." in text
