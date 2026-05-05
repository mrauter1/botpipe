"""Closed-loop workflow refinement building-block workflow package."""

from __future__ import annotations

import json
from collections.abc import Mapping
from functools import partial
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from autoloop_optimizer import (
    derive_candidate_surface_manifest,
    materialize_baseline_surface,
    normalize_candidate_surface_boundary,
    normalize_candidate_surface_overlay_result,
    validate_authoritative_surface_sources_unchanged,
    validate_baseline_surface_manifest,
    validate_candidate_surface_manifest,
    validate_candidate_surface_overlay,
    write_selected_workflow_authoring_surface,
    write_selected_workflow_capability_snapshot,
)
from autoloop.stdlib import (
    normalize_optional_string,
    read_json_object,
    require_mapping,
    require_non_empty_string,
    require_positive_int,
    require_string_list,
    validate_selected_workflow_artifact_alignment,
    validate_selected_workflow_capability_and_authoring_snapshots,
)
from autoloop.stdlib.lifecycle import open_workflow_sessions, write_invocation_contract, write_publication_receipt, write_workflow_json

from autoloop import Event, FINISH, Outcome, Prompt, Session, Workflow, produce_verify_step, python_step
from autoloop.core import Artifact

from .contracts import (
    DESIGN_REFINEMENT_PLAN_ROUTE_CONTRACTS,
    EVALUATE_REFINED_WORKFLOW_ROUTE_CONTRACTS,
    FRAME_REFINEMENT_REQUEST_ROUTE_CONTRACTS,
    IMPLEMENT_REFINED_WORKFLOW_ROUTE_CONTRACTS,
    RefinementRequestFramingPayload,
    WorkflowRefinementBuildPayload,
    WorkflowRefinementEvaluationPayload,
    WorkflowRefinementPlanPayload,
)


_AUTHORITATIVE_EVALUATION_ARTIFACTS = frozenset(
    {
        "refinement_verification_report",
        "evaluation_delta_report",
        "promotion_record",
        "rollback_plan",
    }
)

_NO_FAILURE_MODES_SUPPLIED_TEXT = """# Failure Modes

No dedicated failure-modes artifact was supplied for this refinement run.
Use `baseline_evaluation_summary.json` and `baseline_evaluation_findings.md` as the authoritative baseline evidence.
"""

_REFINEMENT_EVIDENCE_SCHEMA = "autoloop.workflow_refinement_evidence/v1"
_ALLOWED_OPTIMIZATION_EVIDENCE_KINDS = frozenset(
    {
        "step_optimization_priority_report",
        "workflow_failure_scenarios",
        "producer_prompt_optimization_candidates",
        "verifier_rubric_optimization_candidates",
        "token_optimization_candidates",
        "adversarial_case_candidates",
        "workflow_level_optimization_candidates",
        "workflow_optimization_scorecard",
        "optimization_ablation_results",
    }
)


