"""Workflow-local output contracts for the incident hardening package."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from workflow import RouteContract


class IncidentFramingPayload(BaseModel):
    """Verifier payload for the incident framing step."""

    summary: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    evidence_focus: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class IncidentEvidencePayload(BaseModel):
    """Verifier payload for the evidence assembly step."""

    summary: str = Field(min_length=1)
    evidence_artifacts: list[str] = Field(min_length=1)
    unresolved_gaps: list[str] = Field(default_factory=list)
    impacted_surfaces: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class IncidentHypothesisPayload(BaseModel):
    """Verifier payload for the incident analysis step."""

    summary: str = Field(min_length=1)
    analysis_artifacts: list[str] = Field(min_length=1)
    recommended_posture: Literal["urgent", "high", "planned"] | None = None
    primary_hypothesis: str | None = None
    replan_reason: str | None = None


class IncidentHardeningProgramPayload(BaseModel):
    """Verifier payload for the final hardening-package step."""

    summary: str = Field(min_length=1)
    package_artifacts: list[str] = Field(min_length=1)
    recommended_posture: Literal["urgent", "high", "planned"] | None = None
    owner_ready: bool = False
    replan_reason: str | None = None


FRAME_INCIDENT_ROUTE_CONTRACTS = {
    "incident_framed": RouteContract(
        summary="The incident boundary, response objectives, and evidence intake plan are explicit and authoritative.",
        required_artifacts=("incident_scope_brief", "response_objectives", "evidence_intake_register"),
        work_item_effect="Locks the incident framing so evidence assembly can proceed against a fixed scope and objective set.",
    ),
    "needs_rework": RouteContract(
        summary="The same incident framing boundary still holds, but the framing artifacts need local repair.",
        required_artifacts=("incident_scope_brief", "response_objectives"),
        work_item_effect="Keeps the incident framing boundary intact and reruns the same step for local correction.",
    ),
    "needs_replan": RouteContract(
        summary="The incident boundary, trigger, or response objective changed materially and framing must restart.",
        required_artifacts=("incident_scope_brief", "response_objectives", "evidence_intake_register"),
        work_item_effect="Resets the incident framing boundary before downstream evidence work continues.",
    ),
}

ASSEMBLE_EVIDENCE_ROUTE_CONTRACTS = {
    "evidence_pack_ready": RouteContract(
        summary="The incident evidence pack captures the timeline, affected surface, blast radius, observability gaps, and evidence gaps.",
        required_artifacts=(
            "incident_timeline",
            "affected_surface",
            "blast_radius",
            "observability_gaps",
            "evidence_gap_register",
        ),
        work_item_effect="Promotes the incident evidence pack to cause ranking and mitigation analysis.",
    ),
    "needs_rework": RouteContract(
        summary="The same evidence assembly boundary holds, but the pack or gap handling needs local repair.",
        required_artifacts=("incident_timeline", "blast_radius", "evidence_gap_register"),
        work_item_effect="Keeps evidence assembly local and reruns the same step for tighter proof collection.",
    ),
    "needs_replan": RouteContract(
        summary="The incident boundary or evidence plan changed materially enough that framing must be revisited.",
        required_artifacts=("incident_scope_brief", "response_objectives", "evidence_intake_register"),
        work_item_effect="Routes back to incident framing because the evidence contract is no longer authoritative.",
    ),
}

RANK_CAUSE_HYPOTHESES_ROUTE_CONTRACTS = {
    "hypotheses_ranked": RouteContract(
        summary="The workflow has a ranked hypothesis set, immediate mitigation guidance, validation logic, and machine-readable incident summary.",
        required_artifacts=(
            "cause_hypothesis_ranking",
            "immediate_mitigation_plan",
            "validation_plan",
            "incident_summary",
        ),
        work_item_effect="Promotes the incident analysis to hardening-program assembly.",
    ),
    "needs_rework": RouteContract(
        summary="The same analysis boundary holds, but the hypothesis ranking or mitigation logic needs local repair.",
        required_artifacts=("cause_hypothesis_ranking", "immediate_mitigation_plan", "incident_summary"),
        work_item_effect="Keeps the incident analysis local and reruns the same step with tighter synthesis.",
    ),
    "needs_replan": RouteContract(
        summary="Analysis proved that the incident boundary or evidence surface changed materially and framing must restart.",
        required_artifacts=("incident_scope_brief", "incident_timeline", "cause_hypothesis_ranking"),
        work_item_effect="Returns the workflow to incident framing because the current analysis contract is materially wrong.",
    ),
}

PREPARE_HARDENING_PROGRAM_ROUTE_CONTRACTS = {
    "hardening_program_ready": RouteContract(
        summary="The hardening program, backlog, owner map, communications draft, and final incident package are complete and aligned.",
        required_artifacts=(
            "hardening_program",
            "hardening_backlog",
            "follow_up_owners",
            "stakeholder_communications_draft",
            "incident_resolution_package",
        ),
        work_item_effect="Advances the incident workflow to deterministic publication of the terminal receipt.",
    ),
    "needs_rework": RouteContract(
        summary="The same hardening-package boundary holds, but the final package artifacts need local repair.",
        required_artifacts=("hardening_program", "hardening_backlog", "incident_resolution_package"),
        work_item_effect="Keeps package assembly local and reruns the same step for final polish.",
    ),
    "needs_replan": RouteContract(
        summary="Package assembly proved the analysis or package contract changed materially and analysis must be revisited.",
        required_artifacts=("cause_hypothesis_ranking", "incident_summary", "incident_resolution_package"),
        work_item_effect="Routes back to incident analysis because the final package no longer matches the assessed hardening posture.",
    ),
}


__all__ = [
    "ASSEMBLE_EVIDENCE_ROUTE_CONTRACTS",
    "FRAME_INCIDENT_ROUTE_CONTRACTS",
    "IncidentEvidencePayload",
    "IncidentFramingPayload",
    "IncidentHardeningProgramPayload",
    "IncidentHypothesisPayload",
    "PREPARE_HARDENING_PROGRAM_ROUTE_CONTRACTS",
    "RANK_CAUSE_HYPOTHESES_ROUTE_CONTRACTS",
]
