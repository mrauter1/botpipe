"""Closed-loop workflow refinement building-block workflow package."""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from contextlib import contextmanager
from functools import partial
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

try:  # pragma: no branch - supports both package and direct repo-root imports
    from autoloop_v3.core.compiler import compile_workflow
    from autoloop_v3.runtime.loader import resolve_workflow_reference
    from autoloop_v3.stdlib import (
        normalize_optional_string,
        normalize_unique_strings,
        read_json_object,
        require_mapping,
        require_non_empty_string,
        require_positive_int,
        require_string_list,
        write_selected_workflow_authoring_surface,
        write_selected_workflow_capability_snapshot,
    )
    from autoloop_v3.stdlib.control import event_on_outcome_tags, global_routes, merge_transitions, pause_on_outcome_tags
    from autoloop_v3.stdlib.lifecycle import (
        open_workflow_sessions,
        write_invocation_contract,
        write_publication_receipt,
        write_workflow_json,
    )
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from core.compiler import compile_workflow
    from runtime.loader import resolve_workflow_reference
    from stdlib import (
        normalize_optional_string,
        normalize_unique_strings,
        read_json_object,
        require_mapping,
        require_non_empty_string,
        require_positive_int,
        require_string_list,
        write_selected_workflow_authoring_surface,
        write_selected_workflow_capability_snapshot,
    )
    from stdlib.control import event_on_outcome_tags, global_routes, merge_transitions, pause_on_outcome_tags
    from stdlib.lifecycle import open_workflow_sessions, write_invocation_contract, write_publication_receipt, write_workflow_json

