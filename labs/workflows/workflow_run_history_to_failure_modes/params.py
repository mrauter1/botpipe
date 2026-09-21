"""Typed invocation parameters."""

from __future__ import annotations

from pydantic import Field

from botpipe_optimizer import SelectedWorkflowTaskFramingParameters


class Params(SelectedWorkflowTaskFramingParameters):
    statuses: list[str] = Field(default_factory=list)
    max_runs: int = Field(default=25, gt=0)


__all__ = ["Params"]
