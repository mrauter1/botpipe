"""Artifact contracts for observation-driven optimization."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from labs.workflows._shared import LabPhaseOutcome


class SourceSitePayload(BaseModel):
    site_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    line: int = Field(ge=1)


class SelectedWorkflowSourceManifestArtifactPayload(BaseModel):
    workflow_name: str = Field(min_length=1)
    source_path: str | None = None
    source_sha256: str = Field(min_length=1)
    topology_dynamic: Literal[True] = True
    sites: list[SourceSitePayload] = Field(default_factory=list)
    branch_lines: list[int] = Field(default_factory=list)


class OperationObservationPayload(BaseModel):
    operation_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    name: str = Field(min_length=1)
    status: str = Field(min_length=1)
    outcome: str | None = None
    attempts: int = Field(ge=1)
    duration_ms: float | None = Field(default=None, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class WorkflowOptimizationTraceCorpusArtifactPayload(BaseModel):
    workflow_name: str = Field(min_length=1)
    run_ids: list[str] = Field(default_factory=list)
    operations: list[OperationObservationPayload] = Field(default_factory=list)
    observation_absent: bool


class OperationMetricPayload(BaseModel):
    name: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    observation_count: int = Field(ge=1)
    success_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    retry_count: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    mean_duration_ms: float | None = Field(default=None, ge=0)
    evidence_operation_ids: list[str] = Field(min_length=1)


class OptimizationCandidatePayload(BaseModel):
    candidate_id: str = Field(min_length=1)
    target_name: str = Field(min_length=1)
    target_kind: str = Field(min_length=1)
    category: Literal["reliability", "token_cost", "latency", "evidence_gap"]
    score: float = Field(ge=0)
    rationale: str = Field(min_length=1)
    proposed_change: str = Field(min_length=1)
    evidence_operation_ids: list[str] = Field(min_length=1)
    requires_ablation: bool = False


class WorkflowOptimizationScorecardArtifactPayload(BaseModel):
    workflow_name: str = Field(min_length=1)
    observed_run_ids: list[str] = Field(default_factory=list)
    observed_operation_count: int = Field(ge=0)
    observation_absent: bool
    unseen_declared_paths: list[str] = Field(default_factory=list)
    metrics: list[OperationMetricPayload] = Field(default_factory=list)
    candidates: list[OptimizationCandidatePayload] = Field(default_factory=list)


class FrameOptimizationPayload(LabPhaseOutcome):
    selected_workflow_name: str = Field(min_length=1)
    observed_operation_count: int = Field(ge=0)
    unseen_declared_paths: list[str] = Field(default_factory=list)
    next_action: Literal["analyze", "package_only"] = "analyze"


class RankTargetsPayload(LabPhaseOutcome):
    selected_workflow_name: str = Field(min_length=1)
    ranked_operations: list[str] = Field(default_factory=list)
    ranking_method: str = Field(min_length=1)
    next_action: Literal["mine_failures", "package_only"] = "mine_failures"


class FailureScenarioPayload(LabPhaseOutcome):
    selected_workflow_name: str = Field(min_length=1)
    target_operations: list[str] = Field(default_factory=list)
    failure_ids: list[str] = Field(default_factory=list)


class CandidatePassPayload(LabPhaseOutcome):
    selected_workflow_name: str = Field(min_length=1)
    target_operations: list[str] = Field(default_factory=list)


class AdversarialCasesPayload(LabPhaseOutcome):
    selected_workflow_name: str = Field(min_length=1)
    case_ids: list[str] = Field(default_factory=list)


class OptimizationPackagePayload(LabPhaseOutcome):
    selected_workflow_name: str = Field(min_length=1)
    highest_priority_candidate_ids: list[str] = Field(default_factory=list)
    recommended_next_action: str = Field(min_length=1)
    requires_ablation_before_promotion: bool
    source_mutation_check_expected: bool


__all__ = [
    "RankTargetsPayload",
    "FailureScenarioPayload",
    "CandidatePassPayload",
    "AdversarialCasesPayload",
    "OptimizationPackagePayload",
    "FrameOptimizationPayload",
    "OperationMetricPayload",
    "OperationObservationPayload",
    "OptimizationCandidatePayload",
    "SelectedWorkflowSourceManifestArtifactPayload",
    "SourceSitePayload",
    "WorkflowOptimizationScorecardArtifactPayload",
    "WorkflowOptimizationTraceCorpusArtifactPayload",
]
