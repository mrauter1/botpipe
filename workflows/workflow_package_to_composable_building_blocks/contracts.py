"""Workflow-local output contracts for the decomposition building block."""

from __future__ import annotations

from pydantic import BaseModel, Field

from autoloop import Route, SELF


class DecompositionRequestFramingPayload(BaseModel):
    """Verifier payload for the decomposition-request framing step."""

    summary: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    extraction_focus: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class DecompositionPlanPayload(BaseModel):
    """Verifier payload for the decomposition-plan design step."""

    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    building_block_names: list[str] = Field(min_length=1)
    planned_change_paths: list[str] = Field(min_length=1)
    verification_focus: list[str] = Field(min_length=1)
    replan_reason: str | None = None


class CandidateDecompositionBuildPayload(BaseModel):
    """Verifier payload for the candidate decomposition build step."""

    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    candidate_file_count: int = Field(ge=1)
    changed_relative_paths: list[str] = Field(min_length=1)
    building_block_names: list[str] = Field(min_length=1)
    replan_reason: str | None = None


class CandidateDecompositionEvaluationPayload(BaseModel):
    """Verifier payload for the terminal decomposition evaluation step."""

    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    candidate_file_count: int = Field(ge=1)
    validated_overlay_command: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    building_block_names: list[str] = Field(min_length=1)
    next_action: str = Field(min_length=1)
    ready_for_publication: bool
    replan_reason: str | None = None


FRAME_DECOMPOSITION_REQUEST_ROUTE_CONTRACTS = {
    "decomposition_request_framed": Route.to(
        "design_decomposition_plan",
        summary="The selected workflow, decomposition trigger, evidence boundary, and acceptance surface are explicit enough for concrete extraction planning.",
        required_writes=("decomposition_request_brief", "decomposition_acceptance_criteria"),
        handoff="Locks the decomposition boundary so the workflow can design explicit building-block extraction and parent-rewrite contracts.",
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The same decomposition-request framing boundary still holds, but the framing artifacts need local repair.",
        required_writes=("decomposition_request_brief", "decomposition_acceptance_criteria"),
        handoff="Keeps decomposition framing local and reruns the same step for clearer extraction goals and acceptance criteria.",
    ),
    "needs_replan": Route.to(
        SELF,
        summary="The selected workflow, evidence interpretation, or decomposition boundary changed materially and framing must restart.",
        handoff="Routes back to decomposition framing because the current boundary is no longer authoritative.",
    ),
}

DESIGN_DECOMPOSITION_PLAN_ROUTE_CONTRACTS = {
    "decomposition_plan_designed": Route.to(
        "implement_candidate_decomposition",
        summary="The extraction strategy, interface contracts, parent rewrite plan, and regression guardrails are explicit enough for candidate implementation.",
        required_writes=(
            "extraction_strategy",
            "building_block_interface_contracts",
            "parent_rewrite_plan",
            "regression_guardrails",
        ),
        handoff="Locks the decomposition plan so the workflow can publish a candidate overlay against an explicit extraction boundary.",
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The same decomposition-planning boundary still holds, but the extraction strategy or interface contracts need local repair.",
        required_writes=(
            "extraction_strategy",
            "building_block_interface_contracts",
            "parent_rewrite_plan",
            "regression_guardrails",
        ),
        handoff="Keeps decomposition planning local and reruns the same step for tighter extraction and migration guidance.",
    ),
    "needs_replan": Route.to(
        "frame_decomposition_request",
        summary="Planning proved that the selected workflow, package boundary, or acceptance surface changed materially and framing must be revisited.",
        handoff="Routes back to framing because the current extraction plan no longer fits the accepted decomposition request.",
    ),
}

IMPLEMENT_CANDIDATE_DECOMPOSITION_ROUTE_CONTRACTS = {
    "candidate_decomposition_built": Route.to(
        "evaluate_candidate_decomposition",
        summary="The candidate decomposition surface, building-block index, and build artifacts are complete and ready for explicit evaluation.",
        required_writes=(
            "candidate_decomposition_surface",
            "candidate_building_block_index",
            "decomposition_build_report",
            "candidate_diff_summary",
        ),
        handoff="Advances the workflow to candidate verification, migration guidance, and publication readiness checks.",
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The same candidate-decomposition boundary still holds, but the candidate files or build artifacts need local repair.",
        required_writes=(
            "candidate_decomposition_surface",
            "candidate_building_block_index",
            "decomposition_build_report",
            "candidate_diff_summary",
        ),
        handoff="Keeps candidate implementation local and reruns the same step for clearer parent and building-block package changes.",
    ),
    "needs_replan": Route.to(
        "design_decomposition_plan",
        summary="Implementation exposed a material change to the selected workflow boundary, declared building-block set, or accepted plan and planning must be revisited.",
        handoff="Routes back to planning because the current candidate no longer fits the accepted decomposition strategy.",
    ),
}

EVALUATE_CANDIDATE_DECOMPOSITION_ROUTE_CONTRACTS = {
    "candidate_decomposition_evaluated": Route.to(
        "publish_candidate_decomposition",
        summary="The decomposition verification report, migration guide, promotion record, and rollback plan are complete and ready for deterministic publication of the candidate receipt.",
        required_writes=(
            "decomposition_verification_report",
            "composition_migration_guide",
            "promotion_record",
            "rollback_plan",
        ),
    ),
    "needs_rework": Route.to(
        "implement_candidate_decomposition",
        summary="The same decomposition boundary still holds, but the candidate package needs local repair before publication.",
        required_writes=(
            "decomposition_verification_report",
            "composition_migration_guide",
            "promotion_record",
            "rollback_plan",
        ),
        handoff="Routes back to implementation because the candidate still fits the same decomposition boundary but needs local repair.",
    ),
    "needs_replan": Route.to(
        "design_decomposition_plan",
        summary="Evaluation showed that the accepted decomposition boundary or building-block set changed materially and planning must be revisited.",
        handoff="Routes back to planning because the evaluated candidate no longer matches the accepted extraction strategy.",
    ),
}


__all__ = [
    "CandidateDecompositionBuildPayload",
    "CandidateDecompositionEvaluationPayload",
    "DecompositionPlanPayload",
    "DecompositionRequestFramingPayload",
    "DESIGN_DECOMPOSITION_PLAN_ROUTE_CONTRACTS",
    "EVALUATE_CANDIDATE_DECOMPOSITION_ROUTE_CONTRACTS",
    "FRAME_DECOMPOSITION_REQUEST_ROUTE_CONTRACTS",
    "IMPLEMENT_CANDIDATE_DECOMPOSITION_ROUTE_CONTRACTS",
]
