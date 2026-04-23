"""Workflow-local output contracts for the release go/no-go package."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from workflow import RouteContract


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
    "release_framed": RouteContract(
        summary="The release boundary, decision criteria, and evidence intake plan are explicit and authoritative.",
        required_artifacts=("release_scope_brief", "decision_criteria", "evidence_intake_register"),
        work_item_effect="Locks the release framing so evidence assembly can proceed against a fixed gate.",
    ),
    "needs_rework": RouteContract(
        summary="The same release framing boundary holds, but the brief or criteria need local repair.",
        required_artifacts=("release_scope_brief", "decision_criteria"),
        work_item_effect="Keeps the framing boundary intact and reruns the same step for local correction.",
    ),
    "needs_replan": RouteContract(
        summary="The release boundary, target outcome, or evidence intake surface changed materially and must be reframed.",
        required_artifacts=("release_scope_brief", "decision_criteria", "evidence_intake_register"),
        work_item_effect="Resets the release framing boundary before downstream evidence work continues.",
    ),
}

ASSEMBLE_EVIDENCE_ROUTE_CONTRACTS = {
    "evidence_pack_ready": RouteContract(
        summary="The release evidence pack captures scope, test proof, operational readiness, rollback readiness, and blockers.",
        required_artifacts=(
            "release_inventory",
            "test_evidence_pack",
            "operational_readiness",
            "rollback_readiness",
            "blocking_issues",
        ),
        work_item_effect="Promotes the release evidence pack to readiness assessment.",
    ),
    "needs_rework": RouteContract(
        summary="The same evidence assembly boundary holds, but the evidence pack or blocker analysis needs local repair.",
        required_artifacts=("release_inventory", "test_evidence_pack", "blocking_issues"),
        work_item_effect="Keeps evidence assembly local and reruns the same step for tighter proof collection.",
    ),
    "needs_replan": RouteContract(
        summary="The evidence plan, release boundary, or decision gate changed materially and framing must be revisited.",
        required_artifacts=("release_scope_brief", "decision_criteria", "evidence_intake_register"),
        work_item_effect="Routes back to release framing because the evidence contract is no longer authoritative.",
    ),
}

ASSESS_GO_NO_GO_ROUTE_CONTRACTS = {
    "assessment_ready": RouteContract(
        summary="The workflow has an explicit recommendation, ranked risks, and machine-readable decision summary.",
        required_artifacts=("go_no_go_assessment", "risk_register", "decision_summary"),
        work_item_effect="Promotes the assessed release candidate to final package assembly.",
    ),
    "needs_rework": RouteContract(
        summary="The same assessment boundary holds, but the synthesis, risk ranking, or recommendation needs local repair.",
        required_artifacts=("go_no_go_assessment", "risk_register", "decision_summary"),
        work_item_effect="Keeps the readiness assessment local and reruns the same step with tighter synthesis.",
    ),
    "needs_replan": RouteContract(
        summary="The evidence or decision surface changed materially enough that the release must be reframed before reassessment.",
        required_artifacts=("decision_criteria", "blocking_issues", "go_no_go_assessment"),
        work_item_effect="Returns the workflow to release framing because the current assessment contract is materially wrong.",
    ),
}

PREPARE_DECISION_PACKAGE_ROUTE_CONTRACTS = {
    "decision_package_ready": RouteContract(
        summary="The final release decision package and stakeholder communication draft are complete and aligned to the assessment.",
        required_artifacts=("release_decision_package", "release_communications_draft"),
        work_item_effect="Advances the release workflow to deterministic publication of the terminal receipt.",
    ),
    "needs_rework": RouteContract(
        summary="The same package assembly boundary holds, but the package or communications draft needs local repair.",
        required_artifacts=("release_decision_package", "release_communications_draft"),
        work_item_effect="Keeps package assembly local and reruns the same step for final polish.",
    ),
    "needs_replan": RouteContract(
        summary="Package assembly proved the recommendation or evidence story changed materially and assessment must be revisited.",
        required_artifacts=("go_no_go_assessment", "decision_summary", "release_decision_package"),
        work_item_effect="Routes back to readiness assessment because the package no longer matches the assessed recommendation.",
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
