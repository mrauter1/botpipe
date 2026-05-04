"""Reusable workflow parameter-model bundles for optimizer-facing workflows."""

from __future__ import annotations

from pydantic import BaseModel, Field

from autoloop.stdlib.validation import deduped_string_list_fields, optional_text_fields, required_text_fields


class TaskContextParameters(BaseModel):
    """Shared task-framing fields reused across workflow families."""

    sponsor_role: str | None = None
    desired_outcome: str | None = None
    constraints: list[str] = Field(default_factory=list)

    _normalize_optional_text = optional_text_fields("sponsor_role", "desired_outcome")
    _normalize_constraints = deduped_string_list_fields("constraints")


class TaskFramingParameters(TaskContextParameters):
    """Shared task-framing bundle with one required task title."""

    task_title: str

    _validate_task_title = required_text_fields("task_title")


class TaskFramingWithEvidenceParameters(TaskFramingParameters):
    """Shared task-framing bundle plus evidence expectations."""

    evidence_expectations: list[str] = Field(default_factory=list)

    _normalize_evidence_expectations = deduped_string_list_fields("evidence_expectations")


class SelectedWorkflowTaskFramingParameters(TaskContextParameters):
    """Shared selected-workflow bundle used by adaptation-oriented workflows."""

    selected_workflow: str
    task_title: str

    _validate_required_text = required_text_fields(
        "selected_workflow",
        "task_title",
        error_message="value must be non-empty",
    )


class SelectedWorkflowTaskFramingWithEvidenceParameters(SelectedWorkflowTaskFramingParameters):
    """Shared selected-workflow bundle plus evidence expectations."""

    evidence_expectations: list[str] = Field(default_factory=list)

    _normalize_evidence_expectations = deduped_string_list_fields("evidence_expectations")


class PortfolioReviewParameters(TaskFramingParameters):
    """Shared portfolio-review bundle used by governance workflows."""

    decision_drivers: list[str] = Field(default_factory=list)

    _normalize_decision_drivers = deduped_string_list_fields("decision_drivers")


__all__ = [
    "PortfolioReviewParameters",
    "SelectedWorkflowTaskFramingParameters",
    "SelectedWorkflowTaskFramingWithEvidenceParameters",
    "TaskContextParameters",
    "TaskFramingParameters",
    "TaskFramingWithEvidenceParameters",
]
