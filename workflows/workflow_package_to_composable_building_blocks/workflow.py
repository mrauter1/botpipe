"""Reusable decomposition building-block workflow package."""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from functools import partial
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

try:  # pragma: no branch - supports both package and direct repo-root imports
    from autoloop_v3.stdlib import (
        derive_candidate_surface_manifest,
        materialize_baseline_surface,
        normalize_candidate_surface_overlay_result,
        normalize_candidate_surface_boundary,
        normalize_optional_string,
        normalize_unique_strings,
        read_json_object,
        require_mapping,
        require_non_empty_string,
        require_positive_int,
        require_string_list,
        validate_selected_workflow_decomposition_surface_snapshot,
        validate_authoritative_surface_sources_unchanged,
        validate_baseline_surface_manifest,
        validate_candidate_surface_manifest,
        validate_candidate_surface_overlay,
        write_selected_workflow_decomposition_surface,
    )
    from autoloop_v3.stdlib.control import event_on_outcome_tags, global_routes, merge_transitions, pause_on_outcome_tags
    from autoloop_v3.stdlib.lifecycle import (
        open_workflow_sessions,
        write_invocation_contract,
        write_publication_receipt,
        write_workflow_json,
    )
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from stdlib import (
        derive_candidate_surface_manifest,
        materialize_baseline_surface,
        normalize_candidate_surface_overlay_result,
        normalize_candidate_surface_boundary,
        normalize_optional_string,
        normalize_unique_strings,
        read_json_object,
        require_mapping,
        require_non_empty_string,
        require_positive_int,
        require_string_list,
        validate_selected_workflow_decomposition_surface_snapshot,
        validate_authoritative_surface_sources_unchanged,
        validate_baseline_surface_manifest,
        validate_candidate_surface_manifest,
        validate_candidate_surface_overlay,
        write_selected_workflow_decomposition_surface,
    )
    from stdlib.control import event_on_outcome_tags, global_routes, merge_transitions, pause_on_outcome_tags
    from stdlib.lifecycle import open_workflow_sessions, write_invocation_contract, write_publication_receipt, write_workflow_json

from workflow import Artifact, FAIL, PairStep, Session, SUCCESS, SystemStep, Workflow
from workflow.primitives import Event, Outcome

from .contracts import (
    CandidateDecompositionBuildPayload,
    CandidateDecompositionEvaluationPayload,
    DecompositionPlanPayload,
    DecompositionRequestFramingPayload,
    DESIGN_DECOMPOSITION_PLAN_ROUTE_CONTRACTS,
    EVALUATE_CANDIDATE_DECOMPOSITION_ROUTE_CONTRACTS,
    FRAME_DECOMPOSITION_REQUEST_ROUTE_CONTRACTS,
    IMPLEMENT_CANDIDATE_DECOMPOSITION_ROUTE_CONTRACTS,
)


_AUTHORITATIVE_EVALUATION_ARTIFACTS = frozenset(
    {
        "decomposition_verification_report",
        "composition_migration_guide",
        "promotion_record",
        "rollback_plan",
    }
)


class _CaptureBlockedError(RuntimeError):
    """Raised when deterministic context capture must route the workflow to blocked."""


