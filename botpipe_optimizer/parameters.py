"""Typed parameter bundles shared by labs workflows."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


def _strings(value) -> list[str]:
    if value is None:
        return []
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result


class TaskContextParameters(BaseModel):
    sponsor_role: str | None = None
    desired_outcome: str | None = None
    constraints: list[str] = Field(default_factory=list)

    @field_validator("sponsor_role", "desired_outcome", mode="before")
    @classmethod
    def normalize_optional(cls, value):
        return None if value is None or not str(value).strip() else str(value).strip()

    @field_validator("constraints", mode="before")
    @classmethod
    def normalize_constraints(cls, value):
        return _strings(value)


class TaskFramingParameters(TaskContextParameters):
    task_title: str = Field(min_length=1)


class TaskFramingWithEvidenceParameters(TaskFramingParameters):
    evidence_expectations: list[str] = Field(default_factory=list)

    @field_validator("evidence_expectations", mode="before")
    @classmethod
    def normalize_evidence(cls, value):
        return _strings(value)


class SelectedWorkflowTaskFramingParameters(TaskContextParameters):
    selected_workflow: str = Field(min_length=1)
    task_title: str = Field(min_length=1)


class SelectedWorkflowTaskFramingWithEvidenceParameters(
    SelectedWorkflowTaskFramingParameters
):
    evidence_expectations: list[str] = Field(default_factory=list)

    @field_validator("evidence_expectations", mode="before")
    @classmethod
    def normalize_evidence(cls, value):
        return _strings(value)


class PortfolioReviewParameters(TaskFramingParameters):
    decision_drivers: list[str] = Field(default_factory=list)

    @field_validator("decision_drivers", mode="before")
    @classmethod
    def normalize_drivers(cls, value):
        return _strings(value)


__all__ = [
    "PortfolioReviewParameters",
    "SelectedWorkflowTaskFramingParameters",
    "SelectedWorkflowTaskFramingWithEvidenceParameters",
    "TaskContextParameters",
    "TaskFramingParameters",
    "TaskFramingWithEvidenceParameters",
]
