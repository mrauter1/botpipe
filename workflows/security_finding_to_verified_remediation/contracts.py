"""Workflow-local output contracts for the security remediation package."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from autoloop import Route, SELF


class SecurityAssessmentPayload(BaseModel):
    """Verifier payload for the security-assessment step."""

    summary: str = Field(min_length=1)
    assessment_artifacts: list[str] = Field(min_length=1)
    preferred_remediation_option: str | None = None
    exploitability: Literal["confirmed", "credible", "uncertain"] | None = None
    replan_reason: str | None = None


class VerifiedRemediationPayload(BaseModel):
    """Verifier payload for the remediation-planning step."""

    summary: str = Field(min_length=1)
    remediation_artifacts: list[str] = Field(min_length=1)
    selected_remediation: str | None = None
    verification_ready: bool = False
    rollout_ready: bool = False
    replan_reason: str | None = None


class SecurityClosurePackagePayload(BaseModel):
    """Verifier payload for the closure-package step."""

    summary: str = Field(min_length=1)
    package_artifacts: list[str] = Field(min_length=1)
    communication_ready: bool = False
    closure_ready: bool = False
    replan_reason: str | None = None


ASSESS_SECURITY_FINDING_ROUTE_CONTRACTS = {
    "finding_assessed": Route.to(
        "plan_verified_remediation",
        summary="The finding has an explicit exploit summary, affected-surface map, root-cause analysis, remediation options, and machine-readable assessment summary.",
        required_writes=(
            "exploit_summary",
            "affected_surface",
            "root_cause_analysis",
            "remediation_options",
            "assessment_summary",
        ),
        handoff="Locks the security assessment so remediation planning can proceed against an explicit exploit and evidence boundary.",
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The same assessment boundary still holds, but the exploit analysis, root-cause reasoning, or remediation options need local repair.",
        required_writes=(
            "exploit_summary",
            "affected_surface",
            "root_cause_analysis",
            "remediation_options",
            "assessment_summary",
        ),
        handoff="Keeps the security assessment local and reruns the same step for tighter exploit analysis and option comparison.",
    ),
    "needs_replan": Route.to(
        "compose_evidence_pack",
        summary="The evidence boundary, affected surface, or remediation framing changed materially and the evidence-pack stage must be revisited.",
    ),
}

PLAN_VERIFIED_REMEDIATION_ROUTE_CONTRACTS = {
    "remediation_planned": Route.to(
        "prepare_closure_package",
        summary="The workflow has a selected remediation plan, verification strategy, rollout guidance, rollback safety plan, and machine-readable remediation summary.",
        required_writes=(
            "selected_remediation_plan",
            "verification_plan",
            "rollout_plan",
            "rollback_safety_plan",
            "remediation_summary",
        ),
        handoff="Promotes the security finding from assessment into execution-ready remediation planning.",
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The same remediation-planning boundary holds, but the chosen remediation, verification plan, or rollout detail needs local repair.",
        required_writes=(
            "selected_remediation_plan",
            "verification_plan",
            "rollout_plan",
            "rollback_safety_plan",
            "remediation_summary",
        ),
        handoff="Keeps remediation planning local and reruns the same step for tighter implementation and verification planning.",
    ),
    "needs_replan": Route.to(
        "assess_security_finding",
        summary="The assessment conclusion or fix strategy changed materially enough that the security finding must be reassessed before planning continues.",
        handoff="Returns the workflow to the security-assessment step because the current remediation boundary is materially wrong.",
    ),
}

PREPARE_CLOSURE_PACKAGE_ROUTE_CONTRACTS = {
    "closure_package_ready": Route.to(
        "publish_remediation",
        summary="The final remediation package, stakeholder communication draft, and closure-evidence requirements are aligned to the selected remediation plan.",
        required_writes=(
            "security_remediation_package",
            "stakeholder_communication_draft",
            "closure_evidence_requirements",
        ),
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The same closure-packaging boundary holds, but the package, communication draft, or closure evidence contract needs local repair.",
        required_writes=(
            "security_remediation_package",
            "stakeholder_communication_draft",
            "closure_evidence_requirements",
        ),
        handoff="Keeps closure packaging local and reruns the same step for final packaging corrections.",
    ),
    "needs_replan": Route.to(
        "plan_verified_remediation",
        summary="Closure packaging revealed a material change in the remediation or verification story and planning must be revisited.",
        handoff="Routes back to remediation planning because the closure package no longer matches the planned fix and proof contract.",
    ),
}


__all__ = [
    "ASSESS_SECURITY_FINDING_ROUTE_CONTRACTS",
    "PLAN_VERIFIED_REMEDIATION_ROUTE_CONTRACTS",
    "PREPARE_CLOSURE_PACKAGE_ROUTE_CONTRACTS",
    "SecurityAssessmentPayload",
    "SecurityClosurePackagePayload",
    "VerifiedRemediationPayload",
]