class WorkflowPackageToComposableBuildingBlocks(Workflow):
    """Turn one workflow package into a candidate decomposition overlay and receipt."""

    name = "workflow_package_to_composable_building_blocks"

    class State(BaseModel):
        selected_workflow_reference: str = ""
        selected_workflow_name: str | None = None
        task_title: str = ""
        evidence_paths: list[str] = Field(default_factory=list)
        sponsor_role: str | None = None
        desired_outcome: str | None = None
        constraints: list[str] = Field(default_factory=list)
        target_test_command: str = "pytest -q"
        max_candidate_building_blocks: int = 3
        framing_status: str | None = None
        planning_status: str | None = None
        build_status: str | None = None
        evaluation_status: str | None = None
        candidate_file_count: int = 0
        candidate_changed_paths: list[str] = Field(default_factory=list)
        candidate_building_block_names: list[str] = Field(default_factory=list)
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
    decomposition_package_checklist = Artifact("{package_folder}/assets/decomposition_package_checklist.md")

    invocation_contract = Artifact("{workflow_folder}/invocation_contract.json")
    selected_workflow_decomposition_surface = Artifact("{workflow_folder}/selected_workflow_decomposition_surface.json")
    baseline_parent_workflow_surface = Artifact("{workflow_folder}/baseline_parent_workflow_surface")
    baseline_parent_manifest = Artifact("{workflow_folder}/baseline_parent_manifest.json")
    decomposition_evidence_manifest = Artifact("{workflow_folder}/decomposition_evidence_manifest.json")
    decomposition_request_brief = Artifact("{workflow_folder}/decomposition_request_brief.md")
    decomposition_acceptance_criteria = Artifact("{workflow_folder}/decomposition_acceptance_criteria.md")
    extraction_strategy = Artifact("{workflow_folder}/extraction_strategy.md")
    building_block_interface_contracts = Artifact("{workflow_folder}/building_block_interface_contracts.json")
    parent_rewrite_plan = Artifact("{workflow_folder}/parent_rewrite_plan.md")
    regression_guardrails = Artifact("{workflow_folder}/regression_guardrails.md")
    candidate_decomposition_surface = Artifact("{workflow_folder}/candidate_decomposition_surface")
    candidate_decomposition_manifest = Artifact("{workflow_folder}/candidate_decomposition_manifest.json")
    candidate_building_block_index = Artifact("{workflow_folder}/candidate_building_block_index.json")
    decomposition_build_report = Artifact("{workflow_folder}/decomposition_build_report.md")
    candidate_diff_summary = Artifact("{workflow_folder}/candidate_diff_summary.md")
    decomposition_verification_report = Artifact("{workflow_folder}/decomposition_verification_report.md")
    composition_migration_guide = Artifact("{workflow_folder}/composition_migration_guide.md")
    promotion_record = Artifact("{workflow_folder}/promotion_record.md")
    rollback_plan = Artifact("{workflow_folder}/rollback_plan.md")
    workflow_decomposition_receipt = Artifact("{workflow_folder}/workflow_decomposition_receipt.json")

    bootstrap = SystemStep(
        name="bootstrap",
        requires=[request],
        produces={"invocation_contract": invocation_contract},
    )
    capture_decomposition_context = SystemStep(
        name="capture_decomposition_context",
        requires=[request, invocation_contract],
        produces={
            "selected_workflow_decomposition_surface": selected_workflow_decomposition_surface,
            "baseline_parent_workflow_surface": baseline_parent_workflow_surface,
            "baseline_parent_manifest": baseline_parent_manifest,
            "decomposition_evidence_manifest": decomposition_evidence_manifest,
        },
    )
    frame_decomposition_request = PairStep(
        name="frame_decomposition_request",
        session=frame_session,
        producer="prompts/frame_producer.md",
        verifier="prompts/frame_verifier.md",
        requires=[
            request,
            invocation_contract,
            selected_workflow_decomposition_surface,
            baseline_parent_manifest,
            decomposition_evidence_manifest,
            framework_architecture_doc,
            framework_authoring_doc,
            workflow_instructions,
        ],
        produces={
            "decomposition_request_brief": decomposition_request_brief,
            "decomposition_acceptance_criteria": decomposition_acceptance_criteria,
        },
        expected_output_schema=DecompositionRequestFramingPayload,
        route_contracts=FRAME_DECOMPOSITION_REQUEST_ROUTE_CONTRACTS,
    )
    design_decomposition_plan = PairStep(
        name="design_decomposition_plan",
        session=design_session,
        producer="prompts/design_producer.md",
        verifier="prompts/design_verifier.md",
        requires=[
            request,
            invocation_contract,
            selected_workflow_decomposition_surface,
            baseline_parent_manifest,
            decomposition_evidence_manifest,
            decomposition_request_brief,
            decomposition_acceptance_criteria,
            decomposition_package_checklist,
        ],
        produces={
            "extraction_strategy": extraction_strategy,
            "building_block_interface_contracts": building_block_interface_contracts,
            "parent_rewrite_plan": parent_rewrite_plan,
            "regression_guardrails": regression_guardrails,
        },
        expected_output_schema=DecompositionPlanPayload,
        route_contracts=DESIGN_DECOMPOSITION_PLAN_ROUTE_CONTRACTS,
    )
    implement_candidate_decomposition = PairStep(
        name="implement_candidate_decomposition",
        session=build_session,
        producer="prompts/implement_producer.md",
        verifier="prompts/implement_verifier.md",
        requires=[
            request,
            invocation_contract,
            selected_workflow_decomposition_surface,
            baseline_parent_workflow_surface,
            baseline_parent_manifest,
            decomposition_evidence_manifest,
            decomposition_request_brief,
            decomposition_acceptance_criteria,
            extraction_strategy,
            building_block_interface_contracts,
            parent_rewrite_plan,
            regression_guardrails,
        ],
        produces={
            "candidate_decomposition_surface": candidate_decomposition_surface,
            "candidate_building_block_index": candidate_building_block_index,
            "decomposition_build_report": decomposition_build_report,
            "candidate_diff_summary": candidate_diff_summary,
        },
        expected_output_schema=CandidateDecompositionBuildPayload,
        route_contracts=IMPLEMENT_CANDIDATE_DECOMPOSITION_ROUTE_CONTRACTS,
    )
    evaluate_candidate_decomposition = PairStep(
        name="evaluate_candidate_decomposition",
        session=evaluate_session,
        producer="prompts/evaluate_producer.md",
        verifier="prompts/evaluate_verifier.md",
        requires=[
            request,
            invocation_contract,
            selected_workflow_decomposition_surface,
            baseline_parent_workflow_surface,
            baseline_parent_manifest,
            decomposition_evidence_manifest,
            decomposition_request_brief,
            decomposition_acceptance_criteria,
            extraction_strategy,
            building_block_interface_contracts,
            parent_rewrite_plan,
            regression_guardrails,
            candidate_decomposition_surface,
            candidate_decomposition_manifest,
            candidate_building_block_index,
            decomposition_build_report,
            candidate_diff_summary,
        ],
        produces={
            "decomposition_verification_report": decomposition_verification_report,
            "composition_migration_guide": composition_migration_guide,
            "promotion_record": promotion_record,
            "rollback_plan": rollback_plan,
        },
        expected_output_schema=CandidateDecompositionEvaluationPayload,
        route_contracts=EVALUATE_CANDIDATE_DECOMPOSITION_ROUTE_CONTRACTS,
    )
    publish_candidate_decomposition = SystemStep(
        name="publish_candidate_decomposition",
        requires=[
            selected_workflow_decomposition_surface,
            baseline_parent_manifest,
            decomposition_evidence_manifest,
            candidate_decomposition_manifest,
            candidate_building_block_index,
            decomposition_verification_report,
            composition_migration_guide,
            promotion_record,
            rollback_plan,
        ],
        produces={"workflow_decomposition_receipt": workflow_decomposition_receipt},
    )

    entry = bootstrap

    transitions = merge_transitions(
        global_routes(pause_on_outcome_tags("question", "blocked"), failed=FAIL),
        {
            bootstrap: {"inputs_prepared": capture_decomposition_context},
            capture_decomposition_context: {"decomposition_context_captured": frame_decomposition_request},
            frame_decomposition_request: {
                "decomposition_request_framed": design_decomposition_plan,
                "needs_rework": frame_decomposition_request,
                "needs_replan": frame_decomposition_request,
            },
            design_decomposition_plan: {
                "decomposition_plan_designed": implement_candidate_decomposition,
                "needs_rework": design_decomposition_plan,
                "needs_replan": frame_decomposition_request,
            },
            implement_candidate_decomposition: {
                "candidate_decomposition_built": evaluate_candidate_decomposition,
                "needs_rework": implement_candidate_decomposition,
                "needs_replan": design_decomposition_plan,
            },
            evaluate_candidate_decomposition: {
                "candidate_decomposition_evaluated": publish_candidate_decomposition,
                "needs_rework": implement_candidate_decomposition,
                "needs_replan": design_decomposition_plan,
            },
            publish_candidate_decomposition: {"candidate_decomposition_published": SUCCESS},
        },
    )

    @staticmethod
    def on_bootstrap(state: State, ctx) -> tuple[State, Event]:
        payload = dict(ctx.workflow_params)
        selected_workflow_reference = _require_text(
            payload.get("selected_workflow"),
            "workflow_package_to_composable_building_blocks requires workflow parameter 'selected_workflow'",
        )
        task_title = _require_text(
            payload.get("task_title"),
            "workflow_package_to_composable_building_blocks requires workflow parameter 'task_title'",
        )
        target_test_command = _require_text(
            payload.get("target_test_command") or "pytest -q",
            "workflow_package_to_composable_building_blocks requires a non-empty target_test_command",
        )
        max_candidate_building_blocks = _require_positive_int(
            payload.get("max_candidate_building_blocks") or 3,
            "workflow_package_to_composable_building_blocks requires max_candidate_building_blocks >= 1",
        )

        next_state = state.model_copy(
            update={
                "selected_workflow_reference": selected_workflow_reference,
                "selected_workflow_name": None,
                "task_title": task_title,
                "evidence_paths": _normalize_unique_strings(payload.get("evidence_paths")),
                "sponsor_role": _normalize_optional_text(payload.get("sponsor_role")),
                "desired_outcome": _normalize_optional_text(payload.get("desired_outcome")),
                "constraints": _normalize_unique_strings(payload.get("constraints")),
                "target_test_command": target_test_command,
                "max_candidate_building_blocks": max_candidate_building_blocks,
                "framing_status": None,
                "planning_status": None,
                "build_status": None,
                "evaluation_status": None,
                "candidate_file_count": 0,
                "candidate_changed_paths": [],
                "candidate_building_block_names": [],
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
                "evidence_paths": next_state.evidence_paths,
                "sponsor_role": next_state.sponsor_role,
                "desired_outcome": next_state.desired_outcome,
                "constraints": next_state.constraints,
                "target_test_command": next_state.target_test_command,
                "max_candidate_building_blocks": next_state.max_candidate_building_blocks,
            },
        )
        return next_state, Event("inputs_prepared")

    @staticmethod
    def on_capture_decomposition_context(state: State, ctx) -> tuple[State, Event]:
        repo_root = _repo_root_from_context(ctx)
        try:
            surface_path = write_selected_workflow_decomposition_surface(ctx, state.selected_workflow_reference)
            surface_snapshot = _read_json(surface_path)
            selected_workflow_name = _validated_selected_workflow_name(
                surface_snapshot,
                state.selected_workflow_reference,
            )
            boundary = _decomposition_surface_boundary(surface_snapshot, repo_root)
            _write_baseline_parent_manifest(
                ctx,
                repo_root=repo_root,
                selected_workflow_name=selected_workflow_name,
                boundary=boundary,
            )
            _capture_decomposition_evidence(ctx, repo_root=repo_root, requested_paths=state.evidence_paths)
        except _CaptureBlockedError as exc:
            return state, Event("blocked", reason=str(exc))
        return (
            state.model_copy(update={"selected_workflow_name": selected_workflow_name}),
            Event("decomposition_context_captured"),
        )

    @staticmethod
    def on_frame_decomposition_request(state: State, outcome: Outcome, artifacts):
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
    def on_design_decomposition_plan(state: State, outcome: Outcome, artifacts):
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
    def on_implement_candidate_decomposition(state: State, outcome: Outcome, artifacts):
        payload = outcome.payload
        selected_workflow_name = payload.get("selected_workflow_name")
        if outcome.tag == "needs_replan":
            return state.model_copy(
                update={
                    "build_status": outcome.tag,
                    "selected_workflow_name": (
                        selected_workflow_name if isinstance(selected_workflow_name, str) else state.selected_workflow_name
                    ),
                }
            )

        candidate_manifest = _write_candidate_decomposition_manifest(
            artifacts.candidate_decomposition_manifest.path.parent,
            _read_json(artifacts.baseline_parent_manifest.path),
            _read_json(artifacts.candidate_building_block_index.path),
            state.selected_workflow_name
            or _require_text(selected_workflow_name, "build payload must define selected_workflow_name"),
            state.max_candidate_building_blocks,
        )
        actual_candidate_file_count = _require_positive_int(
            candidate_manifest.get("file_count"),
            "candidate_decomposition_manifest.json must define positive integer file_count",
        )
        actual_changed_relative_paths = _require_string_list(
            candidate_manifest.get("changed_relative_paths"),
            "candidate_decomposition_manifest.json must define non-empty changed_relative_paths",
        )
        actual_building_block_names = _require_string_list(
            candidate_manifest.get("building_block_names"),
            "candidate_decomposition_manifest.json must define non-empty building_block_names",
        )
        payload_candidate_file_count = _require_positive_int(
            payload.get("candidate_file_count"),
            "build verifier payload must define positive integer candidate_file_count",
        )
        payload_changed_relative_paths = _require_string_list(
            payload.get("changed_relative_paths"),
            "build verifier payload must define non-empty changed_relative_paths",
        )
        payload_building_block_names = _require_string_list(
            payload.get("building_block_names"),
            "build verifier payload must define non-empty building_block_names",
        )
        if payload_candidate_file_count != actual_candidate_file_count:
            raise ValueError(
                "build verifier payload candidate_file_count must match candidate_decomposition_manifest.json"
            )
        if payload_changed_relative_paths != actual_changed_relative_paths:
            raise ValueError(
                "build verifier payload changed_relative_paths must match candidate_decomposition_manifest.json"
            )
        if sorted(payload_building_block_names) != actual_building_block_names:
            raise ValueError(
                "build verifier payload building_block_names must match candidate_decomposition_manifest.json"
            )
        return state.model_copy(
            update={
                "build_status": outcome.tag,
                "selected_workflow_name": (
                    selected_workflow_name if isinstance(selected_workflow_name, str) else state.selected_workflow_name
                ),
                "candidate_file_count": actual_candidate_file_count,
                "candidate_changed_paths": actual_changed_relative_paths,
                "candidate_building_block_names": actual_building_block_names,
            }
        )

    @staticmethod
    def on_evaluate_candidate_decomposition(state: State, outcome: Outcome, artifacts):
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
        building_block_names = _require_string_list(
            payload.get("building_block_names"),
            "evaluation verifier payload must define non-empty building_block_names",
        )
        next_action = _require_text(
            payload.get("next_action"),
            "evaluation verifier payload must define a non-empty next_action",
        )
        ready_for_publication = payload.get("ready_for_publication")
        if outcome.tag == "candidate_decomposition_evaluated" and ready_for_publication is not True:
            raise ValueError("candidate_decomposition_evaluated requires ready_for_publication=true")
        if state.candidate_file_count and candidate_file_count != state.candidate_file_count:
            raise ValueError("evaluation verifier payload candidate_file_count must match workflow state")
        if state.candidate_building_block_names and sorted(building_block_names) != state.candidate_building_block_names:
            raise ValueError("evaluation verifier payload building_block_names must match workflow state")
        return state.model_copy(
            update={
                "evaluation_status": outcome.tag,
                "selected_workflow_name": (
                    selected_workflow_name if isinstance(selected_workflow_name, str) else state.selected_workflow_name
                ),
                "candidate_file_count": candidate_file_count,
                "candidate_building_block_names": sorted(building_block_names),
                "evaluation_authoritative_artifacts": authoritative_artifacts,
                "evaluation_next_action": next_action,
            }
        )

    @staticmethod
    def on_publish_candidate_decomposition(state: State, ctx) -> tuple[State, Event]:
        workflow_folder = ctx.workflow_folder
        required_paths = {
            "selected_workflow_decomposition_surface": workflow_folder / "selected_workflow_decomposition_surface.json",
            "baseline_parent_manifest": workflow_folder / "baseline_parent_manifest.json",
            "decomposition_evidence_manifest": workflow_folder / "decomposition_evidence_manifest.json",
            "candidate_decomposition_manifest": workflow_folder / "candidate_decomposition_manifest.json",
            "candidate_building_block_index": workflow_folder / "candidate_building_block_index.json",
            "decomposition_verification_report": workflow_folder / "decomposition_verification_report.md",
            "composition_migration_guide": workflow_folder / "composition_migration_guide.md",
            "promotion_record": workflow_folder / "promotion_record.md",
            "rollback_plan": workflow_folder / "rollback_plan.md",
        }
        required_dirs = {
            "baseline_parent_workflow_surface": workflow_folder / "baseline_parent_workflow_surface",
            "candidate_decomposition_surface": workflow_folder / "candidate_decomposition_surface",
        }
        for artifact_path in required_paths.values():
            if not artifact_path.exists():
                raise FileNotFoundError(f"missing required publication artifact at {artifact_path}")
        for artifact_path in required_dirs.values():
            if not artifact_path.exists():
                raise FileNotFoundError(f"missing required publication artifact at {artifact_path}")

        repo_root = _repo_root_from_context(ctx)
        decomposition_surface_snapshot = _read_json(required_paths["selected_workflow_decomposition_surface"])
        baseline_manifest = _read_json(required_paths["baseline_parent_manifest"])
        evidence_manifest = _read_json(required_paths["decomposition_evidence_manifest"])
        candidate_manifest = _read_json(required_paths["candidate_decomposition_manifest"])
        building_block_index = _read_json(required_paths["candidate_building_block_index"])
        _require_non_empty_text_file(
            required_paths["decomposition_verification_report"],
            "decomposition_verification_report.md must be non-empty",
        )
        _require_non_empty_text_file(
            required_paths["composition_migration_guide"],
            "composition_migration_guide.md must be non-empty",
        )
        _require_non_empty_text_file(required_paths["promotion_record"], "promotion_record.md must be non-empty")
        _require_non_empty_text_file(required_paths["rollback_plan"], "rollback_plan.md must be non-empty")

        selected_workflow_name = _validated_selected_workflow_name(
            decomposition_surface_snapshot,
            state.selected_workflow_reference,
        )
        if state.selected_workflow_name is not None and state.selected_workflow_name != selected_workflow_name:
            raise ValueError("selected_workflow_decomposition_surface.json must match workflow state")

        boundary = _decomposition_surface_boundary(decomposition_surface_snapshot, repo_root)
        _validate_evidence_manifest(
            evidence_manifest,
            request_path=ctx.run_folder / "request.md",
            workflow_folder=ctx.workflow_folder,
        )
        _validate_baseline_parent_manifest(baseline_manifest, repo_root, boundary)
        _validate_authoritative_files_unchanged(baseline_manifest, repo_root)

        declared_building_blocks = _validate_building_block_index(
            building_block_index,
            repo_root=repo_root,
            selected_workflow_name=selected_workflow_name,
            boundary=boundary,
            max_candidate_building_blocks=state.max_candidate_building_blocks,
        )
        _validate_candidate_decomposition_manifest(
            candidate_manifest,
            repo_root=repo_root,
            boundary=boundary,
            baseline_manifest=baseline_manifest,
            declared_building_blocks=declared_building_blocks,
        )

        candidate_file_count = _require_positive_int(
            candidate_manifest.get("file_count"),
            "candidate_decomposition_manifest.json must define positive integer file_count",
        )
        candidate_changed_paths = _require_string_list(
            candidate_manifest.get("changed_relative_paths"),
            "candidate_decomposition_manifest.json must define non-empty changed_relative_paths",
        )
        candidate_building_block_names = _require_string_list(
            candidate_manifest.get("building_block_names"),
            "candidate_decomposition_manifest.json must define non-empty building_block_names",
        )
        if state.candidate_file_count and candidate_file_count != state.candidate_file_count:
            raise ValueError("candidate_decomposition_manifest.json file_count must match workflow state")
        if state.candidate_changed_paths and candidate_changed_paths != state.candidate_changed_paths:
            raise ValueError("candidate_decomposition_manifest.json changed_relative_paths must match workflow state")
        if state.candidate_building_block_names and candidate_building_block_names != state.candidate_building_block_names:
            raise ValueError("candidate_decomposition_manifest.json building_block_names must match workflow state")
        if not _AUTHORITATIVE_EVALUATION_ARTIFACTS.issubset(state.evaluation_authoritative_artifacts):
            raise ValueError(
                "workflow state authoritative evaluation artifacts must include decomposition_verification_report, composition_migration_guide, promotion_record, and rollback_plan"
            )
        if state.evaluation_next_action is None:
            raise ValueError("workflow state must define evaluation_next_action before publication")

        overlay_validation = _validate_candidate_overlay(
            repo_root=repo_root,
            selected_workflow_name=selected_workflow_name,
            building_block_names=candidate_building_block_names,
            candidate_manifest=candidate_manifest,
            target_test_command=state.target_test_command,
        )

        write_publication_receipt(
            ctx,
            "workflow_decomposition_receipt.json",
            {
                "workflow_name": ctx.workflow_name,
                "task_title": state.task_title,
                "sponsor_role": state.sponsor_role,
                "desired_outcome": state.desired_outcome,
                "selected_workflow_reference": state.selected_workflow_reference,
                "selected_workflow_name": selected_workflow_name,
                "target_test_command": state.target_test_command,
                "max_candidate_building_blocks": state.max_candidate_building_blocks,
                "candidate_file_count": candidate_file_count,
                "changed_relative_paths": candidate_changed_paths,
                "building_block_names": candidate_building_block_names,
                "authoritative_artifacts": [
                    "selected_workflow_decomposition_surface",
                    "baseline_parent_manifest",
                    "decomposition_evidence_manifest",
                    "candidate_decomposition_manifest",
                    "candidate_building_block_index",
                    "decomposition_verification_report",
                    "composition_migration_guide",
                    "promotion_record",
                    "rollback_plan",
                    "workflow_decomposition_receipt",
                ],
                "selected_workflow_decomposition_surface": str(required_paths["selected_workflow_decomposition_surface"]),
                "baseline_parent_workflow_surface": str(required_dirs["baseline_parent_workflow_surface"]),
                "baseline_parent_manifest": str(required_paths["baseline_parent_manifest"]),
                "decomposition_evidence_manifest": str(required_paths["decomposition_evidence_manifest"]),
                "candidate_decomposition_surface": str(required_dirs["candidate_decomposition_surface"]),
                "candidate_decomposition_manifest": str(required_paths["candidate_decomposition_manifest"]),
                "candidate_building_block_index": str(required_paths["candidate_building_block_index"]),
                "decomposition_verification_report": str(required_paths["decomposition_verification_report"]),
                "composition_migration_guide": str(required_paths["composition_migration_guide"]),
                "promotion_record": str(required_paths["promotion_record"]),
                "rollback_plan": str(required_paths["rollback_plan"]),
                "next_action": state.evaluation_next_action,
                "overlay_validation": overlay_validation,
                "published": True,
            },
        )
        return state.model_copy(update={"selected_workflow_name": selected_workflow_name, "published": True}), Event(
            "candidate_decomposition_published"
        )

    on_outcome = staticmethod(event_on_outcome_tags("question", "blocked", "failed"))


