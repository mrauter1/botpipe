"""Workflow-specific parameter model for the task-to-workflow-strategy package."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class Parameters(BaseModel):
    """Invocation contract for ``task_to_workflow_strategy``."""

    task_title: str
    sponsor_role: str | None = None
    desired_outcome: str | None = None
    constraints: list[str] = Field(default_factory=list)
    evidence_expectations: list[str] = Field(default_factory=list)

    @field_validator("task_title")
    @classmethod
    def _validate_task_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("task_title must be non-empty")
        return normalized

    @field_validator("sponsor_role", "desired_outcome")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("constraints", "evidence_expectations")
    @classmethod
    def _normalize_repeatable_strings(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            candidate = value.strip()
            if candidate and candidate not in normalized:
                normalized.append(candidate)
        return normalized


__all__ = ["Parameters"]
