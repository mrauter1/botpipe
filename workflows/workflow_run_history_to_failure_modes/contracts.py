"""Workflow-local output contracts for the run-history failure-mode building block."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from workflow import RouteContract


PublicationBoundary = Literal["diagnostic_publication_only"]


class DiagnosticScopePayload(BaseModel):
    """Verifier payload for the diagnostic-scope framing step."""

    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    evidence_run_ids: list[str] = Field(min_length=1)
    diagnostic_axes: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class FailureModeMapPayload(BaseModel):
    """Verifier payload for the failure-mode mapping step."""

    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    evidence_run_ids: list[str] = Field(min_length=1)
    failure_mode_ids: list[str] = Field(min_length=1)
    recurring_weak_point_ids: list[str] = Field(min_length=1)
    replan_reason: str | None = None


class ImprovementPressurePayload(BaseModel):
    """Verifier payload for the terminal improvement-packaging step."""

    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    evidence_run_ids: list[str] = Field(min_length=1)
    failure_mode_ids: list[str] = Field(min_length=1)
    ranked_opportunity_ids: list[str] = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    next_action: str = Field(min_length=1)
    publication_boundary: PublicationBoundary
    ready_for_publication: bool
    replan_reason: str | None = None


FRAME_DIAGNOSTIC_SCOPE_ROUTE_CONTRACTS = {
    "diagnostic_scope_framed": RouteContract(
        summary="The selected workflow, filtered run window, and diagnostic acceptance boundary are explicit enough for failure-mode clustering.",
        required_artifacts=("diagnostic_scope_brief", "run_history_scope"),
        work_item_effect="Locks the diagnostic framing so failure-mode clustering can proceed against an explicit run-history boundary.",
    ),
    "needs_rework": RouteContract(
        summary="The same diagnostic framing boundary still holds, but the scope brief or run-history boundary needs local repair.",
        required_artifacts=("diagnostic_scope_brief", "run_history_scope"),
        work_item_effect="Keeps diagnostic framing local and reruns the same step for stronger evidence scoping only.",
    ),
    "needs_replan": RouteContract(
        summary="The selected workflow, filtered history boundary, or diagnostic objective changed materially and framing must restart.",
        required_artifacts=("diagnostic_scope_brief", "run_history_scope"),
        work_item_effect="Routes back to diagnostic framing because the current evidence boundary is no longer authoritative.",
    ),
}

MAP_FAILURE_MODES_ROUTE_CONTRACTS = {
    "failure_modes_mapped": RouteContract(
        summary="The failure-mode map, machine-readable manifest, and recurring weak-points artifact cluster the selected workflow's history explicitly and are ready for improvement packaging.",
        required_artifacts=("failure_mode_map", "failure_mode_manifest", "recurring_weak_points"),
        work_item_effect="Locks the failure clusters and recurring weak points so the workflow can rank improvement pressure without reinterpreting the run history.",
    ),
    "needs_rework": RouteContract(
        summary="The same failure-mode mapping boundary still holds, but the clusters, manifest, or weak-points artifact need local repair.",
        required_artifacts=("failure_mode_map", "failure_mode_manifest", "recurring_weak_points"),
        work_item_effect="Keeps failure-mode mapping local and reruns the same step for clearer clustering or evidence linkage.",
    ),
    "needs_replan": RouteContract(
        summary="Failure-mode mapping revealed that the selected workflow boundary or evidence window changed materially and framing must be revisited.",
        required_artifacts=("diagnostic_scope_brief", "run_history_scope"),
        work_item_effect="Routes back to framing because the current failure clustering boundary is no longer credible.",
    ),
}

PACKAGE_IMPROVEMENT_PRESSURE_ROUTE_CONTRACTS = {
    "improvement_pressure_packaged": RouteContract(
        summary="The ranked improvement package, machine-readable summary, and next-action artifact are aligned and ready for deterministic diagnostic publication.",
        required_artifacts=("improvement_opportunities", "improvement_opportunities_summary", "diagnostic_next_actions"),
        work_item_effect="Advances the building block to deterministic publication of the diagnostic receipt without hidden downstream execution.",
    ),
    "needs_rework": RouteContract(
        summary="The same improvement-packaging boundary still holds, but the ranked package or next actions need local repair before publication.",
        required_artifacts=("improvement_opportunities", "improvement_opportunities_summary", "diagnostic_next_actions"),
        work_item_effect="Keeps improvement packaging local and reruns the same step for packaging corrections only.",
    ),
    "needs_replan": RouteContract(
        summary="Packaging revealed that the mapped failure modes or recurring weak points changed materially and failure-mode mapping must be revisited.",
        required_artifacts=("failure_mode_map", "failure_mode_manifest", "recurring_weak_points"),
        work_item_effect="Routes back to failure-mode mapping because the current ranked package no longer matches the authoritative diagnostic surface.",
    ),
}


__all__ = [
    "DiagnosticScopePayload",
    "FailureModeMapPayload",
    "FRAME_DIAGNOSTIC_SCOPE_ROUTE_CONTRACTS",
    "ImprovementPressurePayload",
    "MAP_FAILURE_MODES_ROUTE_CONTRACTS",
    "PACKAGE_IMPROVEMENT_PRESSURE_ROUTE_CONTRACTS",
    "PublicationBoundary",
]
