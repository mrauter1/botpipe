"""Inputs and useful outcomes for one evidence-backed workflow improvement."""

from __future__ import annotations

import sys
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from botpipe_optimizer.candidate_validation import ValidationResult
from botpipe_optimizer.evidence import EvidenceSnapshot
from botpipe_optimizer.records import CandidateReview, CandidateSet, PublicationReceipt


class EvidenceLink(BaseModel):
    """A diagnostic claim and the kind of evidence that supports it."""

    model_config = ConfigDict(extra="forbid")

    basis: Literal["observation", "source", "inference"]
    statement: str = Field(min_length=1)
    observation_ids: list[str] = Field(default_factory=list)
    source_paths: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def basis_is_explicit(self):
        if self.basis == "observation" and not self.observation_ids:
            raise ValueError("observation evidence must name an observation")
        if self.basis == "source" and not self.source_paths:
            raise ValueError("source evidence must name a captured source path")
        if self.basis == "observation" and self.source_paths:
            raise ValueError("observation evidence cannot also claim source inspection")
        if self.basis == "source" and self.observation_ids:
            raise ValueError("source evidence cannot also claim a run observation")
        if self.basis == "inference" and (self.observation_ids or self.source_paths):
            raise ValueError("inference must not masquerade as direct evidence")
        if len(self.observation_ids) != len(set(self.observation_ids)):
            raise ValueError("observation evidence IDs must be unique")
        if len(self.source_paths) != len(set(self.source_paths)):
            raise ValueError("source evidence paths must be unique")
        return self


class ScopeAssessment(BaseModel):
    """One semantic assessment, without pretending every scope was observed."""

    model_config = ConfigDict(extra="forbid")

    scope: Literal["whole_workflow", "step"]
    step_name: str | None = None
    classification: Literal[
        "failure", "opportunity", "strength", "uncertain", "not_assessed"
    ]
    dimensions: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1)
    evidence: list[EvidenceLink] = Field(default_factory=list)
    uncertainty: str | None = None

    @model_validator(mode="after")
    def scope_is_coherent(self):
        if self.scope == "step" and not (self.step_name and self.step_name.strip()):
            raise ValueError("a step assessment must name the step")
        if self.scope == "whole_workflow" and self.step_name is not None:
            raise ValueError("a whole-workflow assessment cannot name one step")
        if self.classification in {"uncertain", "not_assessed"} and not (
            self.uncertainty and self.uncertainty.strip()
        ):
            raise ValueError("uncertain or unassessed scopes must explain the gap")
        if self.classification in {"failure", "opportunity", "strength"} and not (
            self.evidence
        ):
            raise ValueError("affirmative classifications must identify their evidence")
        if any(not item.strip() for item in self.dimensions):
            raise ValueError("assessment dimensions must be non-empty")
        return self


class SuccessCriterion(BaseModel):
    """A context-specific criterion frozen before a candidate is proposed."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    applies_to: str = Field(min_length=1)
    description: str = Field(min_length=1)
    evidence_needed: list[str] = Field(min_length=1)
    falsification: str = Field(min_length=1)


class DiagnosticAssessment(BaseModel):
    """Model-led interpretation of intent, traces, source, and uncertainty."""

    model_config = ConfigDict(extra="forbid")

    workflow_intent: str = Field(min_length=1)
    intent_evidence: list[EvidenceLink] = Field(min_length=1)
    scope_assessments: list[ScopeAssessment] = Field(min_length=1)
    rubric: list[SuccessCriterion] = Field(min_length=1)
    uncertainties: list[str] = Field(default_factory=list)


class ImproveWorkflowParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_workflow: str = Field(min_length=1)
    objective: str = Field(
        default="Improve fitness for the workflow purpose while preserving obligations",
        min_length=1,
    )
    metric_view: Literal["reliability", "token_usage", "latency"] | None = None
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

    @field_validator("selected_workflow", "evaluation_spec_path", "objective")
    @classmethod
    def nonblank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError(
                "workflow references, paths, and priorities must not be blank"
            )
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
    assessment: DiagnosticAssessment
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
