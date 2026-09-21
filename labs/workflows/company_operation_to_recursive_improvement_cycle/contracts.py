"""Typed domain result contracts for this durable labs workflow."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from labs.workflows._shared import LabPhaseOutcome

PriorityLevel = Literal["P1", "P2", "P3"]
PriorityCategory = Literal[
    "workflow_portfolio",
    "workflow_package",
    "evaluation_follow_through",
    "refinement_follow_through",
    "decomposition_follow_through",
    "composition_or_escalation_policy",
    "operating_pattern",
]
PublicationBoundary = Literal["recursive_improvement_publication_only"]


class RecursiveImprovementPriority(BaseModel):
    """One ranked recursive-improvement item."""

    candidate_id: str = Field(min_length=1)
    category: PriorityCategory
    priority: PriorityLevel


class CompanyOperationFramingPayload(LabPhaseOutcome):
    """Verifier payload for the company-framing step."""

    summary: str = Field(min_length=1)
    focus_task_ids: list[str] = Field(min_length=1)
    focus_workflows: list[str] = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    decision_axes: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class RecursiveImprovementAnalysisPayload(LabPhaseOutcome):
    """Verifier payload for recursive-improvement pressure analysis."""

    summary: str = Field(min_length=1)
    focus_task_ids: list[str] = Field(min_length=1)
    focus_workflows: list[str] = Field(min_length=1)
    candidate_ids: list[str] = Field(min_length=1)
    priority_recommendations: list[RecursiveImprovementPriority] = Field(min_length=1)
    replan_reason: str | None = None


class RecursiveImprovementCyclePayload(LabPhaseOutcome):
    """Verifier payload for the terminal recursive-improvement package."""

    summary: str = Field(min_length=1)
    focus_task_ids: list[str] = Field(min_length=1)
    focus_workflows: list[str] = Field(min_length=1)
    candidate_ids: list[str] = Field(min_length=1)
    priority_item_ids: list[str] = Field(min_length=1)
    priority_categories: list[PriorityCategory] = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    next_action: str = Field(min_length=1)
    publication_boundary: PublicationBoundary
    ready_for_publication: bool
    replan_reason: str | None = None


class RecursiveImprovementSummaryArtifactPayload(BaseModel):
    """Typed contract for recursive_improvement_summary.json."""

    workflow_name: str = Field(min_length=1)
    focus_task_ids: list[str] = Field(min_length=1)
    focus_workflows: list[str] = Field(min_length=1)
    candidate_ids: list[str] = Field(min_length=1)
    priority_item_ids: list[str] = Field(min_length=1)
    priority_categories: list[str] = Field(min_length=1)
    priority_category_counts: dict[str, int]
    authoritative_artifacts: list[str] = Field(min_length=1)
    next_action: str = Field(min_length=1)
    publication_boundary: str = Field(min_length=1)
    ready_for_publication: bool


__all__ = [
    "CompanyOperationFramingPayload",
    "RecursiveImprovementAnalysisPayload",
    "RecursiveImprovementCyclePayload",
    "RecursiveImprovementPriority",
    "RecursiveImprovementSummaryArtifactPayload",
]
