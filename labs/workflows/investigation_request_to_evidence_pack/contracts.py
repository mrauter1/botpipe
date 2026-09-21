"""Typed domain result contracts for this durable labs workflow."""

from __future__ import annotations

from pydantic import Field

from labs.workflows._shared import LabPhaseOutcome


class InvestigationFramingPayload(LabPhaseOutcome):
    """Verifier payload for the framing step."""

    summary: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    evidence_focus: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class InvestigationEvidencePackPayload(LabPhaseOutcome):
    """Verifier payload for the evidence-pack assembly step."""

    summary: str = Field(min_length=1)
    evidence_artifacts: list[str] = Field(min_length=1)
    source_count: int = Field(default=0, ge=0)
    unresolved_gaps: list[str] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    ready_for_downstream_assessment: bool = False
    replan_reason: str | None = None


__all__ = ["InvestigationEvidencePackPayload", "InvestigationFramingPayload"]
