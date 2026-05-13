"""Workflow-local output contracts for the company recursive-improvement workflow."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from botpipe.stdlib import JsonArtifactSpec

from botpipe import Route, SELF


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


class CompanyOperationFramingPayload(BaseModel):
    """Verifier payload for the company-framing step."""

    summary: str = Field(min_length=1)
    focus_task_ids: list[str] = Field(min_length=1)
    focus_workflows: list[str] = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    decision_axes: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class RecursiveImprovementAnalysisPayload(BaseModel):
    """Verifier payload for recursive-improvement pressure analysis."""

    summary: str = Field(min_length=1)
    focus_task_ids: list[str] = Field(min_length=1)
    focus_workflows: list[str] = Field(min_length=1)
    candidate_ids: list[str] = Field(min_length=1)
    priority_recommendations: list[RecursiveImprovementPriority] = Field(min_length=1)
    replan_reason: str | None = None


class RecursiveImprovementCyclePayload(BaseModel):
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


RECURSIVE_IMPROVEMENT_SUMMARY_ARTIFACT = JsonArtifactSpec(
    "recursive_improvement_summary.json",
    RecursiveImprovementSummaryArtifactPayload,
)


FRAME_COMPANY_OPERATION_ROUTE_CONTRACTS = {
    "company_operation_framed": Route.to(
        "analyze_recursive_improvement_pressures",
        summary="The company scope, sponsor pressure, and recursive-improvement criteria are explicit enough for priority analysis.",
        required_writes=("company_operation_brief", "recursive_improvement_criteria"),
        handoff="Locks the company framing so recursive-improvement analysis can proceed against an explicit scope and acceptance surface.",
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The same framing boundary still holds, but the company brief or recursive-improvement criteria need local repair.",
        required_writes=("company_operation_brief", "recursive_improvement_criteria"),
        handoff="Keeps company framing local and reruns the same step for tighter scope or criteria articulation only.",
    ),
    "needs_replan": Route.to(
        SELF,
        summary="The company scope, sponsor pressure, or recursive-improvement objective changed materially and framing must restart.",
        handoff="Routes back to company framing because the current scope boundary is no longer authoritative.",
    ),
}

ANALYZE_RECURSIVE_IMPROVEMENT_ROUTE_CONTRACTS = {
    "recursive_improvement_pressures_analyzed": Route.to(
        "package_recursive_improvement_cycle",
        summary="The pressure map, priority matrix, and machine-readable candidate set rank the scoped recursive-improvement work explicitly and are ready for cycle packaging.",
        required_writes=(
            "company_pressure_map",
            "recursive_improvement_priority_matrix",
            "recursive_improvement_candidates",
        ),
        handoff="Locks the scoped pressure map, ranked candidate set, and priority categories so packaging can publish the cycle package without reinterpreting evidence.",
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The same recursive-improvement analysis boundary still holds, but the pressure map, priority matrix, or candidate manifest need local repair.",
        required_writes=(
            "company_pressure_map",
            "recursive_improvement_priority_matrix",
            "recursive_improvement_candidates",
        ),
        handoff="Keeps recursive-improvement analysis local and reruns the same step for clearer evidence-backed priorities only.",
    ),
    "needs_replan": Route.to(
        "frame_company_operation",
        summary="Pressure analysis showed that the company scope, task slice, or workflow slice changed materially and framing must be revisited.",
        handoff="Routes back to framing because the current recursive-improvement analysis scope is no longer credible.",
    ),
}

PACKAGE_RECURSIVE_IMPROVEMENT_CYCLE_ROUTE_CONTRACTS = {
    "recursive_improvement_cycle_ready": Route.to(
        "publish_recursive_improvement_cycle",
        summary="The recursive-improvement cycle package, machine-readable summary, and next-actions artifact are aligned and ready for deterministic publication.",
        required_writes=(
            "recursive_improvement_cycle",
            "recursive_improvement_summary",
            "recursive_improvement_next_actions",
        ),
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The same cycle-packaging boundary still holds, but the cycle package, summary, or next-actions artifact need local repair before publication.",
        required_writes=(
            "recursive_improvement_cycle",
            "recursive_improvement_summary",
            "recursive_improvement_next_actions",
        ),
        handoff="Keeps cycle packaging local and reruns the same step for packaging corrections only.",
    ),
    "needs_replan": Route.to(
        "analyze_recursive_improvement_pressures",
        summary="Packaging showed that the ranked improvement set or candidate categories changed materially and recursive-improvement analysis must be revisited.",
        handoff="Routes back to recursive-improvement analysis because the current cycle package no longer matches the authoritative pressure map.",
    ),
}


__all__ = [
    "ANALYZE_RECURSIVE_IMPROVEMENT_ROUTE_CONTRACTS",
    "CompanyOperationFramingPayload",
    "FRAME_COMPANY_OPERATION_ROUTE_CONTRACTS",
    "PACKAGE_RECURSIVE_IMPROVEMENT_CYCLE_ROUTE_CONTRACTS",
    "PriorityCategory",
    "PriorityLevel",
    "PublicationBoundary",
    "RecursiveImprovementAnalysisPayload",
    "RecursiveImprovementCyclePayload",
    "RecursiveImprovementPriority",
    "RECURSIVE_IMPROVEMENT_SUMMARY_ARTIFACT",
    "RecursiveImprovementSummaryArtifactPayload",
]
