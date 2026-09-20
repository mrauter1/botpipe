"""Closed-loop workflow refinement building-block workflow package."""

from __future__ import annotations

import json
from collections.abc import Mapping
from functools import partial
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from botpipe_optimizer import (
    derive_candidate_surface_manifest,
    materialize_baseline_surface,
    normalize_candidate_surface_boundary,
    validate_authoritative_surface_sources_unchanged,
    validate_baseline_surface_manifest,
    validate_candidate_surface_manifest,
    write_selected_workflow_authoring_surface,
    write_selected_workflow_capability_snapshot,
)
from botpipe_optimizer.candidate_validation import (
    ValidationResult,
    validate_frozen_candidate,
)
from botpipe_optimizer.execution_trees import (
    ExecutionArm,
    assert_execution_arm_unchanged,
    capture_execution_tree,
    cleanup_owned_directory,
    materialize_execution_arm,
    snapshot_execution_arm,
    verify_frozen_execution_tree,
)
from botpipe_optimizer.paired_evaluation import (
    PAIRED_EVALUATION_SCHEMA,
    finalize_paired_evaluation_record,
    load_evaluation_spec,
    run_paired_evaluation,
    validate_paired_evaluation_record,
)
from botpipe_optimizer.candidate_surfaces import derive_surface_manifest
from botpipe.stdlib import (
    normalize_optional_string,
    read_json_object,
    read_required_text,
    require_mapping,
    require_non_empty_string,
    require_positive_int,
    require_string_list,
    validate_selected_workflow_artifact_alignment,
    validate_selected_workflow_capability_and_authoring_snapshots,
)
from botpipe.stdlib.lifecycle import (
    open_workflow_sessions,
    write_invocation_contract,
    write_publication_receipt,
    write_workflow_json,
)

from botpipe import (
    Event,
    FINISH,
    Prompt,
    Session,
    Workflow,
    produce_verify_step,
    python_step,
)
from botpipe.core import Artifact
from botpipe.core.schema_registry import WORKFLOW_REFINEMENT_EVIDENCE_SCHEMA
from botpipe_optimizer.recommendations import (
    OptimizationCandidateSelection,
    load_optimization_candidate,
)
from botpipe_optimizer.records import REFINEMENT_HANDOFF_SCHEMA

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

