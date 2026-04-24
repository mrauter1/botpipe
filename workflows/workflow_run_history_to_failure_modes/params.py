"""Workflow-specific parameter model for the failure-mode diagnostics building block."""

from __future__ import annotations

try:
    from autoloop_v3.stdlib import deduped_string_list_fields, optional_text_fields, positive_int_fields, required_text_fields
except ImportError:  # pragma: no cover - direct repo execution fallback
    from stdlib import deduped_string_list_fields, optional_text_fields, positive_int_fields, required_text_fields

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

    _validate_required_text = required_text_fields(
        "selected_workflow",
        "task_title",
        error_message="value must be non-empty",
    )

    @field_validator("statuses")
    @classmethod
    def _normalize_status_filters(cls, values: list[str]) -> list[str]:
        normalized: set[str] = set()
        for value in values:
            candidate = value.strip()
            if candidate:
                normalized.add(candidate)
        return sorted(normalized)

    _validate_max_runs = positive_int_fields("max_runs", error_message="max_runs must be a positive integer")
    _normalize_optional_text = optional_text_fields("sponsor_role", "desired_outcome")
    _normalize_repeatable_strings = deduped_string_list_fields("constraints")


__all__ = ["Parameters"]
