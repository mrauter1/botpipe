"""Workflow-specific parameter model for the failure-mode diagnostics building block."""

from __future__ import annotations

from autoloop_v3.autoloop_optimizer import SelectedWorkflowTaskFramingParameters
from stdlib import positive_int_fields

from pydantic import Field, field_validator


class Params(SelectedWorkflowTaskFramingParameters):
    """Invocation contract for ``workflow_run_history_to_failure_modes``."""

    statuses: list[str] = Field(default_factory=list)
    max_runs: int = 25

    @field_validator("statuses")
    @classmethod
    def _normalize_status_filters(cls, values: list[str]) -> list[str]:
        normalized: set[str] = set()
        for value in values:
            candidate = value.strip()
            if candidate:
                normalized.add(candidate)
        return sorted(normalized)

    _validate_max_runs = positive_int_fields("max_runs", error_message="max_runs must be a positive integer")


__all__ = ["Params"]
