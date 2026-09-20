"""Typed domain result contracts for this durable labs workflow."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from labs.workflows._shared import LabPhaseOutcome


class ReleaseFramingPayload(LabPhaseOutcome):
    """Verifier payload for the framing step."""

    summary: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    evidence_focus: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class ReleaseEvidencePayload(LabPhaseOutcome):
    """Verifier payload for the evidence assembly step."""

    summary: str = Field(min_length=1)
    evidence_artifacts: list[str] = Field(min_length=1)
    blocker_artifacts: list[str] = Field(default_factory=list)
    unresolved_gaps: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class ReleaseAssessmentPayload(LabPhaseOutcome):
    """Verifier payload for the readiness assessment step."""

    summary: str = Field(min_length=1)
    evidence_artifacts: list[str] = Field(min_length=1)
    recommended_decision: Literal["go", "conditional_go", "no_go"] | None = None
    blocking_issue_count: int = Field(default=0, ge=0)
    replan_reason: str | None = None


class ReleaseDecisionPackagePayload(LabPhaseOutcome):
    """Verifier payload for the final package assembly step."""

    summary: str = Field(min_length=1)
    package_artifacts: list[str] = Field(min_length=1)
    decision: Literal["go", "conditional_go", "no_go"] | None = None
    communication_ready: bool = False
    replan_reason: str | None = None


__all__ = [
    "ReleaseAssessmentPayload",
    "ReleaseDecisionPackagePayload",
    "ReleaseEvidencePayload",
    "ReleaseFramingPayload",
]
