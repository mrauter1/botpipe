"""Typed domain result contracts for this durable labs workflow."""

from __future__ import annotations

from pydantic import Field

from labs.workflows._shared import LabPhaseOutcome


class DecompositionRequestFramingPayload(LabPhaseOutcome):
    """Verifier payload for the decomposition-request framing step."""

    summary: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    extraction_focus: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class DecompositionPlanPayload(LabPhaseOutcome):
    """Verifier payload for the decomposition-plan design step."""

    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    building_block_names: list[str] = Field(min_length=1)
    planned_change_paths: list[str] = Field(min_length=1)
    verification_focus: list[str] = Field(min_length=1)
    replan_reason: str | None = None


class CandidateDecompositionBuildPayload(LabPhaseOutcome):
    """Verifier payload for the candidate decomposition build step."""

    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    candidate_file_count: int = Field(ge=1)
    changed_relative_paths: list[str] = Field(min_length=1)
    building_block_names: list[str] = Field(min_length=1)
    replan_reason: str | None = None


class CandidateDecompositionEvaluationPayload(LabPhaseOutcome):
    """Verifier payload for the terminal decomposition evaluation step."""

    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    candidate_file_count: int = Field(ge=1)
    validated_overlay_command: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    building_block_names: list[str] = Field(min_length=1)
    next_action: str = Field(min_length=1)
    ready_for_publication: bool
    replan_reason: str | None = None


__all__ = [
    "CandidateDecompositionBuildPayload",
    "CandidateDecompositionEvaluationPayload",
    "DecompositionPlanPayload",
    "DecompositionRequestFramingPayload",
]
