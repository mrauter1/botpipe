"""Workflow-specific parameter model for the portfolio-governance workflow."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class Parameters(BaseModel):
    """Invocation contract for ``workflow_portfolio_to_operating_system``."""

    task_title: str
    sponsor_role: str | None = None
    desired_outcome: str | None = None
    decision_drivers: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    focus_workflows: list[str] = Field(default_factory=list)
    max_runs_per_workflow: int = 10

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

    @field_validator("decision_drivers", "constraints", "focus_workflows")
    @classmethod
    def _normalize_repeatable_strings(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            candidate = value.strip()
            if candidate and candidate not in normalized:
                normalized.append(candidate)
        return normalized

    @field_validator("max_runs_per_workflow")
    @classmethod
    def _validate_max_runs_per_workflow(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("max_runs_per_workflow must be a positive integer")
        return value


__all__ = ["Parameters"]