def _repo_root_from_context(ctx) -> Path:
    return ctx.package_folder.resolve().parent.parent


def _validated_selected_workflow_name(
    decomposition_surface_snapshot: Mapping[str, Any],
    selected_workflow_reference: str,
) -> str:
    selected_workflow_name, _, _, _ = validate_selected_workflow_decomposition_surface_snapshot(
        decomposition_surface_snapshot
    )
    if not selected_workflow_reference.strip():
        raise ValueError("selected_workflow_reference must stay non-empty")
    return selected_workflow_name


def _decomposition_surface_boundary(
    decomposition_surface_snapshot: Mapping[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    decomposition_surface = _require_mapping(
        decomposition_surface_snapshot.get("selected_workflow_decomposition_surface"),
        "selected_workflow_decomposition_surface.json must define selected_workflow_decomposition_surface as a JSON object",
    )
    identity = _require_mapping(
        decomposition_surface.get("selected_workflow_identity"),
        "selected_workflow_decomposition_surface.json must define selected_workflow_identity as a JSON object",
    )
    authoring_surface = _require_mapping(
        decomposition_surface.get("selected_workflow_authoring_surface"),
        "selected_workflow_decomposition_surface.json must define selected_workflow_authoring_surface as a JSON object",
    )
    normalized_boundary = normalize_candidate_surface_boundary(
        repo_root,
        authoring_surface,
        error_prefix="selected_workflow_decomposition_surface.json",
    )

    return {
        "selected_workflow_name": _require_text(
            identity.get("workflow_name"),
            "selected_workflow_decomposition_surface.json must define selected_workflow_identity.workflow_name",
        ),
        "parent_package_name": _require_text(
            identity.get("package_name"),
            "selected_workflow_decomposition_surface.json must define selected_workflow_identity.package_name",
        ),
        "parent_package_root_relative_path": normalized_boundary["package_root_relative_path"],
        "parent_doc_relative_path": normalized_boundary["doc_relative_path"],
        "parent_runtime_test_relative_path": normalized_boundary["runtime_test_relative_path"],
        "baseline_relative_paths": normalized_boundary["baseline_relative_paths"],
    }


def _write_baseline_parent_manifest(
    ctx,
    *,
    repo_root: Path,
    selected_workflow_name: str,
    boundary: Mapping[str, Any],
) -> dict[str, Any]:
    surface_manifest = materialize_baseline_surface(
        workflow_folder=ctx.workflow_folder,
        repo_root=repo_root,
        baseline_relative_paths=_require_string_list(
            boundary.get("baseline_relative_paths"),
            "baseline boundary must define non-empty baseline_relative_paths",
        ),
        baseline_dir_name="baseline_parent_workflow_surface",
        candidate_dir_name="candidate_decomposition_surface",
    )

    manifest = {
        "surface_kind": "baseline_parent",
        "selected_workflow_name": selected_workflow_name,
        "parent_package_name": _require_text(
            boundary.get("parent_package_name"),
            "baseline boundary must define parent_package_name",
        ),
        "parent_package_root_relative_path": _require_text(
            boundary.get("parent_package_root_relative_path"),
            "baseline boundary must define parent_package_root_relative_path",
        ),
        "parent_doc_relative_path": _normalize_optional_text(boundary.get("parent_doc_relative_path")),
        "parent_runtime_test_relative_path": _normalize_optional_text(
            boundary.get("parent_runtime_test_relative_path")
        ),
        "repo_root": str(repo_root),
        **surface_manifest,
    }
    write_workflow_json(ctx, "baseline_parent_manifest.json", manifest)
    return manifest


def _capture_decomposition_evidence(
    ctx,
    *,
    repo_root: Path,
    requested_paths: list[str],
) -> dict[str, Any]:
    evidence_root = ctx.workflow_folder / "decomposition_evidence"
    shutil.rmtree(evidence_root, ignore_errors=True)
    evidence_root.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, Any]] = []
    if not requested_paths:
        request_path = ctx.run_folder / "request.md"
        copied_path = evidence_root / "request.md"
        shutil.copy2(request_path, copied_path)
        manifest = {
            "capture_status": "captured",
            "request_fallback_used": True,
            "entries": [
                {
                    "requested_path": "request.md",
                    "source_path": str(request_path),
                    "copied_path": str(copied_path),
                    "repo_relative_path": None,
                    "sha256": _sha256_file(request_path),
                    "size_bytes": request_path.stat().st_size,
                    "fallback_request": True,
                }
            ],
        }
        write_workflow_json(ctx, "decomposition_evidence_manifest.json", manifest)
        return manifest

    for index, raw_path in enumerate(requested_paths):
        try:
            source_path = _resolve_input_path(repo_root, raw_path, "evidence_paths")
        except (FileNotFoundError, ValueError) as exc:
            manifest = {
                "capture_status": "blocked",
                "request_fallback_used": False,
                "blocking_reason": str(exc),
                "entries": entries
                + [
                    {
                        "requested_path": raw_path,
                        "status": "unreadable",
                    }
                ],
            }
            write_workflow_json(ctx, "decomposition_evidence_manifest.json", manifest)
            raise _CaptureBlockedError(str(exc)) from exc

        copied_path = evidence_root / f"{index:02d}_{source_path.name}"
        shutil.copy2(source_path, copied_path)
        entries.append(
            {
                "requested_path": raw_path,
                "source_path": str(source_path),
                "copied_path": str(copied_path),
                "repo_relative_path": _path_under_repo_or_none(repo_root, source_path),
                "sha256": _sha256_file(source_path),
                "size_bytes": source_path.stat().st_size,
                "fallback_request": False,
            }
        )

    manifest = {
        "capture_status": "captured",
        "request_fallback_used": False,
        "entries": entries,
    }
    write_workflow_json(ctx, "decomposition_evidence_manifest.json", manifest)
    return manifest


