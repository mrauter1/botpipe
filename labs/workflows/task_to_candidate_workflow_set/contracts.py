"""Typed domain result contracts for this durable labs workflow."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from labs.workflows._shared import LabPhaseOutcome

PortfolioPosture = Literal[
    "direct_fit", "compose_needed", "adapt_needed", "material_gap"
]


class CandidateRequestFramingPayload(LabPhaseOutcome):
    """Verifier payload for the candidate-request framing step."""

    summary: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    decision_axes: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class CandidateWorkflowAnalysisPayload(LabPhaseOutcome):
    """Verifier payload for the candidate-workflow analysis step."""

    summary: str = Field(min_length=1)
    compared_workflows: list[str] = Field(min_length=1)
    ranked_candidates: list[str] = Field(min_length=1)
    portfolio_posture: PortfolioPosture
    builder_considered: bool = False
    replan_reason: str | None = None


class CandidateWorkflowSetPayload(LabPhaseOutcome):
    """Verifier payload for the candidate-workflow-set packaging step."""

    summary: str = Field(min_length=1)
    comparison_candidates: list[str] = Field(min_length=1)
    ranked_candidates: list[str] = Field(min_length=1)
    recommended_candidate_workflows: list[str] = Field(min_length=1)
    builder_baseline_workflow: str = Field(min_length=1)
    builder_considered: bool = False
    portfolio_posture: PortfolioPosture
    authoritative_artifacts: list[str] = Field(min_length=1)
    next_action: str = Field(min_length=1)
    ready_for_strategy_selection: bool = False
    replan_reason: str | None = None


class CandidateWorkflowSetSummaryPayload(BaseModel):
    """Typed contract for candidate_workflow_set_summary.json."""

    comparison_candidates: list[str] = Field(min_length=1)
    ranked_candidates: list[str] = Field(min_length=1)
    recommended_candidate_workflows: list[str] = Field(min_length=1)
    builder_baseline_workflow: str = Field(min_length=1)
    builder_considered: bool = False
    portfolio_posture: PortfolioPosture
    authoritative_artifacts: list[str] = Field(min_length=1)
    next_action: str = Field(min_length=1)
    ready_for_strategy_selection: bool = False


__all__ = [
    "CandidateRequestFramingPayload",
    "CandidateWorkflowAnalysisPayload",
    "CandidateWorkflowSetPayload",
    "CandidateWorkflowSetSummaryPayload",
]
