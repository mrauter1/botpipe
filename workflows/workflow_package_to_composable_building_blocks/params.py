"""Workflow-specific parameter model for the decomposition building block."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class Parameters(BaseModel):
    """Invocation contract for ``workflow_package_to_composable_building_blocks``."""

    selected_workflow: str
    task_title: str
    evidence_paths: list[str] = Field(default_factory=list)
    sponsor_role: str | None = None
    desired_outcome: str | None = None
    constraints: list[str] = Field(default_factory=list)
    target_test_command: str = "pytest -q"
    max_candidate_building_blocks: int = Field(default=3, ge=1)

    @field_validator("selected_workflow", "task_title", "target_test_command")
    @classmethod
    def _validate_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must be non-empty")
        return normalized

    @field_validator("sponsor_role", "desired_outcome")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("evidence_paths", "constraints")
    @classmethod
    def _normalize_repeatable_strings(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            candidate = value.strip()
            if candidate and candidate not in normalized:
                normalized.append(candidate)
        return normalized


__all__ = ["Parameters"]
