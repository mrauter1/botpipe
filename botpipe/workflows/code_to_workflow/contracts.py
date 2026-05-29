"""Route payload contracts for code_to_workflow."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from botpipe import Route, SELF


class BehaviorDistillationPayload(BaseModel):
    """Verifier payload for the behavior distillation step."""

    summary: str = Field(min_length=1)
    behavior_count: int = Field(ge=1)
    evidence_artifacts: list[str] = Field(min_length=1)
    uncovered_areas: list[str] = Field(default_factory=list)
    rework_reason: str | None = None


class WorkflowDesignPayload(BaseModel):
    """Verifier payload for the workflow design step."""

    summary: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    coverage_count: int = Field(ge=1)
    uncovered_required_behaviors: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class BuildValidationPayload(BaseModel):
    """Verifier payload for the generated workflow build and validation step."""

    summary: str = Field(min_length=1)
    changed_paths: list[str] = Field(min_length=1)
    evidence_artifacts: list[str] = Field(min_length=1)
    validation_commands: list[str] = Field(default_factory=list)
    coverage_status: Literal["complete", "needs_rework", "needs_replan"]
    replan_reason: str | None = None


BEHAVIOR_DISTILLATION_ROUTE_CONTRACTS = {
    "behavior_distilled": Route.to(
        "design_botpipe_recreation",
        summary="The source behavior inventory is evidence-backed and ready for workflow design.",
        required_writes=["behavior_inventory", "behavior_inventory_report", "trace_pattern_notes", "behavior_review"],
        handoff="Use the accepted behavior inventory as the authoritative behavior contract.",
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The same distillation boundary holds, but the inventory needs local repair.",
        required_writes=["behavior_review"],
        handoff="Read behavior_review.md and address every required correction before rewriting the inventory.",
    ),
}

WORKFLOW_DESIGN_ROUTE_CONTRACTS = {
    "design_accepted": Route.to(
        "build_and_validate",
        summary="The Botpipe recreation design covers the behavior inventory and is ready to build.",
        required_writes=[
            "workflow_design",
            "step_contracts",
            "prompt_contract_matrix",
            "equivalence_plan",
            "coverage_map",
            "design_review",
        ],
        handoff="Build the generated workflow exactly to the accepted design unless validation proves the design wrong.",
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The same design boundary holds, but the design artifacts need local repair.",
        required_writes=["design_review"],
        handoff="Read design_review.md and address every required correction before rewriting the design.",
    ),
    "needs_replan": Route.to(
        "distill_behavior",
        summary="The behavior contract is incomplete or wrong, so behavior distillation must be revisited.",
        required_writes=["design_review"],
        handoff="Return to behavior distillation and repair the source behavior inventory.",
    ),
}

BUILD_VALIDATION_ROUTE_CONTRACTS = {
    "build_validated": Route.to(
        "publish_generated_workflow",
        summary="The generated workflow exists, validates, and has enough evidence for publication.",
        required_writes=[
            "generated_workflow_root",
            "generated_flow",
            "generated_manifest",
            "generated_layout",
            "validation_report",
            "build_review",
        ],
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The accepted design still holds, but generated files or validation evidence need local repair.",
        required_writes=["build_review"],
        handoff="Read build_review.md and repair the generated workflow before rerunning validation.",
    ),
    "needs_replan": Route.to(
        "design_botpipe_recreation",
        summary="Validation proved the accepted topology or equivalence strategy is wrong.",
        required_writes=["build_review"],
        handoff="Return to design and revise the workflow topology or equivalence plan.",
    ),
}


__all__ = [
    "BEHAVIOR_DISTILLATION_ROUTE_CONTRACTS",
    "BUILD_VALIDATION_ROUTE_CONTRACTS",
    "BehaviorDistillationPayload",
    "BuildValidationPayload",
    "WORKFLOW_DESIGN_ROUTE_CONTRACTS",
    "WorkflowDesignPayload",
]
