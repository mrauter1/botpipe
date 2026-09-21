"""Typed review contracts shared by all devloop verifier turns."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PhaseCriterion(StrictModel):
    id: NonEmptyText
    text: NonEmptyText


class Assessment(StrictModel):
    verdict: Literal["passed", "failed", "blocked"]
    evidence: list[NonEmptyText]
    reason: NonEmptyText

    @model_validator(mode="after")
    def require_pass_evidence(self):
        if self.verdict == "passed" and not self.evidence:
            raise ValueError("a passing assessment needs supporting evidence")
        return self


class CriterionAssessment(Assessment):
    id: NonEmptyText


class ReviewReport(StrictModel):
    review_id: NonEmptyText
    criteria: list[CriterionAssessment]
    findings: list[Assessment] = Field(default_factory=list)
    summary: str = ""
    repair_target: Literal["candidate", "phase_item"] = "candidate"

    @property
    def verdict(self) -> Literal["passed", "failed", "blocked"]:
        verdicts = {item.verdict for item in (*self.criteria, *self.findings)}
        if "blocked" in verdicts:
            return "blocked"
        return "failed" if "failed" in verdicts else "passed"

    def issues(self) -> list[str]:
        return [
            f"{getattr(item, 'id', 'Additional finding')}: {item.reason}"
            for item in (*self.criteria, *self.findings)
            if item.verdict != "passed"
        ]


PROCESS_CRITERIA: dict[str, dict[str, str]] = {
    "plan": {
        "request_coverage": "The phases cover the request without unrelated work.",
        "executable_plan": "Scope, dependencies, criteria, deliverables, risks and rollback are executable.",
    },
    "phase_item": {
        "bounded_repair": "The repair preserves completed work, phase identity, order and valid statuses.",
        "executable_item": "The active phase is executable and the review explains the changes.",
    },
    "audit": {
        "grounded_audit": "The audit accounts for the request and actual phase evidence.",
        "consistent_findings": "The audit result and gap report agree on remaining work.",
        "actionable_followup": "Any revised request is standalone and actionable.",
    },
}


def validate_review(
    report: ReviewReport, review_id: str, criteria: list[PhaseCriterion]
) -> list[str]:
    issues: list[str] = []
    if report.review_id != review_id:
        issues.append("review_id does not match the current candidate")
    expected = {criterion.id for criterion in criteria}
    actual = [criterion.id for criterion in report.criteria]
    if len(actual) != len(set(actual)):
        issues.append("review contains duplicate criterion IDs")
    if expected != set(actual):
        issues.append(
            f"review must cover exactly the current criteria; missing={sorted(expected - set(actual))}, "
            f"unknown={sorted(set(actual) - expected)}"
        )
    return [*issues, *report.issues()]


__all__ = [
    "Assessment",
    "CriterionAssessment",
    "PhaseCriterion",
    "PROCESS_CRITERIA",
    "ReviewReport",
    "StrictModel",
    "validate_review",
]