def _write_candidate_decomposition_manifest(
    workflow_folder: Path,
    baseline_manifest: Mapping[str, Any],
    building_block_index: Mapping[str, Any],
    selected_workflow_name: str,
    max_candidate_building_blocks: int,
) -> dict[str, Any]:
    boundary = {
        "parent_package_name": _require_text(
            baseline_manifest.get("parent_package_name"),
            "baseline_parent_manifest.json must define non-empty parent_package_name",
        ),
        "parent_package_root_relative_path": _require_text(
            baseline_manifest.get("parent_package_root_relative_path"),
            "baseline_parent_manifest.json must define non-empty parent_package_root_relative_path",
        ),
        "parent_doc_relative_path": _normalize_optional_text(baseline_manifest.get("parent_doc_relative_path")),
        "parent_runtime_test_relative_path": _normalize_optional_text(
            baseline_manifest.get("parent_runtime_test_relative_path")
        ),
    }
    declared_building_blocks = _validate_building_block_index(
        building_block_index,
        repo_root=Path(
            _require_text(
                baseline_manifest.get("repo_root"),
                "baseline_parent_manifest.json must define non-empty repo_root",
            )
        ),
        selected_workflow_name=selected_workflow_name,
        boundary=boundary,
        max_candidate_building_blocks=max_candidate_building_blocks,
    )
    surface_manifest = derive_candidate_surface_manifest(
        workflow_folder=workflow_folder,
        baseline_manifest=baseline_manifest,
        candidate_dir_name="candidate_decomposition_surface",
        baseline_manifest_label="baseline_parent_manifest.json",
        candidate_manifest_label="candidate_decomposition_manifest.json",
    )

    manifest = {
        "surface_kind": "candidate_decomposition",
        "selected_workflow_name": selected_workflow_name,
        "parent_package_name": boundary["parent_package_name"],
        "parent_package_root_relative_path": boundary["parent_package_root_relative_path"],
        "parent_doc_relative_path": boundary["parent_doc_relative_path"],
        "parent_runtime_test_relative_path": boundary["parent_runtime_test_relative_path"],
        **surface_manifest,
        "building_block_names": declared_building_blocks["building_block_names"],
        "building_block_package_roots": declared_building_blocks["allowed_package_roots"],
    }
    target_path = workflow_folder / "candidate_decomposition_manifest.json"
    target_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def _validate_evidence_manifest(
    evidence_manifest: Mapping[str, Any],
    *,
    request_path: Path,
    workflow_folder: Path,
) -> None:
    if _require_text(
        evidence_manifest.get("capture_status"),
        "decomposition_evidence_manifest.json must define non-empty capture_status",
    ) != "captured":
        raise ValueError("decomposition_evidence_manifest.json capture_status must be captured for publication")
    request_fallback_used = evidence_manifest.get("request_fallback_used")
    entries = evidence_manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("decomposition_evidence_manifest.json must define non-empty entries")
    for entry in entries:
        payload = _require_mapping(
            entry,
            "decomposition_evidence_manifest.json entries must be JSON objects",
        )
        source_path = Path(
            _require_text(payload.get("source_path"), "decomposition_evidence_manifest.json entries need source_path")
        )
        copied_path = Path(
            _require_text(payload.get("copied_path"), "decomposition_evidence_manifest.json entries need copied_path")
        )
        if not source_path.exists() or not copied_path.exists():
            raise FileNotFoundError("decomposition_evidence_manifest.json entries must point at existing files")
        if _sha256_file(copied_path) != _require_text(
            payload.get("sha256"),
            "decomposition_evidence_manifest.json entries need sha256",
        ):
            raise ValueError("decomposition_evidence_manifest.json copied artifacts must match their recorded sha256")
        try:
            copied_path.relative_to(workflow_folder)
        except ValueError as exc:
            raise ValueError(
                "decomposition_evidence_manifest.json copied_path must stay under the workflow folder"
            ) from exc
    if request_fallback_used:
        fallback_entry = _require_mapping(
            entries[0],
            "decomposition_evidence_manifest.json fallback entry must be a JSON object",
        )
        if fallback_entry.get("fallback_request") is not True:
            raise ValueError("decomposition_evidence_manifest.json fallback entry must set fallback_request true")
        if Path(
            _require_text(
                fallback_entry.get("source_path"),
                "decomposition_evidence_manifest.json fallback entry needs source_path",
            )
        ) != request_path:
            raise ValueError("decomposition_evidence_manifest.json fallback entry must point at request.md")


