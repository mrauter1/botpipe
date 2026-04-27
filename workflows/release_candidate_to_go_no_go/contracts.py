"""Workflow-local output contracts for the release go/no-go package."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from core import RouteInfo


class ReleaseFramingPayload(BaseModel):
    """Verifier payload for the framing step."""

    summary: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    evidence_focus: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class ReleaseEvidencePayload(BaseModel):
    """Verifier payload for the evidence assembly step."""

    summary: str = Field(min_length=1)
    evidence_artifacts: list[str] = Field(min_length=1)
    blocker_artifacts: list[str] = Field(default_factory=list)
    unresolved_gaps: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class ReleaseAssessmentPayload(BaseModel):
    """Verifier payload for the readiness assessment step."""

    summary: str = Field(min_length=1)
    evidence_artifacts: list[str] = Field(min_length=1)
    recommended_decision: Literal["go", "conditional_go", "no_go"] | None = None
    blocking_issue_count: int = Field(default=0, ge=0)
    replan_reason: str | None = None


class ReleaseDecisionPackagePayload(BaseModel):
    """Verifier payload for the final package assembly step."""

    summary: str = Field(min_length=1)
    package_artifacts: list[str] = Field(min_length=1)
    decision: Literal["go", "conditional_go", "no_go"] | None = None
    communication_ready: bool = False
    replan_reason: str | None = None


FRAME_RELEASE_ROUTE_CONTRACTS = {
    "release_framed": RouteInfo(
        summary="The release boundary, decision criteria, and evidence intake plan are explicit and authoritative.",
        required_outputs=("release_scope_brief", "decision_criteria", "evidence_intake_register"),
        handoff="Locks the release framing so evidence assembly can proceed against a fixed gate.",
    ),
    "needs_rework": RouteInfo(
        summary="The same release framing boundary holds, but the brief or criteria need local repair.",
        required_outputs=("release_scope_brief", "decision_criteria"),
        handoff="Keeps the framing boundary intact and reruns the same step for local correction.",
    ),
    "needs_replan": RouteInfo(
        summary="The release boundary, target outcome, or evidence intake surface changed materially and must be reframed.",
        handoff="Resets the release framing boundary before downstream evidence work continues.",
    ),
}

ASSEMBLE_EVIDENCE_ROUTE_CONTRACTS = {
    "evidence_pack_ready": RouteInfo(
        summary="The release evidence pack captures scope, test proof, operational readiness, rollback readiness, and blockers.",
        required_outputs=(
            "release_inventory",
            "test_evidence_pack",
            "operational_readiness",
            "rollback_readiness",
            "blocking_issues",
        ),
        handoff="Promotes the release evidence pack to readiness assessment.",
    ),
    "needs_rework": RouteInfo(
        summary="The same evidence assembly boundary holds, but the evidence pack or blocker analysis needs local repair.",
        required_outputs=("release_inventory", "test_evidence_pack", "blocking_issues"),
        handoff="Keeps evidence assembly local and reruns the same step for tighter proof collection.",
    ),
    "needs_replan": RouteInfo(
        summary="The evidence plan, release boundary, or decision gate changed materially and framing must be revisited.",
        handoff="Routes back to release framing because the evidence contract is no longer authoritative.",
    ),
}

ASSESS_GO_NO_GO_ROUTE_CONTRACTS = {
    "assessment_ready": RouteInfo(
        summary="The workflow has an explicit recommendation, ranked risks, and machine-readable decision summary.",
        required_outputs=("go_no_go_assessment", "risk_register", "decision_summary"),
        handoff="Promotes the assessed release candidate to final package assembly.",
    ),
    "needs_rework": RouteInfo(
        summary="The same assessment boundary holds, but the synthesis, risk ranking, or recommendation needs local repair.",
        required_outputs=("go_no_go_assessment", "risk_register", "decision_summary"),
        handoff="Keeps the readiness assessment local and reruns the same step with tighter synthesis.",
    ),
    "needs_replan": RouteInfo(
        summary="The evidence or decision surface changed materially enough that the release must be reframed before reassessment.",
        handoff="Returns the workflow to release framing because the current assessment contract is materially wrong.",
    ),
}

PREPARE_DECISION_PACKAGE_ROUTE_CONTRACTS = {
    "decision_package_ready": RouteInfo(
        summary="The final release decision package and stakeholder communication draft are complete and aligned to the assessment.",
        required_outputs=("release_decision_package", "release_communications_draft"),
        handoff="Advances the release workflow to deterministic publication of the terminal receipt.",
    ),
    "needs_rework": RouteInfo(
        summary="The same package assembly boundary holds, but the package or communications draft needs local repair.",
        required_outputs=("release_decision_package", "release_communications_draft"),
        handoff="Keeps package assembly local and reruns the same step for final polish.",
    ),
    "needs_replan": RouteInfo(
        summary="Package assembly proved the recommendation or evidence story changed materially and assessment must be revisited.",
        handoff="Routes back to readiness assessment because the package no longer matches the assessed recommendation.",
    ),
}


__all__ = [
    "ASSEMBLE_EVIDENCE_ROUTE_CONTRACTS",
    "ASSESS_GO_NO_GO_ROUTE_CONTRACTS",
    "FRAME_RELEASE_ROUTE_CONTRACTS",
    "PREPARE_DECISION_PACKAGE_ROUTE_CONTRACTS",
    "ReleaseAssessmentPayload",
    "ReleaseDecisionPackagePayload",
    "ReleaseEvidencePayload",
    "ReleaseFramingPayload",
]
