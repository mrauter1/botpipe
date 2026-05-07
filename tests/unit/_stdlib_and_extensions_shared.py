from __future__ import annotations
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
import autoloop.core.route_reporting as route_reporting_helpers
import autoloop_optimizer._selected_workflow as selected_workflow_helpers
import autoloop_optimizer.adaptation as adaptation_helpers
import autoloop_optimizer.candidate_surfaces as candidate_surface_helpers
import autoloop_optimizer.company as company_helpers
import autoloop_optimizer.decomposition as decomposition_helpers
import autoloop_optimizer.diagnostics as diagnostics_helpers
import autoloop_optimizer.evaluation as evaluation_helpers
import autoloop.stdlib.json_artifacts as json_artifact_helpers
import autoloop_optimizer.parameters as parameter_helpers
import autoloop_optimizer.portfolio as portfolio_helpers
import autoloop_optimizer.refinement as refinement_helpers
import autoloop.stdlib.validation as validation_helpers
from autoloop_optimizer.adaptation import write_selected_workflow_capability_snapshot
from autoloop_optimizer.candidate_surfaces import (
    derive_candidate_surface_manifest,
    materialize_baseline_surface,
    normalize_candidate_surface_boundary,
    normalize_candidate_surface_overlay_result,
    validate_authoritative_surface_sources_unchanged,
    validate_baseline_surface_manifest,
    validate_candidate_surface_manifest,
    validate_candidate_surface_overlay,
)
from autoloop_optimizer.company import write_company_operation_snapshot
from autoloop_optimizer.decomposition import write_selected_workflow_decomposition_surface
from autoloop_optimizer.diagnostics import write_selected_workflow_run_history_snapshot
from autoloop_optimizer.evaluation import write_validated_eval_case_manifest
from autoloop_optimizer.portfolio import (
    write_workflow_capability_snapshot,
    write_workflow_portfolio_health_snapshot,
    write_workflow_portfolio_snapshot,
)
from autoloop_optimizer.refinement import write_selected_workflow_authoring_surface
import pytest
from pydantic import BaseModel
from autoloop.core import Context
from autoloop.core.context import ChildWorkflowResult
from autoloop.core.workflow_capabilities import (
    inspect_workflow_reference,
    selected_workflow_authoring_surface_payload,
    selected_workflow_capability_payload,
    selected_workflow_decomposition_surface_payload,
)
from autoloop.extensions.session_paths import SessionPaths, extract_session_path_strategy
from autoloop.extensions.git.filters import (
    delta_pathspecs,
    filter_delta_by_pathspecs,
    filter_delta_by_prefixes,
    workflow_workspace_pathspec,
)
from autoloop.extensions.git.policy import GitChange, GitCommitPlan, GitDelta
from autoloop.extensions.git.repo import GitRepo
from autoloop.core.stores import InMemorySessionStore
from autoloop.stdlib import (
    JsonArtifactSpec,
    PromptBundle,
    ValidationIssue,
    ValidationReport,
    adopt_child_artifacts,
    await_input_on_outcome_tags,
    deduped_string_list_fields,
    event_on_outcome_tags,
    global_routes,
    merge_transitions,
    normalize_optional_string,
    normalize_unique_strings,
    open_workflow_sessions,
    optional_text_fields,
    positive_int_fields,
    read_json_object,
    read_model_file,
    require_child_workflow_result,
    require_mapping,
    require_mapping_list,
    require_non_negative_int,
    require_non_empty_string,
    require_positive_int,
    required_text_fields,
    require_string_list,
    require_unique_values,
    run_child_workflow,
    validate_selected_workflow_artifact_alignment,
    validate_selected_workflow_capability_and_authoring_snapshots,
    validate_model_file,
    validate_selected_workflow_authoring_surface_snapshot,
    validate_selected_workflow_capability_snapshot,
    validate_selected_workflow_decomposition_surface_snapshot,
    validate_selected_workflow_name_alignment,
    write_model_file,
    write_invocation_contract,
    write_publication_receipt,
    write_workflow_json,
)
from autoloop_optimizer import (
    PortfolioReviewParameters,
    SelectedWorkflowTaskFramingParameters,
    SelectedWorkflowTaskFramingWithEvidenceParameters,
    TaskFramingParameters,
    TaskFramingWithEvidenceParameters,
    write_validated_workflow_parameters,
)
from autoloop import Route, SELF
from autoloop.stdlib.state import SequenceCursor
from autoloop.core.extensions import RunBinding
from autoloop.runtime.loader import WorkflowParameterError, coerce_workflow_parameter_mapping, resolve_workflow_reference
from autoloop.core import AWAIT_INPUT, FAIL, FINISH, GLOBAL
from autoloop.core.primitives import Event, Outcome
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REMOVED_CONTRACTS_PATH = "contracts" + "_path"
REMOVED_CONTRACTS_PATH_REPO_RELATIVE = "contracts" + "_path_repo_relative"
REMOVED_WORKFLOW_PY_FIELD = "legacy_" + "workflow_path"
ACTIVE_CONSUMER_RUNTIME_FILES = (
    "tests/runtime/test_optional_extensions.py",
    "tests/runtime/test_workspace_and_context.py",
    "tests/runtime/test_runtime_static_graph.py",
    "tests/runtime/test_runtime_git_tracking.py",
)
BANNED_CONSUMER_TOKENS = (
    "SU" + "CCESS",
    "System" + "Step",
    "L" + "LMStep",
    "Pair" + "Step",
    "Route" + "Info",
    "required_" + "outputs",
    "route_" + "infos",
    "route_required_" + "outputs",
)
def _assert_mapping_contains(actual: dict[str, object], expected: dict[str, object]) -> None:
    for key, value in expected.items():
        assert key in actual
        if isinstance(value, dict):
            assert isinstance(actual[key], dict)
            _assert_mapping_contains(actual[key], value)
            continue
        assert actual[key] == value
