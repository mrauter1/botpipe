"""Workflow-specific parameter model for the portfolio-governance workflow."""

from __future__ import annotations

try:
    from autoloop_v3.stdlib import deduped_string_list_fields, optional_text_fields, positive_int_fields, required_text_fields
except ImportError:  # pragma: no cover - direct repo execution fallback
    from stdlib import deduped_string_list_fields, optional_text_fields, positive_int_fields, required_text_fields

from pydantic import BaseModel, Field


class Parameters(BaseModel):
    """Invocation contract for ``workflow_portfolio_to_operating_system``."""

    task_title: str
    sponsor_role: str | None = None
    desired_outcome: str | None = None
    decision_drivers: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    focus_workflows: list[str] = Field(default_factory=list)
    max_runs_per_workflow: int = 10

    _validate_task_title = required_text_fields("task_title")
    _normalize_optional_text = optional_text_fields("sponsor_role", "desired_outcome")
    _normalize_repeatable_strings = deduped_string_list_fields("decision_drivers", "constraints", "focus_workflows")
    _validate_max_runs_per_workflow = positive_int_fields(
        "max_runs_per_workflow",
        error_message="max_runs_per_workflow must be a positive integer",
    )


__all__ = ["Parameters"]
