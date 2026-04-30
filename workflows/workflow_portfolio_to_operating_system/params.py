"""Workflow-specific parameter model for the portfolio-governance workflow."""

from __future__ import annotations

from autoloop_v3.autoloop_optimizer import PortfolioReviewParameters
from stdlib import deduped_string_list_fields, positive_int_fields

from pydantic import Field


class Params(PortfolioReviewParameters):
    """Invocation contract for ``workflow_portfolio_to_operating_system``."""

    focus_workflows: list[str] = Field(default_factory=list)
    max_runs_per_workflow: int = 10

    _normalize_focus_workflows = deduped_string_list_fields("focus_workflows")
    _validate_max_runs_per_workflow = positive_int_fields(
        "max_runs_per_workflow",
        error_message="max_runs_per_workflow must be a positive integer",
    )


__all__ = ["Params"]