_REFINEMENT_EVIDENCE_SCHEMA = WORKFLOW_REFINEMENT_EVIDENCE_SCHEMA
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
        or _require_text(
            selected_workflow_name, "build payload must define selected_workflow_name"
        ),
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
        raise ValueError(
            "build verifier payload candidate_file_count must match candidate_workflow_manifest.json"
        )
    if payload_changed_relative_paths != actual_changed_relative_paths:
        raise ValueError(
            "build verifier payload changed_relative_paths must match candidate_workflow_manifest.json"
        )
    ctx.state.build_status = outcome.tag
    if isinstance(selected_workflow_name, str):
        ctx.state.selected_workflow_name = selected_workflow_name
    ctx.state.candidate_file_count = actual_candidate_file_count
    ctx.state.candidate_changed_paths = actual_changed_relative_paths
    ctx.state.candidate_surface_id = candidate_manifest["surface_id"]
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
    if (
        outcome.tag == "workflow_refinement_evaluated"
        and ready_for_publication is not True
    ):
        raise ValueError(
            "workflow_refinement_evaluated requires ready_for_publication=true"
        )
    if (
        ctx.state.candidate_file_count
        and candidate_file_count != ctx.state.candidate_file_count
    ):
        raise ValueError(
            "evaluation verifier payload candidate_file_count must match workflow state"
        )
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
        evaluation_summary_path: str | None = None
        evaluation_findings_path: str | None = None
        optimization_receipt_path: str | None = None
        candidate_id: str | None = None
        evaluation_spec_path: str | None = None
        failure_modes_path: str | None = None
        refinement_evidence_path: str | None = None
        sponsor_role: str | None = None
        desired_outcome: str | None = None
        constraints: list[str] = Field(default_factory=list)
        target_test_command: str | None = None
        target_test_argv: list[str] | None = Field(
            default_factory=lambda: ["pytest", "-q"]
        )
        framing_status: str | None = None
        planning_status: str | None = None
        build_status: str | None = None
        evaluation_status: str | None = None
        candidate_file_count: int = 0
        candidate_changed_paths: list[str] = Field(default_factory=list)
        baseline_surface_id: str | None = None
        baseline_authoritative_sources: dict[str, str] = Field(default_factory=dict)
        candidate_surface_id: str | None = None
        evaluation_authoritative_artifacts: list[str] = Field(default_factory=list)
        evaluation_next_action: str | None = None
        published: bool = False

    frame_session = Session()
    design_session = Session()
    build_session = Session()
    evaluate_session = Session()

    request = Artifact("{{ run.folder }}/request.md")
    framework_architecture_doc = Artifact("{{ root }}/docs/architecture.md")
    framework_authoring_doc = Artifact("{{ root }}/docs/authoring.md")
    workflow_authoring_guidelines = Artifact(
        "{{ root }}/docs/workflow_authoring_guidelines.md"
    )
    refinement_package_checklist = Artifact(
        "{{ package.folder }}/assets/refinement_package_checklist.md"
    )

    invocation_contract = Artifact("{{ workflow.folder }}/invocation_contract.json")
    selected_workflow_capability = Artifact(
        "{{ workflow.folder }}/selected_workflow_capability.json"
    )
    selected_workflow_authoring_surface = Artifact(
        "{{ workflow.folder }}/selected_workflow_authoring_surface.json"
    )
    baseline_workflow_surface = Artifact(
        "{{ workflow.folder }}/baseline_workflow_surface"
    )
    baseline_workflow_manifest = Artifact(
        "{{ workflow.folder }}/baseline_workflow_manifest.json"
    )
    baseline_evaluation_summary = Artifact(
        "{{ workflow.folder }}/baseline_evaluation_summary.json"
    )
    baseline_evaluation_findings = Artifact(
        "{{ workflow.folder }}/baseline_evaluation_findings.md"
    )
    baseline_failure_modes = Artifact("{{ workflow.folder }}/baseline_failure_modes.md")
    baseline_refinement_evidence = Artifact(
        "{{ workflow.folder }}/baseline_refinement_evidence.json"
    )
    baseline_refinement_evidence_summary = Artifact(
        "{{ workflow.folder }}/baseline_refinement_evidence.md"
    )
    refinement_request_brief = Artifact(
        "{{ workflow.folder }}/refinement_request_brief.md"
    )
    refinement_acceptance_criteria = Artifact(
        "{{ workflow.folder }}/refinement_acceptance_criteria.md"
    )
    refinement_strategy = Artifact("{{ workflow.folder }}/refinement_strategy.md")
    workflow_change_plan = Artifact("{{ workflow.folder }}/workflow_change_plan.md")
    regression_guardrails = Artifact("{{ workflow.folder }}/regression_guardrails.md")
    candidate_workflow_surface = Artifact(
        "{{ workflow.folder }}/candidate_workflow_surface"
    )
    candidate_workflow_manifest = Artifact(
        "{{ workflow.folder }}/candidate_workflow_manifest.json"
    )
    refinement_build_report = Artifact(
        "{{ workflow.folder }}/refinement_build_report.md"
    )
    candidate_diff_summary = Artifact("{{ workflow.folder }}/candidate_diff_summary.md")
    refinement_verification_report = Artifact(
        "{{ workflow.folder }}/refinement_verification_report.md"
    )
    evaluation_delta_report = Artifact(
        "{{ workflow.folder }}/evaluation_delta_report.md"
    )
    promotion_record = Artifact("{{ workflow.folder }}/promotion_record.md")
    rollback_plan = Artifact("{{ workflow.folder }}/rollback_plan.md")
    paired_evaluation_result = Artifact(
        "{{ workflow.folder }}/paired_evaluation_result.json"
    )
    workflow_refinement_receipt = Artifact(
        "{{ workflow.folder }}/workflow_refinement_receipt.json"
    )

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
            workflow_authoring_guidelines,
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
        producer_writes=[
            refinement_strategy,
            workflow_change_plan,
            regression_guardrails,
        ],
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
        writes=[invocation_contract, workflow_refinement_receipt],
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
                "optimization_receipt_path": params.optimization_receipt_path,
                "candidate_id": params.candidate_id,
                "evaluation_spec_path": params.evaluation_spec_path,
                "failure_modes_path": params.failure_modes_path,
                "refinement_evidence_path": params.refinement_evidence_path,
                "sponsor_role": params.sponsor_role,
                "desired_outcome": params.desired_outcome,
                "constraints": list(params.constraints),
                "target_test_command": params.target_test_command,
                "target_test_argv": params.target_test_argv,
                "framing_status": None,
                "planning_status": None,
                "build_status": None,
                "evaluation_status": None,
                "candidate_file_count": 0,
                "candidate_changed_paths": [],
                "baseline_surface_id": None,
                "baseline_authoritative_sources": {},
                "candidate_surface_id": None,
                "evaluation_authoritative_artifacts": [],
                "evaluation_next_action": None,
                "published": False,
            }
        )
        write_workflow_json(
            ctx,
            "workflow_refinement_receipt.json",
            {
                "workflow_name": ctx.workflow_name,
                "run_id": ctx.run_id,
                "published": False,
                "status": "incomplete",
                "stop_reason": "refinement_in_progress",
            },
        )
        open_workflow_sessions(
            ctx, "frame_session", "design_session", "build_session", "evaluate_session"
        )
        write_invocation_contract(
            ctx,
            {
                "selected_workflow_reference": next_state.selected_workflow_reference,
                "task_title": next_state.task_title,
                "evaluation_summary_path": next_state.evaluation_summary_path,
                "evaluation_findings_path": next_state.evaluation_findings_path,
                "optimization_receipt_path": next_state.optimization_receipt_path,
                "candidate_id": next_state.candidate_id,
                "evaluation_spec_path": next_state.evaluation_spec_path,
                "failure_modes_path": next_state.failure_modes_path,
                "refinement_evidence_path": next_state.refinement_evidence_path,
                "sponsor_role": next_state.sponsor_role,
                "desired_outcome": next_state.desired_outcome,
                "constraints": next_state.constraints,
                "target_test_command": next_state.target_test_command,
                "target_test_argv": next_state.target_test_argv,
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
        repo_root = ctx.root.resolve()
        capability_path = write_selected_workflow_capability_snapshot(
            ctx, ctx.state.selected_workflow_reference
        )
        authoring_surface_path = write_selected_workflow_authoring_surface(
            ctx, ctx.state.selected_workflow_reference
        )

        capability_snapshot = _read_json(capability_path)
        authoring_snapshot = _read_json(authoring_surface_path)
        _require_text(
            ctx.state.selected_workflow_reference,
            "selected_workflow_reference must stay non-empty",
        )
        selected_workflow_name, _, authoring_surface = (
            validate_selected_workflow_capability_and_authoring_snapshots(
                capability_snapshot,
                authoring_snapshot,
            )
        )
        baseline_manifest = _write_baseline_workflow_manifest(
            ctx,
            repo_root=repo_root,
            selected_workflow_name=selected_workflow_name,
            authoring_surface=authoring_surface,
        )

        selection = None
        if ctx.state.optimization_receipt_path is not None:
            selection = load_optimization_candidate(
                optimization_receipt_path=_resolve_input_path(
                    repo_root,
                    ctx.state.optimization_receipt_path,
                    "optimization_receipt_path",
                ),
                candidate_id=_require_text(
                    ctx.state.candidate_id, "candidate_id must be non-empty"
                ),
                expected_selected_workflow=selected_workflow_name,
                allowed_kinds=(
                    "producer_prompt",
                    "verifier_rubric",
                    "tokens",
                    "workflow",
                ),
            )
            _assert_optimizer_baseline_matches_capture(selection, baseline_manifest)
            _write_optimization_selection_inputs(ctx, selection, selected_workflow_name)
        else:
            summary_source = _resolve_input_path(
                repo_root,
                _require_text(
                    ctx.state.evaluation_summary_path,
                    "evaluation_summary_path must be non-empty",
                ),
                "evaluation_summary_path",
            )
            findings_source = _resolve_input_path(
                repo_root,
                _require_text(
                    ctx.state.evaluation_findings_path,
                    "evaluation_findings_path must be non-empty",
                ),
                "evaluation_findings_path",
            )
            summary_payload = _read_json(summary_source)
            _validate_evaluation_summary_selected_workflow(
                summary_payload, selected_workflow_name
            )
            write_workflow_json(
                ctx, "baseline_evaluation_summary.json", summary_payload
            )
            _write_text(
                ctx.workflow_folder / "baseline_evaluation_findings.md",
                findings_source.read_text(encoding="utf-8"),
            )

        if ctx.state.failure_modes_path is None:
            failure_modes_text = _NO_FAILURE_MODES_SUPPLIED_TEXT
        else:
            failure_modes_source = _resolve_input_path(
                repo_root, ctx.state.failure_modes_path, "failure_modes_path"
            )
            failure_modes_text = failure_modes_source.read_text(encoding="utf-8")
        _write_text(
            ctx.workflow_folder / "baseline_failure_modes.md", failure_modes_text
        )
        if selection is None:
            _write_refinement_evidence_inputs(
                ctx,
                repo_root=repo_root,
                selected_workflow_name=selected_workflow_name,
                refinement_evidence_path=ctx.state.refinement_evidence_path,
            )
        ctx.state.selected_workflow_name = selected_workflow_name
        ctx.state.baseline_surface_id = baseline_manifest["surface_id"]
        ctx.state.baseline_authoritative_sources = {
            entry["relative_path"]: entry["source_path"]
            for entry in baseline_manifest["files"]
        }
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
        writes=[paired_evaluation_result, workflow_refinement_receipt],
        routes={"workflow_refinement_published": FINISH},
    )
    def publish_refined_workflow(ctx):
        workflow_folder = ctx.workflow_folder
        required_paths = {
            "selected_workflow_capability": workflow_folder
            / "selected_workflow_capability.json",
            "selected_workflow_authoring_surface": workflow_folder
            / "selected_workflow_authoring_surface.json",
            "baseline_workflow_manifest": workflow_folder
            / "baseline_workflow_manifest.json",
            "baseline_evaluation_summary": workflow_folder
            / "baseline_evaluation_summary.json",
            "baseline_evaluation_findings": workflow_folder
            / "baseline_evaluation_findings.md",
            "baseline_failure_modes": workflow_folder / "baseline_failure_modes.md",
            "baseline_refinement_evidence": workflow_folder
            / "baseline_refinement_evidence.json",
            "baseline_refinement_evidence_summary": workflow_folder
            / "baseline_refinement_evidence.md",
            "candidate_workflow_manifest": workflow_folder
            / "candidate_workflow_manifest.json",
            "refinement_verification_report": workflow_folder
            / "refinement_verification_report.md",
            "evaluation_delta_report": workflow_folder / "evaluation_delta_report.md",
            "promotion_record": workflow_folder / "promotion_record.md",
            "rollback_plan": workflow_folder / "rollback_plan.md",
        }
        required_dirs = {
            "baseline_workflow_surface": workflow_folder / "baseline_workflow_surface",
            "candidate_workflow_surface": workflow_folder
            / "candidate_workflow_surface",
        }
        for artifact_path in required_paths.values():
            if not artifact_path.exists():
                raise FileNotFoundError(
                    f"missing required publication artifact at {artifact_path}"
                )
        for artifact_path in required_dirs.values():
            if not artifact_path.exists():
                raise FileNotFoundError(
                    f"missing required publication artifact at {artifact_path}"
                )

        repo_root = ctx.root.resolve()
        capability_snapshot = _read_json(required_paths["selected_workflow_capability"])
        authoring_snapshot = _read_json(
            required_paths["selected_workflow_authoring_surface"]
        )
        baseline_manifest = _read_json(required_paths["baseline_workflow_manifest"])
        candidate_manifest = _read_json(required_paths["candidate_workflow_manifest"])
        read_required_text(
            required_paths["baseline_evaluation_findings"],
            "baseline_evaluation_findings.md must be non-empty",
        )
        read_required_text(
            required_paths["baseline_failure_modes"],
            "baseline_failure_modes.md must be non-empty",
        )
        baseline_evaluation_summary = _read_json(
            required_paths["baseline_evaluation_summary"]
        )
        read_required_text(
            required_paths["refinement_verification_report"],
            "refinement_verification_report.md must be non-empty",
        )
        read_required_text(
            required_paths["evaluation_delta_report"],
            "evaluation_delta_report.md must be non-empty",
        )
        read_required_text(
            required_paths["promotion_record"],
            "promotion_record.md must be non-empty",
        )
        read_required_text(
            required_paths["rollback_plan"],
            "rollback_plan.md must be non-empty",
        )

        _require_text(
            ctx.state.selected_workflow_reference,
            "selected_workflow_reference must stay non-empty",
        )
        selected_workflow_name, _, authoring_surface = (
            validate_selected_workflow_capability_and_authoring_snapshots(
                capability_snapshot,
                authoring_snapshot,
            )
        )
        refinement_evidence_payload = _read_json(
            required_paths["baseline_refinement_evidence"]
        )
        _validate_refinement_evidence_payload(
            refinement_evidence_payload, selected_workflow_name
        )
        optimization_selection = _reload_optimization_selection(
            ctx, repo_root, selected_workflow_name
        )
        if optimization_selection is not None:
            _assert_optimizer_baseline_matches_capture(
                optimization_selection, baseline_manifest
            )
        read_required_text(
            required_paths["baseline_refinement_evidence_summary"],
            "baseline_refinement_evidence.md must be non-empty",
        )
        _validate_evaluation_summary_selected_workflow(
            baseline_evaluation_summary, selected_workflow_name
        )
        if (
            ctx.state.selected_workflow_name is not None
            and ctx.state.selected_workflow_name != selected_workflow_name
        ):
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
        _validate_capability_matches_authoring_surface(
            capability_snapshot, authoring_surface
        )
        _assert_refinement_anchors(ctx, baseline_manifest, candidate_manifest)
        _validate_baseline_manifest(
            baseline_manifest,
            repo_root,
            expected_boundary,
            expected_surface_root=required_dirs["baseline_workflow_surface"],
        )
        validate_authoritative_surface_sources_unchanged(
            baseline_manifest,
            repo_root,
            baseline_manifest_label="baseline_workflow_manifest.json",
            drift_error_prefix="authoritative selected workflow file changed during refinement publication",
        )
        _validate_candidate_manifest(
            candidate_manifest,
            repo_root,
            expected_boundary,
            baseline_manifest,
            expected_surface_root=required_dirs["candidate_workflow_surface"],
        )

        candidate_file_count = _require_positive_int(
            candidate_manifest.get("file_count"),
            "candidate_workflow_manifest.json must define positive integer file_count",
        )
        candidate_changed_paths = _require_string_list(
            candidate_manifest.get("changed_relative_paths"),
            "candidate_workflow_manifest.json must define non-empty changed_relative_paths",
        )
        if (
            ctx.state.candidate_file_count
            and candidate_file_count != ctx.state.candidate_file_count
        ):
            raise ValueError(
                "candidate_workflow_manifest.json file_count must match workflow state"
            )
        if (
            ctx.state.candidate_changed_paths
            and candidate_changed_paths != ctx.state.candidate_changed_paths
        ):
            raise ValueError(
                "candidate_workflow_manifest.json changed_relative_paths must match workflow state"
            )
        if not _AUTHORITATIVE_EVALUATION_ARTIFACTS.issubset(
            ctx.state.evaluation_authoritative_artifacts
        ):
            raise ValueError(
                "workflow state authoritative evaluation artifacts must include refinement_verification_report, evaluation_delta_report, promotion_record, and rollback_plan"
            )
        if ctx.state.evaluation_next_action is None:
            raise ValueError(
                "workflow state must define evaluation_next_action before publication"
            )

        validation_result, paired_evaluation = _validate_and_evaluate_candidate(
            ctx,
            repo_root=repo_root,
            selected_workflow_name=selected_workflow_name,
            baseline_manifest=baseline_manifest,
            candidate_manifest=candidate_manifest,
        )
        # Recheck the exact published files after all subprocesses have returned.
        baseline_manifest = _read_json(required_paths["baseline_workflow_manifest"])
        candidate_manifest = _read_json(required_paths["candidate_workflow_manifest"])
        _assert_refinement_anchors(ctx, baseline_manifest, candidate_manifest)
        _validate_baseline_manifest(
            baseline_manifest,
            repo_root,
            expected_boundary,
            expected_surface_root=required_dirs["baseline_workflow_surface"],
        )
        validate_authoritative_surface_sources_unchanged(
            baseline_manifest,
            repo_root,
            baseline_manifest_label="baseline_workflow_manifest.json",
            drift_error_prefix="authoritative selected workflow file changed during validation",
        )
        _validate_candidate_manifest(
            candidate_manifest,
            repo_root,
            expected_boundary,
            baseline_manifest,
            expected_surface_root=required_dirs["candidate_workflow_surface"],
        )
        write_workflow_json(ctx, "paired_evaluation_result.json", paired_evaluation)

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
                "target_test_argv": ctx.state.target_test_argv,
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
                    "paired_evaluation_result",
                    "workflow_refinement_receipt",
                ],
                "selected_workflow_capability": str(
                    required_paths["selected_workflow_capability"]
                ),
                "selected_workflow_authoring_surface": str(
                    required_paths["selected_workflow_authoring_surface"]
                ),
                "baseline_workflow_surface": str(
                    required_dirs["baseline_workflow_surface"]
                ),
                "baseline_workflow_manifest": str(
                    required_paths["baseline_workflow_manifest"]
                ),
                "baseline_evaluation_summary": str(
                    required_paths["baseline_evaluation_summary"]
                ),
                "baseline_evaluation_findings": str(
                    required_paths["baseline_evaluation_findings"]
                ),
                "baseline_failure_modes": str(required_paths["baseline_failure_modes"]),
                "baseline_refinement_evidence": str(
                    required_paths["baseline_refinement_evidence"]
                ),
                "baseline_refinement_evidence_summary": str(
                    required_paths["baseline_refinement_evidence_summary"]
                ),
                "candidate_workflow_surface": str(
                    required_dirs["candidate_workflow_surface"]
                ),
                "candidate_workflow_manifest": str(
                    required_paths["candidate_workflow_manifest"]
                ),
                "refinement_verification_report": str(
                    required_paths["refinement_verification_report"]
                ),
                "evaluation_delta_report": str(
                    required_paths["evaluation_delta_report"]
                ),
                "promotion_record": str(required_paths["promotion_record"]),
                "rollback_plan": str(required_paths["rollback_plan"]),
                "paired_evaluation_result": str(
                    workflow_folder / "paired_evaluation_result.json"
                ),
                "next_action": ctx.state.evaluation_next_action,
                "optimization_candidate_id": (
                    None
                    if optimization_selection is None
                    else optimization_selection.candidate.candidate_id
                ),
                "optimization_candidate_set_id": (
                    None
                    if optimization_selection is None
                    else optimization_selection.candidate_set.candidate_set_id
                ),
                "optimization_evidence_snapshot_id": (
                    None
                    if optimization_selection is None
                    else optimization_selection.candidate_set.evidence_snapshot_id
                ),
                "validation_result": validation_result.model_dump(
                    mode="json", by_alias=True
                ),
                "paired_evaluation": paired_evaluation,
                "published": True,
                "status": "accepted",
            },
        )
        ctx.state.selected_workflow_name = selected_workflow_name
        ctx.state.published = True
        return "workflow_refinement_published"

    entry = bootstrap