class _StrategySummaryModel(BaseModel):
    selected_strategy: str
    recommended_workflows: list[str]
    comparison_candidates: list[str]
class _ValidatedEvalCaseModel(BaseModel):
    expected_artifacts: list[str]
class _ValidatedEvalCaseManifestModel(BaseModel):
    case_ids: list[str]
    validated_cases: list[_ValidatedEvalCaseModel]
class _PortfolioOperatingSummaryModel(BaseModel):
    priority_workflows: list[str]
    publication_boundary: str
class _RecursiveImprovementSummaryModel(BaseModel):
    workflow_name: str
    priority_category_counts: dict[str, int]
class _CandidateWorkflowSetSummaryModel(BaseModel):
    portfolio_posture: str
class _AdaptedExecutionSummaryModel(BaseModel):
    selected_workflow_entry_step: str
class _FailureModeManifestModel(BaseModel):
    workflow_name: str
    failure_modes: list[dict[str, object]]
class _ImprovementOpportunitiesSummaryModel(BaseModel):
    workflow_name: str
    opportunities: list[dict[str, object]]
    ready_for_publication: bool
class _WorkflowEvalSuiteSummaryModel(BaseModel):
    case_count: int
STRATEGY_SUMMARY_ARTIFACT = JsonArtifactSpec("_typed/strategy_summary.json", _StrategySummaryModel)
VALIDATED_EVAL_CASE_MANIFEST_ARTIFACT = JsonArtifactSpec(
    "_typed/validated_eval_case_manifest.json",
    _ValidatedEvalCaseManifestModel,
)
PORTFOLIO_OPERATING_SUMMARY_ARTIFACT = JsonArtifactSpec(
    "_typed/portfolio_operating_summary.json",
    _PortfolioOperatingSummaryModel,
)
RECURSIVE_IMPROVEMENT_SUMMARY_ARTIFACT = JsonArtifactSpec(
    "_typed/recursive_improvement_summary.json",
    _RecursiveImprovementSummaryModel,
)
CANDIDATE_WORKFLOW_SET_SUMMARY_ARTIFACT = JsonArtifactSpec(
    "_typed/candidate_workflow_set_summary.json",
    _CandidateWorkflowSetSummaryModel,
)
ADAPTED_EXECUTION_SUMMARY_ARTIFACT = JsonArtifactSpec(
    "_typed/adapted_execution_summary.json",
    _AdaptedExecutionSummaryModel,
)
FAILURE_MODE_MANIFEST_ARTIFACT = JsonArtifactSpec("_typed/failure_mode_manifest.json", _FailureModeManifestModel)
IMPROVEMENT_OPPORTUNITIES_SUMMARY_ARTIFACT = JsonArtifactSpec(
    "_typed/improvement_opportunities_summary.json",
    _ImprovementOpportunitiesSummaryModel,
)
WORKFLOW_EVAL_SUITE_SUMMARY_ARTIFACT = JsonArtifactSpec(
    "_typed/workflow_eval_suite_summary.json",
    _WorkflowEvalSuiteSummaryModel,
)
class _ExampleModel(BaseModel):
    status: str
    count: int