from workflow import Artifact, FAIL, PairStep, Session, SUCCESS, SystemStep, Workflow
from workflow.primitives import Event, Outcome

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
    framework_architecture_doc = Artifact("{package_folder}/../../docs/architecture.md")
    framework_authoring_doc = Artifact("{package_folder}/../../docs/authoring.md")
    workflow_instructions = Artifact("{package_folder}/../../Workflow_Instructions.md")
    refinement_package_checklist = Artifact("{package_folder}/assets/refinement_package_checklist.md")

    invocation_contract = Artifact("{workflow_folder}/invocation_contract.json")
    selected_workflow_capability = Artifact("{workflow_folder}/selected_workflow_capability.json")
    selected_workflow_authoring_surface = Artifact("{workflow_folder}/selected_workflow_authoring_surface.json")
    baseline_workflow_surface = Artifact("{workflow_folder}/baseline_workflow_surface")
    baseline_workflow_manifest = Artifact("{workflow_folder}/baseline_workflow_manifest.json")
    baseline_evaluation_summary = Artifact("{workflow_folder}/baseline_evaluation_summary.json")
    baseline_evaluation_findings = Artifact("{workflow_folder}/baseline_evaluation_findings.md")
    baseline_failure_modes = Artifact("{workflow_folder}/baseline_failure_modes.md")
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

    bootstrap = SystemStep(
        name="bootstrap",
        requires=[request],
        produces={"invocation_contract": invocation_contract},
    )
    capture_refinement_context = SystemStep(
        name="capture_refinement_context",
        requires=[request, invocation_contract],
        produces={
            "selected_workflow_capability": selected_workflow_capability,
            "selected_workflow_authoring_surface": selected_workflow_authoring_surface,
            "baseline_workflow_surface": baseline_workflow_surface,
            "baseline_workflow_manifest": baseline_workflow_manifest,
            "baseline_evaluation_summary": baseline_evaluation_summary,
            "baseline_evaluation_findings": baseline_evaluation_findings,
            "baseline_failure_modes": baseline_failure_modes,
        },
    )
    frame_refinement_request = PairStep(
        name="frame_refinement_request",
        session=frame_session,
        producer="prompts/frame_producer.md",
        verifier="prompts/frame_verifier.md",
        requires=[
            request,
            invocation_contract,
            selected_workflow_capability,
            selected_workflow_authoring_surface,
            baseline_workflow_manifest,
            baseline_evaluation_summary,
            baseline_evaluation_findings,
            baseline_failure_modes,
            framework_architecture_doc,
            framework_authoring_doc,
            workflow_instructions,
        ],
        produces={
            "refinement_request_brief": refinement_request_brief,
            "refinement_acceptance_criteria": refinement_acceptance_criteria,
        },
        expected_output_schema=RefinementRequestFramingPayload,
        route_contracts=FRAME_REFINEMENT_REQUEST_ROUTE_CONTRACTS,
    )
    design_refinement_plan = PairStep(
        name="design_refinement_plan",
        session=design_session,
        producer="prompts/design_producer.md",
        verifier="prompts/design_verifier.md",
        requires=[
            request,
            invocation_contract,
            selected_workflow_capability,
            selected_workflow_authoring_surface,
            baseline_workflow_manifest,
            baseline_evaluation_summary,
            baseline_evaluation_findings,
            baseline_failure_modes,
            refinement_request_brief,
            refinement_acceptance_criteria,
        ],
        produces={
            "refinement_strategy": refinement_strategy,
            "workflow_change_plan": workflow_change_plan,
            "regression_guardrails": regression_guardrails,
        },
        expected_output_schema=WorkflowRefinementPlanPayload,
        route_contracts=DESIGN_REFINEMENT_PLAN_ROUTE_CONTRACTS,
    )
    implement_refined_workflow = PairStep(
        name="implement_refined_workflow",
        session=build_session,
        producer="prompts/implement_producer.md",
        verifier="prompts/implement_verifier.md",
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
        produces={
            "candidate_workflow_surface": candidate_workflow_surface,
            "candidate_workflow_manifest": candidate_workflow_manifest,
            "refinement_build_report": refinement_build_report,
            "candidate_diff_summary": candidate_diff_summary,
        },
        expected_output_schema=WorkflowRefinementBuildPayload,
        route_contracts=IMPLEMENT_REFINED_WORKFLOW_ROUTE_CONTRACTS,
    )
    evaluate_refined_workflow = PairStep(
        name="evaluate_refined_workflow",
        session=evaluate_session,
        producer="prompts/evaluate_producer.md",
        verifier="prompts/evaluate_verifier.md",
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
            refinement_strategy,
            workflow_change_plan,
            regression_guardrails,
            candidate_workflow_surface,
            candidate_workflow_manifest,
            refinement_build_report,
            candidate_diff_summary,
        ],
        produces={
            "refinement_verification_report": refinement_verification_report,
            "evaluation_delta_report": evaluation_delta_report,
            "promotion_record": promotion_record,
            "rollback_plan": rollback_plan,
        },
        expected_output_schema=WorkflowRefinementEvaluationPayload,
        route_contracts=EVALUATE_REFINED_WORKFLOW_ROUTE_CONTRACTS,
    )
    publish_refined_workflow = SystemStep(
        name="publish_refined_workflow",
        requires=[
            selected_workflow_capability,
            selected_workflow_authoring_surface,
            baseline_workflow_manifest,
            baseline_evaluation_summary,
            baseline_evaluation_findings,
            baseline_failure_modes,
            candidate_workflow_manifest,
            refinement_verification_report,
            evaluation_delta_report,
            promotion_record,
            rollback_plan,
        ],
        produces={"workflow_refinement_receipt": workflow_refinement_receipt},
    )

    entry = bootstrap

    transitions = merge_transitions(
        global_routes(pause_on_outcome_tags("question", "blocked"), failed=FAIL),
        {
            bootstrap: {"inputs_prepared": capture_refinement_context},
            capture_refinement_context: {"refinement_context_captured": frame_refinement_request},
            frame_refinement_request: {
                "refinement_request_framed": design_refinement_plan,
                "needs_rework": frame_refinement_request,
                "needs_replan": frame_refinement_request,
            },
            design_refinement_plan: {
                "refinement_plan_designed": implement_refined_workflow,
                "needs_rework": design_refinement_plan,
                "needs_replan": frame_refinement_request,
            },
            implement_refined_workflow: {
                "workflow_refinement_applied": evaluate_refined_workflow,
                "needs_rework": implement_refined_workflow,
                "needs_replan": design_refinement_plan,
            },
            evaluate_refined_workflow: {
                "workflow_refinement_evaluated": publish_refined_workflow,
                "needs_rework": implement_refined_workflow,
                "needs_replan": design_refinement_plan,
            },
            publish_refined_workflow: {"workflow_refinement_published": SUCCESS},
        },
    )

    @staticmethod
    def on_bootstrap(state: State, ctx) -> tuple[State, Event]:
        payload = dict(ctx.workflow_params)
        selected_workflow_reference = _require_text(
            payload.get("selected_workflow"),
            "workflow_and_eval_to_refined_workflow_package requires workflow parameter 'selected_workflow'",
        )
        task_title = _require_text(
            payload.get("task_title"),
            "workflow_and_eval_to_refined_workflow_package requires workflow parameter 'task_title'",
        )
        evaluation_summary_path = _require_text(
            payload.get("evaluation_summary_path"),
            "workflow_and_eval_to_refined_workflow_package requires workflow parameter 'evaluation_summary_path'",
        )
        evaluation_findings_path = _require_text(
            payload.get("evaluation_findings_path"),
            "workflow_and_eval_to_refined_workflow_package requires workflow parameter 'evaluation_findings_path'",
        )
        target_test_command = _require_text(
            payload.get("target_test_command") or "pytest -q",
            "workflow_and_eval_to_refined_workflow_package requires a non-empty target_test_command",
        )

        next_state = state.model_copy(
            update={
                "selected_workflow_reference": selected_workflow_reference,
                "selected_workflow_name": None,
                "task_title": task_title,
                "evaluation_summary_path": evaluation_summary_path,
                "evaluation_findings_path": evaluation_findings_path,
                "failure_modes_path": _normalize_optional_text(payload.get("failure_modes_path")),
                "sponsor_role": _normalize_optional_text(payload.get("sponsor_role")),
                "desired_outcome": _normalize_optional_text(payload.get("desired_outcome")),
                "constraints": normalize_unique_strings(payload.get("constraints"))
                if isinstance(payload.get("constraints"), list)
                else [],
                "target_test_command": target_test_command,
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
                "sponsor_role": next_state.sponsor_role,
                "desired_outcome": next_state.desired_outcome,
                "constraints": next_state.constraints,
                "target_test_command": next_state.target_test_command,
            },
        )
        return next_state, Event("inputs_prepared")

    @staticmethod
    def on_capture_refinement_context(state: State, ctx) -> tuple[State, Event]:
        repo_root = _repo_root_from_context(ctx)
        capability_path = write_selected_workflow_capability_snapshot(ctx, state.selected_workflow_reference)
        authoring_surface_path = write_selected_workflow_authoring_surface(ctx, state.selected_workflow_reference)

        capability_snapshot = _read_json(capability_path)
        authoring_snapshot = _read_json(authoring_surface_path)
        selected_workflow_name = _validated_selected_workflow_name(
            capability_snapshot,
            authoring_snapshot,
            state.selected_workflow_reference,
        )
        authoring_surface = _require_mapping(
            authoring_snapshot.get("selected_workflow_authoring_surface"),
            "selected_workflow_authoring_surface.json must define selected_workflow_authoring_surface as a JSON object",
        )
        baseline_manifest = _write_baseline_workflow_manifest(
            ctx,
            repo_root=repo_root,
            selected_workflow_name=selected_workflow_name,
            authoring_surface=authoring_surface,
        )

        summary_source = _resolve_input_path(repo_root, state.evaluation_summary_path, "evaluation_summary_path")
        findings_source = _resolve_input_path(repo_root, state.evaluation_findings_path, "evaluation_findings_path")
        summary_payload = _read_json(summary_source)
        _validate_evaluation_summary_selected_workflow(summary_payload, selected_workflow_name)
        write_workflow_json(ctx, "baseline_evaluation_summary.json", summary_payload)
        _write_text(ctx.workflow_folder / "baseline_evaluation_findings.md", findings_source.read_text(encoding="utf-8"))

        if state.failure_modes_path is None:
            failure_modes_text = _NO_FAILURE_MODES_SUPPLIED_TEXT
        else:
            failure_modes_source = _resolve_input_path(repo_root, state.failure_modes_path, "failure_modes_path")
            failure_modes_text = failure_modes_source.read_text(encoding="utf-8")
        _write_text(ctx.workflow_folder / "baseline_failure_modes.md", failure_modes_text)

        return (
            state.model_copy(update={"selected_workflow_name": selected_workflow_name}),
            Event("refinement_context_captured"),
        )

    @staticmethod
    def on_frame_refinement_request(state: State, outcome: Outcome, artifacts):
        del artifacts
        payload = outcome.payload
        selected_workflow_name = payload.get("selected_workflow_name")
        return state.model_copy(
            update={
                "framing_status": outcome.tag,
                "selected_workflow_name": (
                    selected_workflow_name if isinstance(selected_workflow_name, str) else state.selected_workflow_name
                ),
            }
        )

    @staticmethod
    def on_design_refinement_plan(state: State, outcome: Outcome, artifacts):
        del artifacts
        payload = outcome.payload
        selected_workflow_name = payload.get("selected_workflow_name")
        return state.model_copy(
            update={
                "planning_status": outcome.tag,
                "selected_workflow_name": (
                    selected_workflow_name if isinstance(selected_workflow_name, str) else state.selected_workflow_name
                ),
            }
        )

    @staticmethod
    def on_implement_refined_workflow(state: State, outcome: Outcome, artifacts):
        payload = outcome.payload
        selected_workflow_name = payload.get("selected_workflow_name")
        if outcome.tag == "needs_replan":
            return state.model_copy(
                update={
                    "build_status": outcome.tag,
                    "selected_workflow_name": (
                        selected_workflow_name
                        if isinstance(selected_workflow_name, str)
                        else state.selected_workflow_name
                    ),
                }
            )

        candidate_manifest = _write_candidate_workflow_manifest(
            artifacts.candidate_workflow_manifest.path.parent,
            _read_json(artifacts.baseline_workflow_manifest.path),
            state.selected_workflow_name or _require_text(selected_workflow_name, "build payload must define selected_workflow_name"),
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
        return state.model_copy(
            update={
                "build_status": outcome.tag,
                "selected_workflow_name": (
                    selected_workflow_name if isinstance(selected_workflow_name, str) else state.selected_workflow_name
                ),
                "candidate_file_count": actual_candidate_file_count,
                "candidate_changed_paths": actual_changed_relative_paths,
            }
        )

    @staticmethod
    def on_evaluate_refined_workflow(state: State, outcome: Outcome, artifacts):
        del artifacts
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
        if state.candidate_file_count and candidate_file_count != state.candidate_file_count:
            raise ValueError("evaluation verifier payload candidate_file_count must match workflow state")
        return state.model_copy(
            update={
                "evaluation_status": outcome.tag,
                "selected_workflow_name": (
                    selected_workflow_name if isinstance(selected_workflow_name, str) else state.selected_workflow_name
                ),
                "candidate_file_count": candidate_file_count,
                "evaluation_authoritative_artifacts": authoritative_artifacts,
                "evaluation_next_action": next_action,
            }
        )

    @staticmethod
    def on_publish_refined_workflow(state: State, ctx) -> tuple[State, Event]:
        workflow_folder = ctx.workflow_folder
        required_paths = {
            "selected_workflow_capability": workflow_folder / "selected_workflow_capability.json",
            "selected_workflow_authoring_surface": workflow_folder / "selected_workflow_authoring_surface.json",
            "baseline_workflow_manifest": workflow_folder / "baseline_workflow_manifest.json",
            "baseline_evaluation_summary": workflow_folder / "baseline_evaluation_summary.json",
            "baseline_evaluation_findings": workflow_folder / "baseline_evaluation_findings.md",
            "baseline_failure_modes": workflow_folder / "baseline_failure_modes.md",
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

        selected_workflow_name = _validated_selected_workflow_name(
            capability_snapshot,
            authoring_snapshot,
            state.selected_workflow_reference,
        )
        _validate_evaluation_summary_selected_workflow(baseline_evaluation_summary, selected_workflow_name)
        if state.selected_workflow_name is not None and state.selected_workflow_name != selected_workflow_name:
            raise ValueError("selected_workflow snapshots must match workflow state")

        authoring_surface = _require_mapping(
            authoring_snapshot.get("selected_workflow_authoring_surface"),
            "selected_workflow_authoring_surface.json must define selected_workflow_authoring_surface as a JSON object",
        )
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
        if state.candidate_file_count and candidate_file_count != state.candidate_file_count:
            raise ValueError("candidate_workflow_manifest.json file_count must match workflow state")
        if state.candidate_changed_paths and candidate_changed_paths != state.candidate_changed_paths:
            raise ValueError("candidate_workflow_manifest.json changed_relative_paths must match workflow state")
        if not _AUTHORITATIVE_EVALUATION_ARTIFACTS.issubset(state.evaluation_authoritative_artifacts):
            raise ValueError(
                "workflow state authoritative evaluation artifacts must include refinement_verification_report, evaluation_delta_report, promotion_record, and rollback_plan"
            )
        if state.evaluation_next_action is None:
            raise ValueError("workflow state must define evaluation_next_action before publication")

        overlay_validation = _validate_candidate_overlay(
            repo_root=repo_root,
            selected_workflow_name=selected_workflow_name,
            candidate_manifest=candidate_manifest,
            target_test_command=state.target_test_command,
        )

        write_publication_receipt(
            ctx,
            "workflow_refinement_receipt.json",
            {
                "workflow_name": ctx.workflow_name,
                "task_title": state.task_title,
                "sponsor_role": state.sponsor_role,
                "desired_outcome": state.desired_outcome,
                "selected_workflow_reference": state.selected_workflow_reference,
                "selected_workflow_name": selected_workflow_name,
                "target_test_command": state.target_test_command,
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
                "candidate_workflow_surface": str(required_dirs["candidate_workflow_surface"]),
                "candidate_workflow_manifest": str(required_paths["candidate_workflow_manifest"]),
                "refinement_verification_report": str(required_paths["refinement_verification_report"]),
                "evaluation_delta_report": str(required_paths["evaluation_delta_report"]),
                "promotion_record": str(required_paths["promotion_record"]),
                "rollback_plan": str(required_paths["rollback_plan"]),
                "next_action": state.evaluation_next_action,
                "overlay_validation": overlay_validation,
                "published": True,
            },
        )
        return state.model_copy(update={"selected_workflow_name": selected_workflow_name, "published": True}), Event(
            "workflow_refinement_published"
        )

    on_outcome = staticmethod(event_on_outcome_tags("question", "blocked", "failed"))


def _repo_root_from_context(ctx) -> Path:
    return ctx.package_folder.resolve().parent.parent


def _validated_selected_workflow_name(
    capability_snapshot: Mapping[str, Any],
    authoring_snapshot: Mapping[str, Any],
    selected_workflow_reference: str,
) -> str:
    capability_selected_workflow_name = _require_text(
        capability_snapshot.get("selected_workflow_name"),
        "selected_workflow_capability.json must define a non-empty selected_workflow_name",
    )
    capability = _require_mapping(
        capability_snapshot.get("selected_workflow_capability"),
        "selected_workflow_capability.json must define selected_workflow_capability as a JSON object",
    )
    capability_workflow_name = _require_text(
        capability.get("workflow_name"),
        "selected_workflow_capability.json must define selected_workflow_capability.workflow_name",
    )
    if capability_workflow_name != capability_selected_workflow_name:
        raise ValueError("selected_workflow_capability.json workflow_name must match selected_workflow_name")

    authoring_selected_workflow_name = _require_text(
        authoring_snapshot.get("selected_workflow_name"),
        "selected_workflow_authoring_surface.json must define a non-empty selected_workflow_name",
    )
    authoring_surface = _require_mapping(
        authoring_snapshot.get("selected_workflow_authoring_surface"),
        "selected_workflow_authoring_surface.json must define selected_workflow_authoring_surface as a JSON object",
    )
    authoring_workflow_name = _require_text(
        authoring_surface.get("workflow_name"),
        "selected_workflow_authoring_surface.json must define selected_workflow_authoring_surface.workflow_name",
    )
    if authoring_workflow_name != authoring_selected_workflow_name:
        raise ValueError("selected_workflow_authoring_surface.json workflow_name must match selected_workflow_name")
    if capability_selected_workflow_name != authoring_selected_workflow_name:
        raise ValueError("selected_workflow_authoring_surface.json must match selected_workflow_capability.json")
    if not selected_workflow_reference.strip():
        raise ValueError("selected_workflow_reference must stay non-empty")
    return capability_selected_workflow_name


def _validate_evaluation_summary_selected_workflow(
    summary_payload: Mapping[str, Any],
    selected_workflow_name: str,
) -> None:
    summary_selected_workflow_name = _require_text(
        summary_payload.get("selected_workflow_name"),
        "baseline_evaluation_summary.json must define non-empty selected_workflow_name",
    )
    if summary_selected_workflow_name != selected_workflow_name:
        raise ValueError("baseline_evaluation_summary.json selected_workflow_name must match selected workflow")


def _write_baseline_workflow_manifest(
    ctx,
    *,
    repo_root: Path,
    selected_workflow_name: str,
    authoring_surface: Mapping[str, Any],
) -> dict[str, Any]:
    boundary = _authoring_surface_boundary(authoring_surface, repo_root)
    baseline_root = ctx.workflow_folder / "baseline_workflow_surface"
    candidate_root = ctx.workflow_folder / "candidate_workflow_surface"
    shutil.rmtree(baseline_root, ignore_errors=True)
    shutil.rmtree(candidate_root, ignore_errors=True)

    files: list[dict[str, Any]] = []
    for relative_path in boundary["baseline_relative_paths"]:
        source_path = repo_root / relative_path
        target_path = baseline_root / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
        digest = _sha256_file(source_path)
        files.append(
            {
                "relative_path": relative_path,
                "source_path": str(source_path),
                "surface_path": str(target_path),
                "surface_sha256": digest,
                "authoritative_source_sha256": digest,
                "size_bytes": source_path.stat().st_size,
            }
        )

    manifest = {
        "surface_kind": "baseline",
        "selected_workflow_name": selected_workflow_name,
        "package_name": boundary["package_name"],
        "package_root_relative_path": boundary["package_root_relative_path"],
        "doc_relative_path": boundary["doc_relative_path"],
        "runtime_test_relative_path": boundary["runtime_test_relative_path"],
        "repo_root": str(repo_root),
        "surface_root": str(baseline_root),
        "relative_paths": boundary["baseline_relative_paths"],
        "file_count": len(boundary["baseline_relative_paths"]),
        "files": files,
    }
    write_workflow_json(ctx, "baseline_workflow_manifest.json", manifest)
    return manifest


def _write_candidate_workflow_manifest(workflow_folder: Path, baseline_manifest: Mapping[str, Any], selected_workflow_name: str) -> dict[str, Any]:
    candidate_root = workflow_folder / "candidate_workflow_surface"
    if not candidate_root.is_dir():
        raise FileNotFoundError(f"candidate workflow surface was not written at {candidate_root}")

    baseline_files = _manifest_file_map(
        baseline_manifest,
        "baseline_workflow_manifest.json must define files as a JSON array of objects with relative_path",
    )
    baseline_relative_paths = _require_string_list(
        baseline_manifest.get("relative_paths"),
        "baseline_workflow_manifest.json must define non-empty relative_paths",
    )
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
    candidate_relative_paths = sorted(
        path.relative_to(candidate_root).as_posix() for path in candidate_root.rglob("*") if path.is_file()
    )
    if not candidate_relative_paths:
        raise ValueError("candidate_workflow_surface must contain at least one file")

    files: list[dict[str, Any]] = []
    changed_relative_paths: list[str] = []
    added_relative_paths: list[str] = []
    for relative_path in candidate_relative_paths:
        surface_path = candidate_root / relative_path
        digest = _sha256_file(surface_path)
        baseline_entry = baseline_files.get(relative_path)
        changed_from_baseline = baseline_entry is None or digest != _require_text(
            baseline_entry.get("surface_sha256"),
            "baseline_workflow_manifest.json file entries must define non-empty surface_sha256",
        )
        if baseline_entry is None:
            added_relative_paths.append(relative_path)
        if changed_from_baseline:
            changed_relative_paths.append(relative_path)
        files.append(
            {
                "relative_path": relative_path,
                "surface_path": str(surface_path),
                "surface_sha256": digest,
                "size_bytes": surface_path.stat().st_size,
                "changed_from_baseline": changed_from_baseline,
            }
        )

    manifest = {
        "surface_kind": "candidate",
        "selected_workflow_name": selected_workflow_name,
        "package_name": package_name,
        "package_root_relative_path": package_root_relative_path,
        "doc_relative_path": doc_relative_path,
        "runtime_test_relative_path": runtime_test_relative_path,
        "repo_root": _require_text(
            baseline_manifest.get("repo_root"),
            "baseline_workflow_manifest.json must define non-empty repo_root",
        ),
        "surface_root": str(candidate_root),
        "baseline_relative_paths": baseline_relative_paths,
        "relative_paths": candidate_relative_paths,
        "file_count": len(candidate_relative_paths),
        "changed_relative_paths": changed_relative_paths,
        "added_relative_paths": added_relative_paths,
        "files": files,
    }
    target_path = workflow_folder / "candidate_workflow_manifest.json"
    target_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def _authoring_surface_boundary(authoring_surface: Mapping[str, Any], repo_root: Path) -> dict[str, Any]:
    package_dir = Path(
        _require_text(
            authoring_surface.get("package_dir"),
            "selected_workflow_authoring_surface.json must define selected_workflow_authoring_surface.package_dir",
        )
    ).resolve()
    try:
        package_root_relative_path = package_dir.relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise ValueError("selected_workflow_authoring_surface.json package_dir must stay under the repo root") from exc

    baseline_relative_paths = []
    for raw_path in _require_string_list(
        authoring_surface.get("editable_paths"),
        "selected_workflow_authoring_surface.json must define non-empty editable_paths",
    ):
        path = Path(raw_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"selected_workflow_authoring_surface.json path does not exist: {path}")
        try:
            relative_path = path.relative_to(repo_root).as_posix()
        except ValueError as exc:
            raise ValueError("selected_workflow_authoring_surface.json editable_paths must stay under the repo root") from exc
        if relative_path not in baseline_relative_paths:
            baseline_relative_paths.append(relative_path)

    doc_relative_path = _optional_repo_relative_path(
        repo_root,
        authoring_surface.get("doc_path"),
        "selected_workflow_authoring_surface.json doc_path must stay under the repo root",
    )
    runtime_test_relative_path = _optional_repo_relative_path(
        repo_root,
        authoring_surface.get("runtime_test_path"),
        "selected_workflow_authoring_surface.json runtime_test_path must stay under the repo root",
    )
    return {
        "package_name": _require_text(
            authoring_surface.get("package_name"),
            "selected_workflow_authoring_surface.json must define selected_workflow_authoring_surface.package_name",
        ),
        "package_root_relative_path": package_root_relative_path,
        "doc_relative_path": doc_relative_path,
        "runtime_test_relative_path": runtime_test_relative_path,
        "baseline_relative_paths": sorted(baseline_relative_paths),
    }


def _optional_repo_relative_path(repo_root: Path, raw_value: Any, error_message: str) -> str | None:
    normalized = _normalize_optional_text(raw_value)
    if normalized is None:
        return None
    path = Path(normalized).resolve()
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise ValueError(error_message) from exc


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
    if _require_text(
        baseline_manifest.get("surface_kind"),
        "baseline_workflow_manifest.json must define non-empty surface_kind",
    ) != "baseline":
        raise ValueError("baseline_workflow_manifest.json surface_kind must be baseline")
    if _require_text(
        baseline_manifest.get("repo_root"),
        "baseline_workflow_manifest.json must define non-empty repo_root",
    ) != str(repo_root):
        raise ValueError("baseline_workflow_manifest.json repo_root must match the runtime repo root")
    if _require_text(
        baseline_manifest.get("package_name"),
        "baseline_workflow_manifest.json must define non-empty package_name",
    ) != _require_text(
        expected_boundary.get("package_name"),
        "expected boundary must define package_name",
    ):
        raise ValueError("baseline_workflow_manifest.json package_name must match selected_workflow_authoring_surface.json")
    if _require_text(
        baseline_manifest.get("package_root_relative_path"),
        "baseline_workflow_manifest.json must define non-empty package_root_relative_path",
    ) != _require_text(
        expected_boundary.get("package_root_relative_path"),
        "expected boundary must define package_root_relative_path",
    ):
        raise ValueError("baseline_workflow_manifest.json package_root_relative_path must match selected_workflow_authoring_surface.json")
    if _normalize_optional_text(baseline_manifest.get("doc_relative_path")) != _normalize_optional_text(
        expected_boundary.get("doc_relative_path")
    ):
        raise ValueError("baseline_workflow_manifest.json doc_relative_path must match selected_workflow_authoring_surface.json")
    if _normalize_optional_text(baseline_manifest.get("runtime_test_relative_path")) != _normalize_optional_text(
        expected_boundary.get("runtime_test_relative_path")
    ):
        raise ValueError("baseline_workflow_manifest.json runtime_test_relative_path must match selected_workflow_authoring_surface.json")
    file_entries = _manifest_file_map(
        baseline_manifest,
        "baseline_workflow_manifest.json must define files as a JSON array of objects with relative_path",
    )
    relative_paths = _require_string_list(
        baseline_manifest.get("relative_paths"),
        "baseline_workflow_manifest.json must define non-empty relative_paths",
    )
    if sorted(file_entries) != relative_paths:
        raise ValueError("baseline_workflow_manifest.json files must match relative_paths")
    for relative_path, entry in file_entries.items():
        source_path = Path(
            _require_text(
                entry.get("source_path"),
                "baseline_workflow_manifest.json file entries must define non-empty source_path",
            )
        )
        surface_path = Path(
            _require_text(
                entry.get("surface_path"),
                "baseline_workflow_manifest.json file entries must define non-empty surface_path",
            )
        )
        if source_path != repo_root / relative_path:
            raise ValueError("baseline_workflow_manifest.json source_path entries must stay aligned to the repo root")
        if not source_path.exists() or not surface_path.exists():
            raise FileNotFoundError("baseline_workflow_manifest.json file entries must point at existing files")
        expected_digest = _require_text(
            entry.get("surface_sha256"),
            "baseline_workflow_manifest.json file entries must define non-empty surface_sha256",
        )
        if _sha256_file(surface_path) != expected_digest:
            raise ValueError("baseline_workflow_manifest.json surface_sha256 must match the copied baseline surface")


def _validate_authoritative_files_unchanged(baseline_manifest: Mapping[str, Any], repo_root: Path) -> None:
    for relative_path, entry in _manifest_file_map(
        baseline_manifest,
        "baseline_workflow_manifest.json must define files as a JSON array of objects with relative_path",
    ).items():
        source_path = repo_root / relative_path
        if not source_path.exists():
            raise FileNotFoundError(f"authoritative selected workflow file is missing: {source_path}")
        current_digest = _sha256_file(source_path)
        expected_digest = _require_text(
            entry.get("authoritative_source_sha256"),
            "baseline_workflow_manifest.json file entries must define non-empty authoritative_source_sha256",
        )
        if current_digest != expected_digest:
            raise ValueError(f"authoritative selected workflow file changed during refinement publication: {relative_path}")


def _validate_candidate_manifest(
    candidate_manifest: Mapping[str, Any],
    repo_root: Path,
    expected_boundary: Mapping[str, Any],
    baseline_manifest: Mapping[str, Any],
) -> None:
    if _require_text(
        candidate_manifest.get("surface_kind"),
        "candidate_workflow_manifest.json must define non-empty surface_kind",
    ) != "candidate":
        raise ValueError("candidate_workflow_manifest.json surface_kind must be candidate")
    if _require_text(
        candidate_manifest.get("repo_root"),
        "candidate_workflow_manifest.json must define non-empty repo_root",
    ) != str(repo_root):
        raise ValueError("candidate_workflow_manifest.json repo_root must match the runtime repo root")
    if _require_text(
        candidate_manifest.get("package_name"),
        "candidate_workflow_manifest.json must define non-empty package_name",
    ) != _require_text(
        expected_boundary.get("package_name"),
        "expected boundary must define package_name",
    ):
        raise ValueError("candidate_workflow_manifest.json package_name must match selected_workflow_authoring_surface.json")
    if _require_text(
        candidate_manifest.get("package_root_relative_path"),
        "candidate_workflow_manifest.json must define non-empty package_root_relative_path",
    ) != _require_text(
        expected_boundary.get("package_root_relative_path"),
        "expected boundary must define package_root_relative_path",
    ):
        raise ValueError("candidate_workflow_manifest.json package_root_relative_path must match selected_workflow_authoring_surface.json")
    if _normalize_optional_text(candidate_manifest.get("doc_relative_path")) != _normalize_optional_text(
        expected_boundary.get("doc_relative_path")
    ):
        raise ValueError("candidate_workflow_manifest.json doc_relative_path must match selected_workflow_authoring_surface.json")
    if _normalize_optional_text(candidate_manifest.get("runtime_test_relative_path")) != _normalize_optional_text(
        expected_boundary.get("runtime_test_relative_path")
    ):
        raise ValueError("candidate_workflow_manifest.json runtime_test_relative_path must match selected_workflow_authoring_surface.json")

    baseline_relative_paths = _require_string_list(
        baseline_manifest.get("relative_paths"),
        "baseline_workflow_manifest.json must define non-empty relative_paths",
    )
    candidate_baseline_relative_paths = _require_string_list(
        candidate_manifest.get("baseline_relative_paths"),
        "candidate_workflow_manifest.json must define non-empty baseline_relative_paths",
    )
    if candidate_baseline_relative_paths != baseline_relative_paths:
        raise ValueError("candidate_workflow_manifest.json baseline_relative_paths must match baseline_workflow_manifest.json")

    candidate_relative_paths = _require_string_list(
        candidate_manifest.get("relative_paths"),
        "candidate_workflow_manifest.json must define non-empty relative_paths",
    )
    missing_baseline_paths = sorted(set(baseline_relative_paths) - set(candidate_relative_paths))
    if missing_baseline_paths:
        raise ValueError("candidate_workflow_manifest.json must preserve every baseline relative_path")

    package_root_relative_path = _require_text(
        expected_boundary.get("package_root_relative_path"),
        "expected boundary must define package_root_relative_path",
    )
    allowed_exact_paths = {
        path
        for path in (
            _normalize_optional_text(expected_boundary.get("doc_relative_path")),
            _normalize_optional_text(expected_boundary.get("runtime_test_relative_path")),
        )
        if path is not None
    }
    for relative_path in candidate_relative_paths:
        if relative_path in baseline_relative_paths:
            continue
        if relative_path.startswith(f"{package_root_relative_path}/"):
            continue
        if relative_path in allowed_exact_paths:
            continue
        raise ValueError("candidate_workflow_manifest.json must stay scoped to the selected workflow boundary")

    file_entries = _manifest_file_map(
        candidate_manifest,
        "candidate_workflow_manifest.json must define files as a JSON array of objects with relative_path",
    )
    if sorted(file_entries) != candidate_relative_paths:
        raise ValueError("candidate_workflow_manifest.json files must match relative_paths")

    candidate_root = Path(
        _require_text(
            candidate_manifest.get("surface_root"),
            "candidate_workflow_manifest.json must define non-empty surface_root",
        )
    )
    for relative_path, entry in file_entries.items():
        surface_path = Path(
            _require_text(
                entry.get("surface_path"),
                "candidate_workflow_manifest.json file entries must define non-empty surface_path",
            )
        )
        if surface_path != candidate_root / relative_path:
            raise ValueError("candidate_workflow_manifest.json surface_path entries must stay under candidate_workflow_surface")
        if not surface_path.exists():
            raise FileNotFoundError(f"candidate surface file is missing: {surface_path}")
        expected_digest = _require_text(
            entry.get("surface_sha256"),
            "candidate_workflow_manifest.json file entries must define non-empty surface_sha256",
        )
        if _sha256_file(surface_path) != expected_digest:
            raise ValueError("candidate_workflow_manifest.json surface_sha256 must match candidate_workflow_surface")


def _validate_candidate_overlay(
    *,
    repo_root: Path,
    selected_workflow_name: str,
    candidate_manifest: Mapping[str, Any],
    target_test_command: str,
) -> dict[str, Any]:
    candidate_root = Path(
        _require_text(
            candidate_manifest.get("surface_root"),
            "candidate_workflow_manifest.json must define non-empty surface_root",
        )
    )
    command = _require_text(target_test_command, "target_test_command must stay non-empty")
    command_args = shlex.split(command)
    if command_args and command_args[0] == "pytest":
        command_args = [sys.executable, "-m", "pytest", *command_args[1:]]
    overlay_source_root = _resolve_overlay_source_root(repo_root)

    with tempfile.TemporaryDirectory(prefix="workflow_refinement_overlay_") as tmp_dir:
        overlay_root = Path(tmp_dir) / overlay_source_root.name
        shutil.copytree(
            overlay_source_root,
            overlay_root,
            ignore=shutil.ignore_patterns(".autoloop", ".git", ".pytest_cache", "__pycache__", "*.pyc", ".mypy_cache", ".ruff_cache", ".venv"),
        )
        repo_venv = overlay_source_root / ".venv"
        overlay_venv = overlay_root / ".venv"
        if repo_venv.exists() and not overlay_venv.exists():
            overlay_venv.symlink_to(repo_venv, target_is_directory=True)

        for relative_path in _require_string_list(
            candidate_manifest.get("relative_paths"),
            "candidate_workflow_manifest.json must define non-empty relative_paths",
        ):
            source_path = candidate_root / relative_path
            target_path = overlay_root / relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)

        with _preserved_workflow_modules():
            resolved = resolve_workflow_reference(overlay_root, selected_workflow_name)
            compiled = compile_workflow(resolved.workflow_cls)
        completed = subprocess.run(
            command_args,
            cwd=overlay_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise ValueError(
                "overlay validation command failed for candidate workflow surface: "
                f"{command}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
            )
        return {
            "compiled_workflow_name": compiled.workflow_name,
            "test_command": command,
            "test_returncode": completed.returncode,
        }


def _resolve_overlay_source_root(repo_root: Path) -> Path:
    if _is_runnable_repo_root(repo_root):
        return repo_root
    try:
        import autoloop_v3
    except ImportError as exc:  # pragma: no cover - defensive fallback for broken test/runtime setup
        raise ValueError(
            "publish-time overlay validation requires a runnable repo root or an importable autoloop_v3 package"
        ) from exc

    package_root = Path(autoloop_v3.__file__).resolve().parent
    if not _is_runnable_repo_root(package_root):
        raise ValueError(f"autoloop_v3 package root is not runnable for overlay validation: {package_root}")
    return package_root


def _is_runnable_repo_root(path: Path) -> bool:
    return (
        path.is_dir()
        and (path / "__init__.py").is_file()
        and (path / "core").is_dir()
        and (path / "runtime").is_dir()
        and (path / "tests" / "conftest.py").is_file()
    )


@contextmanager
def _preserved_workflow_modules():
    preserved = {
        name: module for name, module in sys.modules.items() if name == "workflows" or name.startswith("workflows.")
    }
    try:
        yield
    finally:
        for name in tuple(sys.modules):
            if name == "workflows" or name.startswith("workflows."):
                sys.modules.pop(name, None)
        sys.modules.update(preserved)


def _resolve_input_path(repo_root: Path, raw_value: str, field_name: str) -> Path:
    candidate = Path(_require_text(raw_value, f"{field_name} must be non-empty"))
    path = candidate if candidate.is_absolute() else repo_root / candidate
    if not path.exists():
        raise FileNotFoundError(f"{field_name} does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"{field_name} must point to a file: {path}")
    return path


def _manifest_file_map(manifest: Mapping[str, Any], error_message: str) -> dict[str, dict[str, Any]]:
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValueError(error_message)
    result: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(files):
        mapping = _require_mapping(entry, error_message)
        relative_path = _require_text(
            mapping.get("relative_path"),
            f"{error_message}; offending index {index}",
        )
        result[relative_path] = dict(mapping)
    return result


_read_json = read_json_object


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _require_non_empty_text_file(path: Path, error_message: str) -> str:
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(error_message)
    return content


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


_require_text = partial(require_non_empty_string, coerce=True)
_normalize_optional_text = normalize_optional_string
_require_string_list = partial(require_string_list, dedupe=True, coerce=True)
_require_positive_int = require_positive_int
_require_mapping = require_mapping
