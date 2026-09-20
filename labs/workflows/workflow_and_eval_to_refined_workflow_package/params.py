"""Typed invocation parameters."""

from __future__ import annotations

import sys

from pydantic import Field

from botpipe_optimizer import SelectedWorkflowTaskFramingParameters


class Params(SelectedWorkflowTaskFramingParameters):
    evaluation_summary_path: str = Field(min_length=1)
    evaluation_findings_path: str = Field(min_length=1)
    failure_modes_path: str | None = None
    refinement_evidence_path: str | None = None
    candidate_paths: list[str] = Field(default_factory=list)
    target_test_argv: list[str] = Field(
        default_factory=lambda: [sys.executable, "-m", "pytest", "-q"],
        min_length=1,
    )
    validation_timeout: float = Field(default=300, gt=0)


__all__ = ["Params"]
