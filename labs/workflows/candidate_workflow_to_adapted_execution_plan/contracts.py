"""Typed domain result contracts for this durable labs workflow."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from labs.workflows._shared import LabPhaseOutcome


class AdaptationRequestFramingPayload(LabPhaseOutcome):
    """Verifier payload for the adaptation-request framing step."""

    summary: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    decision_axes: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class AdaptationSurfaceAnalysisPayload(LabPhaseOutcome):
    """Verifier payload for the adaptation-surface analysis step."""

    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    expected_downstream_artifacts: list[str] = Field(min_length=1)
    proposed_parameter_keys: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class AdaptedExecutionPlanPayload(LabPhaseOutcome):
    """Verifier payload for the terminal adapted-execution package step."""

    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    selected_workflow_entry_step: str = Field(min_length=1)
    selected_workflow_parameters_supported: bool
    proposed_parameter_keys: list[str]
    expected_downstream_artifacts: list[str] = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    next_action: str = Field(min_length=1)
    ready_for_execution: bool
    replan_reason: str | None = None


class ValidatedWorkflowParametersPayload(BaseModel):
    """Typed contract for validated_workflow_parameters.json."""

    repo_root: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    validated_parameters: dict[str, Any] = Field(default_factory=dict)
    workflow_name: str = Field(min_length=1)


class AdaptedExecutionSummaryPayload(BaseModel):
    """Typed contract for adapted_execution_summary.json."""

    selected_workflow_name: str = Field(min_length=1)
    selected_workflow_entry_step: str = Field(min_length=1)
    selected_workflow_parameters_supported: bool
    proposed_parameter_keys: list[str]
    expected_downstream_artifacts: list[str] = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    next_action: str = Field(min_length=1)
    ready_for_execution: bool


__all__ = [
    "AdaptationRequestFramingPayload",
    "AdaptationSurfaceAnalysisPayload",
    "AdaptedExecutionPlanPayload",
    "AdaptedExecutionSummaryPayload",
    "ValidatedWorkflowParametersPayload",
]
