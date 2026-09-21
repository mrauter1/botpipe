"""Typed domain result contracts for this durable labs workflow."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from labs.workflows._shared import LabPhaseOutcome


class SecurityAssessmentPayload(LabPhaseOutcome):
    """Verifier payload for the security-assessment step."""

    summary: str = Field(min_length=1)
    assessment_artifacts: list[str] = Field(min_length=1)
    preferred_remediation_option: str | None = None
    exploitability: Literal["confirmed", "credible", "uncertain"] | None = None
    replan_reason: str | None = None


class VerifiedRemediationPayload(LabPhaseOutcome):
    """Verifier payload for the remediation-planning step."""

    summary: str = Field(min_length=1)
    remediation_artifacts: list[str] = Field(min_length=1)
    selected_remediation: str | None = None
    verification_ready: bool = False
    rollout_ready: bool = False
    replan_reason: str | None = None


class SecurityClosurePackagePayload(LabPhaseOutcome):
    """Verifier payload for the closure-package step."""

    summary: str = Field(min_length=1)
    package_artifacts: list[str] = Field(min_length=1)
    communication_ready: bool = False
    closure_ready: bool = False
    replan_reason: str | None = None


__all__ = [
    "SecurityAssessmentPayload",
    "SecurityClosurePackagePayload",
    "VerifiedRemediationPayload",
]
