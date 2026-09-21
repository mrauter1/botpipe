"""Typed domain result contracts for this durable labs workflow."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from labs.workflows._shared import LabPhaseOutcome


class CandidateSelectionPayload(LabPhaseOutcome):
    """Verifier payload for the framing step."""

    summary: str = Field(min_length=1)
    evidence_artifacts: list[str] = Field(min_length=1)
    selected_candidate: str | None = None
    selected_kind: Literal["end_to_end", "building_block"] | None = None
    replan_reason: str | None = None


class WorkflowDesignPayload(LabPhaseOutcome):
    """Verifier payload for the design step."""

    summary: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    prompt_files: list[str] = Field(default_factory=list)
    next_action: str = Field(min_length=1)
    replan_reason: str | None = None


class WorkflowBuildPayload(LabPhaseOutcome):
    """Verifier payload for the build step."""

    summary: str = Field(min_length=1)
    changed_paths: list[str] = Field(min_length=1)
    evidence_artifacts: list[str] = Field(min_length=1)
    replan_reason: str | None = None


class WorkflowEvaluationPayload(LabPhaseOutcome):
    """Verifier payload for the evaluation step."""

    summary: str = Field(min_length=1)
    evidence_artifacts: list[str] = Field(min_length=1)
    validation_commands: list[str] = Field(default_factory=list)
    promotion_decision: Literal["promote", "rework", "replan"] | None = None
    replan_reason: str | None = None


__all__ = [
    "CandidateSelectionPayload",
    "WorkflowBuildPayload",
    "WorkflowDesignPayload",
    "WorkflowEvaluationPayload",
]
