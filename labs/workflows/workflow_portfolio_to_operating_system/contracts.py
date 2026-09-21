"""Typed domain result contracts for this durable labs workflow."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from labs.workflows._shared import LabPhaseOutcome

PublicationBoundary = Literal["operating_system_publication_only"]
LifecyclePosture = Literal["keep", "refine", "decompose", "merge", "retire"]
PriorityLevel = Literal["P1", "P2", "P3"]


class LifecycleRecommendation(BaseModel):
    """One workflow-level lifecycle recommendation."""

    workflow_name: str = Field(min_length=1)
    lifecycle_posture: LifecyclePosture
    priority: PriorityLevel


class PortfolioGovernanceFramingPayload(LabPhaseOutcome):
    """Verifier payload for the governance-framing step."""

    summary: str = Field(min_length=1)
    focus_workflows: list[str] = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    decision_axes: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class PortfolioOperatingModelPayload(LabPhaseOutcome):
    """Verifier payload for the lifecycle-analysis step."""

    summary: str = Field(min_length=1)
    focus_workflows: list[str] = Field(min_length=1)
    analyzed_workflows: list[str] = Field(min_length=1)
    lifecycle_recommendations: list[LifecycleRecommendation] = Field(min_length=1)
    change_candidate_ids: list[str] = Field(min_length=1)
    replan_reason: str | None = None


class PortfolioOperatingSystemPayload(LabPhaseOutcome):
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
    lifecycle_recommendations: list[PortfolioLifecycleRecommendationArtifactPayload] = (
        Field(min_length=1)
    )
    governance_posture_counts: dict[str, int]
    change_candidate_ids: list[str] = Field(min_length=1)
    priority_workflows: list[str] = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    next_action: str = Field(min_length=1)
    publication_boundary: str = Field(min_length=1)
    ready_for_publication: bool


__all__ = [
    "LifecycleRecommendation",
    "PortfolioGovernanceFramingPayload",
    "PortfolioLifecycleRecommendationArtifactPayload",
    "PortfolioOperatingModelPayload",
    "PortfolioOperatingSummaryArtifactPayload",
    "PortfolioOperatingSystemPayload",
]
