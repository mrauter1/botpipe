"""Typed invocation parameters."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from botpipe_optimizer import SelectedWorkflowTaskFramingParameters


class Params(SelectedWorkflowTaskFramingParameters):
    run_refs: list[str] = Field(default_factory=list)
    run_statuses: list[str] = Field(
        default_factory=lambda: ["failed", "awaiting_input", "interrupted"]
    )
    history_limit: int = Field(default=25, gt=0)
    top_k_steps: int = Field(default=3, gt=0)
    optimization_depth: Literal["cheap", "standard", "ablation"] = "cheap"
    include_adversarial_generation: bool = True
    include_token_optimization: bool = True
    include_workflow_level_candidates: bool = True
    max_failure_scenarios: int = Field(default=25, gt=0)
    max_candidates_per_pass: int = Field(default=3, gt=0)
    focus: str | None = None

    @field_validator("run_refs")
    @classmethod
    def valid_refs(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("run_refs must be unique")
        if any(not v.strip() or v.count("/") > 1 for v in values):
            raise ValueError("run_refs must be run ids or task/run refs")
        return values


__all__ = ["Params"]