class _LifecycleState(BaseModel):
    marker: str = ""
def _build_lifecycle_context(
    tmp_path: Path,
    workflow_invoker=None,
    *,
    workflow_name: str = "release_candidate_to_go_no_go",
) -> Context:
    task_folder = tmp_path / ".autoloop" / "tasks" / "task-1"
    workflow_folder = task_folder / f"wf_{workflow_name}"
    run_folder = workflow_folder / "runs" / "run-1"
    package_folder = tmp_path / "workflows" / workflow_name
    run_folder.mkdir(parents=True, exist_ok=True)
    workflow_folder.mkdir(parents=True, exist_ok=True)
    package_folder.mkdir(parents=True, exist_ok=True)
    (run_folder / "request.md").write_text("Ship release 2026.04.\n", encoding="utf-8")
    return Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name=workflow_name,
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        state=_LifecycleState(),
        session_store=InMemorySessionStore(),
        workflow_invoker=workflow_invoker,
    )
def _build_child_result(tmp_path: Path, output_artifacts: dict[str, Path]) -> ChildWorkflowResult:
    child_task_folder = tmp_path / ".autoloop" / "tasks" / "task-1"
    child_workflow_folder = child_task_folder / "wf_investigation_request_to_evidence_pack"
    child_run_folder = child_workflow_folder / "runs" / "child-run-1"
    child_package_folder = tmp_path / "autoloop" / "workflows" / "investigation_request_to_evidence_pack"
    child_run_folder.mkdir(parents=True, exist_ok=True)
    child_workflow_folder.mkdir(parents=True, exist_ok=True)
    child_package_folder.mkdir(parents=True, exist_ok=True)
    request_file = child_run_folder / "request.md"
    request_file.write_text("Investigate this request.\n", encoding="utf-8")
    return ChildWorkflowResult(
        workflow_name="investigation_request_to_evidence_pack",
        run_id="child-run-1",
        terminal="FINISH",
        status="success",
        last_event=Event("evidence_pack_ready"),
        output_metadata={"summary": "child complete"},
        output_artifacts=dict(output_artifacts),
        task_folder=child_task_folder,
        workflow_folder=child_workflow_folder,
        run_folder=child_run_folder,
        package_folder=child_package_folder,
        request_file=request_file,
        run_meta_file=child_run_folder / "run.json",
        events_file=child_run_folder / "events.jsonl",
        checkpoint_file=child_run_folder / "checkpoint.json",
        sessions_dir=child_run_folder / "sessions",
        trace_file=child_run_folder / "trace.jsonl",
        raw_dir=child_run_folder / "raw",
        parent_file=child_run_folder / "parent.json",
    )
