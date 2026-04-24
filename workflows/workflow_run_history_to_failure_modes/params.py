"""Workflow-specific parameter model for the failure-mode diagnostics building block."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class Parameters(BaseModel):
    """Invocation contract for ``workflow_run_history_to_failure_modes``."""

    selected_workflow: str
    task_title: str
    statuses: list[str] = Field(default_factory=list)
    max_runs: int = 25
    sponsor_role: str | None = None
    desired_outcome: str | None = None
    constraints: list[str] = Field(default_factory=list)

    @field_validator("selected_workflow", "task_title")
    @classmethod
    def _validate_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must be non-empty")
        return normalized

    @field_validator("statuses")
    @classmethod
    def _normalize_status_filters(cls, values: list[str]) -> list[str]:
        normalized: set[str] = set()
        for value in values:
            candidate = value.strip()
            if candidate:
                normalized.add(candidate)
        return sorted(normalized)

    @field_validator("max_runs")
    @classmethod
    def _validate_max_runs(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("max_runs must be a positive integer")
        return value

    @field_validator("sponsor_role", "desired_outcome")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("constraints")
    @classmethod
    def _normalize_repeatable_strings(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            candidate = value.strip()
            if candidate and candidate not in normalized:
                normalized.append(candidate)
        return normalized


__all__ = ["Parameters"]