def _after_frame_refinement_request(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    payload = outcome.payload
    selected_workflow_name = payload.get("selected_workflow_name")
    ctx.state.framing_status = outcome.tag
    if isinstance(selected_workflow_name, str):
        ctx.state.selected_workflow_name = selected_workflow_name
    return None


def _after_design_refinement_plan(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    payload = outcome.payload
    selected_workflow_name = payload.get("selected_workflow_name")
    ctx.state.planning_status = outcome.tag
    if isinstance(selected_workflow_name, str):
        ctx.state.selected_workflow_name = selected_workflow_name
    return None


def _after_implement_refined_workflow(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    payload = outcome.payload
    selected_workflow_name = payload.get("selected_workflow_name")
    if outcome.tag == "needs_replan":
        ctx.state.build_status = outcome.tag
        if isinstance(selected_workflow_name, str):
            ctx.state.selected_workflow_name = selected_workflow_name
        return None

    candidate_manifest = _write_candidate_workflow_manifest(
        ctx.artifacts.candidate_workflow_manifest.path.parent,
        _read_json(ctx.artifacts.baseline_workflow_manifest.path),
        ctx.state.selected_workflow_name
        or _require_text(selected_workflow_name, "build payload must define selected_workflow_name"),
    )
    actual_candidate_file_count = _require_positive_int(
        candidate_manifest.get("file_count"),
        "candidate_workflow_manifest.json must define positive integer file_count",
    )
    actual_changed_relative_paths = _require_string_list(
        candidate_manifest.get("changed_relative_paths"),
        "candidate_workflow_manifest.json must define non-empty changed_relative_paths",
    )
    payload_candidate_file_count = _require_positive_int(
        payload.get("candidate_file_count"),
        "build verifier payload must define positive integer candidate_file_count",
    )
    payload_changed_relative_paths = _require_string_list(
        payload.get("changed_relative_paths"),
        "build verifier payload must define non-empty changed_relative_paths",
    )
    if payload_candidate_file_count != actual_candidate_file_count:
        raise ValueError("build verifier payload candidate_file_count must match candidate_workflow_manifest.json")
    if payload_changed_relative_paths != actual_changed_relative_paths:
        raise ValueError("build verifier payload changed_relative_paths must match candidate_workflow_manifest.json")
    ctx.state.build_status = outcome.tag
    if isinstance(selected_workflow_name, str):
        ctx.state.selected_workflow_name = selected_workflow_name
    ctx.state.candidate_file_count = actual_candidate_file_count
    ctx.state.candidate_changed_paths = actual_changed_relative_paths
    return None


def _after_evaluate_refined_workflow(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    payload = outcome.payload
    selected_workflow_name = payload.get("selected_workflow_name")
    candidate_file_count = _require_positive_int(
        payload.get("candidate_file_count"),
        "evaluation verifier payload must define positive integer candidate_file_count",
    )
    authoritative_artifacts = _require_string_list(
        payload.get("authoritative_artifacts"),
        "evaluation verifier payload must define non-empty authoritative_artifacts",
    )
    next_action = _require_text(
        payload.get("next_action"),
        "evaluation verifier payload must define a non-empty next_action",
    )
    ready_for_publication = payload.get("ready_for_publication")
    if outcome.tag == "workflow_refinement_evaluated" and ready_for_publication is not True:
        raise ValueError("workflow_refinement_evaluated requires ready_for_publication=true")
    if ctx.state.candidate_file_count and candidate_file_count != ctx.state.candidate_file_count:
        raise ValueError("evaluation verifier payload candidate_file_count must match workflow state")
    ctx.state.evaluation_status = outcome.tag
    if isinstance(selected_workflow_name, str):
        ctx.state.selected_workflow_name = selected_workflow_name
    ctx.state.candidate_file_count = candidate_file_count
    ctx.state.evaluation_authoritative_artifacts = authoritative_artifacts
    ctx.state.evaluation_next_action = next_action
    return None


class WorkflowAndEvalToRefinedWorkflowPackage(Workflow):
    """Turn one selected workflow plus evaluation evidence into a candidate refinement package."""

    name = "workflow_and_eval_to_refined_workflow_package"

    class State(BaseModel):
        selected_workflow_reference: str = ""
        selected_workflow_name: str | None = None
        task_title: str = ""
        evaluation_summary_path: str = ""
        evaluation_findings_path: str = ""
        failure_modes_path: str | None = None
        refinement_evidence_path: str | None = None
        sponsor_role: str | None = None
        desired_outcome: str | None = None
        constraints: list[str] = Field(default_factory=list)
        target_test_command: str = "pytest -q"
        framing_status: str | None = None
        planning_status: str | None = None
        build_status: str | None = None
        evaluation_status: str | None = None
        candidate_file_count: int = 0
        candidate_changed_paths: list[str] = Field(default_factory=list)
        evaluation_authoritative_artifacts: list[str] = Field(default_factory=list)
        evaluation_next_action: str | None = None
        published: bool = False

    frame_session = Session()
    design_session = Session()
    build_session = Session()
    evaluate_session = Session()

    request = Artifact("{run_folder}/request.md")
    framework_architecture_doc = Artifact("{root}/docs/architecture.md")
    framework_authoring_doc = Artifact("{root}/docs/authoring.md")
    workflow_instructions = Artifact("{root}/Workflow_Instructions.md")
    refinement_package_checklist = Artifact("{package_folder}/assets/refinement_package_checklist.md")

    invocation_contract = Artifact("{workflow_folder}/invocation_contract.json")
    selected_workflow_capability = Artifact("{workflow_folder}/selected_workflow_capability.json")
    selected_workflow_authoring_surface = Artifact("{workflow_folder}/selected_workflow_authoring_surface.json")
    baseline_workflow_surface = Artifact("{workflow_folder}/baseline_workflow_surface")
    baseline_workflow_manifest = Artifact("{workflow_folder}/baseline_workflow_manifest.json")
    baseline_evaluation_summary = Artifact("{workflow_folder}/baseline_evaluation_summary.json")
    baseline_evaluation_findings = Artifact("{workflow_folder}/baseline_evaluation_findings.md")
    baseline_failure_modes = Artifact("{workflow_folder}/baseline_failure_modes.md")
    baseline_refinement_evidence = Artifact("{workflow_folder}/baseline_refinement_evidence.json")
    baseline_refinement_evidence_summary = Artifact("{workflow_folder}/baseline_refinement_evidence.md")
    refinement_request_brief = Artifact("{workflow_folder}/refinement_request_brief.md")
    refinement_acceptance_criteria = Artifact("{workflow_folder}/refinement_acceptance_criteria.md")
    refinement_strategy = Artifact("{workflow_folder}/refinement_strategy.md")
    workflow_change_plan = Artifact("{workflow_folder}/workflow_change_plan.md")
    regression_guardrails = Artifact("{workflow_folder}/regression_guardrails.md")
    candidate_workflow_surface = Artifact("{workflow_folder}/candidate_workflow_surface")
    candidate_workflow_manifest = Artifact("{workflow_folder}/candidate_workflow_manifest.json")
    refinement_build_report = Artifact("{workflow_folder}/refinement_build_report.md")
    candidate_diff_summary = Artifact("{workflow_folder}/candidate_diff_summary.md")
    refinement_verification_report = Artifact("{workflow_folder}/refinement_verification_report.md")
    evaluation_delta_report = Artifact("{workflow_folder}/evaluation_delta_report.md")
    promotion_record = Artifact("{workflow_folder}/promotion_record.md")
    rollback_plan = Artifact("{workflow_folder}/rollback_plan.md")
    workflow_refinement_receipt = Artifact("{workflow_folder}/workflow_refinement_receipt.json")

    frame_refinement_request = produce_verify_step(
        producer_prompt=Prompt.file("prompts/frame_producer.md"),
        verifier_prompt=Prompt.file("prompts/frame_verifier.md"),
        session=frame_session,
        requires=[
            request,
            invocation_contract,
            selected_workflow_capability,
            selected_workflow_authoring_surface,
            baseline_workflow_manifest,
            baseline_evaluation_summary,
            baseline_evaluation_findings,
            baseline_failure_modes,
            baseline_refinement_evidence_summary,
            framework_architecture_doc,
            framework_authoring_doc,
            workflow_instructions,
        ],
        producer_writes=[refinement_request_brief, refinement_acceptance_criteria],
        control_schema=RefinementRequestFramingPayload,
        routes=FRAME_REFINEMENT_REQUEST_ROUTE_CONTRACTS,
        after_verifier=_after_frame_refinement_request,
    )
    design_refinement_plan = produce_verify_step(
        producer_prompt=Prompt.file("prompts/design_producer.md"),
        verifier_prompt=Prompt.file("prompts/design_verifier.md"),
        session=design_session,
        requires=[
            request,
            invocation_contract,
            selected_workflow_capability,
            selected_workflow_authoring_surface,
            baseline_workflow_manifest,
            baseline_evaluation_summary,
            baseline_evaluation_findings,
            baseline_failure_modes,
            baseline_refinement_evidence_summary,
            refinement_request_brief,
            refinement_acceptance_criteria,
        ],
        producer_writes=[refinement_strategy, workflow_change_plan, regression_guardrails],
        control_schema=WorkflowRefinementPlanPayload,
        routes=DESIGN_REFINEMENT_PLAN_ROUTE_CONTRACTS,
        after_verifier=_after_design_refinement_plan,
    )
    implement_refined_workflow = produce_verify_step(
        producer_prompt=Prompt.file("prompts/implement_producer.md"),
        verifier_prompt=Prompt.file("prompts/implement_verifier.md"),
        session=build_session,
        requires=[
            request,
            invocation_contract,
            selected_workflow_capability,
            selected_workflow_authoring_surface,
            baseline_workflow_surface,
            baseline_workflow_manifest,
            refinement_strategy,
            workflow_change_plan,
            regression_guardrails,
        ],
        producer_writes=[
            candidate_workflow_surface,
            candidate_workflow_manifest,
            refinement_build_report,
            candidate_diff_summary,
        ],
        control_schema=WorkflowRefinementBuildPayload,
        routes=IMPLEMENT_REFINED_WORKFLOW_ROUTE_CONTRACTS,
        after_verifier=_after_implement_refined_workflow,
    )
    evaluate_refined_workflow = produce_verify_step(
        producer_prompt=Prompt.file("prompts/evaluate_producer.md"),
        verifier_prompt=Prompt.file("prompts/evaluate_verifier.md"),
        session=evaluate_session,
        requires=[
            request,
            invocation_contract,
            selected_workflow_capability,
            selected_workflow_authoring_surface,
            baseline_workflow_surface,
            baseline_workflow_manifest,
            baseline_evaluation_summary,
            baseline_evaluation_findings,
            baseline_failure_modes,
            baseline_refinement_evidence_summary,
            refinement_strategy,
            workflow_change_plan,
            regression_guardrails,
            candidate_workflow_surface,
            candidate_workflow_manifest,
            refinement_build_report,
            candidate_diff_summary,
        ],
        producer_writes=[
            refinement_verification_report,
            evaluation_delta_report,
            promotion_record,
            rollback_plan,
        ],
        control_schema=WorkflowRefinementEvaluationPayload,
        routes=EVALUATE_REFINED_WORKFLOW_ROUTE_CONTRACTS,
        after_verifier=_after_evaluate_refined_workflow,
    )

    @python_step(
        name="bootstrap",
        requires=[request],
        writes=[invocation_contract],
        routes={"inputs_prepared": "capture_refinement_context"},
    )
    def bootstrap(ctx):
        params = ctx.params
        next_state = ctx.state.model_copy(
            update={
                "selected_workflow_reference": params.selected_workflow,
                "selected_workflow_name": None,
                "task_title": params.task_title,
                "evaluation_summary_path": params.evaluation_summary_path,
                "evaluation_findings_path": params.evaluation_findings_path,
                "failure_modes_path": params.failure_modes_path,
                "refinement_evidence_path": params.refinement_evidence_path,
                "sponsor_role": params.sponsor_role,
                "desired_outcome": params.desired_outcome,
                "constraints": list(params.constraints),
                "target_test_command": params.target_test_command,
                "framing_status": None,
                "planning_status": None,
                "build_status": None,
                "evaluation_status": None,
                "candidate_file_count": 0,
                "candidate_changed_paths": [],
                "evaluation_authoritative_artifacts": [],
                "evaluation_next_action": None,
                "published": False,
            }
        )
        open_workflow_sessions(ctx, "frame_session", "design_session", "build_session", "evaluate_session")
        write_invocation_contract(
            ctx,
            {
                "selected_workflow_reference": next_state.selected_workflow_reference,
                "task_title": next_state.task_title,
                "evaluation_summary_path": next_state.evaluation_summary_path,
                "evaluation_findings_path": next_state.evaluation_findings_path,
                "failure_modes_path": next_state.failure_modes_path,
                "refinement_evidence_path": next_state.refinement_evidence_path,
                "sponsor_role": next_state.sponsor_role,
                "desired_outcome": next_state.desired_outcome,
                "constraints": next_state.constraints,
                "target_test_command": next_state.target_test_command,
            },
        )
        ctx.state = next_state
        return "inputs_prepared"

    @python_step(
        name="capture_refinement_context",
        requires=[request, invocation_contract],
        writes=[
            selected_workflow_capability,
            selected_workflow_authoring_surface,
            baseline_workflow_surface,
            baseline_workflow_manifest,
            baseline_evaluation_summary,
            baseline_evaluation_findings,
            baseline_failure_modes,
            baseline_refinement_evidence,
            baseline_refinement_evidence_summary,
        ],
        routes={"refinement_context_captured": "frame_refinement_request"},
    )
    def capture_refinement_context(ctx):
        repo_root = _repo_root_from_context(ctx)
        capability_path = write_selected_workflow_capability_snapshot(ctx, ctx.state.selected_workflow_reference)
        authoring_surface_path = write_selected_workflow_authoring_surface(ctx, ctx.state.selected_workflow_reference)

        capability_snapshot = _read_json(capability_path)
        authoring_snapshot = _read_json(authoring_surface_path)
        _require_text(ctx.state.selected_workflow_reference, "selected_workflow_reference must stay non-empty")
        selected_workflow_name, _, authoring_surface = validate_selected_workflow_capability_and_authoring_snapshots(
            capability_snapshot,
            authoring_snapshot,
        )
        baseline_manifest = _write_baseline_workflow_manifest(
            ctx,
            repo_root=repo_root,
            selected_workflow_name=selected_workflow_name,
            authoring_surface=authoring_surface,
        )

        summary_source = _resolve_input_path(repo_root, ctx.state.evaluation_summary_path, "evaluation_summary_path")
        findings_source = _resolve_input_path(repo_root, ctx.state.evaluation_findings_path, "evaluation_findings_path")
        summary_payload = _read_json(summary_source)
        _validate_evaluation_summary_selected_workflow(summary_payload, selected_workflow_name)
        write_workflow_json(ctx, "baseline_evaluation_summary.json", summary_payload)
        _write_text(ctx.workflow_folder / "baseline_evaluation_findings.md", findings_source.read_text(encoding="utf-8"))

        if ctx.state.failure_modes_path is None:
            failure_modes_text = _NO_FAILURE_MODES_SUPPLIED_TEXT
        else:
            failure_modes_source = _resolve_input_path(repo_root, ctx.state.failure_modes_path, "failure_modes_path")
            failure_modes_text = failure_modes_source.read_text(encoding="utf-8")
        _write_text(ctx.workflow_folder / "baseline_failure_modes.md", failure_modes_text)
        _write_refinement_evidence_inputs(
            ctx,
            repo_root=repo_root,
            selected_workflow_name=selected_workflow_name,
            refinement_evidence_path=ctx.state.refinement_evidence_path,
        )
        ctx.state.selected_workflow_name = selected_workflow_name
        return Event("refinement_context_captured")

    @python_step(
        name="publish_refined_workflow",
        requires=[
            selected_workflow_capability,
            selected_workflow_authoring_surface,
            baseline_workflow_manifest,
            baseline_evaluation_summary,
            baseline_evaluation_findings,
            baseline_failure_modes,
            baseline_refinement_evidence,
            baseline_refinement_evidence_summary,
            candidate_workflow_manifest,
            refinement_verification_report,
            evaluation_delta_report,
            promotion_record,
            rollback_plan,
        ],
        writes=[workflow_refinement_receipt],
        routes={"workflow_refinement_published": FINISH},
    )
    def publish_refined_workflow(ctx):
        workflow_folder = ctx.workflow_folder
        required_paths = {
            "selected_workflow_capability": workflow_folder / "selected_workflow_capability.json",
            "selected_workflow_authoring_surface": workflow_folder / "selected_workflow_authoring_surface.json",
            "baseline_workflow_manifest": workflow_folder / "baseline_workflow_manifest.json",
            "baseline_evaluation_summary": workflow_folder / "baseline_evaluation_summary.json",
            "baseline_evaluation_findings": workflow_folder / "baseline_evaluation_findings.md",
            "baseline_failure_modes": workflow_folder / "baseline_failure_modes.md",
            "baseline_refinement_evidence": workflow_folder / "baseline_refinement_evidence.json",
            "baseline_refinement_evidence_summary": workflow_folder / "baseline_refinement_evidence.md",
            "candidate_workflow_manifest": workflow_folder / "candidate_workflow_manifest.json",
            "refinement_verification_report": workflow_folder / "refinement_verification_report.md",
            "evaluation_delta_report": workflow_folder / "evaluation_delta_report.md",
            "promotion_record": workflow_folder / "promotion_record.md",
            "rollback_plan": workflow_folder / "rollback_plan.md",
        }
        required_dirs = {
            "baseline_workflow_surface": workflow_folder / "baseline_workflow_surface",
            "candidate_workflow_surface": workflow_folder / "candidate_workflow_surface",
        }
        for artifact_path in required_paths.values():
            if not artifact_path.exists():
                raise FileNotFoundError(f"missing required publication artifact at {artifact_path}")
        for artifact_path in required_dirs.values():
            if not artifact_path.exists():
                raise FileNotFoundError(f"missing required publication artifact at {artifact_path}")

        repo_root = _repo_root_from_context(ctx)
        capability_snapshot = _read_json(required_paths["selected_workflow_capability"])
        authoring_snapshot = _read_json(required_paths["selected_workflow_authoring_surface"])
        baseline_manifest = _read_json(required_paths["baseline_workflow_manifest"])
        candidate_manifest = _read_json(required_paths["candidate_workflow_manifest"])
        _require_non_empty_text_file(
            required_paths["baseline_evaluation_findings"],
            "baseline_evaluation_findings.md must be non-empty",
        )
        _require_non_empty_text_file(
            required_paths["baseline_failure_modes"],
            "baseline_failure_modes.md must be non-empty",
        )
        baseline_evaluation_summary = _read_json(required_paths["baseline_evaluation_summary"])
        _require_non_empty_text_file(
            required_paths["refinement_verification_report"],
            "refinement_verification_report.md must be non-empty",
        )
        _require_non_empty_text_file(
            required_paths["evaluation_delta_report"],
            "evaluation_delta_report.md must be non-empty",
        )
        _require_non_empty_text_file(
            required_paths["promotion_record"],
            "promotion_record.md must be non-empty",
        )
        _require_non_empty_text_file(
            required_paths["rollback_plan"],
            "rollback_plan.md must be non-empty",
        )

        _require_text(ctx.state.selected_workflow_reference, "selected_workflow_reference must stay non-empty")
        selected_workflow_name, _, authoring_surface = validate_selected_workflow_capability_and_authoring_snapshots(
            capability_snapshot,
            authoring_snapshot,
        )
        refinement_evidence_payload = _read_json(required_paths["baseline_refinement_evidence"])
        _validate_refinement_evidence_payload(refinement_evidence_payload, selected_workflow_name)
        _require_non_empty_text_file(
            required_paths["baseline_refinement_evidence_summary"],
            "baseline_refinement_evidence.md must be non-empty",
        )
        _validate_evaluation_summary_selected_workflow(baseline_evaluation_summary, selected_workflow_name)
        if ctx.state.selected_workflow_name is not None and ctx.state.selected_workflow_name != selected_workflow_name:
            raise ValueError("selected_workflow snapshots must match workflow state")
        expected_boundary = _authoring_surface_boundary(authoring_surface, repo_root)

        baseline_relative_paths = _require_string_list(
            baseline_manifest.get("relative_paths"),
            "baseline_workflow_manifest.json must define non-empty relative_paths",
        )
        if baseline_relative_paths != expected_boundary["baseline_relative_paths"]:
            raise ValueError(
                "baseline_workflow_manifest.json relative_paths must match selected_workflow_authoring_surface.json"
            )
        _validate_capability_matches_authoring_surface(capability_snapshot, authoring_surface)
        _validate_baseline_manifest(baseline_manifest, repo_root, expected_boundary)
        _validate_authoritative_files_unchanged(baseline_manifest, repo_root)
        _validate_candidate_manifest(candidate_manifest, repo_root, expected_boundary, baseline_manifest)

        candidate_file_count = _require_positive_int(
            candidate_manifest.get("file_count"),
            "candidate_workflow_manifest.json must define positive integer file_count",
        )
        candidate_changed_paths = _require_string_list(
            candidate_manifest.get("changed_relative_paths"),
            "candidate_workflow_manifest.json must define non-empty changed_relative_paths",
        )
        if ctx.state.candidate_file_count and candidate_file_count != ctx.state.candidate_file_count:
            raise ValueError("candidate_workflow_manifest.json file_count must match workflow state")
        if ctx.state.candidate_changed_paths and candidate_changed_paths != ctx.state.candidate_changed_paths:
            raise ValueError("candidate_workflow_manifest.json changed_relative_paths must match workflow state")
        if not _AUTHORITATIVE_EVALUATION_ARTIFACTS.issubset(ctx.state.evaluation_authoritative_artifacts):
            raise ValueError(
                "workflow state authoritative evaluation artifacts must include refinement_verification_report, evaluation_delta_report, promotion_record, and rollback_plan"
            )
        if ctx.state.evaluation_next_action is None:
            raise ValueError("workflow state must define evaluation_next_action before publication")

        overlay_validation = _validate_candidate_overlay(
            repo_root=repo_root,
            selected_workflow_name=selected_workflow_name,
            candidate_manifest=candidate_manifest,
            target_test_command=ctx.state.target_test_command,
        )

        write_publication_receipt(
            ctx,
            "workflow_refinement_receipt.json",
            {
                "workflow_name": ctx.workflow_name,
                "task_title": ctx.state.task_title,
                "sponsor_role": ctx.state.sponsor_role,
                "desired_outcome": ctx.state.desired_outcome,
                "selected_workflow_reference": ctx.state.selected_workflow_reference,
                "selected_workflow_name": selected_workflow_name,
                "target_test_command": ctx.state.target_test_command,
                "candidate_file_count": candidate_file_count,
                "changed_relative_paths": candidate_changed_paths,
                "authoritative_artifacts": [
                    "selected_workflow_capability",
                    "selected_workflow_authoring_surface",
                    "baseline_workflow_manifest",
                    "candidate_workflow_manifest",
                    "refinement_verification_report",
                    "evaluation_delta_report",
                    "promotion_record",
                    "rollback_plan",
                    "workflow_refinement_receipt",
                ],
                "selected_workflow_capability": str(required_paths["selected_workflow_capability"]),
                "selected_workflow_authoring_surface": str(required_paths["selected_workflow_authoring_surface"]),
                "baseline_workflow_surface": str(required_dirs["baseline_workflow_surface"]),
                "baseline_workflow_manifest": str(required_paths["baseline_workflow_manifest"]),
                "baseline_evaluation_summary": str(required_paths["baseline_evaluation_summary"]),
                "baseline_evaluation_findings": str(required_paths["baseline_evaluation_findings"]),
                "baseline_failure_modes": str(required_paths["baseline_failure_modes"]),
                "baseline_refinement_evidence": str(required_paths["baseline_refinement_evidence"]),
                "baseline_refinement_evidence_summary": str(required_paths["baseline_refinement_evidence_summary"]),
                "candidate_workflow_surface": str(required_dirs["candidate_workflow_surface"]),
                "candidate_workflow_manifest": str(required_paths["candidate_workflow_manifest"]),
                "refinement_verification_report": str(required_paths["refinement_verification_report"]),
                "evaluation_delta_report": str(required_paths["evaluation_delta_report"]),
                "promotion_record": str(required_paths["promotion_record"]),
                "rollback_plan": str(required_paths["rollback_plan"]),
                "next_action": ctx.state.evaluation_next_action,
                "overlay_validation": overlay_validation,
                "published": True,
            },
        )
        ctx.state.selected_workflow_name = selected_workflow_name
        ctx.state.published = True
        return "workflow_refinement_published"

    entry = bootstrap



def _repo_root_from_context(ctx) -> Path:
    return ctx.root.resolve()


def _validate_evaluation_summary_selected_workflow(
    summary_payload: Mapping[str, Any],
    selected_workflow_name: str,
) -> None:
    validate_selected_workflow_artifact_alignment(
        summary_payload,
        artifact_name="baseline_evaluation_summary.json",
        expected_selected_workflow_name=selected_workflow_name,
        expected_artifact_name="selected workflow",
    )


def _write_baseline_workflow_manifest(
    ctx,
    *,
    repo_root: Path,
    selected_workflow_name: str,
    authoring_surface: Mapping[str, Any],
) -> dict[str, Any]:
    boundary = _authoring_surface_boundary(authoring_surface, repo_root)
    surface_manifest = materialize_baseline_surface(
        workflow_folder=ctx.workflow_folder,
        repo_root=repo_root,
        baseline_relative_paths=boundary["baseline_source_entries"],
        baseline_dir_name="baseline_workflow_surface",
        candidate_dir_name="candidate_workflow_surface",
    )

    manifest = {
        "surface_kind": "baseline",
        "selected_workflow_name": selected_workflow_name,
        "package_name": boundary["package_name"],
        "package_root_relative_path": boundary["package_root_relative_path"],
        "doc_relative_path": boundary["doc_relative_path"],
        "runtime_test_relative_path": boundary["runtime_test_relative_path"],
        "repo_root": str(repo_root),
        **surface_manifest,
    }
    write_workflow_json(ctx, "baseline_workflow_manifest.json", manifest)
    return manifest


def _write_candidate_workflow_manifest(
    workflow_folder: Path,
    baseline_manifest: Mapping[str, Any],
    selected_workflow_name: str,
) -> dict[str, Any]:
    package_name = _require_text(
        baseline_manifest.get("package_name"),
        "baseline_workflow_manifest.json must define non-empty package_name",
    )
    package_root_relative_path = _require_text(
        baseline_manifest.get("package_root_relative_path"),
        "baseline_workflow_manifest.json must define non-empty package_root_relative_path",
    )
    doc_relative_path = _normalize_optional_text(baseline_manifest.get("doc_relative_path"))
    runtime_test_relative_path = _normalize_optional_text(baseline_manifest.get("runtime_test_relative_path"))
    surface_manifest = derive_candidate_surface_manifest(
        workflow_folder=workflow_folder,
        baseline_manifest=baseline_manifest,
        candidate_dir_name="candidate_workflow_surface",
        baseline_manifest_label="baseline_workflow_manifest.json",
        candidate_manifest_label="candidate_workflow_manifest.json",
    )

    manifest = {
        "surface_kind": "candidate",
        "selected_workflow_name": selected_workflow_name,
        "package_name": package_name,
        "package_root_relative_path": package_root_relative_path,
        "doc_relative_path": doc_relative_path,
        "runtime_test_relative_path": runtime_test_relative_path,
        **surface_manifest,
    }
    target_path = workflow_folder / "candidate_workflow_manifest.json"
    target_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def _authoring_surface_boundary(authoring_surface: Mapping[str, Any], repo_root: Path) -> dict[str, Any]:
    normalized_boundary = normalize_candidate_surface_boundary(
        repo_root,
        authoring_surface,
        error_prefix="selected_workflow_authoring_surface.json",
    )
    return {
        "package_name": _require_text(
            authoring_surface.get("package_name"),
            "selected_workflow_authoring_surface.json must define selected_workflow_authoring_surface.package_name",
        ),
        **normalized_boundary,
    }


def _validate_capability_matches_authoring_surface(
    capability_snapshot: Mapping[str, Any],
    authoring_surface: Mapping[str, Any],
) -> None:
    capability = _require_mapping(
        capability_snapshot.get("selected_workflow_capability"),
        "selected_workflow_capability.json must define selected_workflow_capability as a JSON object",
    )
    if _require_text(
        capability.get("package_name"),
        "selected_workflow_capability.json must define selected_workflow_capability.package_name",
    ) != _require_text(
        authoring_surface.get("package_name"),
        "selected_workflow_authoring_surface.json must define selected_workflow_authoring_surface.package_name",
    ):
        raise ValueError("selected_workflow_authoring_surface.json package_name must match selected_workflow_capability.json")
    if _require_text(
        capability.get("workflow_path"),
        "selected_workflow_capability.json must define selected_workflow_capability.workflow_path",
    ) != _require_text(
        authoring_surface.get("workflow_path"),
        "selected_workflow_authoring_surface.json must define selected_workflow_authoring_surface.workflow_path",
    ):
        raise ValueError("selected_workflow_authoring_surface.json workflow_path must match selected_workflow_capability.json")
    if _require_text(
        capability.get("manifest_path"),
        "selected_workflow_capability.json must define selected_workflow_capability.manifest_path",
    ) != _require_text(
        authoring_surface.get("manifest_path"),
        "selected_workflow_authoring_surface.json must define selected_workflow_authoring_surface.manifest_path",
    ):
        raise ValueError("selected_workflow_authoring_surface.json manifest_path must match selected_workflow_capability.json")
    if _normalize_optional_text(capability.get("params_path")) != _normalize_optional_text(authoring_surface.get("params_path")):
        raise ValueError("selected_workflow_authoring_surface.json params_path must match selected_workflow_capability.json")
    if _normalize_optional_text(capability.get("doc_path")) != _normalize_optional_text(authoring_surface.get("doc_path")):
        raise ValueError("selected_workflow_authoring_surface.json doc_path must match selected_workflow_capability.json")


def _validate_baseline_manifest(
    baseline_manifest: Mapping[str, Any],
    repo_root: Path,
    expected_boundary: Mapping[str, Any],
) -> None:
    validate_baseline_surface_manifest(
        baseline_manifest,
        repo_root,
        manifest_label="baseline_workflow_manifest.json",
        expected_surface_kind="baseline",
        expected_boundary=expected_boundary,
        boundary_field_map={
            "package_name": "package_name",
            "package_root_relative_path": "package_root_relative_path",
            "doc_relative_path": "doc_relative_path",
            "runtime_test_relative_path": "runtime_test_relative_path",
        },
        optional_boundary_fields=("doc_relative_path", "runtime_test_relative_path"),
        expected_relative_paths=_require_string_list(
            expected_boundary.get("baseline_relative_paths"),
            "expected boundary must define non-empty baseline_relative_paths",
        ),
    )


def _validate_authoritative_files_unchanged(baseline_manifest: Mapping[str, Any], repo_root: Path) -> None:
    validate_authoritative_surface_sources_unchanged(
        baseline_manifest,
        repo_root,
        baseline_manifest_label="baseline_workflow_manifest.json",
        drift_error_prefix="authoritative selected workflow file changed during refinement publication",
    )


def _validate_candidate_manifest(
    candidate_manifest: Mapping[str, Any],
    repo_root: Path,
    expected_boundary: Mapping[str, Any],
    baseline_manifest: Mapping[str, Any],
) -> None:
    try:
        validate_candidate_surface_manifest(
            candidate_manifest,
            repo_root=repo_root,
            manifest_label="candidate_workflow_manifest.json",
            expected_surface_kind="candidate",
            expected_boundary=expected_boundary,
            boundary_field_map={
                "package_name": "package_name",
                "package_root_relative_path": "package_root_relative_path",
                "doc_relative_path": "doc_relative_path",
                "runtime_test_relative_path": "runtime_test_relative_path",
            },
            optional_boundary_fields=("doc_relative_path", "runtime_test_relative_path"),
            baseline_manifest=baseline_manifest,
            baseline_manifest_label="baseline_workflow_manifest.json",
            allowed_added_path_prefixes=[
                _require_text(
                    expected_boundary.get("package_root_relative_path"),
                    "expected boundary must define package_root_relative_path",
                )
            ],
            allowed_added_exact_paths=[
                _normalize_optional_text(expected_boundary.get("doc_relative_path")),
                _normalize_optional_text(expected_boundary.get("runtime_test_relative_path")),
            ],
        )
    except ValueError as exc:
        if str(exc) == "candidate_workflow_manifest.json must stay within the allowed repo-relative boundary":
            raise ValueError("candidate_workflow_manifest.json must stay scoped to the selected workflow boundary") from exc
        raise


def _validate_candidate_overlay(
    *,
    repo_root: Path,
    selected_workflow_name: str,
    candidate_manifest: Mapping[str, Any],
    target_test_command: str,
) -> dict[str, Any]:
    return normalize_candidate_surface_overlay_result(
        validate_candidate_surface_overlay(
            repo_root=repo_root,
            workflow_names=selected_workflow_name,
            candidate_manifest=candidate_manifest,
            target_test_command=target_test_command,
            candidate_manifest_label="candidate_workflow_manifest.json",
            overlay_failure_prefix="overlay validation command failed for candidate workflow surface",
            overlay_temp_prefix="workflow_refinement_overlay_",
        ),
        expect_single_compiled_workflow=True,
    )


def _resolve_input_path(repo_root: Path, raw_value: str, field_name: str) -> Path:
    candidate = Path(_require_text(raw_value, f"{field_name} must be non-empty"))
    path = candidate if candidate.is_absolute() else repo_root / candidate
    if not path.exists():
        raise FileNotFoundError(f"{field_name} does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"{field_name} must point to a file: {path}")
    return path


def _write_refinement_evidence_inputs(
    ctx,
    *,
    repo_root: Path,
    selected_workflow_name: str,
    refinement_evidence_path: str | None,
) -> None:
    if refinement_evidence_path is None:
        payload = {
            "schema": _REFINEMENT_EVIDENCE_SCHEMA,
            "source_path": None,
            "target_workflow_id": selected_workflow_name,
            "evidence_entries": [],
        }
    else:
        source_path = _resolve_input_path(repo_root, refinement_evidence_path, "refinement_evidence_path")
        payload = _read_json(source_path)
        _validate_refinement_evidence_payload(payload, selected_workflow_name)
        payload = {
            "schema": _REFINEMENT_EVIDENCE_SCHEMA,
            "source_path": str(source_path),
            "target_workflow_id": selected_workflow_name,
            "evidence_entries": [dict(entry) for entry in payload["evidence_entries"]],
        }

    write_workflow_json(ctx, "baseline_refinement_evidence.json", payload)
    _write_text(ctx.workflow_folder / "baseline_refinement_evidence.md", _render_refinement_evidence_summary(payload))


def _validate_refinement_evidence_payload(payload: Mapping[str, Any], selected_workflow_name: str) -> None:
    if _require_text(
        payload.get("schema"),
        "baseline_refinement_evidence.json must define non-empty schema",
    ) != _REFINEMENT_EVIDENCE_SCHEMA:
        raise ValueError("baseline_refinement_evidence.json schema must equal autoloop.workflow_refinement_evidence/v1")
    if _require_text(
        payload.get("target_workflow_id"),
        "baseline_refinement_evidence.json must define non-empty target_workflow_id",
    ) != selected_workflow_name:
        raise ValueError("baseline_refinement_evidence.json target_workflow_id must match selected workflow")
    raw_entries = payload.get("evidence_entries")
    if not isinstance(raw_entries, list):
        raise ValueError("baseline_refinement_evidence.json must define evidence_entries as a JSON array")
    for index, raw_entry in enumerate(raw_entries):
        if not isinstance(raw_entry, Mapping):
            raise ValueError("baseline_refinement_evidence.json evidence_entries must contain JSON objects")
        kind = _require_text(
            raw_entry.get("kind"),
            f"baseline_refinement_evidence.json evidence_entries[{index}].kind must be non-empty",
        )
        if kind not in _ALLOWED_OPTIMIZATION_EVIDENCE_KINDS:
            raise ValueError(f"baseline_refinement_evidence.json evidence_entries[{index}].kind is not supported")
        _require_text(
            raw_entry.get("path"),
            f"baseline_refinement_evidence.json evidence_entries[{index}].path must be non-empty",
        )
        _require_text(
            raw_entry.get("summary"),
            f"baseline_refinement_evidence.json evidence_entries[{index}].summary must be non-empty",
        )
        _require_text(
            raw_entry.get("handling"),
            f"baseline_refinement_evidence.json evidence_entries[{index}].handling must be non-empty",
        )


def _render_refinement_evidence_summary(payload: Mapping[str, Any]) -> str:
    entries = payload.get("evidence_entries")
    assert isinstance(entries, list)
    source_path = payload.get("source_path")
    lines = [
        "# Refinement Evidence",
        "",
        f"- Target workflow: `{_require_text(payload.get('target_workflow_id'), 'refinement evidence target_workflow_id must be non-empty')}`.",
        (
            f"- Source path: `{source_path}`."
            if isinstance(source_path, str) and source_path
            else "- No additional optimization refinement evidence was supplied for this run."
        ),
        "- Optimization candidates are candidate-only input and remain unproven until separate ablation or rerun evidence exists.",
        "- `optimization_ablation_results`, when present, are stronger evidence than candidate estimates.",
        "- Token optimization candidates must preserve semantics before any later materialization.",
        "- `adversarial_case_candidates` should usually feed `workflow_to_eval_suite` before prompt or workflow promotion.",
        "",
        "## Evidence Entries",
    ]
    if not entries:
        lines.extend(("", "- No additional refinement evidence entries were supplied.", ""))
        return "\n".join(lines)

    for raw_entry in entries:
        entry = dict(raw_entry)
        lines.extend(
            (
                "",
                f"- `{entry['kind']}` from `{entry['path']}`",
                f"  Summary: {entry['summary']}",
                f"  Handling: {entry['handling']}",
            )
        )
    lines.append("")
    return "\n".join(lines)


_read_json = read_json_object


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _require_non_empty_text_file(path: Path, error_message: str) -> str:
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(error_message)
    return content


_require_text = partial(require_non_empty_string, coerce=True)
_normalize_optional_text = normalize_optional_string
_require_string_list = partial(require_string_list, dedupe=True, coerce=True)
_require_positive_int = require_positive_int
_require_mapping = require_mapping
