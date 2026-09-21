"""Typed domain result contracts for this durable labs workflow."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from labs.workflows._shared import LabPhaseOutcome


class IncidentFramingPayload(LabPhaseOutcome):
    """Verifier payload for the incident framing step."""

    summary: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    evidence_focus: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class IncidentEvidencePayload(LabPhaseOutcome):
    """Verifier payload for the evidence assembly step."""

    summary: str = Field(min_length=1)
    evidence_artifacts: list[str] = Field(min_length=1)
    unresolved_gaps: list[str] = Field(default_factory=list)
    impacted_surfaces: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class IncidentHypothesisPayload(LabPhaseOutcome):
    """Verifier payload for the incident analysis step."""

    summary: str = Field(min_length=1)
    analysis_artifacts: list[str] = Field(min_length=1)
    recommended_posture: Literal["urgent", "high", "planned"] | None = None
    primary_hypothesis: str | None = None
    replan_reason: str | None = None


class IncidentHardeningProgramPayload(LabPhaseOutcome):
    """Verifier payload for the final hardening-package step."""

    summary: str = Field(min_length=1)
    package_artifacts: list[str] = Field(min_length=1)
    recommended_posture: Literal["urgent", "high", "planned"] | None = None
    owner_ready: bool = False
    replan_reason: str | None = None


__all__ = [
    "IncidentEvidencePayload",
    "IncidentFramingPayload",
    "IncidentHardeningProgramPayload",
    "IncidentHypothesisPayload",
]