def _validate_baseline_parent_manifest(
    baseline_manifest: Mapping[str, Any],
    repo_root: Path,
    boundary: Mapping[str, Any],
) -> None:
    validate_baseline_surface_manifest(
        baseline_manifest,
        repo_root,
        manifest_label="baseline_parent_manifest.json",
        expected_surface_kind="baseline_parent",
        expected_boundary=boundary,
        boundary_field_map={
            "parent_package_name": "parent_package_name",
            "parent_package_root_relative_path": "parent_package_root_relative_path",
            "parent_doc_relative_path": "parent_doc_relative_path",
            "parent_runtime_test_relative_path": "parent_runtime_test_relative_path",
        },
        optional_boundary_fields=("parent_doc_relative_path", "parent_runtime_test_relative_path"),
        expected_relative_paths=_require_string_list(
            boundary.get("baseline_relative_paths"),
            "boundary must define non-empty baseline_relative_paths",
        ),
    )


def _validate_authoritative_files_unchanged(baseline_manifest: Mapping[str, Any], repo_root: Path) -> None:
    validate_authoritative_surface_sources_unchanged(
        baseline_manifest,
        repo_root,
        baseline_manifest_label="baseline_parent_manifest.json",
        drift_error_prefix="authoritative selected workflow file changed during decomposition publication",
    )


