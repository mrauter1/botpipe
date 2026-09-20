"""Typed domain result contracts for this durable labs workflow."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from labs.workflows._shared import LabPhaseOutcome

CaseKind = Literal["benchmark", "edge", "adversarial"]


class EvaluationTargetFramingPayload(LabPhaseOutcome):
    """Verifier payload for the evaluation-target framing step."""

    summary: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    evaluation_axes: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class EvalCaseDesignPayload(LabPhaseOutcome):
    """Verifier payload for the eval-case design step."""

    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    case_ids: list[str] = Field(min_length=1)
    case_kinds: list[CaseKind] = Field(min_length=1)
    covered_expected_artifacts: list[str] = Field(min_length=1)
    replan_reason: str | None = None


class WorkflowEvalSuitePayload(LabPhaseOutcome):
    """Verifier payload for the terminal eval-suite package step."""

    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    selected_workflow_entry_step: str = Field(min_length=1)
    selected_workflow_parameters_supported: bool
    case_count: int = Field(ge=1)
    case_ids: list[str] = Field(min_length=1)
    case_kinds: list[CaseKind] = Field(min_length=1)
    covered_expected_artifacts: list[str] = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    next_action: str = Field(min_length=1)
    ready_for_publication: bool
    replan_reason: str | None = None


class WorkflowEvalSuiteSummaryPayload(BaseModel):
    """Typed contract for workflow_eval_suite_summary.json."""

    selected_workflow_name: str = Field(min_length=1)
    selected_workflow_entry_step: str = Field(min_length=1)
    selected_workflow_parameters_supported: bool
    case_count: int = Field(ge=1)
    case_ids: list[str] = Field(min_length=1)
    case_kinds: list[CaseKind] = Field(min_length=1)
    covered_expected_artifacts: list[str] = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    next_action: str = Field(min_length=1)
    ready_for_publication: bool


class ValidatedEvalCasePayload(BaseModel):
    """Typed contract for one validated eval case."""

    case_id: str = Field(min_length=1)
    case_kind: CaseKind
    expected_artifacts: list[str] = Field(min_length=1)
    prompt: str = Field(min_length=1)
    workflow_parameters: dict[str, Any] = Field(default_factory=dict)


class ValidatedEvalCaseManifestPayload(BaseModel):
    """Typed contract for validated_eval_case_manifest.json."""

    repo_root: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    workflow_name: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    case_ids: list[str] = Field(min_length=1)
    case_kinds: list[CaseKind] = Field(min_length=1)
    validated_cases: list[ValidatedEvalCasePayload] = Field(min_length=1)


__all__ = [
    "EvalCaseDesignPayload",
    "EvaluationTargetFramingPayload",
    "ValidatedEvalCaseManifestPayload",
    "ValidatedEvalCasePayload",
    "WorkflowEvalSuitePayload",
    "WorkflowEvalSuiteSummaryPayload",
]
