"""Workflow-local output contracts for the refinement building block."""

from __future__ import annotations

from pydantic import BaseModel, Field

from autoloop import Route, SELF


class RefinementRequestFramingPayload(BaseModel):
    """Verifier payload for the refinement-request framing step."""

    summary: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    decision_axes: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class WorkflowRefinementPlanPayload(BaseModel):
    """Verifier payload for the refinement-plan design step."""

    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    planned_change_paths: list[str] = Field(min_length=1)
    verification_focus: list[str] = Field(min_length=1)
    replan_reason: str | None = None


class WorkflowRefinementBuildPayload(BaseModel):
    """Verifier payload for the candidate refinement build step."""

    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    candidate_file_count: int = Field(ge=1)
    changed_relative_paths: list[str] = Field(min_length=1)
    replan_reason: str | None = None


class WorkflowRefinementEvaluationPayload(BaseModel):
    """Verifier payload for the terminal refinement-evaluation step."""

    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    candidate_file_count: int = Field(ge=1)
    validated_overlay_command: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    next_action: str = Field(min_length=1)
    ready_for_publication: bool
    replan_reason: str | None = None


FRAME_REFINEMENT_REQUEST_ROUTE_CONTRACTS = {
    "refinement_request_framed": Route.to(
        "design_refinement_plan",
        summary="The selected workflow, baseline evidence, target refinement boundary, and acceptance surface are explicit enough for concrete change planning.",
        required_writes=("refinement_request_brief", "refinement_acceptance_criteria"),
        handoff="Locks the refinement boundary so the workflow can design a file-level change plan against explicit baseline evidence.",
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The same refinement-request framing boundary still holds, but the framing artifacts need local repair.",
        required_writes=("refinement_request_brief", "refinement_acceptance_criteria"),
        handoff="Keeps refinement framing local and reruns the same step for clearer boundaries and acceptance criteria.",
    ),
    "needs_replan": Route.to(
        SELF,
        summary="The selected workflow, evidence interpretation, or refinement boundary changed materially and the framing must restart.",
        handoff="Routes back to refinement framing because the current boundary is no longer authoritative.",
    ),
}

DESIGN_REFINEMENT_PLAN_ROUTE_CONTRACTS = {
    "refinement_plan_designed": Route.to(
        "implement_refined_workflow",
        summary="The refinement strategy, concrete workflow change plan, and regression guardrails are explicit enough for candidate implementation.",
        required_writes=("refinement_strategy", "workflow_change_plan", "regression_guardrails"),
        handoff="Locks the change plan so the selected workflow can be refined inside an explicit candidate surface.",
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The same refinement-planning boundary still holds, but the strategy, change plan, or regression guardrails need local repair.",
        required_writes=("refinement_strategy", "workflow_change_plan", "regression_guardrails"),
        handoff="Keeps refinement planning local and reruns the same step for clearer change and regression guidance.",
    ),
    "needs_replan": Route.to(
        "frame_refinement_request",
        summary="Planning proved the selected workflow, evidence boundary, or acceptance surface changed materially and framing must be revisited.",
        handoff="Routes back to framing because the current refinement plan is no longer credible as stated.",
    ),
}

IMPLEMENT_REFINED_WORKFLOW_ROUTE_CONTRACTS = {
    "workflow_refinement_applied": Route.to(
        "evaluate_refined_workflow",
        summary="The candidate workflow surface, build report, and diff summary are complete and ready for explicit evaluation against the baseline evidence.",
        required_writes=("candidate_workflow_surface", "refinement_build_report", "candidate_diff_summary"),
        handoff="Advances the workflow to candidate verification and promotion or rollback analysis.",
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The same candidate-implementation boundary still holds, but the candidate files or build artifacts need local repair.",
        required_writes=("candidate_workflow_surface", "refinement_build_report", "candidate_diff_summary"),
        handoff="Keeps candidate implementation local and reruns the same step for tighter workflow-surface changes.",
    ),
    "needs_replan": Route.to(
        "design_refinement_plan",
        summary="Implementation exposed a material change to the selected workflow boundary, artifact graph, or accepted plan and planning must be revisited.",
        handoff="Routes back to planning because the current candidate no longer fits the accepted refinement strategy.",
    ),
}

EVALUATE_REFINED_WORKFLOW_ROUTE_CONTRACTS = {
    "workflow_refinement_evaluated": Route.to(
        "publish_refined_workflow",
        summary="The refinement verification report, evaluation delta, promotion record, and rollback plan are complete and ready for deterministic publication of the candidate receipt.",
        required_writes=(
            "refinement_verification_report",
            "evaluation_delta_report",
            "promotion_record",
            "rollback_plan",
        ),
    ),
    "needs_rework": Route.to(
        "implement_refined_workflow",
        summary="The same selected workflow and accepted refinement boundary still hold, but the candidate package needs local repair before publication.",
        required_writes=(
            "refinement_verification_report",
            "evaluation_delta_report",
            "promotion_record",
            "rollback_plan",
        ),
        handoff="Routes back to implementation because the candidate still fits the same refinement boundary but needs local repair.",
    ),
    "needs_replan": Route.to(
        "design_refinement_plan",
        summary="Evaluation showed the accepted refinement boundary or change plan changed materially and planning must be revisited.",
        handoff="Routes back to planning because the evaluated candidate no longer matches the accepted refinement strategy.",
    ),
}


__all__ = [
    "DESIGN_REFINEMENT_PLAN_ROUTE_CONTRACTS",
    "EVALUATE_REFINED_WORKFLOW_ROUTE_CONTRACTS",
    "FRAME_REFINEMENT_REQUEST_ROUTE_CONTRACTS",
    "IMPLEMENT_REFINED_WORKFLOW_ROUTE_CONTRACTS",
    "RefinementRequestFramingPayload",
    "WorkflowRefinementBuildPayload",
    "WorkflowRefinementEvaluationPayload",
    "WorkflowRefinementPlanPayload",
]
