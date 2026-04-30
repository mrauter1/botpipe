"""Workflow-specific parameter model for the company recursive-improvement workflow."""

from __future__ import annotations

from autoloop_optimizer import PortfolioReviewParameters
from stdlib import deduped_string_list_fields, positive_int_fields

from pydantic import Field


class Params(PortfolioReviewParameters):
    """Invocation contract for ``company_operation_to_recursive_improvement_cycle``."""

    focus_tasks: list[str] = Field(default_factory=list)
    focus_workflows: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    max_tasks: int = 25
    max_runs_per_workflow: int = 10
    max_messages_per_task: int = 5

    _normalize_repeatable_strings = deduped_string_list_fields("focus_tasks", "focus_workflows", "statuses")
    _validate_positive_ints = positive_int_fields(
        "max_tasks",
        "max_runs_per_workflow",
        "max_messages_per_task",
        error_message="must be a positive integer",
    )


__all__ = ["Params"]
