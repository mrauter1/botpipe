"""Strict, content-addressed optimizer v2 recommendation records."""

from __future__ import annotations
import hashlib, json
from typing import Annotated, Literal, TypeAlias
from pydantic import BaseModel, ConfigDict, Field, field_validator

CANDIDATE_SET_SCHEMA = "botpipe.workflow_optimization.candidate_set/v2"
CANDIDATE_REVIEW_SCHEMA = "botpipe.workflow_optimization.candidate_review/v2"
RECOMMENDATION_RECEIPT_SCHEMA = "botpipe.workflow_optimization.publication_receipt/v2"
REFINEMENT_HANDOFF_SCHEMA = "botpipe.workflow_refinement_evidence/v2"
CandidateKind: TypeAlias = Literal[
    "producer_prompt", "verifier_rubric", "tokens", "workflow", "evaluation_case"
]
NextAction: TypeAlias = Literal["implement_candidate", "collect_evidence", "no_change"]


class StrictRecord(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, populate_by_name=True, serialize_by_alias=True
    )


def canonical_record_bytes(
    value: BaseModel | dict[str, object], *, exclude: set[str] = frozenset()
) -> bytes:
    payload = (
        value.model_dump(mode="json", by_alias=True)
        if isinstance(value, BaseModel)
        else dict(value)
    )
    for key in exclude:
        payload.pop(key, None)
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def content_id(
    prefix: str, value: BaseModel | dict[str, object], *, exclude: set[str]
) -> str:
    return f"{prefix}_{hashlib.sha256(canonical_record_bytes(value,exclude=exclude)).hexdigest()}"


class ValidationPlan(StrictRecord):
    description: str = Field(min_length=1)
    checks: list[str] = Field(min_length=1)
    falsification: str = Field(min_length=1)

    @field_validator("checks")
    @classmethod
    def checks_valid(cls, v):
        if any(not x.strip() for x in v) or len(v) != len(set(v)):
            raise ValueError("validation checks must be non-empty and unique")
        return v


class ProducerPromptPayload(StrictRecord):
    prompt_paths: list[str] = Field(min_length=1)
    replacement_strategy: str = Field(min_length=1)


class VerifierRubricPayload(StrictRecord):
    rubric_paths: list[str] = Field(min_length=1)
    acceptance_change: str = Field(min_length=1)


class TokenPayload(StrictRecord):
    target_paths: list[str] = Field(min_length=1)
    compression_change: str = Field(min_length=1)
    semantic_invariants: list[str] = Field(min_length=1)


class WorkflowPayload(StrictRecord):
    target_paths: list[str] = Field(min_length=1)
    workflow_change: str = Field(min_length=1)


class EvaluationCasePayload(StrictRecord):
    suite_target: str = Field(min_length=1)
    case_descriptions: list[str] = Field(min_length=1)


class CandidateBase(StrictRecord):
    candidate_id: str = Field(pattern=r"^candidate_[0-9a-f]{64}$")
    title: str = Field(min_length=1)
    targets: list[str] = Field(min_length=1)
    cited_observation_ids: list[str] = Field(min_length=1)
    proposed_change: str = Field(min_length=1)
    expected_effect: str = Field(min_length=1)
    risks: list[str] = Field(min_length=1)
    validation_plan: ValidationPlan

    @field_validator("targets", "cited_observation_ids", "risks")
    @classmethod
    def unique_values(cls, v):
        if any(not x.strip() for x in v) or len(v) != len(set(v)):
            raise ValueError("candidate list entries must be non-empty and unique")
        return v

    def expected_candidate_id(self):
        return content_id("candidate", self, exclude={"candidate_id"})

    def verify_identity(self):
        if self.candidate_id != self.expected_candidate_id():
            raise ValueError(
                f"candidate_id does not match candidate content: {self.candidate_id}"
            )


class ProducerPromptCandidate(CandidateBase):
    kind: Literal["producer_prompt"]
    payload: ProducerPromptPayload


class VerifierRubricCandidate(CandidateBase):
    kind: Literal["verifier_rubric"]
    payload: VerifierRubricPayload


class TokenCandidate(CandidateBase):
    kind: Literal["tokens"]
    payload: TokenPayload


class WorkflowCandidate(CandidateBase):
    kind: Literal["workflow"]
    payload: WorkflowPayload


