"""Workflow-local output contracts for the task-to-candidate-workflow-set package."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from stdlib import JsonArtifactSpec

from autoloop import Route, SELF


PortfolioPosture = Literal["direct_fit", "compose_needed", "adapt_needed", "material_gap"]


class CandidateRequestFramingPayload(BaseModel):
    """Verifier payload for the candidate-request framing step."""

    summary: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    decision_axes: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class CandidateWorkflowAnalysisPayload(BaseModel):
    """Verifier payload for the candidate-workflow analysis step."""

    summary: str = Field(min_length=1)
    compared_workflows: list[str] = Field(min_length=1)
    ranked_candidates: list[str] = Field(min_length=1)
    portfolio_posture: PortfolioPosture
    builder_considered: bool = False
    replan_reason: str | None = None


class CandidateWorkflowSetPayload(BaseModel):
    """Verifier payload for the candidate-workflow-set packaging step."""

    summary: str = Field(min_length=1)
    comparison_candidates: list[str] = Field(min_length=1)
    ranked_candidates: list[str] = Field(min_length=1)
    recommended_candidate_workflows: list[str] = Field(min_length=1)
    builder_baseline_workflow: str = Field(min_length=1)
    builder_considered: bool = False
    portfolio_posture: PortfolioPosture
    authoritative_artifacts: list[str] = Field(min_length=1)
    next_action: str = Field(min_length=1)
    ready_for_strategy_selection: bool = False
    replan_reason: str | None = None


class CandidateWorkflowSetSummaryPayload(BaseModel):
    """Typed contract for candidate_workflow_set_summary.json."""

    comparison_candidates: list[str] = Field(min_length=1)
    ranked_candidates: list[str] = Field(min_length=1)
    recommended_candidate_workflows: list[str] = Field(min_length=1)
    builder_baseline_workflow: str = Field(min_length=1)
    builder_considered: bool = False
    portfolio_posture: PortfolioPosture
    authoritative_artifacts: list[str] = Field(min_length=1)
    next_action: str = Field(min_length=1)
    ready_for_strategy_selection: bool = False


CANDIDATE_WORKFLOW_SET_SUMMARY_ARTIFACT = JsonArtifactSpec(
    "candidate_workflow_set_summary.json",
    CandidateWorkflowSetSummaryPayload,
)


FRAME_CANDIDATE_REQUEST_ROUTE_CONTRACTS = {
    "candidate_request_framed": Route.to(
        "analyze_candidate_workflows",
        summary="The task trigger, sponsor, terminal outcome, and candidate-selection criteria are explicit enough to compare portfolio options without hidden assumptions.",
        required_writes=("candidate_request_brief", "candidate_selection_criteria"),
        handoff="Locks the candidate-request framing so capability-backed workflow comparison can proceed against an explicit problem and acceptance boundary.",
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The same framing boundary still holds, but the candidate-request brief or criteria need local repair before analysis can continue.",
        required_writes=("candidate_request_brief", "candidate_selection_criteria"),
        handoff="Keeps the candidate-request framing work item local and reruns the same step for stronger comparison criteria.",
    ),
    "needs_replan": Route.to(
        "frame_candidate_request",
        summary="The task trigger, sponsor, or terminal outcome changed materially and the candidate-request framing must restart before credible analysis can continue.",
        handoff="Resets the framing boundary before capability-backed workflow comparison continues.",
    ),
}

ANALYZE_CANDIDATE_WORKFLOWS_ROUTE_CONTRACTS = {
    "candidate_workflows_analyzed": Route.to(
        "package_candidate_workflow_set",
        summary="The workflow matrix, gap analysis, and portfolio-posture artifact compare the current portfolio explicitly and keep the builder baseline visible.",
        required_writes=("workflow_candidate_matrix", "workflow_gap_analysis", "candidate_route_posture"),
        handoff="Locks the ranked candidate set and fit-gap posture so packaging can produce a durable strategy-ready handoff.",
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The same analysis boundary holds, but the candidate comparison, fit-gap reasoning, or posture explanation needs local repair.",
        required_writes=("workflow_candidate_matrix", "workflow_gap_analysis", "candidate_route_posture"),
        handoff="Keeps candidate analysis local and reruns the same step for a clearer ranked candidate set.",
    ),
    "needs_replan": Route.to(
        "frame_candidate_request",
        summary="The task framing, legal comparison boundary, or portfolio posture changed materially and the candidate request must be reframed.",
        handoff="Routes back to framing because the current analysis boundary is no longer authoritative.",
    ),
}

PACKAGE_CANDIDATE_WORKFLOW_SET_ROUTE_CONTRACTS = {
    "candidate_workflow_set_ready": Route.to(
        "publish_candidate_workflow_set",
        summary="The terminal candidate-workflow-set package, machine-readable summary, and next-action artifact all exist and are ready for downstream strategy selection.",
        required_writes=("candidate_workflow_set", "candidate_workflow_set_summary", "candidate_next_action"),
        handoff="Advances the building block to deterministic publication of the candidate-workflow-set package and receipt.",
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The ranked candidate set still stands, but the package, summary, or next-action artifact needs local repair before publication.",
        required_writes=("candidate_workflow_set", "candidate_workflow_set_summary", "candidate_next_action"),
        handoff="Keeps candidate-set packaging local and reruns the same step for packaging corrections only.",
    ),
    "needs_replan": Route.to(
        "analyze_candidate_workflows",
        summary="Packaging revealed that the ranked candidates, portfolio posture, or downstream handoff contract changed materially and analysis must be revisited.",
        handoff="Routes back to analysis because the current package no longer matches the authoritative candidate set.",
    ),
}


__all__ = [
    "ANALYZE_CANDIDATE_WORKFLOWS_ROUTE_CONTRACTS",
    "CANDIDATE_WORKFLOW_SET_SUMMARY_ARTIFACT",
    "CandidateRequestFramingPayload",
    "CandidateWorkflowAnalysisPayload",
    "CandidateWorkflowSetPayload",
    "CandidateWorkflowSetSummaryPayload",
    "FRAME_CANDIDATE_REQUEST_ROUTE_CONTRACTS",
    "PACKAGE_CANDIDATE_WORKFLOW_SET_ROUTE_CONTRACTS",
    "PortfolioPosture",
]
