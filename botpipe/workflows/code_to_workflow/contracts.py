"""Typed verifier decisions for :mod:`code_to_workflow`."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BehaviorDistillationPayload(_Decision):
    verdict: Literal["behavior_distilled", "needs_rework"]
    summary: str = Field(min_length=1)
    behavior_count: int = Field(ge=1)
    evidence_artifacts: list[str] = Field(min_length=1)
    uncovered_areas: list[str] = Field(default_factory=list)
    rework_reason: str | None = None


class WorkflowDesignPayload(_Decision):
    verdict: Literal["design_accepted", "needs_rework", "needs_replan"]
    summary: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    coverage_count: int = Field(ge=1)
    uncovered_required_behaviors: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class BuildValidationPayload(_Decision):
    verdict: Literal["build_validated", "needs_rework", "needs_replan"]
    summary: str = Field(min_length=1)
    changed_paths: list[str] = Field(min_length=1)
    evidence_artifacts: list[str] = Field(min_length=1)
    validation_commands: list[str] = Field(default_factory=list)
    coverage_status: Literal["complete", "needs_rework", "needs_replan"]
    replan_reason: str | None = None


__all__ = [
    "BehaviorDistillationPayload",
    "BuildValidationPayload",
    "WorkflowDesignPayload",
]
