"""Typed invocation parameters."""

from __future__ import annotations

from pydantic import Field

from botpipe_optimizer import PortfolioReviewParameters


class Params(PortfolioReviewParameters):
    max_provider_turns: int = Field(default=32, gt=0, strict=True)
    focus_workflows: list[str] = Field(default_factory=list)
    max_runs_per_workflow: int = Field(default=10, gt=0)


__all__ = ["Params"]
