"""Workflow-local output contracts for the run-history failure-mode building block."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

try:  # pragma: no branch - supports both package and direct repo-root imports
    from autoloop_v3.stdlib import JsonArtifactSpec
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from stdlib import JsonArtifactSpec

from autoloop import Route, SELF


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


class FailureModeArtifactPayload(BaseModel):
    """Durable failure-mode record for failure_mode_manifest.json."""

    failure_mode_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    severity: str = Field(min_length=1)
    evidence_run_ids: list[str] = Field(min_length=1)
    symptom_pattern: str = Field(min_length=1)
    likely_causes: list[str] = Field(min_length=1)
    supporting_signals: list[str] = Field(min_length=1)


class FailureModeManifestArtifactPayload(BaseModel):
    """Typed contract for failure_mode_manifest.json."""

    selected_workflow_name: str = Field(min_length=1)
    evidence_run_ids: list[str] = Field(min_length=1)
    failure_mode_ids: list[str] = Field(min_length=1)
    failure_modes: list[FailureModeArtifactPayload] = Field(min_length=1)
    recurring_weak_point_ids: list[str] = Field(min_length=1)
    workflow_name: str = Field(min_length=1)


class ImprovementOpportunityArtifactPayload(BaseModel):
    """Durable improvement-opportunity record for improvement_opportunities.json."""

    opportunity_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    priority: str = Field(min_length=1)
    linked_failure_mode_ids: list[str] = Field(min_length=1)
    recommended_next_step: str = Field(min_length=1)
    why_now: str = Field(min_length=1)
    expected_impact: str = Field(min_length=1)


class ImprovementOpportunitiesSummaryArtifactPayload(BaseModel):
    """Typed contract for improvement_opportunities.json."""

    selected_workflow_name: str = Field(min_length=1)
    evidence_run_ids: list[str] = Field(min_length=1)
    failure_mode_ids: list[str] = Field(min_length=1)
    ranked_opportunity_ids: list[str] = Field(min_length=1)
    opportunities: list[ImprovementOpportunityArtifactPayload] = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    next_action: str = Field(min_length=1)
    publication_boundary: str = Field(min_length=1)
    ready_for_publication: bool
    workflow_name: str = Field(min_length=1)


FAILURE_MODE_MANIFEST_ARTIFACT = JsonArtifactSpec(
    "failure_mode_manifest.json",
    FailureModeManifestArtifactPayload,
)
IMPROVEMENT_OPPORTUNITIES_SUMMARY_ARTIFACT = JsonArtifactSpec(
    "improvement_opportunities.json",
    ImprovementOpportunitiesSummaryArtifactPayload,
)


FRAME_DIAGNOSTIC_SCOPE_ROUTE_CONTRACTS = {
    "diagnostic_scope_framed": Route.to(
        "map_failure_modes",
        summary="The selected workflow, filtered run window, and diagnostic acceptance boundary are explicit enough for failure-mode clustering.",
        required_writes=("diagnostic_scope_brief", "run_history_scope"),
        handoff="Locks the diagnostic framing so failure-mode clustering can proceed against an explicit run-history boundary.",
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The same diagnostic framing boundary still holds, but the scope brief or run-history boundary needs local repair.",
        required_writes=("diagnostic_scope_brief", "run_history_scope"),
        handoff="Keeps diagnostic framing local and reruns the same step for stronger evidence scoping only.",
    ),
    "needs_replan": Route.to(
        "frame_diagnostic_scope",
        summary="The selected workflow, filtered history boundary, or diagnostic objective changed materially and framing must restart.",
        handoff="Routes back to diagnostic framing because the current evidence boundary is no longer authoritative.",
    ),
}

MAP_FAILURE_MODES_ROUTE_CONTRACTS = {
    "failure_modes_mapped": Route.to(
        "package_improvement_pressure",
        summary="The failure-mode map, machine-readable manifest, and recurring weak-points artifact cluster the selected workflow's history explicitly and are ready for improvement packaging.",
        required_writes=("failure_mode_map", "failure_mode_manifest", "recurring_weak_points"),
        handoff="Locks the failure clusters and recurring weak points so the workflow can rank improvement pressure without reinterpreting the run history.",
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The same failure-mode mapping boundary still holds, but the clusters, manifest, or weak-points artifact need local repair.",
        required_writes=("failure_mode_map", "failure_mode_manifest", "recurring_weak_points"),
        handoff="Keeps failure-mode mapping local and reruns the same step for clearer clustering or evidence linkage.",
    ),
    "needs_replan": Route.to(
        "frame_diagnostic_scope",
        summary="Failure-mode mapping revealed that the selected workflow boundary or evidence window changed materially and framing must be revisited.",
        handoff="Routes back to framing because the current failure clustering boundary is no longer credible.",
    ),
}

PACKAGE_IMPROVEMENT_PRESSURE_ROUTE_CONTRACTS = {
    "improvement_pressure_packaged": Route.to(
        "publish_failure_mode_package",
        summary="The ranked improvement package, machine-readable summary, and next-action artifact are aligned and ready for deterministic diagnostic publication.",
        required_writes=("improvement_opportunities", "improvement_opportunities_summary", "diagnostic_next_actions"),
        handoff="Advances the building block to deterministic publication of the diagnostic receipt without hidden downstream execution.",
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The same improvement-packaging boundary still holds, but the ranked package or next actions need local repair before publication.",
        required_writes=("improvement_opportunities", "improvement_opportunities_summary", "diagnostic_next_actions"),
        handoff="Keeps improvement packaging local and reruns the same step for packaging corrections only.",
    ),
    "needs_replan": Route.to(
        "map_failure_modes",
        summary="Packaging revealed that the mapped failure modes or recurring weak points changed materially and failure-mode mapping must be revisited.",
        handoff="Routes back to failure-mode mapping because the current ranked package no longer matches the authoritative diagnostic surface.",
    ),
}


__all__ = [
    "DiagnosticScopePayload",
    "FAILURE_MODE_MANIFEST_ARTIFACT",
    "FailureModeArtifactPayload",
    "FailureModeManifestArtifactPayload",
    "FailureModeMapPayload",
    "FRAME_DIAGNOSTIC_SCOPE_ROUTE_CONTRACTS",
    "IMPROVEMENT_OPPORTUNITIES_SUMMARY_ARTIFACT",
    "ImprovementOpportunitiesSummaryArtifactPayload",
    "ImprovementOpportunityArtifactPayload",
    "ImprovementPressurePayload",
    "MAP_FAILURE_MODES_ROUTE_CONTRACTS",
    "PACKAGE_IMPROVEMENT_PRESSURE_ROUTE_CONTRACTS",
    "PublicationBoundary",
]
