"""Typed domain result contracts for this durable labs workflow."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from labs.workflows._shared import LabPhaseOutcome

PublicationBoundary = Literal["diagnostic_publication_only"]


class DiagnosticScopePayload(LabPhaseOutcome):
    """Verifier payload for the diagnostic-scope framing step."""

    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    evidence_run_ids: list[str] = Field(min_length=1)
    diagnostic_axes: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class FailureModeMapPayload(LabPhaseOutcome):
    """Verifier payload for the failure-mode mapping step."""

    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    evidence_run_ids: list[str] = Field(min_length=1)
    failure_mode_ids: list[str] = Field(min_length=1)
    recurring_weak_point_ids: list[str] = Field(min_length=1)
    replan_reason: str | None = None


class ImprovementPressurePayload(LabPhaseOutcome):
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


__all__ = [
    "DiagnosticScopePayload",
    "FailureModeArtifactPayload",
    "FailureModeManifestArtifactPayload",
    "FailureModeMapPayload",
    "ImprovementOpportunitiesSummaryArtifactPayload",
    "ImprovementOpportunityArtifactPayload",
    "ImprovementPressurePayload",
]
