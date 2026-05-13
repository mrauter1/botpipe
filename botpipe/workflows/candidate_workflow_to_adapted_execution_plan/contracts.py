"""Workflow-local contracts for the adaptation-planning building block."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from botpipe.stdlib import JsonArtifactSpec

from botpipe import AWAIT_INPUT, FAIL, Route, SELF


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


class ValidatedWorkflowParametersPayload(BaseModel):
    """Typed contract for validated_workflow_parameters.json."""

    repo_root: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    validated_parameters: dict[str, Any] = Field(default_factory=dict)
    workflow_name: str = Field(min_length=1)


class AdaptedExecutionSummaryPayload(BaseModel):
    """Typed contract for adapted_execution_summary.json."""

    selected_workflow_name: str = Field(min_length=1)
    selected_workflow_entry_step: str = Field(min_length=1)
    selected_workflow_parameters_supported: bool
    proposed_parameter_keys: list[str]
    expected_downstream_artifacts: list[str] = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    next_action: str = Field(min_length=1)
    ready_for_execution: bool


ADAPTED_EXECUTION_SUMMARY_ARTIFACT = JsonArtifactSpec(
    "adapted_execution_summary.json",
    AdaptedExecutionSummaryPayload,
)
VALIDATED_WORKFLOW_PARAMETERS_ARTIFACT = JsonArtifactSpec(
    "validated_workflow_parameters.json",
    ValidatedWorkflowParametersPayload,
)

_QUESTION_ROUTE = Route.to(AWAIT_INPUT, summary="Execution is awaiting user input.")
_BLOCKED_ROUTE = Route.to(
    AWAIT_INPUT,
    summary="The current adaptation work item is blocked pending missing context, evidence, or approval.",
)
_FAILED_ROUTE = Route.to(
    FAIL,
    summary="The current adaptation work item cannot continue because a required assumption, artifact, or validation failed.",
)


FRAME_ADAPTATION_REQUEST_ROUTE_CONTRACTS = {
    "adaptation_request_framed": Route.to(
        "analyze_adaptation_surface",
        summary="The selected workflow, task trigger, terminal outcome, and adaptation acceptance surface are explicit enough to analyze the chosen workflow without guesswork.",
        required_writes=("adaptation_request_brief", "adaptation_success_criteria"),
        handoff="Locks the adaptation-request framing so fit, parameterization, and execution-surface analysis can proceed against an explicit contract.",
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The same framing boundary still holds, but the brief or success criteria need local repair before adaptation analysis can continue.",
        required_writes=("adaptation_request_brief", "adaptation_success_criteria"),
        handoff="Keeps adaptation framing local and reruns the same step for clearer task and acceptance boundaries.",
    ),
    "needs_replan": Route.to(
        SELF,
        summary="The task trigger, selected workflow, or execution boundary changed materially and the adaptation request must be reframed.",
        handoff="Returns the workflow to framing because the current adaptation boundary is no longer authoritative.",
    ),
    "question": _QUESTION_ROUTE,
    "blocked": _BLOCKED_ROUTE,
    "failed": _FAILED_ROUTE,
}

ANALYZE_ADAPTATION_SURFACE_ROUTE_CONTRACTS = {
    "adaptation_surface_analyzed": Route.to(
        "package_adapted_execution_plan",
        summary="The fit assessment and step-adaptation matrix explain what stays fixed, what must be parameterized, and what execution risks remain before packaging.",
        required_writes=("workflow_fit_assessment", "step_adaptation_matrix"),
        handoff="Locks the selected workflow's fit and adaptation surface so packaging can publish an execution-ready handoff.",
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The same analysis boundary holds, but the fit assessment or step-adaptation matrix needs local repair.",
        required_writes=("workflow_fit_assessment", "step_adaptation_matrix"),
        handoff="Keeps adaptation analysis local and reruns the same step for stronger fit and parameterization evidence.",
    ),
    "needs_replan": Route.to(
        "frame_adaptation_request",
        summary="Analysis proved that the selected workflow, acceptance boundary, or execution shape changed materially and framing must be revisited.",
        handoff="Routes back to framing because the chosen workflow or acceptance boundary is no longer credible as stated.",
    ),
    "question": _QUESTION_ROUTE,
    "blocked": _BLOCKED_ROUTE,
    "failed": _FAILED_ROUTE,
}

PACKAGE_ADAPTED_EXECUTION_PLAN_ROUTE_CONTRACTS = {
    "adapted_execution_plan_ready": Route.to(
        "publish_adapted_execution_plan",
        summary="The terminal adapted-execution plan, proposed workflow-parameter artifact, machine-readable summary, and next-action artifact are complete and ready for deterministic publication.",
        required_writes=(
            "adapted_execution_plan",
            "proposed_workflow_parameters",
            "adapted_execution_summary",
            "adapted_execution_next_action",
        ),
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The same selected workflow and adaptation boundary still hold, but the package artifacts need local repair before publication.",
        required_writes=(
            "adapted_execution_plan",
            "proposed_workflow_parameters",
            "adapted_execution_summary",
            "adapted_execution_next_action",
        ),
        handoff="Keeps packaging local and reruns the same step for summary, parameter, or next-action corrections only.",
    ),
    "needs_replan": Route.to(
        "analyze_adaptation_surface",
        summary="Packaging revealed that the selected workflow, adaptation boundary, or execution handoff changed materially and analysis must be revisited.",
        handoff="Routes back to analysis because the current package no longer matches the authoritative adaptation surface.",
    ),
    "question": _QUESTION_ROUTE,
    "blocked": _BLOCKED_ROUTE,
    "failed": _FAILED_ROUTE,
}


__all__ = [
    "ADAPTED_EXECUTION_SUMMARY_ARTIFACT",
    "ANALYZE_ADAPTATION_SURFACE_ROUTE_CONTRACTS",
    "AdaptationRequestFramingPayload",
    "AdaptationSurfaceAnalysisPayload",
    "AdaptedExecutionPlanPayload",
    "AdaptedExecutionSummaryPayload",
    "FRAME_ADAPTATION_REQUEST_ROUTE_CONTRACTS",
    "PACKAGE_ADAPTED_EXECUTION_PLAN_ROUTE_CONTRACTS",
    "VALIDATED_WORKFLOW_PARAMETERS_ARTIFACT",
    "ValidatedWorkflowParametersPayload",
]
