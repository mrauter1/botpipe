"""Typed domain result contracts for this durable labs workflow."""

from __future__ import annotations

from pydantic import Field

from labs.workflows._shared import LabPhaseOutcome


class RefinementRequestFramingPayload(LabPhaseOutcome):
    """Verifier payload for the refinement-request framing step."""

    summary: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    decision_axes: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class WorkflowRefinementPlanPayload(LabPhaseOutcome):
    """Verifier payload for the refinement-plan design step."""

    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    planned_change_paths: list[str] = Field(min_length=1)
    verification_focus: list[str] = Field(min_length=1)
    replan_reason: str | None = None


class WorkflowRefinementBuildPayload(LabPhaseOutcome):
    """Verifier payload for the candidate refinement build step."""

    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    candidate_file_count: int = Field(ge=1)
    changed_relative_paths: list[str] = Field(min_length=1)
    replan_reason: str | None = None


class WorkflowRefinementEvaluationPayload(LabPhaseOutcome):
    """Verifier payload for the terminal refinement-evaluation step."""

    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    candidate_file_count: int = Field(ge=1)
    validated_overlay_command: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    next_action: str = Field(min_length=1)
    ready_for_publication: bool
    replan_reason: str | None = None


__all__ = [
    "RefinementRequestFramingPayload",
    "WorkflowRefinementBuildPayload",
    "WorkflowRefinementEvaluationPayload",
    "WorkflowRefinementPlanPayload",
]