def _write_catalog_workflow(
    root: Path,
    package_name: str,
    *,
    aliases: tuple[str, ...] = (),
    export_parameters: bool = False,
    write_doc: bool = False,
) -> Path:
    workflows_root = root / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    (workflows_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")

    package_dir = workflows_root / package_name
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    (package_dir / "workflow.toml").write_text(
        "\n".join(
            (
                f'name = "{package_name}"',
                f'title = "{package_name.replace("_", " ").title()}"',
                'description = "Workflow description."',
                f"aliases = [{', '.join(repr(alias) for alias in aliases)}]",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (package_dir / "workflow.py").write_text("# workflow entrypoint\n", encoding="utf-8")
    if export_parameters:
        (package_dir / "params.py").write_text("# workflow parameters\n", encoding="utf-8")
    if write_doc:
        docs_root = root / "docs" / "workflows"
        docs_root.mkdir(parents=True, exist_ok=True)
        (docs_root / f"{package_name}.md").write_text(f"# {package_name}\n", encoding="utf-8")
    return package_dir
def _write_runtime_valid_catalog_workflow(
    root: Path,
    package_name: str,
    *,
    aliases: tuple[str, ...] = (),
    export_parameters: bool = False,
    write_doc: bool = False,
) -> Path:
    workflows_root = root / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    (workflows_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")

    package_dir = workflows_root / package_name
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "prompts").mkdir(exist_ok=True)
    (package_dir / "assets").mkdir(exist_ok=True)
    (package_dir / "prompts" / "assess_producer.md").write_text("Produce the assessment.\n", encoding="utf-8")
    (package_dir / "prompts" / "assess_verifier.md").write_text("Verify the assessment.\n", encoding="utf-8")
    class_name = "".join(part[:1].upper() + part[1:] for part in package_name.split("_") if part)

    (package_dir / "workflow.toml").write_text(
        "\n".join(
            (
                f'name = "{package_name}"',
                f'title = "{package_name.replace("_", " ").title()}"',
                'description = "Workflow description."',
                f"aliases = [{', '.join(repr(alias) for alias in aliases)}]",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (package_dir / "workflow.py").write_text(
        (
            f"""
from __future__ import annotations

from pydantic import BaseModel, Field

from autoloop import FINISH, Md, Prompt, Route, SELF, Workflow, produce_verify_step


class AssessmentPayload(BaseModel):
    summary: str = Field(min_length=1)


class {class_name}(Workflow):
    name = "{package_name}"

    class State(BaseModel):
        status: str | None = None

    assess = produce_verify_step(
        producer_prompt=Prompt.file("prompts/assess_producer.md"),
        verifier_prompt=Prompt.file("prompts/assess_verifier.md"),
        producer_writes=[Md("assessment_note", path="{{workflow_folder}}/assessment_note.md")],
        control_schema=AssessmentPayload,
        routes={{
            "assessment_complete": Route.to(
                FINISH,
                summary="The workflow assessment package is complete.",
                required_writes=("assessment_note",),
            ),
            "needs_rework": Route.to(
                SELF,
                summary="The same workflow assessment needs local repair.",
                required_writes=("assessment_note",),
            ),
        }},
    )
""".strip()
            )
            + "\n",
        encoding="utf-8",
    )
    if export_parameters:
        (package_dir / "params.py").write_text(
            (
                """
from pydantic import BaseModel, Field


class Params(BaseModel):
    mode: str = "strict"
    reviewers: list[str] = Field(default_factory=list)
""".strip()
            )
            + "\n",
            encoding="utf-8",
        )

    init_lines = [f"from .workflow import {class_name}"]
    exports = [class_name]
    if export_parameters:
        init_lines.append("from .params import Params")
        exports.append("Params")
    init_lines.append(f"__all__ = {exports!r}")
    (package_dir / "__init__.py").write_text("\n".join(init_lines) + "\n", encoding="utf-8")

    if write_doc:
        docs_root = root / "docs" / "workflows"
        docs_root.mkdir(parents=True, exist_ok=True)
        (docs_root / f"{package_name}.md").write_text(f"# {package_name}\n", encoding="utf-8")

    return package_dir
def _write_single_file_runtime_workflow(root: Path, *, relative_dir: str = "examples") -> Path:
    workflow_root = root / relative_dir
    workflow_root.mkdir(parents=True, exist_ok=True)
    (workflow_root / "prompts").mkdir(exist_ok=True)
    (workflow_root / "prompts" / "ask.md").write_text("Ask for the release summary.\n", encoding="utf-8")
    workflow_path = workflow_root / "single_file_review.py"
    workflow_path.write_text(
        """
from __future__ import annotations

from pydantic import BaseModel

from autoloop import Json, Prompt, Workflow, step


class ReviewPayload(BaseModel):
    summary: str


class SingleFileReview(Workflow):
    Params = None

    class State(BaseModel):
        summary: str = ""

    ask = step(
        prompt=Prompt.file("prompts/ask.md"),
        writes=[Json("review_note", ReviewPayload, path="{workflow_folder}/review_note.md")],
        control_schema=ReviewPayload,
    )
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return workflow_path
def _capture_child_invocation(
    captured: dict[str, object],
    child_result: ChildWorkflowResult,
    *,
    workflow,
    message: str,
    parameters: dict[str, object],
) -> ChildWorkflowResult:
    captured["workflow"] = workflow
    captured["message"] = message
    captured["parameters"] = dict(parameters)
    return child_result
def _write_run_history_record(
    root: Path,
    *,
    task_id: str,
    workflow_name: str,
    run_id: str,
    status: str,
    created_at: str,
    updated_at: str,
    request_text: str,
    events: list[dict[str, object]] | None = None,
    children: list[dict[str, object]] | None = None,
    parent_record: dict[str, object] | None = None,
    workflow_params: dict[str, object] | None = None,
    terminal: str | None = None,
    error: str | None = None,
    pending_question: str | None = None,
) -> Path:
    task_dir = root / ".autoloop" / "tasks" / task_id
    workflow_dir = task_dir / f"wf_{workflow_name}"
    run_dir = workflow_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "request.md").write_text(request_text, encoding="utf-8")
    (run_dir / "events.jsonl").write_text(
        "".join(json.dumps(entry, sort_keys=True) + "\n" for entry in (events or [])),
        encoding="utf-8",
    )
    (run_dir / "children.jsonl").write_text(
        "".join(json.dumps(entry, sort_keys=True) + "\n" for entry in (children or [])),
        encoding="utf-8",
    )
    if parent_record is not None:
        (run_dir / "parent.json").write_text(json.dumps(parent_record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload = {
        "created_at": created_at,
        "package_folder": str(Path("workflows") / workflow_name),
        "request_file": str(
            Path(".autoloop") / "tasks" / task_id / f"wf_{workflow_name}" / "runs" / run_id / "request.md"
        ),
        "run_folder": str(Path(".autoloop") / "tasks" / task_id / f"wf_{workflow_name}" / "runs" / run_id),
        "run_id": run_id,
        "status": status,
        "task_folder": str(Path(".autoloop") / "tasks" / task_id),
        "task_id": task_id,
        "updated_at": updated_at,
        "workflow_folder": str(Path(".autoloop") / "tasks" / task_id / f"wf_{workflow_name}"),
        "workflow_name": workflow_name,
        "workflow_params": dict(workflow_params or {}),
    }
    if terminal is not None:
        payload["terminal"] = terminal
    if error is not None:
        payload["error"] = error
    if pending_question is not None:
        payload["pending_question"] = pending_question
    (run_dir / "run.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return run_dir
def _write_task_operation_record(
    root: Path,
    *,
    task_id: str,
    created_at: str,
    updated_at: str,
    request_text: str,
    messages: list[tuple[str, str]],
) -> Path:
    task_dir = root / ".autoloop" / "tasks" / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "request.md").write_text(request_text, encoding="utf-8")
    (task_dir / "messages.jsonl").write_text(
        "".join(
            json.dumps({"message": message, "ts": ts}, sort_keys=True) + "\n"
            for ts, message in messages
        ),
        encoding="utf-8",
    )
    payload = {
        "created_at": created_at,
        "messages_file": str(Path(".autoloop") / "tasks" / task_id / "messages.jsonl"),
        "request_file": str(Path(".autoloop") / "tasks" / task_id / "request.md"),
        "request_updated_at": messages[-1][0] if messages else updated_at,
        "task_id": task_id,
        "updated_at": updated_at,
    }
    (task_dir / "task.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return task_dir
def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=_git_env(),
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout
def _git_env() -> dict[str, str]:
    blocked = {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CEILING_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_DIR",
        "GIT_INDEX_FILE",
        "GIT_NAMESPACE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_PREFIX",
        "GIT_SUPER_PREFIX",
        "GIT_WORK_TREE",
    }
    return {key: value for key, value in os.environ.items() if key not in blocked}