def _validate_building_block_index(
    building_block_index: Mapping[str, Any],
    *,
    repo_root: Path,
    selected_workflow_name: str,
    boundary: Mapping[str, Any],
    max_candidate_building_blocks: int,
) -> dict[str, Any]:
    if _require_text(
        building_block_index.get("selected_workflow_name"),
        "candidate_building_block_index.json must define non-empty selected_workflow_name",
    ) != selected_workflow_name:
        raise ValueError("candidate_building_block_index.json selected_workflow_name must match the selected workflow")
    if _require_text(
        building_block_index.get("publication_mode"),
        "candidate_building_block_index.json must define non-empty publication_mode",
    ) != "candidate_only":
        raise ValueError(
            "candidate_building_block_index.json must keep publication_mode candidate_only to prevent hidden execution"
        )
    if building_block_index.get("promotion_required") is not True:
        raise ValueError(
            "candidate_building_block_index.json must set promotion_required true to prevent hidden execution"
        )
    blocks = building_block_index.get("building_blocks")
    if not isinstance(blocks, list) or not blocks:
        raise ValueError("candidate_building_block_index.json must define non-empty building_blocks")
    if len(blocks) > max_candidate_building_blocks:
        raise ValueError("candidate_building_block_index.json exceeds max_candidate_building_blocks")

    parent_package_root_relative_path = _require_text(
        boundary.get("parent_package_root_relative_path"),
        "boundary must define parent_package_root_relative_path",
    )
    parent_doc_relative_path = _normalize_optional_text(boundary.get("parent_doc_relative_path"))
    parent_runtime_test_relative_path = _normalize_optional_text(boundary.get("parent_runtime_test_relative_path"))

    building_block_names: list[str] = []
    allowed_package_roots: list[str] = []
    allowed_exact_paths: list[str] = []
    for block in blocks:
        payload = _require_mapping(
            block,
            "candidate_building_block_index.json building_blocks entries must be JSON objects",
        )
        workflow_name = _require_text(
            payload.get("workflow_name"),
            "candidate_building_block_index.json entries must define workflow_name",
        )
        package_name = _require_text(
            payload.get("package_name"),
            "candidate_building_block_index.json entries must define package_name",
        )
        package_root_relative_path = _require_repo_relative_path(
            payload.get("package_root_relative_path"),
            prefix="workflows/",
            error_message="candidate_building_block_index.json package_root_relative_path must stay under workflows/",
        )
        if Path(package_root_relative_path).name != package_name:
            raise ValueError(
                "candidate_building_block_index.json package_root_relative_path must end with package_name"
            )
        if package_root_relative_path == parent_package_root_relative_path:
            raise ValueError("candidate_building_block_index.json must not reuse the parent workflow package root")
        doc_relative_path = _require_repo_relative_path(
            payload.get("doc_relative_path"),
            prefix="docs/workflows/",
            error_message="candidate_building_block_index.json doc_relative_path must stay under docs/workflows/",
        )
        runtime_test_relative_path = _require_repo_relative_path(
            payload.get("runtime_test_relative_path"),
            prefix="tests/runtime/",
            error_message="candidate_building_block_index.json runtime_test_relative_path must stay under tests/runtime/",
        )
        if doc_relative_path == parent_doc_relative_path:
            raise ValueError("candidate_building_block_index.json must not reuse the parent workflow doc path")
        if runtime_test_relative_path == parent_runtime_test_relative_path:
            raise ValueError("candidate_building_block_index.json must not reuse the parent runtime-test path")
        if workflow_name in building_block_names:
            raise ValueError("candidate_building_block_index.json workflow_name entries must be unique")
        for path in (package_root_relative_path, doc_relative_path, runtime_test_relative_path):
            if (repo_root / path).is_absolute() and ".." in Path(path).parts:
                raise ValueError("candidate_building_block_index.json paths must stay repo-relative")
        building_block_names.append(workflow_name)
        allowed_package_roots.append(package_root_relative_path)
        allowed_exact_paths.extend((doc_relative_path, runtime_test_relative_path))

    return {
        "building_block_names": sorted(building_block_names),
        "allowed_package_roots": sorted(allowed_package_roots),
        "allowed_exact_paths": sorted(allowed_exact_paths),
    }


