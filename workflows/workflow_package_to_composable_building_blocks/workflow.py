"""Reusable decomposition building-block workflow package."""

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
    selected_workflow_name = _require_text(
        decomposition_surface_snapshot.get("selected_workflow_name"),
        "selected_workflow_decomposition_surface.json must define a non-empty selected_workflow_name",
    )
    decomposition_surface = _require_mapping(
        decomposition_surface_snapshot.get("selected_workflow_decomposition_surface"),
        "selected_workflow_decomposition_surface.json must define selected_workflow_decomposition_surface as a JSON object",
    )
    identity = _require_mapping(
        decomposition_surface.get("selected_workflow_identity"),
        "selected_workflow_decomposition_surface.json must define selected_workflow_identity as a JSON object",
    )
    identity_workflow_name = _require_text(
        identity.get("workflow_name"),
        "selected_workflow_decomposition_surface.json must define selected_workflow_identity.workflow_name",
    )
    if identity_workflow_name != selected_workflow_name:
        raise ValueError("selected_workflow_decomposition_surface.json identity must match selected_workflow_name")

    compiled_surface = _require_mapping(
        decomposition_surface.get("selected_workflow_compiled_surface"),
        "selected_workflow_decomposition_surface.json must define selected_workflow_compiled_surface as a JSON object",
    )
    _require_positive_int(
        compiled_surface.get("step_count"),
        "selected_workflow_decomposition_surface.json must define positive integer step_count",
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

    package_dir = Path(
        _require_text(
            authoring_surface.get("package_dir"),
            "selected_workflow_decomposition_surface.json must define selected_workflow_authoring_surface.package_dir",
        )
    ).resolve()
    try:
        parent_package_root_relative_path = package_dir.relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise ValueError("selected_workflow_decomposition_surface.json package_dir must stay under the repo root") from exc

    baseline_relative_paths: list[str] = []
    for raw_path in _require_string_list(
        authoring_surface.get("editable_paths"),
        "selected_workflow_decomposition_surface.json must define non-empty editable_paths",
    ):
        path = Path(raw_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"selected_workflow_decomposition_surface.json path does not exist: {path}")
        try:
            relative_path = path.relative_to(repo_root).as_posix()
        except ValueError as exc:
            raise ValueError(
                "selected_workflow_decomposition_surface.json editable_paths must stay under the repo root"
            ) from exc
        if relative_path not in baseline_relative_paths:
            baseline_relative_paths.append(relative_path)

    return {
        "selected_workflow_name": _require_text(
            identity.get("workflow_name"),
            "selected_workflow_decomposition_surface.json must define selected_workflow_identity.workflow_name",
        ),
        "parent_package_name": _require_text(
            identity.get("package_name"),
            "selected_workflow_decomposition_surface.json must define selected_workflow_identity.package_name",
        ),
        "parent_package_root_relative_path": parent_package_root_relative_path,
        "parent_doc_relative_path": _optional_repo_relative_path(
            repo_root,
            authoring_surface.get("doc_path"),
            "selected_workflow_decomposition_surface.json doc_path must stay under the repo root",
        ),
        "parent_runtime_test_relative_path": _optional_repo_relative_path(
            repo_root,
            authoring_surface.get("runtime_test_path"),
            "selected_workflow_decomposition_surface.json runtime_test_path must stay under the repo root",
        ),
        "baseline_relative_paths": sorted(baseline_relative_paths),
    }


def _write_baseline_parent_manifest(
    ctx,
    *,
    repo_root: Path,
    selected_workflow_name: str,
    boundary: Mapping[str, Any],
) -> dict[str, Any]:
    baseline_root = ctx.workflow_folder / "baseline_parent_workflow_surface"
    candidate_root = ctx.workflow_folder / "candidate_decomposition_surface"
    shutil.rmtree(baseline_root, ignore_errors=True)
    shutil.rmtree(candidate_root, ignore_errors=True)

    files: list[dict[str, Any]] = []
    for relative_path in _require_string_list(
        boundary.get("baseline_relative_paths"),
        "baseline boundary must define non-empty baseline_relative_paths",
    ):
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
        "surface_root": str(baseline_root),
        "relative_paths": _require_string_list(
            boundary.get("baseline_relative_paths"),
            "baseline boundary must define non-empty baseline_relative_paths",
        ),
        "file_count": len(files),
        "files": files,
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
    candidate_root = workflow_folder / "candidate_decomposition_surface"
    if not candidate_root.is_dir():
        raise FileNotFoundError(f"candidate decomposition surface was not written at {candidate_root}")

    baseline_files = _manifest_file_map(
        baseline_manifest,
        "baseline_parent_manifest.json must define files as a JSON array of objects with relative_path",
    )
    baseline_relative_paths = _require_string_list(
        baseline_manifest.get("relative_paths"),
        "baseline_parent_manifest.json must define non-empty relative_paths",
    )
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

    candidate_relative_paths = _surface_relative_paths(candidate_root)
    if not candidate_relative_paths:
        raise ValueError("candidate_decomposition_surface must contain at least one file")

    files: list[dict[str, Any]] = []
    changed_relative_paths: list[str] = []
    added_relative_paths: list[str] = []
    for relative_path in candidate_relative_paths:
        surface_path = candidate_root / relative_path
        digest = _sha256_file(surface_path)
        baseline_entry = baseline_files.get(relative_path)
        changed_from_baseline = baseline_entry is None or digest != _require_text(
            baseline_entry.get("surface_sha256"),
            "baseline_parent_manifest.json file entries must define non-empty surface_sha256",
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
        "surface_kind": "candidate_decomposition",
        "selected_workflow_name": selected_workflow_name,
        "parent_package_name": boundary["parent_package_name"],
        "parent_package_root_relative_path": boundary["parent_package_root_relative_path"],
        "parent_doc_relative_path": boundary["parent_doc_relative_path"],
        "parent_runtime_test_relative_path": boundary["parent_runtime_test_relative_path"],
        "repo_root": _require_text(
            baseline_manifest.get("repo_root"),
            "baseline_parent_manifest.json must define non-empty repo_root",
        ),
        "surface_root": str(candidate_root),
        "baseline_relative_paths": baseline_relative_paths,
        "relative_paths": candidate_relative_paths,
        "file_count": len(candidate_relative_paths),
        "changed_relative_paths": changed_relative_paths,
        "added_relative_paths": added_relative_paths,
        "building_block_names": declared_building_blocks["building_block_names"],
        "building_block_package_roots": declared_building_blocks["allowed_package_roots"],
        "files": files,
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
    if _require_text(
        baseline_manifest.get("surface_kind"),
        "baseline_parent_manifest.json must define non-empty surface_kind",
    ) != "baseline_parent":
        raise ValueError("baseline_parent_manifest.json surface_kind must be baseline_parent")
    if _require_text(
        baseline_manifest.get("repo_root"),
        "baseline_parent_manifest.json must define non-empty repo_root",
    ) != str(repo_root):
        raise ValueError("baseline_parent_manifest.json repo_root must match the runtime repo root")
    if _require_text(
        baseline_manifest.get("parent_package_name"),
        "baseline_parent_manifest.json must define non-empty parent_package_name",
    ) != _require_text(boundary.get("parent_package_name"), "boundary must define parent_package_name"):
        raise ValueError("baseline_parent_manifest.json parent_package_name must match the decomposition surface")
    if _require_text(
        baseline_manifest.get("parent_package_root_relative_path"),
        "baseline_parent_manifest.json must define non-empty parent_package_root_relative_path",
    ) != _require_text(
        boundary.get("parent_package_root_relative_path"),
        "boundary must define parent_package_root_relative_path",
    ):
        raise ValueError(
            "baseline_parent_manifest.json parent_package_root_relative_path must match the decomposition surface"
        )
    if _normalize_optional_text(baseline_manifest.get("parent_doc_relative_path")) != _normalize_optional_text(
        boundary.get("parent_doc_relative_path")
    ):
        raise ValueError("baseline_parent_manifest.json parent_doc_relative_path must match the decomposition surface")
    if _normalize_optional_text(
        baseline_manifest.get("parent_runtime_test_relative_path")
    ) != _normalize_optional_text(boundary.get("parent_runtime_test_relative_path")):
        raise ValueError(
            "baseline_parent_manifest.json parent_runtime_test_relative_path must match the decomposition surface"
        )
    file_entries = _manifest_file_map(
        baseline_manifest,
        "baseline_parent_manifest.json must define files as a JSON array of objects with relative_path",
    )
    relative_paths = _require_string_list(
        baseline_manifest.get("relative_paths"),
        "baseline_parent_manifest.json must define non-empty relative_paths",
    )
    if sorted(file_entries) != relative_paths:
        raise ValueError("baseline_parent_manifest.json files must match relative_paths")
    if relative_paths != _require_string_list(
        boundary.get("baseline_relative_paths"),
        "boundary must define non-empty baseline_relative_paths",
    ):
        raise ValueError("baseline_parent_manifest.json relative_paths must match the decomposition surface")
    for relative_path, entry in file_entries.items():
        source_path = Path(
            _require_text(
                entry.get("source_path"),
                "baseline_parent_manifest.json file entries must define non-empty source_path",
            )
        )
        surface_path = Path(
            _require_text(
                entry.get("surface_path"),
                "baseline_parent_manifest.json file entries must define non-empty surface_path",
            )
        )
        if source_path != repo_root / relative_path:
            raise ValueError("baseline_parent_manifest.json source_path entries must stay aligned to the repo root")
        if not source_path.exists() or not surface_path.exists():
            raise FileNotFoundError("baseline_parent_manifest.json file entries must point at existing files")
        expected_digest = _require_text(
            entry.get("surface_sha256"),
            "baseline_parent_manifest.json file entries must define non-empty surface_sha256",
        )
        if _sha256_file(surface_path) != expected_digest:
            raise ValueError("baseline_parent_manifest.json surface_sha256 must match the copied baseline surface")


def _validate_authoritative_files_unchanged(baseline_manifest: Mapping[str, Any], repo_root: Path) -> None:
    for relative_path, entry in _manifest_file_map(
        baseline_manifest,
        "baseline_parent_manifest.json must define files as a JSON array of objects with relative_path",
    ).items():
        source_path = repo_root / relative_path
        if not source_path.exists():
            raise FileNotFoundError(f"authoritative selected workflow file is missing: {source_path}")
        current_digest = _sha256_file(source_path)
        expected_digest = _require_text(
            entry.get("authoritative_source_sha256"),
            "baseline_parent_manifest.json file entries must define non-empty authoritative_source_sha256",
        )
        if current_digest != expected_digest:
            raise ValueError(
                f"authoritative selected workflow file changed during decomposition publication: {relative_path}"
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
    if _require_text(
        candidate_manifest.get("surface_kind"),
        "candidate_decomposition_manifest.json must define non-empty surface_kind",
    ) != "candidate_decomposition":
        raise ValueError("candidate_decomposition_manifest.json surface_kind must be candidate_decomposition")
    if _require_text(
        candidate_manifest.get("repo_root"),
        "candidate_decomposition_manifest.json must define non-empty repo_root",
    ) != str(repo_root):
        raise ValueError("candidate_decomposition_manifest.json repo_root must match the runtime repo root")
    if _require_text(
        candidate_manifest.get("parent_package_name"),
        "candidate_decomposition_manifest.json must define non-empty parent_package_name",
    ) != _require_text(boundary.get("parent_package_name"), "boundary must define parent_package_name"):
        raise ValueError("candidate_decomposition_manifest.json parent_package_name must match the decomposition surface")
    if _require_text(
        candidate_manifest.get("parent_package_root_relative_path"),
        "candidate_decomposition_manifest.json must define non-empty parent_package_root_relative_path",
    ) != _require_text(
        boundary.get("parent_package_root_relative_path"),
        "boundary must define parent_package_root_relative_path",
    ):
        raise ValueError(
            "candidate_decomposition_manifest.json parent_package_root_relative_path must match the decomposition surface"
        )
    if _normalize_optional_text(candidate_manifest.get("parent_doc_relative_path")) != _normalize_optional_text(
        boundary.get("parent_doc_relative_path")
    ):
        raise ValueError("candidate_decomposition_manifest.json parent_doc_relative_path must match the decomposition surface")
    if _normalize_optional_text(
        candidate_manifest.get("parent_runtime_test_relative_path")
    ) != _normalize_optional_text(boundary.get("parent_runtime_test_relative_path")):
        raise ValueError(
            "candidate_decomposition_manifest.json parent_runtime_test_relative_path must match the decomposition surface"
        )

    baseline_relative_paths = _require_string_list(
        baseline_manifest.get("relative_paths"),
        "baseline_parent_manifest.json must define non-empty relative_paths",
    )
    candidate_baseline_relative_paths = _require_string_list(
        candidate_manifest.get("baseline_relative_paths"),
        "candidate_decomposition_manifest.json must define non-empty baseline_relative_paths",
    )
    if candidate_baseline_relative_paths != baseline_relative_paths:
        raise ValueError(
            "candidate_decomposition_manifest.json baseline_relative_paths must match baseline_parent_manifest.json"
        )

    candidate_root = Path(
        _require_text(
            candidate_manifest.get("surface_root"),
            "candidate_decomposition_manifest.json must define non-empty surface_root",
        )
    )
    actual_relative_paths = _surface_relative_paths(candidate_root)
    candidate_relative_paths = _require_string_list(
        candidate_manifest.get("relative_paths"),
        "candidate_decomposition_manifest.json must define non-empty relative_paths",
    )
    if candidate_relative_paths != actual_relative_paths:
        raise ValueError("candidate_decomposition_manifest.json relative_paths must match candidate_decomposition_surface")
    if _require_positive_int(
        candidate_manifest.get("file_count"),
        "candidate_decomposition_manifest.json must define positive integer file_count",
    ) != len(candidate_relative_paths):
        raise ValueError("candidate_decomposition_manifest.json file_count must match candidate_decomposition_surface")
    missing_baseline_paths = sorted(set(baseline_relative_paths) - set(candidate_relative_paths))
    if missing_baseline_paths:
        raise ValueError("candidate_decomposition_manifest.json must preserve every baseline relative_path")

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

    allowed_exact_paths = set(
        _require_string_list(
            declared_building_blocks.get("allowed_exact_paths"),
            "declared building blocks must define non-empty allowed_exact_paths",
            min_length=2,
        )
    )
    missing_declared_exact_paths = sorted(path for path in allowed_exact_paths if path not in candidate_relative_paths)
    if missing_declared_exact_paths:
        raise ValueError(
            "candidate_decomposition_manifest.json must include every declared building-block doc_relative_path and runtime_test_relative_path"
        )
    for relative_path in candidate_relative_paths:
        if relative_path in baseline_relative_paths:
            continue
        if any(relative_path.startswith(f"{package_root}/") for package_root in building_block_package_roots):
            continue
        if relative_path in allowed_exact_paths:
            continue
        raise ValueError("candidate_decomposition_manifest.json must stay within the allowed repo-relative boundary")

    file_entries = _manifest_file_map(
        candidate_manifest,
        "candidate_decomposition_manifest.json must define files as a JSON array of objects with relative_path",
    )
    if sorted(file_entries) != candidate_relative_paths:
        raise ValueError("candidate_decomposition_manifest.json files must match relative_paths")
    for relative_path, entry in file_entries.items():
        surface_path = Path(
            _require_text(
                entry.get("surface_path"),
                "candidate_decomposition_manifest.json file entries must define non-empty surface_path",
            )
        )
        if surface_path != candidate_root / relative_path:
            raise ValueError(
                "candidate_decomposition_manifest.json surface_path entries must stay under candidate_decomposition_surface"
            )
        if not surface_path.exists():
            raise FileNotFoundError(f"candidate surface file is missing: {surface_path}")
        expected_digest = _require_text(
            entry.get("surface_sha256"),
            "candidate_decomposition_manifest.json file entries must define non-empty surface_sha256",
        )
        if _sha256_file(surface_path) != expected_digest:
            raise ValueError("candidate_decomposition_manifest.json surface_sha256 must match candidate_decomposition_surface")


def _validate_candidate_overlay(
    *,
    repo_root: Path,
    selected_workflow_name: str,
    building_block_names: list[str],
    candidate_manifest: Mapping[str, Any],
    target_test_command: str,
) -> dict[str, Any]:
    candidate_root = Path(
        _require_text(
            candidate_manifest.get("surface_root"),
            "candidate_decomposition_manifest.json must define non-empty surface_root",
        )
    )
    command = _require_text(target_test_command, "target_test_command must stay non-empty")
    command_args = shlex.split(command)
    if command_args and command_args[0] == "pytest":
        command_args = [sys.executable, "-m", "pytest", *command_args[1:]]
    overlay_source_root = _resolve_overlay_source_root(repo_root)

    with tempfile.TemporaryDirectory(prefix="workflow_decomposition_overlay_") as tmp_dir:
        overlay_root = Path(tmp_dir) / overlay_source_root.name
        shutil.copytree(
            overlay_source_root,
            overlay_root,
            ignore=shutil.ignore_patterns(
                ".autoloop",
                ".git",
                ".pytest_cache",
                "__pycache__",
                "*.pyc",
                ".mypy_cache",
                ".ruff_cache",
                ".venv",
            ),
        )
        repo_venv = overlay_source_root / ".venv"
        overlay_venv = overlay_root / ".venv"
        if repo_venv.exists() and not overlay_venv.exists():
            overlay_venv.symlink_to(repo_venv, target_is_directory=True)

        for relative_path in _require_string_list(
            candidate_manifest.get("relative_paths"),
            "candidate_decomposition_manifest.json must define non-empty relative_paths",
        ):
            source_path = candidate_root / relative_path
            target_path = overlay_root / relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)

        compiled_workflow_names: list[str] = []
        with _preserved_workflow_modules():
            for workflow_name in [selected_workflow_name, *building_block_names]:
                resolved = resolve_workflow_reference(overlay_root, workflow_name)
                compiled = compile_workflow(resolved.workflow_cls)
                compiled_workflow_names.append(compiled.workflow_name)

        completed = subprocess.run(
            command_args,
            cwd=overlay_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise ValueError(
                "overlay validation command failed for candidate decomposition surface: "
                f"{command}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
            )
        return {
            "compiled_workflow_names": compiled_workflow_names,
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
    for entry in files:
        payload = _require_mapping(entry, error_message)
        relative_path = _require_text(payload.get("relative_path"), error_message)
        result[relative_path] = payload
    return result


def _surface_relative_paths(root: Path) -> list[str]:
    if not root.is_dir():
        raise FileNotFoundError(f"candidate decomposition surface is missing: {root}")
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())


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


def _optional_repo_relative_path(repo_root: Path, raw_value: Any, error_message: str) -> str | None:
    normalized = _normalize_optional_text(raw_value)
    if normalized is None:
        return None
    path = Path(normalized).resolve()
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise ValueError(error_message) from exc


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
