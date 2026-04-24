"""Workflow-local output contracts for the task-to-workflow-strategy package."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from workflow import RouteContract


StrategyRoute = Literal["run_existing", "compose", "adapt", "create_new"]


class TaskFramingPayload(BaseModel):
    """Verifier payload for the task-framing step."""

    summary: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    decision_axes: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class StrategySelectionPayload(BaseModel):
    """Verifier payload for the strategy-selection step."""

    summary: str = Field(min_length=1)
    compared_workflows: list[str] = Field(min_length=3)
    selected_strategy: StrategyRoute
    recommended_workflows: list[str] = Field(min_length=1)
    builder_considered: bool = False
    rejected_routes: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class StrategyPackagePayload(BaseModel):
    """Verifier payload for the strategy-packaging step."""

    summary: str = Field(min_length=1)
    selected_strategy: StrategyRoute
    recommended_workflows: list[str] = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    next_action: str = Field(min_length=1)
    ready_for_handoff: bool = False
    replan_reason: str | None = None


FRAME_TASK_ROUTE_CONTRACTS = {
    "task_framed": RouteContract(
        summary="The task trigger, sponsor, desired outcome, and strategy-selection criteria are explicit enough to compare portfolio options without hidden assumptions.",
        required_artifacts=("task_strategy_brief", "workflow_selection_criteria"),
        work_item_effect="Locks the task framing so workflow comparison can proceed against an explicit problem and acceptance boundary.",
    ),
    "needs_rework": RouteContract(
        summary="The same framing boundary still holds, but the brief or selection criteria need local repair before the portfolio is compared.",
        required_artifacts=("task_strategy_brief", "workflow_selection_criteria"),
        work_item_effect="Keeps the task-framing work item local and reruns the same step for stronger strategy criteria.",
    ),
    "needs_replan": RouteContract(
        summary="The task trigger, desired outcome, or strategy boundary changed materially and the task must be reframed before any portfolio decision is credible.",
        required_artifacts=("task_strategy_brief", "workflow_selection_criteria"),
        work_item_effect="Resets the framing boundary before workflow selection continues.",
    ),
}

SELECT_STRATEGY_ROUTE_CONTRACTS = {
    "strategy_selected": RouteContract(
        summary="At least three candidate workflows or building blocks were compared, the workflow-builder baseline was considered, and one explicit strategy route was selected without running it.",
        required_artifacts=("workflow_candidate_matrix", "workflow_gap_analysis", "strategy_decision"),
        work_item_effect="Locks the selected strategy route and recommended workflows so packaging can produce a durable handoff instead of hidden execution.",
    ),
    "needs_rework": RouteContract(
        summary="The same strategy-selection boundary holds, but the candidate comparison, gap analysis, or route rationale needs local repair.",
        required_artifacts=("workflow_candidate_matrix", "workflow_gap_analysis", "strategy_decision"),
        work_item_effect="Keeps portfolio selection local and reruns the same step for a clearer reuse-versus-rebuild decision.",
    ),
    "needs_replan": RouteContract(
        summary="The framing, candidate set, or legal strategy route changed materially and the task must be reframed before selection continues.",
        required_artifacts=("task_strategy_brief", "workflow_selection_criteria"),
        work_item_effect="Returns the workflow to framing because the current portfolio comparison is no longer authoritative.",
    ),
}

PACKAGE_STRATEGY_ROUTE_CONTRACTS = {
    "strategy_package_ready": RouteContract(
        summary="The terminal strategy package, machine-readable summary, and next-action artifact all exist and make the selected route explicit without triggering downstream execution.",
        required_artifacts=("workflow_strategy_package", "strategy_summary", "strategy_next_action"),
        work_item_effect="Advances the front-door workflow to deterministic publication of the strategy package and receipt.",
    ),
    "needs_rework": RouteContract(
        summary="The selected route still stands, but the strategy package, summary, or next-action artifact needs local repair before publication.",
        required_artifacts=("workflow_strategy_package", "strategy_summary", "strategy_next_action"),
        work_item_effect="Keeps strategy packaging local and reruns the same step for packaging corrections only.",
    ),
    "needs_replan": RouteContract(
        summary="Packaging revealed that the chosen strategy route, recommended workflows, or handoff contract changed materially and selection must be revisited.",
        required_artifacts=("workflow_candidate_matrix", "workflow_gap_analysis", "strategy_decision"),
        work_item_effect="Routes back to strategy selection because the current package no longer matches the chosen route.",
    ),
}


__all__ = [
    "FRAME_TASK_ROUTE_CONTRACTS",
    "PACKAGE_STRATEGY_ROUTE_CONTRACTS",
    "SELECT_STRATEGY_ROUTE_CONTRACTS",
    "StrategyPackagePayload",
    "StrategyRoute",
    "StrategySelectionPayload",
    "TaskFramingPayload",
]