def _validate_candidate_decomposition_manifest(
    candidate_manifest: Mapping[str, Any],
    *,
    repo_root: Path,
    boundary: Mapping[str, Any],
    baseline_manifest: Mapping[str, Any],
    declared_building_blocks: Mapping[str, Any],
) -> None:
    building_block_names = _require_string_list(
        candidate_manifest.get("building_block_names"),
        "candidate_decomposition_manifest.json must define non-empty building_block_names",
    )
    if building_block_names != _require_string_list(
        declared_building_blocks.get("building_block_names"),
        "declared building blocks must define non-empty building_block_names",
    ):
        raise ValueError("candidate_decomposition_manifest.json building_block_names must match candidate_building_block_index.json")
    building_block_package_roots = _require_string_list(
        candidate_manifest.get("building_block_package_roots"),
        "candidate_decomposition_manifest.json must define non-empty building_block_package_roots",
    )
    if building_block_package_roots != _require_string_list(
        declared_building_blocks.get("allowed_package_roots"),
        "declared building blocks must define non-empty allowed_package_roots",
    ):
        raise ValueError(
            "candidate_decomposition_manifest.json building_block_package_roots must match candidate_building_block_index.json"
        )

    allowed_exact_paths = _require_string_list(
        declared_building_blocks.get("allowed_exact_paths"),
        "declared building blocks must define non-empty allowed_exact_paths",
        min_length=2,
    )
    validated_manifest = validate_candidate_surface_manifest(
        candidate_manifest,
        repo_root=repo_root,
        manifest_label="candidate_decomposition_manifest.json",
        expected_surface_kind="candidate_decomposition",
        expected_boundary=boundary,
        boundary_field_map={
            "parent_package_name": "parent_package_name",
            "parent_package_root_relative_path": "parent_package_root_relative_path",
            "parent_doc_relative_path": "parent_doc_relative_path",
            "parent_runtime_test_relative_path": "parent_runtime_test_relative_path",
        },
        optional_boundary_fields=("parent_doc_relative_path", "parent_runtime_test_relative_path"),
        baseline_manifest=baseline_manifest,
        baseline_manifest_label="baseline_parent_manifest.json",
        allowed_added_path_prefixes=building_block_package_roots,
        allowed_added_exact_paths=allowed_exact_paths,
        require_surface_listing_matches_disk=True,
        require_file_count_matches_relative_paths=True,
    )
    missing_declared_exact_paths = sorted(
        path for path in set(allowed_exact_paths) if path not in validated_manifest["relative_paths"]
    )
    if missing_declared_exact_paths:
        raise ValueError(
            "candidate_decomposition_manifest.json must include every declared building-block doc_relative_path and runtime_test_relative_path"
        )


