"""Workflow-specific parameter model for optimization-candidate generation."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

try:
    from autoloop_v3.stdlib import SelectedWorkflowTaskFramingParameters, positive_int_fields
except ImportError:  # pragma: no cover - direct repo execution fallback
    from stdlib import SelectedWorkflowTaskFramingParameters, positive_int_fields


class Parameters(SelectedWorkflowTaskFramingParameters):
    """Invocation contract for ``workflow_run_traces_to_optimization_candidates``."""

    run_refs: list[str] = Field(default_factory=list)
    run_statuses: list[str] = Field(default_factory=lambda: ["failed", "paused", "blocked"])
    route_tags: list[str] = Field(default_factory=lambda: ["needs_rework", "needs_replan", "failed", "blocked"])
    history_limit: int = 25
    top_k_steps: int = 1
    optimization_depth: Literal["cheap", "standard", "ablation"] = "cheap"
    include_adversarial_generation: bool = True
    include_token_optimization: bool = True
    include_workflow_level_candidates: bool = True
    max_failure_scenarios: int = 25
    max_candidates_per_pass: int = 3
    focus: str | None = None
    sponsor_role: str | None = None
    desired_outcome: str | None = None
    constraints: list[str] = Field(default_factory=list)

    @field_validator("run_refs")
    @classmethod
    def _validate_run_refs(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in values:
            candidate = str(raw).strip()
            if not candidate:
                raise ValueError("run_refs entries must be non-empty strings")
            if candidate.count("/") != 1:
                raise ValueError("run_refs entries must contain exactly one '/' separator")
            task_id, run_id = candidate.split("/", 1)
            if not task_id or not run_id:
                raise ValueError("run_refs entries must define non-empty task_id and run_id components")
            if candidate in seen:
                raise ValueError("run_refs entries must be unique")
            seen.add(candidate)
            normalized.append(candidate)
        return normalized

    @field_validator("run_statuses", "route_tags")
    @classmethod
    def _validate_unique_string_lists(cls, values: list[str], info) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in values:
            candidate = str(raw).strip()
            if not candidate:
                raise ValueError(f"{info.field_name} entries must be non-empty strings")
            if candidate in seen:
                raise ValueError(f"{info.field_name} entries must be unique")
            seen.add(candidate)
            normalized.append(candidate)
        return normalized

    @field_validator("constraints")
    @classmethod
    def _validate_constraints(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for raw in values:
            candidate = str(raw).strip()
            if not candidate:
                raise ValueError("constraints entries must be non-empty after normalization")
            if candidate not in normalized:
                normalized.append(candidate)
        return normalized

    @field_validator("focus", "sponsor_role", "desired_outcome")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        candidate = value.strip()
        return candidate or None

    _validate_positive_ints = positive_int_fields(
        "history_limit",
        "top_k_steps",
        "max_failure_scenarios",
        "max_candidates_per_pass",
    )


__all__ = ["Parameters"]
