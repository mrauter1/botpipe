"""One verifier-owned assessment and a runtime-owned request for each review."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, model_validator

from botpipe.core.primitives import Event


NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PhaseCriterion(StrictModel):
    id: NonEmptyText
    text: NonEmptyText


class ReviewRequest(StrictModel):
    id: NonEmptyText
    step: NonEmptyText
    phase_id: str | None
    criteria: list[PhaseCriterion]


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
    def verdict(self) -> str:
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


# These are process obligations. Implementation and testing use the task's own
# phase criteria instead. An audit can validly discover work needing follow-up.
PROCESS_CRITERIA = {
    "plan": {
        "request_coverage": "The phases cover the request without unrelated work.",
        "executable_plan": "Scope, dependencies, criteria, deliverables, risks and rollback are concrete and executable.",
    },
    "review_phase_item": {
        "bounded_repair": "The repair preserves completed work, phase identity, order and valid live statuses.",
        "executable_item": "The repaired active item is executable and the item review accurately explains the changes.",
    },
    "audit": {
        "grounded_audit": "The audit accounts for the request and actual phase evidence, including reduced assurance from skipped checks.",
        "consistent_findings": "The audit result and gap report accurately agree on remaining work.",
        "actionable_followup": "The revised request is appropriate to the audit decision and any required follow-up is standalone and actionable.",
    },
}

REVIEW_ARTIFACTS = {
    "plan": "plan_review",
    "implement": "impl_review",
    "test": "test_review",
    "review_phase_item": "phase_item_review_report",
    "audit": "audit_review",
}

SUCCESS_ROUTES = {
    "plan": "plan_ready",
    "implement": "implemented",
    "test": "phase_passed",
    "review_phase_item": "phase_item_reviewed",
    "audit": "audit_ready",
}


def begin_review(ctx) -> None:
    """Called after production; verifier-only retries/resume retain this request."""
    step = ctx.meta.step.name
    phase = ctx.state.phase
    criteria = (
        [PhaseCriterion(id=key, text=text) for key, text in PROCESS_CRITERIA[step].items()]
        if step in PROCESS_CRITERIA
        else [criterion.model_copy(deep=True) for criterion in phase.criteria]
    )
    ctx.state.review = ReviewRequest(
        id=uuid4().hex,
        step=step,
        phase_id=phase.id if phase is not None else None,
        criteria=criteria,
    )
    # Production can read the previous report as feedback; verification must
    # write its own. Also avoid validating stale optional output on a question.
    getattr(ctx.artifacts, REVIEW_ARTIFACTS[step]).path.unlink(missing_ok=True)


def load_review(ctx, step: str) -> ReviewReport:
    """Normalize once at the file boundary and check the runtime-owned contract."""
    request = ctx.state.review
    if request is None or request.step != step:
        raise ValueError(f"No current {step} review request; rerun the {step} producer/verifier step.")
    phase = ctx.state.phase
    if request.phase_id != (phase.id if phase is not None else None):
        raise ValueError("Review belongs to a different phase; verify the current phase again.")
    if step in {"implement", "test"} and request.criteria != phase.criteria:
        raise ValueError("Phase criteria changed after review began; verify the revised criteria again.")
    artifact = getattr(ctx.artifacts, REVIEW_ARTIFACTS[step])
    try:
        report = ReviewReport.model_validate_json(artifact.read_text())
    except (OSError, ValidationError) as exc:
        raise ValueError(f"Invalid {step} review at {artifact.path}: {exc}") from exc
    if report.review_id != request.id:
        raise ValueError("Stale review: review_id does not match the current candidate; write a fresh review.")
    expected = {criterion.id for criterion in request.criteria}
    actual = [criterion.id for criterion in report.criteria]
    if len(actual) != len(set(actual)):
        raise ValueError("Review contains duplicate criterion IDs.")
    missing, unknown = expected - set(actual), set(actual) - expected
    if missing or unknown:
        raise ValueError(f"Review must cover exactly the current criteria; missing={sorted(missing)}, unknown={sorted(unknown)}.")
    if report.repair_target == "phase_item" and (step != "implement" or report.verdict != "failed"):
        raise ValueError("phase_item repair is only valid for a failed implementation review.")
    return report


def review_issues(ctx, step: str) -> list[str]:
    try:
        return load_review(ctx, step).issues()
    except ValueError as exc:
        return [str(exc)]


def finish_review(ctx):
    """The report decides acceptance; native questions and runtime failures remain."""
    if ctx.outcome.tag in {"question", "blocked", "failed"}:
        return None
    step = ctx.meta.step.name
    artifact = getattr(ctx.artifacts, REVIEW_ARTIFACTS[step])
    # Preserve the runtime's provider-attributable artifact errors and retry
    # behavior. Only a well-formed report reaches semantic contract validation.
    if not artifact.exists() or not artifact.validate().ok:
        return None
    try:
        report = load_review(ctx, step)
    except ValueError:
        # The existing gate writes the precise diagnostic and repairs this pair.
        return "review_invalid"
    if report.verdict == "blocked":
        return Event("blocked", reason="\n".join(report.issues()))
    if report.verdict == "passed":
        return SUCCESS_ROUTES[step]
    if report.repair_target == "phase_item":
        return "needs_phase_item_review"
    return "audit_needs_repair" if step == "audit" else "needs_rework"