def _validate_candidate_overlay(
    *,
    repo_root: Path,
    selected_workflow_name: str,
    building_block_names: list[str],
    candidate_manifest: Mapping[str, Any],
    target_test_command: str,
) -> dict[str, Any]:
    return normalize_candidate_surface_overlay_result(
        validate_candidate_surface_overlay(
            repo_root=repo_root,
            workflow_names=[selected_workflow_name, *building_block_names],
            candidate_manifest=candidate_manifest,
            target_test_command=target_test_command,
            candidate_manifest_label="candidate_decomposition_manifest.json",
            overlay_failure_prefix="overlay validation command failed for candidate decomposition surface",
            overlay_temp_prefix="workflow_decomposition_overlay_",
        ),
        expect_single_compiled_workflow=False,
    )


def _resolve_input_path(repo_root: Path, raw_value: str, field_name: str) -> Path:
    candidate = Path(_require_text(raw_value, f"{field_name} must be non-empty"))
    path = candidate if candidate.is_absolute() else repo_root / candidate
    if not path.exists():
        raise FileNotFoundError(f"{field_name} does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"{field_name} must point to a file: {path}")
    return path


def _path_under_repo_or_none(repo_root: Path, path: Path) -> str | None:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return None


_read_json = read_json_object


def _require_non_empty_text_file(path: Path, error_message: str) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(error_message)
    return text


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_repo_relative_path(value: Any, *, prefix: str, error_message: str) -> str:
    path = _require_text(value, error_message)
    relative = Path(path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(error_message)
    normalized = relative.as_posix()
    if not normalized.startswith(prefix):
        raise ValueError(error_message)
    return normalized


_require_text = require_non_empty_string
_normalize_optional_text = partial(normalize_optional_string, error_message="expected string or null", coerce=False)
_normalize_unique_strings = partial(
    normalize_unique_strings,
    error_message="expected a list of strings",
    item_error_message="list entries must be non-empty strings",
    coerce=False,
)
_require_string_list = partial(require_string_list, sort_output=True)
_require_positive_int = require_positive_int
_require_mapping = require_mapping


__all__ = ["WorkflowPackageToComposableBuildingBlocks"]
