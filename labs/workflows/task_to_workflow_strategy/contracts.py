"""Typed domain result contracts for this durable labs workflow."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from labs.workflows._shared import LabPhaseOutcome

StrategyRoute = Literal["run_existing", "compose", "adapt", "create_new"]


class TaskFramingPayload(LabPhaseOutcome):
    """Verifier payload for the task-framing step."""

    summary: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    decision_axes: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class StrategySelectionPayload(LabPhaseOutcome):
    """Verifier payload for the strategy-selection step."""

    summary: str = Field(min_length=1)
    compared_workflows: list[str] = Field(min_length=3)
    selected_strategy: StrategyRoute
    recommended_workflows: list[str] = Field(min_length=1)
    builder_considered: bool = False
    rejected_routes: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class StrategyPackagePayload(LabPhaseOutcome):
    """Verifier payload for the strategy-packaging step."""

    summary: str = Field(min_length=1)
    selected_strategy: StrategyRoute
    recommended_workflows: list[str] = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    next_action: str = Field(min_length=1)
    ready_for_handoff: bool = False
    replan_reason: str | None = None


class StrategySummaryPayload(BaseModel):
    """Typed contract for strategy_summary.json."""

    selected_strategy: StrategyRoute
    recommended_workflows: list[str] = Field(min_length=1)
    comparison_candidates: list[str] = Field(min_length=1)
    builder_baseline_workflow: str = Field(min_length=1)
    builder_considered: bool
    create_new_required: bool
    authoritative_artifacts: list[str] = Field(min_length=1)
    next_action: str = Field(min_length=1)
    ready_for_handoff: bool = False
    rejected_routes: list[str] = Field(default_factory=list)


__all__ = [
    "StrategyPackagePayload",
    "StrategySelectionPayload",
    "StrategySummaryPayload",
    "TaskFramingPayload",
]
