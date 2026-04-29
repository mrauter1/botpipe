"""Workflow-local output contracts for the eval-suite building block."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

try:  # pragma: no branch - supports both package and direct repo-root imports
    from autoloop_v3.stdlib import JsonArtifactSpec
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from stdlib import JsonArtifactSpec

from autoloop import Route, SELF


CaseKind = Literal["benchmark", "edge", "adversarial"]


class EvaluationTargetFramingPayload(BaseModel):
    """Verifier payload for the evaluation-target framing step."""

    summary: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    evaluation_axes: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class EvalCaseDesignPayload(BaseModel):
    """Verifier payload for the eval-case design step."""

    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    case_ids: list[str] = Field(min_length=1)
    case_kinds: list[CaseKind] = Field(min_length=1)
    covered_expected_artifacts: list[str] = Field(min_length=1)
    replan_reason: str | None = None


class WorkflowEvalSuitePayload(BaseModel):
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


VALIDATED_EVAL_CASE_MANIFEST_ARTIFACT = JsonArtifactSpec(
    "validated_eval_case_manifest.json",
    ValidatedEvalCaseManifestPayload,
)
WORKFLOW_EVAL_SUITE_SUMMARY_ARTIFACT = JsonArtifactSpec(
    "workflow_eval_suite_summary.json",
    WorkflowEvalSuiteSummaryPayload,
)


FRAME_EVALUATION_TARGET_ROUTE_CONTRACTS = {
    "evaluation_target_framed": Route.to(
        "design_eval_cases",
        summary="The selected workflow, evaluation objective, and acceptance dimensions are explicit enough for benchmark, edge, and adversarial case design.",
        required_writes=("evaluation_request_brief", "evaluation_dimensions"),
        handoff="Locks the evaluation-target framing so case and rubric design can proceed against an explicit evaluation contract.",
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The same evaluation-target framing boundary holds, but the framing artifacts need local repair before case design can continue.",
        required_writes=("evaluation_request_brief", "evaluation_dimensions"),
        handoff="Keeps evaluation framing local and reruns the same step for clearer target and acceptance guidance.",
    ),
    "needs_replan": Route.to(
        "frame_evaluation_target",
        summary="The selected workflow, evaluation objective, or acceptance boundary changed materially and the evaluation target must be reframed.",
        handoff="Returns the workflow to framing because the current evaluation boundary is no longer authoritative.",
    ),
}

DESIGN_EVAL_CASES_ROUTE_CONTRACTS = {
    "eval_cases_designed": Route.to(
        "package_workflow_eval_suite",
        summary="Benchmark, edge, and adversarial case coverage plus the evaluation rubric are explicit and ready for terminal suite packaging.",
        required_writes=(
            "benchmark_case_matrix",
            "edge_case_matrix",
            "adversarial_case_matrix",
            "eval_case_manifest",
            "eval_rubric",
        ),
        handoff="Locks the evaluation cases and rubric so the workflow can package a publication-ready eval suite.",
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The same case-design boundary still holds, but the case matrices, manifest, or rubric need local repair.",
        required_writes=(
            "benchmark_case_matrix",
            "edge_case_matrix",
            "adversarial_case_matrix",
            "eval_case_manifest",
            "eval_rubric",
        ),
        handoff="Keeps evaluation design local and reruns the same step for stronger case coverage or rubric clarity.",
    ),
    "needs_replan": Route.to(
        "frame_evaluation_target",
        summary="Case design proved the selected workflow, evaluation objective, or acceptance boundary changed materially and framing must be revisited.",
        handoff="Routes back to framing because the current evaluation target is no longer credible as stated.",
    ),
}

PACKAGE_WORKFLOW_EVAL_SUITE_ROUTE_CONTRACTS = {
    "workflow_eval_suite_ready": Route.to(
        "publish_workflow_eval_suite",
        summary="The terminal eval-suite package, machine-readable summary, and next-action artifact are complete and ready for deterministic publication of the validated manifest and receipt.",
        required_writes=(
            "workflow_eval_suite",
            "workflow_eval_suite_summary",
            "workflow_eval_next_action",
        ),
        handoff="Advances the building block to deterministic publication of the validated eval-case manifest and receipt.",
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The same evaluation-suite packaging boundary still holds, but the package artifacts need local repair before publication.",
        required_writes=(
            "workflow_eval_suite",
            "workflow_eval_suite_summary",
            "workflow_eval_next_action",
        ),
        handoff="Keeps packaging local and reruns the same step for suite, summary, or next-action corrections only.",
    ),
    "needs_replan": Route.to(
        "design_eval_cases",
        summary="Packaging revealed that the designed evaluation surface changed materially and case design must be revisited.",
        handoff="Routes back to case design because the package no longer matches the authoritative evaluation surface.",
    ),
}


__all__ = [
    "DESIGN_EVAL_CASES_ROUTE_CONTRACTS",
    "EvalCaseDesignPayload",
    "EvaluationTargetFramingPayload",
    "FRAME_EVALUATION_TARGET_ROUTE_CONTRACTS",
    "PACKAGE_WORKFLOW_EVAL_SUITE_ROUTE_CONTRACTS",
    "VALIDATED_EVAL_CASE_MANIFEST_ARTIFACT",
    "ValidatedEvalCaseManifestPayload",
    "ValidatedEvalCasePayload",
    "WORKFLOW_EVAL_SUITE_SUMMARY_ARTIFACT",
    "WorkflowEvalSuitePayload",
    "WorkflowEvalSuiteSummaryPayload",
]
