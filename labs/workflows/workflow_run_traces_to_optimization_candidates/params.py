"""Optimizer-v2 invocation parameters and enforced evidence/output bounds."""

from __future__ import annotations

import warnings
from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from botpipe_optimizer import SelectedWorkflowTaskFramingParameters


class Params(SelectedWorkflowTaskFramingParameters):
    model_config = ConfigDict(extra="forbid")

    run_refs: list[str] = Field(default_factory=list)
    run_statuses: list[str] = Field(
        default_factory=lambda: [
            "completed",
            "failed",
            "awaiting_input",
            "blocked",
            "interrupted",
        ]
    )
    route_tags: list[str] = Field(default_factory=list)
    history_limit: int = Field(default=25, gt=0)
    top_k_steps: int = Field(default=1, gt=0)
    objective: Literal["reliability", "token_usage", "latency"] = "reliability"
    include_adversarial_generation: bool = True
    include_token_optimization: bool = True
    include_workflow_level_candidates: bool = True
    max_candidates: int = Field(default=3, gt=0)
    max_provider_turns: int = Field(default=6, gt=0)
    provider_turn_timeout_seconds: int = Field(default=600, gt=0)
    max_analysis_seconds: int = Field(default=1800, gt=0)
    max_evidence_bytes: int = Field(default=50 * 1024 * 1024, gt=0)
    max_output_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    focus: str | None = None

    @model_validator(mode="before")
    @classmethod
    def deprecated_aliases(cls, value: Any):
        if not isinstance(value, dict):
            return value
        result = dict(value)
        max_candidates_per_pass = result.pop("max_candidates_per_pass", None)
        if max_candidates_per_pass is not None:
            if (
                "max_candidates" in result
                and result["max_candidates"] != max_candidates_per_pass
            ):
                raise ValueError(
                    "max_candidates conflicts with deprecated max_candidates_per_pass"
                )
            result["max_candidates"] = max_candidates_per_pass
            warnings.warn(
                "max_candidates_per_pass is deprecated; use max_candidates",
                FutureWarning,
                stacklevel=2,
            )
        optimization_depth = result.pop("optimization_depth", None)
        if optimization_depth is not None:
            if optimization_depth not in ("cheap", "standard", "ablation"):
                raise ValueError(
                    "optimization_depth must be 'cheap', 'standard', or 'ablation'"
                )
            warnings.warn(
                "optimization_depth is deprecated; ablation is planning-only",
                FutureWarning,
                stacklevel=2,
            )
            turns, seconds = (
                (12, 3600) if optimization_depth == "standard" else (6, 1800)
            )
            result.setdefault("max_provider_turns", turns)
            result.setdefault("max_analysis_seconds", seconds)
        return result

    @field_validator("run_refs")
    @classmethod
    def valid_refs(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("run_refs must be unique")
        if any(not v.strip() or v.count("/") > 1 for v in values):
            raise ValueError("run_refs must be run ids or task/run refs")
        return values

    @field_validator("run_statuses", "route_tags")
    @classmethod
    def unique_text(cls, values: list[str]):
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized) or len(normalized) != len(
            set(normalized)
        ):
            raise ValueError("list entries must be non-empty and unique")
        return normalized


__all__ = ["Params"]
