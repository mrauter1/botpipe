"""Typed invocation parameters."""

from __future__ import annotations

from pydantic import Field

from botpipe_optimizer import PortfolioReviewParameters


class Params(PortfolioReviewParameters):
    focus_tasks: list[str] = Field(default_factory=list)
    focus_workflows: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    max_tasks: int = Field(default=25, gt=0)
    max_runs_per_workflow: int = Field(default=10, gt=0)
    max_messages_per_task: int = Field(default=5, gt=0)


__all__ = ["Params"]