class EvaluationCaseCandidate(CandidateBase):
    kind: Literal["evaluation_case"]
    payload: EvaluationCasePayload


Candidate: TypeAlias = Annotated[
    ProducerPromptCandidate
    | VerifierRubricCandidate
    | TokenCandidate
    | WorkflowCandidate
    | EvaluationCaseCandidate,
    Field(discriminator="kind"),
]


class CandidateSet(StrictRecord):
    schema_version: Literal["botpipe.workflow_optimization.candidate_set/v2"] = Field(
        default=CANDIDATE_SET_SCHEMA, alias="schema"
    )
    candidate_set_id: str = Field(pattern=r"^candidate_set_[0-9a-f]{64}$")
    selected_workflow: str = Field(min_length=1)
    evidence_snapshot_id: str = Field(min_length=1)
    baseline_surface_manifest_id: str = Field(min_length=1)
    candidates: list[Candidate]
    next_action: NextAction
    no_candidate_reason: str | None = None

    def expected_candidate_set_id(self):
        return content_id("candidate_set", self, exclude={"candidate_set_id"})

    def verify_identity(self):
        if self.candidate_set_id != self.expected_candidate_set_id():
            raise ValueError("candidate_set_id does not match CandidateSet content")
        for candidate in self.candidates:
            candidate.verify_identity()


class ReviewFinding(StrictRecord):
    candidate_id: str = Field(min_length=1)
    severity: Literal["error", "warning", "note"]
    message: str = Field(min_length=1)


class CandidateReview(StrictRecord):
    schema_version: Literal["botpipe.workflow_optimization.candidate_review/v2"] = (
        Field(default=CANDIDATE_REVIEW_SCHEMA, alias="schema")
    )
    review_id: str = Field(pattern=r"^candidate_review_[0-9a-f]{64}$")
    candidate_set_id: str = Field(min_length=1)
    evidence_snapshot_id: str = Field(min_length=1)
    baseline_surface_manifest_id: str = Field(min_length=1)
    accepted: bool
    reviewed_candidate_ids: list[str]
    findings: list[ReviewFinding]

    def expected_review_id(self):
        return content_id("candidate_review", self, exclude={"review_id"})

    def verify_identity(self):
        if self.review_id != self.expected_review_id():
            raise ValueError("review_id does not match review content")


class SupportingArtifact(StrictRecord):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: int = Field(ge=0)


class PublicationReceipt(StrictRecord):
    schema_version: Literal["botpipe.workflow_optimization.publication_receipt/v2"] = (
        Field(default=RECOMMENDATION_RECEIPT_SCHEMA, alias="schema")
    )
    status: Literal["accepted", "incomplete"]
    selected_workflow: str = Field(min_length=1)
    evidence_snapshot_id: str | None
    evidence_snapshot_path: str | None
    baseline_surface_manifest_id: str | None
    baseline_surface_manifest_path: str | None
    candidate_set_id: str | None
    candidate_set_path: str | None
    review_id: str | None
    review_path: str | None = None
    reviewed_candidate_ids: list[str]
    improvement: Literal["not_evaluated"] = "not_evaluated"
    next_action: NextAction | None
    refinement_handoff_path: str | None
    report_path: str | None
    supporting_artifacts: list[SupportingArtifact] = Field(default_factory=list)
    stop_reason: str | None


class HandoffCandidate(StrictRecord):
    candidate_id: str = Field(min_length=1)
    kind: CandidateKind
    title: str = Field(min_length=1)


class RefinementHandoff(StrictRecord):
    schema_version: Literal["botpipe.workflow_refinement_evidence/v2"] = Field(
        default=REFINEMENT_HANDOFF_SCHEMA, alias="schema"
    )
    target_workflow_id: str = Field(min_length=1)
    evidence_snapshot_id: str = Field(min_length=1)
    evidence_snapshot_path: str = Field(min_length=1)
    baseline_surface_manifest_id: str = Field(min_length=1)
    baseline_surface_manifest_path: str = Field(min_length=1)
    candidate_set_id: str = Field(min_length=1)
    candidate_set_path: str = Field(min_length=1)
    candidates: list[HandoffCandidate]


__all__ = [name for name in tuple(globals()) if not name.startswith("_")]
