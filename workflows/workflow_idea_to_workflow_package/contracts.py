"""Workflow-local output contracts for the workflow-builder package."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from core import RouteInfo


class CandidateSelectionPayload(BaseModel):
    """Verifier payload for the framing step."""

    summary: str = Field(min_length=1)
    evidence_artifacts: list[str] = Field(min_length=1)
    selected_candidate: str | None = None
    selected_kind: Literal["end_to_end", "building_block"] | None = None
    replan_reason: str | None = None


class WorkflowDesignPayload(BaseModel):
    """Verifier payload for the design step."""

    summary: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    prompt_files: list[str] = Field(default_factory=list)
    next_action: str = Field(min_length=1)
    replan_reason: str | None = None


class WorkflowBuildPayload(BaseModel):
    """Verifier payload for the build step."""

    summary: str = Field(min_length=1)
    changed_paths: list[str] = Field(min_length=1)
    evidence_artifacts: list[str] = Field(min_length=1)
    replan_reason: str | None = None


class WorkflowEvaluationPayload(BaseModel):
    """Verifier payload for the evaluation step."""

    summary: str = Field(min_length=1)
    evidence_artifacts: list[str] = Field(min_length=1)
    validation_commands: list[str] = Field(default_factory=list)
    promotion_decision: Literal["promote", "rework", "replan"] | None = None
    replan_reason: str | None = None


FRAME_CANDIDATE_ROUTE_CONTRACTS = {
    "candidate_selected": RouteInfo(
        summary= "Select one addition after comparing at least three strong candidates, explicitly including the workflow-builder.",
        required_outputs= ["candidate_comparison", "selected_workflow_brief"],
        handoff= "Locks the selected addition and its classification for downstream design.",
    ),
    "needs_rework": RouteInfo(
        summary= "The same framing step can succeed after tightening the comparison or rewriting the brief without changing the selected job.",
        required_outputs= ["candidate_comparison", "selected_workflow_brief"],
        handoff= "Keeps the framing boundary intact and reruns the same step.",
    ),
    "needs_replan": RouteInfo(
        summary= "The current framing is materially wrong and the candidate set, selection rationale, or workflow kind must be reframed.",
        handoff= "Returns control to the framing step with a wider reconsideration scope.",
    ),
}

DESIGN_PACKAGE_ROUTE_CONTRACTS = {
    "design_accepted": RouteInfo(
        summary= "The package design is explicit, doctrine-compliant, and ready for direct file creation.",
        required_outputs= [
            "workflow_package_spec",
            "step_contracts",
            "prompt_contract_matrix",
            "verification_plan",
        ],
        handoff= "Allows the build step to author package files without hidden runtime logic.",
    ),
    "needs_rework": RouteInfo(
        summary= "The same design boundary still holds, but the spec or prompt matrix needs local repair before build.",
        required_outputs= [
            "workflow_package_spec",
            "step_contracts",
            "prompt_contract_matrix",
        ],
        handoff= "Loops on the design step with the same package identity.",
    ),
    "needs_replan": RouteInfo(
        summary= "The chosen addition, role topology, artifact graph, or workflow kind changed materially and the framing step must be revisited.",
        handoff= "Returns to framing rather than patching the existing design locally.",
    ),
}

BUILD_PACKAGE_ROUTE_CONTRACTS = {
    "package_built": RouteInfo(
        summary= "The target workflow shape and its declared support files were written in the repository.",
        required_outputs= [
            "generated_layout",
            "build_report",
        ],
        handoff= "Promotes the generated workflow surface to evaluation.",
    ),
    "needs_rework": RouteInfo(
        summary= "The same accepted design still holds, but the generated files or build evidence need local repair.",
        required_outputs= ["build_report"],
        handoff= "Loops on build without widening the design boundary.",
    ),
    "needs_replan": RouteInfo(
        summary= "The accepted design cannot be implemented as written because the prompt matrix, route grammar, or artifact contract changed materially.",
        handoff= "Returns to the design step for a new authoritative contract.",
    ),
}

EVALUATE_PACKAGE_ROUTE_CONTRACTS = {
    "evaluation_passed": RouteInfo(
        summary= "Verification evidence, publication evidence, and rollback evidence all exist and support publication.",
        required_outputs= [
            "verification_report",
            "promotion_record",
            "rollback_plan",
        ],
        handoff= "Allows the publish gate to mark the package ready.",
    ),
    "needs_rework": RouteInfo(
        summary= "The accepted design still stands, but the built package or evidence pack needs local correction before promotion.",
        required_outputs= ["verification_report"],
        handoff= "Routes back to build for repair without reframing the package.",
    ),
    "needs_replan": RouteInfo(
        summary= "Evaluation proved that the design boundary or verification surface is materially wrong and design must change.",
        handoff= "Returns to design for a new contract rather than patch-only repair.",
    ),
}


__all__ = [
    "BUILD_PACKAGE_ROUTE_CONTRACTS",
    "CandidateSelectionPayload",
    "DESIGN_PACKAGE_ROUTE_CONTRACTS",
    "EVALUATE_PACKAGE_ROUTE_CONTRACTS",
    "FRAME_CANDIDATE_ROUTE_CONTRACTS",
    "WorkflowBuildPayload",
    "WorkflowDesignPayload",
    "WorkflowEvaluationPayload",
]
