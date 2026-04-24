"""Workflow-local output contracts for the adaptation-planning building block."""

from __future__ import annotations

from pydantic import BaseModel, Field

from workflow import RouteContract


class AdaptationRequestFramingPayload(BaseModel):
    """Verifier payload for the adaptation-request framing step."""

    summary: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    decision_axes: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class AdaptationSurfaceAnalysisPayload(BaseModel):
    """Verifier payload for the adaptation-surface analysis step."""

    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    expected_downstream_artifacts: list[str] = Field(min_length=1)
    proposed_parameter_keys: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class AdaptedExecutionPlanPayload(BaseModel):
    """Verifier payload for the terminal adapted-execution package step."""

    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    selected_workflow_entry_step: str = Field(min_length=1)
    selected_workflow_parameters_supported: bool
    proposed_parameter_keys: list[str]
    expected_downstream_artifacts: list[str] = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    next_action: str = Field(min_length=1)
    ready_for_execution: bool
    replan_reason: str | None = None


FRAME_ADAPTATION_REQUEST_ROUTE_CONTRACTS = {
    "adaptation_request_framed": RouteContract(
        summary="The selected workflow, task trigger, terminal outcome, and adaptation acceptance surface are explicit enough to analyze the chosen workflow without guesswork.",
        required_artifacts=("adaptation_request_brief", "adaptation_success_criteria"),
        work_item_effect="Locks the adaptation-request framing so fit, parameterization, and execution-surface analysis can proceed against an explicit contract.",
    ),
    "needs_rework": RouteContract(
        summary="The same framing boundary still holds, but the brief or success criteria need local repair before adaptation analysis can continue.",
        required_artifacts=("adaptation_request_brief", "adaptation_success_criteria"),
        work_item_effect="Keeps adaptation framing local and reruns the same step for clearer task and acceptance boundaries.",
    ),
    "needs_replan": RouteContract(
        summary="The task trigger, selected workflow, or execution boundary changed materially and the adaptation request must be reframed.",
        required_artifacts=("adaptation_request_brief", "adaptation_success_criteria"),
        work_item_effect="Returns the workflow to framing because the current adaptation boundary is no longer authoritative.",
    ),
}

ANALYZE_ADAPTATION_SURFACE_ROUTE_CONTRACTS = {
    "adaptation_surface_analyzed": RouteContract(
        summary="The fit assessment and step-adaptation matrix explain what stays fixed, what must be parameterized, and what execution risks remain before packaging.",
        required_artifacts=("workflow_fit_assessment", "step_adaptation_matrix"),
        work_item_effect="Locks the selected workflow's fit and adaptation surface so packaging can publish an execution-ready handoff.",
    ),
    "needs_rework": RouteContract(
        summary="The same analysis boundary holds, but the fit assessment or step-adaptation matrix needs local repair.",
        required_artifacts=("workflow_fit_assessment", "step_adaptation_matrix"),
        work_item_effect="Keeps adaptation analysis local and reruns the same step for stronger fit and parameterization evidence.",
    ),
    "needs_replan": RouteContract(
        summary="Analysis proved that the selected workflow, acceptance boundary, or execution shape changed materially and framing must be revisited.",
        required_artifacts=("adaptation_request_brief", "adaptation_success_criteria"),
        work_item_effect="Routes back to framing because the chosen workflow or acceptance boundary is no longer credible as stated.",
    ),
}

PACKAGE_ADAPTED_EXECUTION_PLAN_ROUTE_CONTRACTS = {
    "adapted_execution_plan_ready": RouteContract(
        summary="The terminal adapted-execution plan, proposed workflow-parameter artifact, machine-readable summary, and next-action artifact are complete and ready for deterministic publication.",
        required_artifacts=(
            "adapted_execution_plan",
            "proposed_workflow_parameters",
            "adapted_execution_summary",
            "adapted_execution_next_action",
        ),
        work_item_effect="Advances the building block to deterministic publication of the adapted plan, validated parameters, and receipt.",
    ),
    "needs_rework": RouteContract(
        summary="The same selected workflow and adaptation boundary still hold, but the package artifacts need local repair before publication.",
        required_artifacts=(
            "adapted_execution_plan",
            "proposed_workflow_parameters",
            "adapted_execution_summary",
            "adapted_execution_next_action",
        ),
        work_item_effect="Keeps packaging local and reruns the same step for summary, parameter, or next-action corrections only.",
    ),
    "needs_replan": RouteContract(
        summary="Packaging revealed that the selected workflow, adaptation boundary, or execution handoff changed materially and analysis must be revisited.",
        required_artifacts=("workflow_fit_assessment", "step_adaptation_matrix"),
        work_item_effect="Routes back to analysis because the current package no longer matches the authoritative adaptation surface.",
    ),
}


__all__ = [
    "ANALYZE_ADAPTATION_SURFACE_ROUTE_CONTRACTS",
    "AdaptationRequestFramingPayload",
    "AdaptationSurfaceAnalysisPayload",
    "AdaptedExecutionPlanPayload",
    "FRAME_ADAPTATION_REQUEST_ROUTE_CONTRACTS",
    "PACKAGE_ADAPTED_EXECUTION_PLAN_ROUTE_CONTRACTS",
]