def _assert_refinement_anchors(ctx, baseline, candidate) -> None:
    if not ctx.state.baseline_surface_id or not ctx.state.candidate_surface_id:
        raise ValueError(
            "refinement checkpoint lacks surface anchors; start a new refinement run"
        )
    if baseline.get("surface_id") != ctx.state.baseline_surface_id:
        raise ValueError("baseline surface changed; start a new refinement run")
    sources = {
        entry.get("relative_path"): entry.get("source_path")
        for entry in baseline.get("files", [])
    }
    if sources != ctx.state.baseline_authoritative_sources:
        raise ValueError("baseline source paths changed; start a new refinement run")
    if candidate.get("surface_id") != ctx.state.candidate_surface_id:
        raise ValueError("candidate surface changed after implementation")


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

    identity_boundary = _surface_identity_boundary(boundary, selected_workflow_name)
    canonical = derive_surface_manifest(
        Path(surface_manifest["surface_root"]),
        expected_root=Path(surface_manifest["surface_root"]),
        boundary=identity_boundary,
        surface_kind="baseline",
        authoritative_sources={
            entry["relative_path"]: Path(entry["source_path"])
            for entry in boundary["baseline_source_entries"]
        },
    )
    manifest = {
        **canonical,
        "selected_workflow_name": selected_workflow_name,
        "package_name": boundary["package_name"],
        "package_root_relative_path": boundary["package_root_relative_path"],
        "doc_relative_path": boundary["doc_relative_path"],
        "runtime_test_relative_path": boundary["runtime_test_relative_path"],
        "repo_root": str(repo_root),
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
    doc_relative_path = _normalize_optional_text(
        baseline_manifest.get("doc_relative_path")
    )
    runtime_test_relative_path = _normalize_optional_text(
        baseline_manifest.get("runtime_test_relative_path")
    )
    legacy_surface = derive_candidate_surface_manifest(
        workflow_folder=workflow_folder,
        baseline_manifest=baseline_manifest,
        candidate_dir_name="candidate_workflow_surface",
        baseline_manifest_label="baseline_workflow_manifest.json",
        candidate_manifest_label="candidate_workflow_manifest.json",
    )

    identity_boundary = {
        "workflow_name": selected_workflow_name,
        "package_name": package_name,
        "package_root_relative_path": package_root_relative_path,
        "doc_relative_path": doc_relative_path,
        "runtime_test_relative_path": runtime_test_relative_path,
        "editable_boundary_version": 1,
    }
    canonical = derive_surface_manifest(
        Path(legacy_surface["surface_root"]),
        expected_root=Path(legacy_surface["surface_root"]),
        boundary=identity_boundary,
        surface_kind="candidate",
    )
    legacy_files = {entry["relative_path"]: entry for entry in legacy_surface["files"]}
    files = [
        {
            **entry,
            "changed_from_baseline": legacy_files[entry["relative_path"]][
                "changed_from_baseline"
            ],
        }
        for entry in canonical["files"]
    ]
    manifest = {
        **canonical,
        "files": files,
        "selected_workflow_name": selected_workflow_name,
        "package_name": package_name,
        "package_root_relative_path": package_root_relative_path,
        "doc_relative_path": doc_relative_path,
        "runtime_test_relative_path": runtime_test_relative_path,
        "repo_root": legacy_surface["repo_root"],
        "baseline_relative_paths": legacy_surface["baseline_relative_paths"],
        "changed_relative_paths": legacy_surface["changed_relative_paths"],
        "added_relative_paths": legacy_surface["added_relative_paths"],
    }
    target_path = workflow_folder / "candidate_workflow_manifest.json"
    target_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def _authoring_surface_boundary(
    authoring_surface: Mapping[str, Any], repo_root: Path
) -> dict[str, Any]:
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


def _surface_identity_boundary(
    boundary: Mapping[str, Any], selected_workflow_name: str
) -> dict[str, Any]:
    return {
        "workflow_name": selected_workflow_name,
        "package_name": boundary["package_name"],
        "package_root_relative_path": boundary["package_root_relative_path"],
        "doc_relative_path": boundary["doc_relative_path"],
        "runtime_test_relative_path": boundary["runtime_test_relative_path"],
        "editable_boundary_version": 1,
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
        raise ValueError(
            "selected_workflow_authoring_surface.json package_name must match selected_workflow_capability.json"
        )
    if _require_text(
        capability.get("workflow_path"),
        "selected_workflow_capability.json must define selected_workflow_capability.workflow_path",
    ) != _require_text(
        authoring_surface.get("workflow_path"),
        "selected_workflow_authoring_surface.json must define selected_workflow_authoring_surface.workflow_path",
    ):
        raise ValueError(
            "selected_workflow_authoring_surface.json workflow_path must match selected_workflow_capability.json"
        )
    if _require_text(
        capability.get("manifest_path"),
        "selected_workflow_capability.json must define selected_workflow_capability.manifest_path",
    ) != _require_text(
        authoring_surface.get("manifest_path"),
        "selected_workflow_authoring_surface.json must define selected_workflow_authoring_surface.manifest_path",
    ):
        raise ValueError(
            "selected_workflow_authoring_surface.json manifest_path must match selected_workflow_capability.json"
        )
    if _normalize_optional_text(
        capability.get("params_path")
    ) != _normalize_optional_text(authoring_surface.get("params_path")):
        raise ValueError(
            "selected_workflow_authoring_surface.json params_path must match selected_workflow_capability.json"
        )
    if _normalize_optional_text(capability.get("doc_path")) != _normalize_optional_text(
        authoring_surface.get("doc_path")
    ):
        raise ValueError(
            "selected_workflow_authoring_surface.json doc_path must match selected_workflow_capability.json"
        )


def _validate_baseline_manifest(
    baseline_manifest: Mapping[str, Any],
    repo_root: Path,
    expected_boundary: Mapping[str, Any],
    *,
    expected_surface_root: Path,
) -> None:
    validate_baseline_surface_manifest(
        baseline_manifest,
        repo_root,
        manifest_label="baseline_workflow_manifest.json",
        expected_surface_kind="baseline",
        expected_boundary=expected_boundary,
        expected_surface_root=expected_surface_root,
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


def _validate_candidate_manifest(
    candidate_manifest: Mapping[str, Any],
    repo_root: Path,
    expected_boundary: Mapping[str, Any],
    baseline_manifest: Mapping[str, Any],
    *,
    expected_surface_root: Path,
) -> None:
    try:
        validate_candidate_surface_manifest(
            candidate_manifest,
            repo_root=repo_root,
            manifest_label="candidate_workflow_manifest.json",
            expected_surface_kind="candidate",
            expected_boundary=expected_boundary,
            expected_surface_root=expected_surface_root,
            boundary_field_map={
                "package_name": "package_name",
                "package_root_relative_path": "package_root_relative_path",
                "doc_relative_path": "doc_relative_path",
                "runtime_test_relative_path": "runtime_test_relative_path",
            },
            optional_boundary_fields=(
                "doc_relative_path",
                "runtime_test_relative_path",
            ),
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
                _normalize_optional_text(
                    expected_boundary.get("runtime_test_relative_path")
                ),
            ],
        )
    except ValueError as exc:
        if (
            str(exc)
            == "candidate_workflow_manifest.json must stay within the allowed repo-relative boundary"
        ):
            raise ValueError(
                "candidate_workflow_manifest.json must stay scoped to the selected workflow boundary"
            ) from exc
        raise


def _resolve_input_path(repo_root: Path, raw_value: str, field_name: str) -> Path:
    candidate = Path(_require_text(raw_value, f"{field_name} must be non-empty"))
    path = candidate if candidate.is_absolute() else repo_root / candidate
    if not path.exists():
        raise FileNotFoundError(f"{field_name} does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"{field_name} must point to a file: {path}")
    return path


def _write_optimization_selection_inputs(
    ctx, selection: OptimizationCandidateSelection, selected_workflow_name: str
) -> None:
    write_workflow_json(
        ctx,
        "baseline_evaluation_summary.json",
        {
            "schema": "botpipe.refinement.optimization_candidate_input/v1",
            "selected_workflow_name": selected_workflow_name,
            "candidate_id": selection.candidate.candidate_id,
            "candidate_set_id": selection.candidate_set.candidate_set_id,
            "evidence_snapshot_id": selection.candidate_set.evidence_snapshot_id,
            "baseline_surface_manifest_id": selection.candidate_set.baseline_surface_manifest_id,
            "improvement": "not_evaluated",
            "candidate": selection.candidate.model_dump(mode="json"),
        },
    )
    _write_text(
        ctx.workflow_folder / "baseline_evaluation_findings.md",
        "\n".join(
            [
                "# Selected optimization candidate",
                "",
                f"- Candidate ID: `{selection.candidate.candidate_id}`",
                f"- Kind: `{selection.candidate.kind}`",
                f"- Proposed change: {selection.candidate.proposed_change}",
                f"- Expected effect (hypothesis): {selection.candidate.expected_effect}",
                f"- Validation plan: {selection.candidate.validation_plan.description}",
                "- Improvement status: `not_evaluated`.",
                "",
            ]
        ),
    )
    handoff = _read_json(selection.refinement_handoff_path)
    _validate_refinement_evidence_payload(handoff, selected_workflow_name)
    write_workflow_json(ctx, "baseline_refinement_evidence.json", handoff)
    _write_text(
        ctx.workflow_folder / "baseline_refinement_evidence.md",
        _render_refinement_evidence_summary(handoff),
    )


def _assert_optimizer_baseline_matches_capture(
    selection: OptimizationCandidateSelection, captured: Mapping[str, Any]
) -> None:
    published = _read_json(selection.baseline_surface_manifest_path)

    def files(payload, current=False):
        result = {}
        for entry in payload.get("files", []):
            if not isinstance(entry, Mapping):
                raise ValueError("baseline manifest files must be objects")
            path = entry.get("path", entry.get("relative_path"))
            digest = entry.get("sha256", entry.get("surface_sha256"))
            if not isinstance(path, str) or not isinstance(digest, str):
                raise ValueError("baseline file identity missing")
            result[path] = digest
        return result

    if not files(published) or files(published) != files(captured, True):
        raise ValueError(
            "optimizer baseline surface is stale relative to selected workflow"
        )


def _validate_and_evaluate_candidate(
    ctx,
    *,
    repo_root: Path,
    selected_workflow_name: str,
    baseline_manifest: Mapping[str, Any],
    candidate_manifest: Mapping[str, Any],
) -> tuple[ValidationResult, dict[str, Any]]:
    staging = (ctx.workflow_folder / ".candidate_execution_staging").resolve()
    staging.mkdir(parents=True, exist_ok=True)
    selected_package = None
    if not (repo_root / "botpipe" / "__init__.py").is_file():
        import botpipe

        selected_package = Path(botpipe.__file__).resolve().parent
    snapshot = capture_execution_tree(
        repo_root,
        staging,
        selected_package_root=selected_package,
        selected_package_import_path="botpipe" if selected_package else None,
        excluded_roots=(ctx.workflow_folder,),
    )
    try:
        candidate_root = Path(
            _require_text(
                candidate_manifest.get("root", candidate_manifest.get("surface_root")),
                "candidate manifest root required",
            )
        )
        validation = validate_frozen_candidate(
            snapshot,
            baseline_surface_manifest=baseline_manifest,
            candidate_surface_manifest=candidate_manifest,
            expected_baseline_root=Path(
                _require_text(
                    baseline_manifest.get(
                        "root", baseline_manifest.get("surface_root")
                    ),
                    "baseline manifest root required",
                )
            ),
            expected_candidate_root=candidate_root,
            expected_boundary=_require_mapping(
                baseline_manifest.get("boundary"), "baseline manifest boundary required"
            ),
            baseline_surface_kind="baseline",
            candidate_surface_kind="candidate",
            workflow_refs=(
                ctx.state.selected_workflow_reference or selected_workflow_name,
            ),
            staging_parent=staging,
            allowed_added_path_prefixes=(
                _require_text(
                    baseline_manifest.get("package_root_relative_path"),
                    "baseline package root required",
                ),
            ),
            allowed_added_exact_paths=tuple(
                path
                for path in (
                    baseline_manifest.get("doc_relative_path"),
                    baseline_manifest.get("runtime_test_relative_path"),
                )
                if isinstance(path, str) and path
            ),
            target_test_command=ctx.state.target_test_command,
            target_test_argv=ctx.state.target_test_argv,
        )
        if not validation.success:
            raise ValueError(
                f"candidate validation failed: {'; '.join(validation.errors)}"
            )
        paired = _run_optional_paired_evaluation(
            ctx,
            repo_root=repo_root,
            snapshot=snapshot,
            staging=staging,
            baseline_manifest=baseline_manifest,
            candidate_manifest=candidate_manifest,
        )
        if paired.get("evaluation") != "not_evaluated":
            comparison = paired.get("comparison")
            if not isinstance(comparison, Mapping):
                raise ValueError("paired evaluation comparison missing")
            validation = validation.with_evaluation(comparison)
        verify_frozen_execution_tree(snapshot)
        return validation, paired
    finally:
        if snapshot.root.exists():
            cleanup_owned_directory(
                snapshot.root,
                owned_parent=snapshot.owned_parent,
                ownership_token=snapshot.ownership_token,
            )
        try:
            staging.rmdir()
        except OSError:
            pass


def _run_optional_paired_evaluation(
    ctx,
    *,
    repo_root: Path,
    snapshot,
    staging: Path,
    baseline_manifest: Mapping[str, Any],
    candidate_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    if ctx.state.evaluation_spec_path is None:
        return {
            "schema": PAIRED_EVALUATION_SCHEMA,
            "evaluation": "not_evaluated",
            "execution_state": "not_run",
            "comparison": {"state": "not_evaluated"},
            "automatic_promotion": False,
        }
    spec_path = _resolve_input_path(
        repo_root, ctx.state.evaluation_spec_path, "evaluation_spec_path"
    )
    baseline_arm = candidate_arm = None
    try:
        raw_baseline = materialize_execution_arm(snapshot, staging)
        baseline_arm = ExecutionArm(
            root=raw_baseline.root,
            execution_tree_id=raw_baseline.execution_tree_id,
            manifest=raw_baseline.manifest,
            surface_id=_require_text(
                baseline_manifest.get("surface_id"),
                "baseline manifest surface_id required",
            ),
            owned_parent=raw_baseline.owned_parent,
            ownership_token=raw_baseline.ownership_token,
        )
        candidate_arm = materialize_execution_arm(
            snapshot, staging, candidate_manifest=candidate_manifest
        )
        spec, spec_id = load_evaluation_spec(spec_path)
        attempt_id = _paired_evaluation_attempt_id(
            invocation_id=ctx.run_id,
            spec_id=spec_id,
            baseline_surface_id=baseline_arm.surface_id,
            candidate_surface_id=_require_text(
                candidate_arm.surface_id, "candidate arm surface_id required"
            ),
            baseline_execution_tree_id=baseline_arm.execution_tree_id,
            candidate_execution_tree_id=candidate_arm.execution_tree_id,
        )
        # One persistent slot per runtime invocation prevents changed inputs from
        # turning an interrupted attempt into a second pair of evaluator launches.
        suffix = sha256(ctx.run_id.encode("utf-8")).hexdigest()
        attempt_path = ctx.workflow_folder / f"paired_evaluation_attempt-{suffix}.json"
        cache_path = ctx.workflow_folder / f"paired_evaluation_cache-{suffix}.json"
        if cache_path.is_file():
            try:
                cached = validate_paired_evaluation_record(
                    _read_json(cache_path),
                    evaluation_spec_path=spec_path,
                    baseline_surface_id=baseline_arm.surface_id,
                    candidate_surface_id=_require_text(
                        candidate_arm.surface_id, "candidate arm surface_id required"
                    ),
                    baseline_execution_tree_id=baseline_arm.execution_tree_id,
                    candidate_execution_tree_id=candidate_arm.execution_tree_id,
                    allowed_output_parent=ctx.workflow_folder,
                    expected_invocation_id=ctx.run_id,
                )
            except (OSError, ValueError) as exc:
                raise ValueError(
                    "paired evaluation inputs or saved results changed; start a new refinement run"
                ) from exc
            if cached.get("evaluation_attempt_id") != attempt_id:
                raise ValueError("paired evaluation attempt identity is stale")
            return cached
        if attempt_path.is_file():
            attempt = _read_json(attempt_path)
            if (
                attempt.get("attempt_id") != attempt_id
                or attempt.get("invocation_id") != ctx.run_id
            ):
                raise ValueError(
                    "paired evaluation inputs changed; start a new refinement run"
                )
            return finalize_paired_evaluation_record(
                {
                    "schema": PAIRED_EVALUATION_SCHEMA,
                    "evaluation": "inconclusive",
                    "execution_state": "failed",
                    "stop_reason": "interrupted_paired_evaluation_restart_required",
                    "invocation_id": ctx.run_id,
                    "evaluation_attempt_id": attempt_id,
                    "spec_id": spec_id,
                    "execution_output_root": str(
                        Path(
                            _require_text(
                                attempt.get("execution_output_root"),
                                "paired evaluation attempt output root required",
                            )
                        ).resolve()
                    ),
                    "frozen_inputs": {},
                    "plan": {
                        "case_ids": spec.case_ids,
                        "repetitions": spec.repetitions,
                        "effective_settings": spec.effective_settings,
                        "stochastic": spec.stochastic,
                        "max_elapsed_seconds": spec.max_elapsed_seconds,
                        "per_arm_timeout_seconds": spec.per_arm_timeout_seconds,
                        "max_provider_turns_per_arm": spec.max_provider_turns_per_arm,
                    },
                    "arms": {
                        "baseline": {
                            "arm": "baseline",
                            "execution_state": "failed",
                            "surface_id": baseline_arm.surface_id,
                            "execution_tree_id": baseline_arm.execution_tree_id,
                            "reason": "prior evaluator attempt interrupted",
                            "diagnostics": {},
                        },
                        "candidate": {
                            "arm": "candidate",
                            "execution_state": "failed",
                            "surface_id": candidate_arm.surface_id,
                            "execution_tree_id": candidate_arm.execution_tree_id,
                            "reason": "prior evaluator attempt interrupted",
                            "diagnostics": {},
                        },
                    },
                    "comparison": {
                        "state": "inconclusive",
                        "primary_metric": spec.primary_metric,
                        "deltas": {},
                        "regressed_metrics": [],
                        "claim_scope": spec.claim_scope,
                        "limitations": [
                            "a prior paired attempt was interrupted; evaluator arms were not relaunched"
                        ],
                    },
                    "automatic_promotion": False,
                }
            )
        output_root = ctx.workflow_folder / f"paired_evaluation_execution-{suffix}"
        _write_json_atomic(
            attempt_path,
            {
                "schema": "botpipe.optimizer.paired_evaluation_attempt/v1",
                "attempt_id": attempt_id,
                "invocation_id": ctx.run_id,
                "spec_id": spec_id,
                "baseline_surface_id": baseline_arm.surface_id,
                "candidate_surface_id": candidate_arm.surface_id,
                "baseline_execution_tree_id": baseline_arm.execution_tree_id,
                "candidate_execution_tree_id": candidate_arm.execution_tree_id,
                "execution_output_root": str(output_root.resolve()),
                "state": "started",
            },
        )
        result = run_paired_evaluation(
            evaluation_spec_path=spec_path,
            baseline_arm=baseline_arm,
            candidate_arm=candidate_arm,
            output_root=output_root,
            snapshot_arm=snapshot_execution_arm,
            assert_arm_unchanged=assert_execution_arm_unchanged,
        )
        result = finalize_paired_evaluation_record(
            {
                **result,
                "invocation_id": ctx.run_id,
                "evaluation_attempt_id": attempt_id,
            }
        )
        _write_json_atomic(cache_path, result)
        _write_json_atomic(
            attempt_path,
            {
                **_read_json(attempt_path),
                "state": "complete",
                "paired_evaluation_id": result["paired_evaluation_id"],
            },
        )
        verify_frozen_execution_tree(snapshot)
        return result
    finally:
        for arm in (candidate_arm, baseline_arm):
            if arm is not None and arm.root.exists():
                cleanup_owned_directory(
                    arm.root,
                    owned_parent=arm.owned_parent,
                    ownership_token=arm.ownership_token,
                )


def _reload_optimization_selection(ctx, repo_root: Path, selected_workflow_name: str):
    if ctx.state.optimization_receipt_path is None:
        return None
    return load_optimization_candidate(
        optimization_receipt_path=_resolve_input_path(
            repo_root, ctx.state.optimization_receipt_path, "optimization_receipt_path"
        ),
        candidate_id=_require_text(
            ctx.state.candidate_id, "candidate_id must be non-empty"
        ),
        expected_selected_workflow=selected_workflow_name,
        allowed_kinds=("producer_prompt", "verifier_rubric", "tokens", "workflow"),
    )


def _paired_evaluation_attempt_id(
    *,
    invocation_id: str,
    spec_id: str,
    baseline_surface_id: str,
    candidate_surface_id: str,
    baseline_execution_tree_id: str,
    candidate_execution_tree_id: str,
) -> str:
    payload = {
        "invocation_id": invocation_id,
        "spec_id": spec_id,
        "baseline_surface_id": baseline_surface_id,
        "candidate_surface_id": candidate_surface_id,
        "baseline_execution_tree_id": baseline_execution_tree_id,
        "candidate_execution_tree_id": candidate_execution_tree_id,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


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
        source_path = _resolve_input_path(
            repo_root, refinement_evidence_path, "refinement_evidence_path"
        )
        payload = _read_json(source_path)
        _validate_refinement_evidence_payload(payload, selected_workflow_name)
        payload = {
            "schema": _REFINEMENT_EVIDENCE_SCHEMA,
            "source_path": str(source_path),
            "target_workflow_id": selected_workflow_name,
            "evidence_entries": [dict(entry) for entry in payload["evidence_entries"]],
        }

    write_workflow_json(ctx, "baseline_refinement_evidence.json", payload)
    _write_text(
        ctx.workflow_folder / "baseline_refinement_evidence.md",
        _render_refinement_evidence_summary(payload),
    )


def _validate_refinement_evidence_payload(
    payload: Mapping[str, Any], selected_workflow_name: str
) -> None:
    schema = _require_text(
        payload.get("schema"),
        "baseline_refinement_evidence.json must define non-empty schema",
    )
    if schema == REFINEMENT_HANDOFF_SCHEMA:
        if (
            _require_text(
                payload.get("target_workflow_id"),
                "handoff target_workflow_id must be non-empty",
            )
            != selected_workflow_name
        ):
            raise ValueError(
                "baseline_refinement_evidence.json target_workflow_id must match selected workflow"
            )
        candidates = payload.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise ValueError("optimizer handoff candidates must be non-empty")
        for entry in candidates:
            if not isinstance(entry, Mapping):
                raise ValueError("optimizer handoff candidates must be objects")
            _require_text(
                entry.get("candidate_id"), "handoff candidate_id must be non-empty"
            )
            if entry.get("kind") not in {
                "producer_prompt",
                "verifier_rubric",
                "tokens",
                "workflow",
                "evaluation_case",
            }:
                raise ValueError("optimizer handoff candidate kind unsupported")
        return
    if schema != _REFINEMENT_EVIDENCE_SCHEMA:
        raise ValueError(
            "baseline_refinement_evidence.json schema must be a supported refinement handoff schema"
        )
    if (
        _require_text(
            payload.get("target_workflow_id"),
            "baseline_refinement_evidence.json must define non-empty target_workflow_id",
        )
        != selected_workflow_name
    ):
        raise ValueError(
            "baseline_refinement_evidence.json target_workflow_id must match selected workflow"
        )
    raw_entries = payload.get("evidence_entries")
    if not isinstance(raw_entries, list):
        raise ValueError(
            "baseline_refinement_evidence.json must define evidence_entries as a JSON array"
        )
    for index, raw_entry in enumerate(raw_entries):
        if not isinstance(raw_entry, Mapping):
            raise ValueError(
                "baseline_refinement_evidence.json evidence_entries must contain JSON objects"
            )
        kind = _require_text(
            raw_entry.get("kind"),
            f"baseline_refinement_evidence.json evidence_entries[{index}].kind must be non-empty",
        )
        if kind not in _ALLOWED_OPTIMIZATION_EVIDENCE_KINDS:
            raise ValueError(
                f"baseline_refinement_evidence.json evidence_entries[{index}].kind is not supported"
            )
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
    if payload.get("schema") == REFINEMENT_HANDOFF_SCHEMA:
        lines = [
            "# Refinement Evidence",
            "",
            f"- Target workflow: `{payload['target_workflow_id']}`.",
            f"- Evidence snapshot: `{payload['evidence_snapshot_id']}`.",
            f"- Baseline surface: `{payload['baseline_surface_manifest_id']}`.",
            f"- Candidate set: `{payload['candidate_set_id']}`.",
            "- Improvement status: `not_evaluated`.",
            "",
            "## Reviewed candidates",
            "",
        ]
        for entry in payload["candidates"]:
            lines.append(
                f"- `{entry.get('candidate_id')}` ({entry.get('kind')}): {entry.get('title')}"
            )
        return "\n".join(lines).rstrip() + "\n"
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
        lines.extend(
            ("", "- No additional refinement evidence entries were supplied.", "")
        )
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


_require_text = partial(require_non_empty_string, coerce=True)
_normalize_optional_text = normalize_optional_string
_require_string_list = partial(require_string_list, dedupe=True, coerce=True)
_require_positive_int = require_positive_int
_require_mapping = require_mapping
