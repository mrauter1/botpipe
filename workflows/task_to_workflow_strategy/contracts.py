"""Workflow-local output contracts for the task-to-workflow-strategy package."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

try:  # pragma: no branch - supports both package and direct repo-root imports
    from autoloop_v3.stdlib import JsonArtifactSpec
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from stdlib import JsonArtifactSpec

from core import RouteInfo

from ..task_to_candidate_workflow_set.contracts import CandidateWorkflowSetSummaryPayload


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


CANDIDATE_WORKFLOW_SET_SUMMARY_ARTIFACT = JsonArtifactSpec(
    "candidate_workflow_set_summary.json",
    CandidateWorkflowSetSummaryPayload,
)
STRATEGY_SUMMARY_ARTIFACT = JsonArtifactSpec("strategy_summary.json", StrategySummaryPayload)


FRAME_TASK_ROUTE_CONTRACTS = {
    "task_framed": RouteInfo(
        summary="The task trigger, sponsor, desired outcome, and strategy-selection criteria are explicit enough to compare portfolio options without hidden assumptions.",
        required_outputs=("task_strategy_brief", "workflow_selection_criteria"),
        handoff="Locks the task framing so workflow comparison can proceed against an explicit problem and acceptance boundary.",
    ),
    "needs_rework": RouteInfo(
        summary="The same framing boundary still holds, but the brief or selection criteria need local repair before the portfolio is compared.",
        required_outputs=("task_strategy_brief", "workflow_selection_criteria"),
        handoff="Keeps the task-framing work item local and reruns the same step for stronger strategy criteria.",
    ),
    "needs_replan": RouteInfo(
        summary="The task trigger, desired outcome, or strategy boundary changed materially and the task must be reframed before any portfolio decision is credible.",
        handoff="Resets the framing boundary before workflow selection continues.",
    ),
}

SELECT_STRATEGY_ROUTE_CONTRACTS = {
    "strategy_selected": RouteInfo(
        summary="The child candidate-workflow-set package was consumed explicitly, the workflow-builder baseline remained visible, and one explicit strategy route was selected without running it.",
        required_outputs=("strategy_decision",),
        handoff="Locks the selected strategy route and recommended workflows so packaging can produce a durable handoff instead of hidden execution.",
    ),
    "needs_rework": RouteInfo(
        summary="The same strategy-selection boundary holds, but the route rationale or its use of the child candidate package needs local repair.",
        required_outputs=("strategy_decision",),
        handoff="Keeps portfolio selection local and reruns the same step for a clearer reuse-versus-rebuild decision.",
    ),
    "needs_replan": RouteInfo(
        summary="The framing, child candidate set, or legal strategy route changed materially and the task must be reframed before selection continues.",
        handoff="Returns the workflow to framing because the current portfolio comparison is no longer authoritative.",
    ),
}

PACKAGE_STRATEGY_ROUTE_CONTRACTS = {
    "strategy_package_ready": RouteInfo(
        summary="The terminal strategy package, machine-readable summary, and next-action artifact all exist and make the selected route explicit without triggering downstream execution.",
        required_outputs=("workflow_strategy_package", "strategy_summary", "strategy_next_action"),
        handoff="Advances the front-door workflow to deterministic publication of the strategy package and receipt.",
    ),
    "needs_rework": RouteInfo(
        summary="The selected route still stands, but the strategy package, summary, or next-action artifact needs local repair before publication.",
        required_outputs=("workflow_strategy_package", "strategy_summary", "strategy_next_action"),
        handoff="Keeps strategy packaging local and reruns the same step for packaging corrections only.",
    ),
    "needs_replan": RouteInfo(
        summary="Packaging revealed that the chosen strategy route, recommended workflows, or handoff contract changed materially and selection must be revisited.",
        handoff="Routes back to strategy selection because the current package no longer matches the chosen route.",
    ),
}


__all__ = [
    "CANDIDATE_WORKFLOW_SET_SUMMARY_ARTIFACT",
    "FRAME_TASK_ROUTE_CONTRACTS",
    "PACKAGE_STRATEGY_ROUTE_CONTRACTS",
    "SELECT_STRATEGY_ROUTE_CONTRACTS",
    "StrategyPackagePayload",
    "StrategyRoute",
    "STRATEGY_SUMMARY_ARTIFACT",
    "StrategySummaryPayload",
    "StrategySelectionPayload",
    "TaskFramingPayload",
]
