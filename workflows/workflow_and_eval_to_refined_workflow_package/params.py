"""Workflow-specific parameter model for the refinement building block."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class Parameters(BaseModel):
    """Invocation contract for ``workflow_and_eval_to_refined_workflow_package``."""

    selected_workflow: str
    task_title: str
    evaluation_summary_path: str
    evaluation_findings_path: str
    failure_modes_path: str | None = None
    sponsor_role: str | None = None
    desired_outcome: str | None = None
    constraints: list[str] = Field(default_factory=list)
    target_test_command: str = "pytest -q"

    @field_validator(
        "selected_workflow",
        "task_title",
        "evaluation_summary_path",
        "evaluation_findings_path",
        "target_test_command",
    )
    @classmethod
    def _validate_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must be non-empty")
        return normalized

    @field_validator("failure_modes_path", "sponsor_role", "desired_outcome")
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
