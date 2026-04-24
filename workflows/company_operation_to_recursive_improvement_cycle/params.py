"""Workflow-specific parameter model for the company recursive-improvement workflow."""

from __future__ import annotations

try:
    from autoloop_v3.stdlib import deduped_string_list_fields, optional_text_fields, positive_int_fields, required_text_fields
except ImportError:  # pragma: no cover - direct repo execution fallback
    from stdlib import deduped_string_list_fields, optional_text_fields, positive_int_fields, required_text_fields

from pydantic import BaseModel, Field


class Parameters(BaseModel):
    """Invocation contract for ``company_operation_to_recursive_improvement_cycle``."""

    task_title: str
    sponsor_role: str | None = None
    desired_outcome: str | None = None
    decision_drivers: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    focus_tasks: list[str] = Field(default_factory=list)
    focus_workflows: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    max_tasks: int = 25
    max_runs_per_workflow: int = 10
    max_messages_per_task: int = 5

    _validate_task_title = required_text_fields("task_title")
    _normalize_optional_text = optional_text_fields("sponsor_role", "desired_outcome")
    _normalize_repeatable_strings = deduped_string_list_fields(
        "decision_drivers",
        "constraints",
        "focus_tasks",
        "focus_workflows",
        "statuses",
    )
    _validate_positive_ints = positive_int_fields(
        "max_tasks",
        "max_runs_per_workflow",
        "max_messages_per_task",
        error_message="must be a positive integer",
    )


__all__ = ["Parameters"]
