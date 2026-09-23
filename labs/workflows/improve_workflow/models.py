"""Inputs and useful outcomes for one evidence-backed workflow improvement."""

from __future__ import annotations

import sys
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from botpipe_optimizer.candidate_validation import ValidationResult
from botpipe_optimizer.evidence import EvidenceSnapshot
from botpipe_optimizer.records import CandidateReview, CandidateSet, PublicationReceipt


class ImproveWorkflowParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_workflow: str = Field(min_length=1)
    objective: Literal["reliability", "token_usage", "latency"] = "reliability"
    run_refs: list[str] = Field(default_factory=list)
    history_limit: int = Field(default=25, gt=0)
    evaluation_spec_path: str | None = None
    target_test_argv: list[str] = Field(
        default_factory=lambda: [sys.executable, "-m", "pytest", "-q"]
    )
    max_revisions: int = Field(default=2, ge=0)
    max_provider_turns: int = Field(default=12, gt=0)
    provider_timeout: float = Field(default=600, gt=0, allow_inf_nan=False)
    max_provider_seconds: float = Field(default=1800, gt=0, allow_inf_nan=False)
    validation_timeout: float = Field(default=600, gt=0, allow_inf_nan=False)
    max_evidence_bytes: int = Field(default=50 * 1024 * 1024, gt=0)
    max_snapshot_bytes: int = Field(default=50 * 1024 * 1024, gt=0)
    max_output_bytes: int = Field(default=10 * 1024 * 1024, gt=0)

    @field_validator("selected_workflow", "evaluation_spec_path")
    @classmethod
    def nonblank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("workflow references and paths must not be blank")
        return value

    @field_validator("run_refs")
    @classmethod
    def valid_refs(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)) or any(
            not value.strip() or value.count("/") > 1 for value in values
        ):
            raise ValueError("run_refs must be unique run IDs or task/run references")
        return values

    @field_validator("target_test_argv")
    @classmethod
    def valid_argv(cls, value: list[str]) -> list[str]:
        if not value or any(not item.strip() for item in value):
            raise ValueError("target_test_argv must be a nonempty argument list")
        return value


class Recommendation(BaseModel):
    evidence_snapshot: EvidenceSnapshot
    candidate_set: CandidateSet
    review: CandidateReview | None = None
    receipt: PublicationReceipt | None = None


class ChangeReview(BaseModel):
    accepted: bool
    summary: str = Field(min_length=1)
    required_changes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_verdict(self):
        if self.accepted and self.required_changes:
            raise ValueError("an accepted review cannot require changes")
        return self


class CandidateResult(BaseModel):
    """A candidate and the exact validation performed on its captured source."""

    root: str
    changed_paths: list[str]
    validation: ValidationResult
    review: ChangeReview | None = None
    evaluation: dict[str, Any]


class ImproveWorkflowResult(BaseModel):
    selected_workflow: str
    outcome: Literal[
        "collect_evidence",
        "no_change",
        "rejected",
        "candidate_ready",
        "improved",
        "regressed",
        "no_material_change",
        "inconclusive",
    ]
    summary: str
    recommendation: Recommendation
    candidate: CandidateResult | None = None
    provider_budget: dict[str, Any]
