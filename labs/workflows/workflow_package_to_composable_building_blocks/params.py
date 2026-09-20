"""Typed invocation parameters."""

from __future__ import annotations

import sys

from pydantic import Field

from botpipe_optimizer import SelectedWorkflowTaskFramingParameters


class Params(SelectedWorkflowTaskFramingParameters):
    evidence_paths: list[str] = Field(default_factory=list)
    candidate_paths: list[str] = Field(default_factory=list)
    target_test_argv: list[str] = Field(
        default_factory=lambda: [sys.executable, "-m", "pytest", "-q"],
        min_length=1,
    )
    validation_timeout: float = Field(default=300, gt=0)
    max_candidate_building_blocks: int = Field(default=3, ge=1)


__all__ = ["Params"]
