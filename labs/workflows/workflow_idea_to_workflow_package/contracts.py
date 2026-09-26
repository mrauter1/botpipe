"""Typed semantic handoffs for the workflow-builder SOP."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from botpipe_optimizer.candidate_validation import ValidationResult
from labs.workflows._shared import LabPhaseOutcome, LabWorkflowResult


class GeneratedWorkflowFile(BaseModel):
    """One generated file, identified from runtime-validated bytes."""

    path: str
    sha256: str
    size_bytes: int


class WorkflowAuthorResult(LabWorkflowResult):
    """A reviewed candidate package and the checks that actually ran."""

    package_name: str
    candidate_root: str
    package_path: str
    workflow_reference: str
    files: list[GeneratedWorkflowFile]
    surface_boundary: dict[str, list[str]]
    validation: ValidationResult


class RequestFramingPayload(LabPhaseOutcome):
    """Accepted interpretation of the workflow the user asked to build."""

    summary: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    requested_workflow: str = Field(min_length=1)
    intended_outcome: str = Field(min_length=1)
    material_assumptions: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class WorkflowDesignPayload(LabPhaseOutcome):
    """Reviewed executable design and prompt handoff."""

    summary: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    step_names: list[str] = Field(min_length=1)
    prompt_files: list[str] = Field(default_factory=list)
    semantic_decisions: list[str] = Field(default_factory=list)
    unresolved_assumptions: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class WorkflowBuildPayload(LabPhaseOutcome):
    """Complete source manifest ready for isolated materialization."""

    summary: str = Field(min_length=1)
    changed_paths: list[str] = Field(min_length=1)
    evidence_artifacts: list[str] = Field(min_length=1)
    replan_reason: str | None = None


class WorkflowEvaluationPayload(LabPhaseOutcome):
    """Accepted assessment of source, executable checks, and handoffs."""

    summary: str = Field(min_length=1)
    evidence_artifacts: list[str] = Field(min_length=1)
    validation_commands: list[str] = Field(default_factory=list)
    package_decision: Literal["accept"]
    proven_outcomes: list[str] = Field(default_factory=list)
    unproven_outcomes: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


__all__ = [
    "GeneratedWorkflowFile",
    "RequestFramingPayload",
    "WorkflowAuthorResult",
    "WorkflowBuildPayload",
    "WorkflowDesignPayload",
    "WorkflowEvaluationPayload",
]
