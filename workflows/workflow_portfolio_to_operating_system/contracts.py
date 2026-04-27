"""Workflow-local output contracts for the portfolio-governance workflow."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

try:  # pragma: no branch - supports both package and direct repo-root imports
    from autoloop_v3.stdlib import JsonArtifactSpec
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from stdlib import JsonArtifactSpec

from core import RouteInfo


PublicationBoundary = Literal["operating_system_publication_only"]
LifecyclePosture = Literal["keep", "refine", "decompose", "merge", "retire"]
PriorityLevel = Literal["P1", "P2", "P3"]


class LifecycleRecommendation(BaseModel):
    """One workflow-level lifecycle recommendation."""

    workflow_name: str = Field(min_length=1)
    lifecycle_posture: LifecyclePosture
    priority: PriorityLevel


class PortfolioGovernanceFramingPayload(BaseModel):
    """Verifier payload for the governance-framing step."""

    summary: str = Field(min_length=1)
    focus_workflows: list[str] = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    decision_axes: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class PortfolioOperatingModelPayload(BaseModel):
    """Verifier payload for the lifecycle-analysis step."""

    summary: str = Field(min_length=1)
    focus_workflows: list[str] = Field(min_length=1)
    analyzed_workflows: list[str] = Field(min_length=1)
    lifecycle_recommendations: list[LifecycleRecommendation] = Field(min_length=1)
    change_candidate_ids: list[str] = Field(min_length=1)
    replan_reason: str | None = None


class PortfolioOperatingSystemPayload(BaseModel):
    """Verifier payload for the terminal governance-package step."""

    summary: str = Field(min_length=1)
    focus_workflows: list[str] = Field(min_length=1)
    analyzed_workflows: list[str] = Field(min_length=1)
    change_candidate_ids: list[str] = Field(min_length=1)
    priority_workflows: list[str] = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    next_action: str = Field(min_length=1)
    publication_boundary: PublicationBoundary
    ready_for_publication: bool
    replan_reason: str | None = None


class PortfolioLifecycleRecommendationArtifactPayload(BaseModel):
    """Durable lifecycle recommendation record for portfolio_operating_summary.json."""

    workflow_name: str = Field(min_length=1)
    lifecycle_posture: str = Field(min_length=1)
    priority: str = Field(min_length=1)


class PortfolioOperatingSummaryArtifactPayload(BaseModel):
    """Typed contract for portfolio_operating_summary.json."""

    focus_workflows: list[str] = Field(min_length=1)
    analyzed_workflows: list[str] = Field(min_length=1)
    lifecycle_recommendations: list[PortfolioLifecycleRecommendationArtifactPayload] = Field(min_length=1)
    governance_posture_counts: dict[str, int]
    change_candidate_ids: list[str] = Field(min_length=1)
    priority_workflows: list[str] = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    next_action: str = Field(min_length=1)
    publication_boundary: str = Field(min_length=1)
    ready_for_publication: bool


PORTFOLIO_OPERATING_SUMMARY_ARTIFACT = JsonArtifactSpec(
    "portfolio_operating_summary.json",
    PortfolioOperatingSummaryArtifactPayload,
)


FRAME_PORTFOLIO_GOVERNANCE_ROUTE_CONTRACTS = {
    "portfolio_governance_framed": RouteInfo(
        summary="The sponsor, focus workflows, governance scope, and lifecycle decision criteria are explicit enough for portfolio operating-model analysis.",
        required_outputs=("portfolio_governance_brief", "portfolio_decision_criteria"),
        handoff="Locks the portfolio-governance framing so lifecycle analysis can proceed against an explicit scope and acceptance boundary.",
    ),
    "needs_rework": RouteInfo(
        summary="The same governance-framing boundary still holds, but the brief or criteria need local repair before lifecycle analysis can continue.",
        required_outputs=("portfolio_governance_brief", "portfolio_decision_criteria"),
        handoff="Keeps governance framing local and reruns the same step for stronger scope or criteria articulation only.",
    ),
    "needs_replan": RouteInfo(
        summary="The portfolio scope, sponsor pressure, or governance objective changed materially and framing must restart.",
        handoff="Routes back to governance framing because the current scope boundary is no longer authoritative.",
    ),
}

ANALYZE_PORTFOLIO_OPERATING_MODEL_ROUTE_CONTRACTS = {
    "portfolio_operating_model_analyzed": RouteInfo(
        summary="The lifecycle matrix, gap analysis, and change-candidate manifest assess the scoped workflow portfolio explicitly and are ready for governance packaging.",
        required_outputs=("workflow_lifecycle_matrix", "portfolio_gap_analysis", "portfolio_change_candidates"),
        handoff="Locks the analyzed workflow set, lifecycle postures, and change candidates so packaging can publish a governance recommendation without reinterpreting the evidence.",
    ),
    "needs_rework": RouteInfo(
        summary="The same lifecycle-analysis boundary still holds, but the matrix, gap analysis, or change-candidate manifest need local repair.",
        required_outputs=("workflow_lifecycle_matrix", "portfolio_gap_analysis", "portfolio_change_candidates"),
        handoff="Keeps portfolio lifecycle analysis local and reruns the same step for clearer evidence-backed recommendations only.",
    ),
    "needs_replan": RouteInfo(
        summary="Lifecycle analysis revealed that the focus set, governance criteria, or evidence boundary changed materially and framing must be revisited.",
        handoff="Routes back to framing because the current lifecycle-analysis scope is no longer credible.",
    ),
}

PACKAGE_PORTFOLIO_OPERATING_SYSTEM_ROUTE_CONTRACTS = {
    "portfolio_operating_system_ready": RouteInfo(
        summary="The governance package, machine-readable summary, and next-actions artifact are aligned and ready for deterministic publication.",
        required_outputs=(
            "workflow_portfolio_operating_system",
            "portfolio_operating_summary",
            "portfolio_next_actions",
        ),
        handoff="Advances the workflow to deterministic governance publication without hidden downstream execution.",
    ),
    "needs_rework": RouteInfo(
        summary="The same governance-packaging boundary still holds, but the package, summary, or next-actions artifact need local repair before publication.",
        required_outputs=(
            "workflow_portfolio_operating_system",
            "portfolio_operating_summary",
            "portfolio_next_actions",
        ),
        handoff="Keeps governance packaging local and reruns the same step for packaging corrections only.",
    ),
    "needs_replan": RouteInfo(
        summary="Packaging revealed that the lifecycle recommendations or change candidates changed materially and lifecycle analysis must be revisited.",
        handoff="Routes back to lifecycle analysis because the current governance package no longer matches the authoritative operating model.",
    ),
}


__all__ = [
    "ANALYZE_PORTFOLIO_OPERATING_MODEL_ROUTE_CONTRACTS",
    "FRAME_PORTFOLIO_GOVERNANCE_ROUTE_CONTRACTS",
    "LifecyclePosture",
    "LifecycleRecommendation",
    "PORTFOLIO_OPERATING_SUMMARY_ARTIFACT",
    "PACKAGE_PORTFOLIO_OPERATING_SYSTEM_ROUTE_CONTRACTS",
    "PortfolioGovernanceFramingPayload",
    "PortfolioLifecycleRecommendationArtifactPayload",
    "PortfolioOperatingModelPayload",
    "PortfolioOperatingSummaryArtifactPayload",
    "PortfolioOperatingSystemPayload",
    "PriorityLevel",
    "PublicationBoundary",
]
