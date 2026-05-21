"""Default devloop workflow."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from botpipe import (
    FAIL,
    FINISH,
    Prompt,
    Route,
    Session,
    ValidationResult,
    Workflow,
    produce_verify_step,
    python_step,
    validation_step,
)
from botpipe.core import Artifact
from botpipe.extensions import SessionPaths

from .conventions import DevLoopSessionPathStrategy, phase_dir_key
from .runtime_artifacts import DevLoopRuntimeArtifacts


PHASE_PLAN_VERSION = 1
AUDIT_RESULT_VERSION = 1

PHASE_STATUS_PLANNED = "planned"
PHASE_STATUS_IN_PROGRESS = "in_progress"
PHASE_STATUS_COMPLETED = "completed"
PHASE_STATUS_BLOCKED = "blocked"
PHASE_STATUS_DEFERRED = "deferred"

PHASE_STATUSES = {
    PHASE_STATUS_PLANNED,
    PHASE_STATUS_IN_PROGRESS,
    PHASE_STATUS_COMPLETED,
    PHASE_STATUS_BLOCKED,
    PHASE_STATUS_DEFERRED,
}

AUDIT_STATUS_PASSED = "passed"
AUDIT_STATUS_NEEDS_FOLLOWUP = "needs_followup"

AUDIT_STATUSES = {
    AUDIT_STATUS_PASSED,
    AUDIT_STATUS_NEEDS_FOLLOWUP,
}

AUDIT_SEVERITIES = {
    "low",
    "medium",
    "high",
    "critical",
}

FOLLOWUP_STATUS_STARTED = "started"
FOLLOWUP_STATUS_SKIPPED = "skipped"
FOLLOWUP_STATUS_FAILED = "failed"

_INACTIVE_PHASE_DIR_KEY = "_inactive"
_CHECKBOX_RE = re.compile(r"(?m)^\s*[-*]\s+\[(?P<mark>[ xX])\](?:\s|$)")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PhaseCriterion(StrictModel):
    id: str
    text: str


class PhaseScope(StrictModel):
    in_scope: list[str]
    out_of_scope: list[str]


class PhasePlanPhase(StrictModel):
    phase_id: str
    title: str
    objective: str
    status: str
    scope: PhaseScope
    dependencies: list[str]
    criteria: list[PhaseCriterion]
    deliverables: list[str]
    risks: list[str]
    rollback: list[str]


class PhasePlanDocument(StrictModel):
    version: int
    task_id: str
    request_snapshot_ref: str
    status: str
    phases: list[PhasePlanPhase]


class Phase(StrictModel):
    id: str
    dir_key: str
    title: str
    objective: str
    status: str
    scope: PhaseScope
    dependencies: list[str]
    criteria: list[PhaseCriterion]
    deliverables: list[str]
    risks: list[str]
    rollback: list[str]


class AuditGap(StrictModel):
    id: str
    severity: str
    summary: str
    evidence: list[str]
    followup: str


class AuditResult(StrictModel):
    version: int
    task_id: str
    request_snapshot_ref: str
    status: str
    summary: str
    gaps: list[AuditGap]


class FollowupRunResult(StrictModel):
    status: str
    reason: str | None = None
    followup_depth: int
    auto_followup_max_depth: int
    child_workflow_name: str | None = None
    child_run_id: str | None = None
    child_status: str | None = None
    child_terminal: str | None = None
    child_last_event: str | None = None
    child_run_folder: str | None = None
    child_request_file: str | None = None


class PhasePlanError(ValueError):
    """Raised when the devloop phase-plan contract is not satisfied."""


class AuditResultError(ValueError):
    """Raised when the devloop audit-result contract is not satisfied."""


def _invalid(message: str, details: Iterable[str] = ()) -> ValidationResult:
    return ValidationResult.invalid(message, details=tuple(details))


def _validate_plan_completion(ctx) -> ValidationResult:
    issues: list[str] = []

    try:
        phases = _load_phase_plan(
            _read_artifact_text(ctx.artifacts.phase_plan, "phase plan"),
            expected_task_id=ctx.task_id,
            expected_request_snapshot_ref=str(ctx.request.file),
        )
    except PhasePlanError as exc:
        phases = []
        issues.append(str(exc))

    issues.extend(_checklist_issues(ctx.artifacts.plan_criteria, "plan criteria"))

    if issues:
        return _invalid("Plan completion gate failed.", issues)

    ctx.state.phases = phases
    ctx.state.phase_index = -1
    ctx.state.phase = None
    ctx.state.phase_dir_key = _INACTIVE_PHASE_DIR_KEY
    ctx.state.audit_status = None
    return ValidationResult.valid()


def _validate_implement_completion(ctx) -> ValidationResult:
    issues = _checklist_issues(ctx.artifacts.impl_criteria, "implementation criteria")
    if issues:
        return _invalid("Implementation completion gate failed.", issues)
    return ValidationResult.valid()


def _validate_test_completion(ctx) -> ValidationResult:
    issues = _checklist_issues(ctx.artifacts.test_criteria, "test criteria")
    if issues:
        return _invalid("Test completion gate failed.", issues)
    return ValidationResult.valid()


def _validate_audit_completion(ctx) -> ValidationResult:
    issues: list[str] = []
    audit_result: AuditResult | None = None

    try:
        audit_result = _load_audit_result(
            _read_artifact_text(
                ctx.artifacts.audit_result,
                "audit result",
                error_cls=AuditResultError,
            ),
            expected_task_id=ctx.task_id,
            expected_request_snapshot_ref=str(ctx.request.file),
        )
    except AuditResultError as exc:
        issues.append(str(exc))

    issues.extend(_non_empty_artifact_issues(ctx.artifacts.gap_report, "gap report"))
    issues.extend(_checklist_issues(ctx.artifacts.audit_criteria, "audit criteria"))

    if audit_result is not None and audit_result.status == AUDIT_STATUS_NEEDS_FOLLOWUP:
        issues.extend(_non_empty_artifact_issues(ctx.artifacts.revised_request, "revised request"))

    if issues:
        return _invalid("Audit completion gate failed.", issues)

    ctx.state.audit_status = audit_result.status if audit_result is not None else None
    return ValidationResult.valid()


class DevLoop(Workflow):
    """Plan, implement, test, audit, and optionally follow up on a software change."""

    name = "devloop"

    class Params(BaseModel):
        followup_depth: int = 0
        auto_followup_max_depth: int = 3
        skip_test_phase: bool = Field(
            default=False,
            description="Skip the per-phase test producer/verifier step while writing explicit skipped-test artifacts.",
        )

    class State(BaseModel):
        phases: list[Phase] = Field(default_factory=list)
        phase_index: int = -1
        phase: Phase | None = None
        phase_dir_key: str = _INACTIVE_PHASE_DIR_KEY
        audit_status: str | None = None

    plan_session = Session(open=True)
    phase_session = Session()
    audit_session = Session(open=True)

    request = Artifact.text(
        "{{ run.folder }}/request.md",
        name="request",
        required=True,
    )

    phase_plan = Artifact.json(
        "{{ task.folder }}/plan/phase_plan.json",
        schema=PhasePlanDocument,
        name="phase_plan",
    )
    plan_criteria = Artifact.md(
        "{{ task.folder }}/plan/criteria.md",
        name="plan_criteria",
    )
    plan_feedback = Artifact.md(
        "{{ task.folder }}/plan/feedback.md",
        name="plan_feedback",
    )
    plan_gate_feedback = Artifact.md(
        "{{ task.folder }}/plan/completion_gate_feedback.md",
        name="plan_gate_feedback",
    )

    impl_notes = Artifact.md(
        "{{ task.folder }}/implement/phases/{{ state.phase_dir_key }}/implementation_notes.md",
        name="impl_notes",
    )
    impl_criteria = Artifact.md(
        "{{ task.folder }}/implement/phases/{{ state.phase_dir_key }}/criteria.md",
        name="impl_criteria",
    )
    impl_feedback = Artifact.md(
        "{{ task.folder }}/implement/phases/{{ state.phase_dir_key }}/feedback.md",
        name="impl_feedback",
    )
    impl_gate_feedback = Artifact.md(
        "{{ task.folder }}/implement/phases/{{ state.phase_dir_key }}/completion_gate_feedback.md",
        name="impl_gate_feedback",
    )

    test_strat = Artifact.md(
        "{{ task.folder }}/test/phases/{{ state.phase_dir_key }}/test_strategy.md",
        name="test_strat",
    )
    test_criteria = Artifact.md(
        "{{ task.folder }}/test/phases/{{ state.phase_dir_key }}/criteria.md",
        name="test_criteria",
    )
    test_feedback = Artifact.md(
        "{{ task.folder }}/test/phases/{{ state.phase_dir_key }}/feedback.md",
        name="test_feedback",
    )
    test_gate_feedback = Artifact.md(
        "{{ task.folder }}/test/phases/{{ state.phase_dir_key }}/completion_gate_feedback.md",
        name="test_gate_feedback",
    )

    audit_evidence = Artifact.md(
        "{{ task.folder }}/audit/evidence.md",
        name="audit_evidence",
    )
    audit_result = Artifact.json(
        "{{ task.folder }}/audit/audit_result.json",
        schema=AuditResult,
        name="audit_result",
    )
    gap_report = Artifact.md(
        "{{ task.folder }}/audit/gap_report.md",
        name="gap_report",
    )
    revised_request = Artifact.md(
        "{{ task.folder }}/audit/revised_request.md",
        name="revised_request",
    )
    audit_criteria = Artifact.md(
        "{{ task.folder }}/audit/criteria.md",
        name="audit_criteria",
    )
    audit_feedback = Artifact.md(
        "{{ task.folder }}/audit/feedback.md",
        name="audit_feedback",
    )
    audit_gate_feedback = Artifact.md(
        "{{ task.folder }}/audit/completion_gate_feedback.md",
        name="audit_gate_feedback",
    )
    followup_result = Artifact.json(
        "{{ task.folder }}/audit/followup_result.json",
        schema=FollowupRunResult,
        name="followup_result",
    )

    plan = produce_verify_step(
        producer_prompt=Prompt.file("prompts/plan_producer.md"),
        verifier_prompt=Prompt.file("prompts/plan_verifier.md"),
        session=plan_session,
        requires=[request],
        reads=[plan_feedback, plan_gate_feedback],
        producer_writes=[phase_plan],
        verifier_writes=[plan_criteria, plan_feedback],
        routes={
            "plan_ready": Route.to(
                "validate_plan_completion",
                required_writes=("phase_plan", "plan_criteria"),
            ),
            "needs_replan": "plan",
        },
    )

    validate_plan_completion = validation_step(
        _validate_plan_completion,
        name="validate_plan_completion",
        feedback=plan_gate_feedback,
        reads=[phase_plan, plan_criteria],
        routes={
            "plan_checked": "activate_next_phase",
            "plan_needs_repair": "plan",
        },
        success="plan_checked",
        repair="plan_needs_repair",
    )

    implement = produce_verify_step(
        producer_prompt=Prompt.file("prompts/implement_producer.md"),
        verifier_prompt=Prompt.file("prompts/implement_verifier.md"),
        session=phase_session,
        requires=[phase_plan],
        reads=[impl_feedback, impl_gate_feedback],
        producer_writes=[impl_notes],
        verifier_writes=[impl_criteria, impl_feedback],
        routes={
            "implemented": Route.to(
                "validate_implement_completion",
                required_writes=("impl_notes", "impl_criteria"),
            ),
            "needs_replan": "plan",
        },
    )

    validate_implement_completion = validation_step(
        _validate_implement_completion,
        name="validate_implement_completion",
        feedback=impl_gate_feedback,
        reads=[impl_criteria],
        routes={
            "implement_checked": "maybe_test",
            "implement_needs_repair": "implement",
        },
        success="implement_checked",
        repair="implement_needs_repair",
    )

    @python_step(
        name="maybe_test",
        reads=[phase_plan, impl_notes],
        writes=[test_strat, test_criteria, test_feedback],
        routes={
            "run_tests": "test",
            "tests_skipped": "validate_test_completion",
        },
    )
    def maybe_test(ctx):
        if not ctx.params.skip_test_phase:
            return "run_tests"

        phase_id = ctx.state.phase.id if ctx.state.phase is not None else "unknown"
        phase_title = ctx.state.phase.title if ctx.state.phase is not None else phase_id
        ctx.artifacts.test_strat.write_text(
            "\n".join(
                (
                    f"# Test Strategy: {phase_id}",
                    "",
                    "## Summary",
                    f"The test phase for `{phase_title}` was intentionally skipped because "
                    "`skip_test_phase=true` was set for this run.",
                    "",
                    "## Validation scope",
                    "- No test producer/verifier turn was run for this phase.",
                    "- Implementation completion was still checked before the skip gate advanced.",
                    "",
                    "## Residual risk",
                    "Skipping this phase removes independent validation for the active phase and should be used only "
                    "when the caller accepts reduced workflow assurance.",
                    "",
                )
            )
        )
        ctx.artifacts.test_criteria.write_text(
            "\n".join(
                (
                    f"# Test Criteria: {phase_id}",
                    "",
                    "- [x] Test phase was intentionally skipped by workflow parameter `skip_test_phase=true`.",
                    "- [x] Implementation completion gate passed before the skipped-test marker was written.",
                    "",
                )
            )
        )
        ctx.artifacts.test_feedback.write_text(
            "\n".join(
                (
                    f"# Test Feedback: {phase_id}",
                    "",
                    "## Decision",
                    "Skipped",
                    "",
                    "## Findings",
                    "- The test phase was intentionally skipped by workflow parameter `skip_test_phase=true`.",
                    "- This is reduced validation, not a passing test result.",
                    "",
                )
            )
        )
        return "tests_skipped"

    test = produce_verify_step(
        producer_prompt=Prompt.file("prompts/test_producer.md"),
        verifier_prompt=Prompt.file("prompts/test_verifier.md"),
        session=phase_session,
        requires=[phase_plan, impl_notes],
        reads=[test_feedback, test_gate_feedback],
        producer_writes=[test_strat],
        verifier_writes=[test_criteria, test_feedback],
        routes={
            "phase_passed": Route.to(
                "validate_test_completion",
                required_writes=("test_strat", "test_criteria"),
            ),
            "needs_replan": "plan",
        },
    )

    validate_test_completion = validation_step(
        _validate_test_completion,
        name="validate_test_completion",
        feedback=test_gate_feedback,
        reads=[test_criteria],
        routes={
            "test_checked": "activate_next_phase",
            "test_needs_repair": "test",
        },
        success="test_checked",
        repair="test_needs_repair",
    )

    audit = produce_verify_step(
        producer_prompt=Prompt.file("prompts/audit_producer.md"),
        verifier_prompt=Prompt.file("prompts/audit_verifier.md"),
        session=audit_session,
        requires=[phase_plan, audit_evidence],
        reads=[audit_feedback, audit_gate_feedback],
        producer_writes=[audit_result, gap_report, revised_request],
        verifier_writes=[audit_criteria, audit_feedback],
        routes={
            "audit_ready": Route.to(
                "validate_audit_completion",
                required_writes=(
                    "audit_result",
                    "gap_report",
                    "audit_criteria",
                    "audit_feedback",
                ),
            ),
            "audit_needs_repair": "audit",
        },
    )

    validate_audit_completion = validation_step(
        _validate_audit_completion,
        name="validate_audit_completion",
        feedback=audit_gate_feedback,
        reads=[audit_result, gap_report, revised_request, audit_criteria],
        routes={
            "audit_checked": "finish_audit",
            "audit_needs_repair": "audit",
        },
        success="audit_checked",
        repair="audit_needs_repair",
    )

    extensions = (
        SessionPaths(DevLoopSessionPathStrategy()),
        DevLoopRuntimeArtifacts(),
    )

    @python_step(
        name="activate_next_phase",
        reads=[phase_plan],
        writes=[phase_plan],
        routes={
            "phase_selected": "implement",
            "all_phases_complete": "collect_audit_evidence",
        },
    )
    def activate_next_phase(ctx):
        if ctx.state.phase is not None:
            _set_phase_status(ctx, ctx.state.phase.id, PHASE_STATUS_COMPLETED)

        next_index = ctx.state.phase_index + 1
        if next_index >= len(ctx.state.phases):
            ctx.state.phase = None
            ctx.state.phase_dir_key = _INACTIVE_PHASE_DIR_KEY
            _set_phase_plan_status(ctx, PHASE_STATUS_COMPLETED)
            return "all_phases_complete"

        phase = ctx.state.phases[next_index]
        ctx.state.phase_index = next_index
        ctx.state.phase = phase
        ctx.state.phase_dir_key = phase.dir_key
        _set_phase_status(ctx, phase.id, PHASE_STATUS_IN_PROGRESS)
        ctx.open_session("phase_session", scope=phase.id)
        return "phase_selected"

    @python_step(
        name="collect_audit_evidence",
        reads=[phase_plan],
        writes=[audit_evidence],
        routes={"audit_evidence_ready": "audit"},
    )
    def collect_audit_evidence(ctx):
        ctx.open_session("audit_session")
        ctx.artifacts.audit_evidence.write_text(_build_audit_evidence(ctx))
        return "audit_evidence_ready"

    @python_step(
        name="finish_audit",
        reads=[audit_result],
        routes={
            "audit_passed": FINISH,
            "needs_followup": "start_followup_run",
        },
    )
    def finish_audit(ctx):
        audit_result = _load_audit_result(
            _read_artifact_text(
                ctx.artifacts.audit_result,
                "audit result",
                error_cls=AuditResultError,
            ),
            expected_task_id=ctx.task_id,
            expected_request_snapshot_ref=str(ctx.request.file),
        )
        ctx.state.audit_status = audit_result.status
        if audit_result.status == AUDIT_STATUS_NEEDS_FOLLOWUP:
            return "needs_followup"
        return "audit_passed"

    @python_step(
        name="start_followup_run",
        reads=[audit_result, revised_request],
        writes=[followup_result],
        routes={
            "followup_started": FINISH,
            "followup_skipped": FINISH,
            "followup_failed": FAIL,
        },
    )
    def start_followup_run(ctx):
        followup_depth = _safe_int(getattr(ctx.params, "followup_depth", 0), default=0)
        max_depth = _safe_int(getattr(ctx.params, "auto_followup_max_depth", 3), default=3)

        if followup_depth >= max_depth:
            ctx.artifacts.followup_result.write_json(
                {
                    "status": FOLLOWUP_STATUS_SKIPPED,
                    "reason": "auto_followup_max_depth_reached",
                    "followup_depth": followup_depth,
                    "auto_followup_max_depth": max_depth,
                    "child_workflow_name": None,
                    "child_run_id": None,
                    "child_status": None,
                    "child_terminal": None,
                    "child_last_event": None,
                    "child_run_folder": None,
                    "child_request_file": None,
                }
            )
            return "followup_skipped"

        revised_request_text = _read_artifact_text(
            ctx.artifacts.revised_request,
            "revised request",
            error_cls=AuditResultError,
        ).strip()
        if not revised_request_text:
            ctx.artifacts.followup_result.write_json(
                {
                    "status": FOLLOWUP_STATUS_FAILED,
                    "reason": "revised_request_empty",
                    "followup_depth": followup_depth,
                    "auto_followup_max_depth": max_depth,
                    "child_workflow_name": None,
                    "child_run_id": None,
                    "child_status": None,
                    "child_terminal": None,
                    "child_last_event": None,
                    "child_run_folder": None,
                    "child_request_file": None,
                }
            )
            return "followup_failed"

        child_result = ctx.invoke_workflow(
            "devloop",
            message=revised_request_text,
            parameters={
                "followup_depth": followup_depth + 1,
                "auto_followup_max_depth": max_depth,
                "skip_test_phase": ctx.params.skip_test_phase,
            },
        )

        payload = _child_followup_payload(
            child_result,
            followup_depth=followup_depth,
            auto_followup_max_depth=max_depth,
        )
        ctx.artifacts.followup_result.write_json(payload)

        if payload["child_status"] != "success":
            return "followup_failed"

        return "followup_started"

    entry = plan


def _load_phase_plan(
    raw: str,
    *,
    expected_task_id: str,
    expected_request_snapshot_ref: str,
) -> list[Phase]:
    payload = _parse_phase_plan_payload(raw)
    document = _validate_phase_plan_document(payload)
    _validate_phase_plan_metadata(
        document,
        expected_task_id=expected_task_id,
        expected_request_snapshot_ref=expected_request_snapshot_ref,
    )
    return [_phase_from_plan_phase(phase) for phase in document.phases]


def _parse_phase_plan_payload(raw: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PhasePlanError(f"phase plan must be valid JSON: {exc.msg}") from exc

    if not isinstance(payload, Mapping):
        raise PhasePlanError("phase plan must be a JSON object")

    return payload


def _validate_phase_plan_document(payload: Mapping[str, Any]) -> PhasePlanDocument:
    try:
        document = PhasePlanDocument.model_validate(payload)
    except ValidationError as exc:
        raise PhasePlanError(f"phase plan schema validation failed: {exc}") from exc

    if document.version != PHASE_PLAN_VERSION:
        raise PhasePlanError(
            f"phase plan version must be {PHASE_PLAN_VERSION}, got {document.version!r}"
        )

    if document.status != PHASE_STATUS_PLANNED:
        raise PhasePlanError("phase plan root status must be 'planned' in a new phase plan")

    if not document.phases:
        raise PhasePlanError("phase plan must define at least one phase")

    all_phase_ids = {
        _non_empty(phase.phase_id, "phase_id")
        for phase in document.phases
    }
    seen_phase_ids: set[str] = set()

    for index, phase in enumerate(document.phases, start=1):
        label = f"phases[{index}]"
        phase_id = _non_empty(phase.phase_id, f"{label}.phase_id")

        if phase_id in seen_phase_ids:
            raise PhasePlanError(f"duplicate phase_id {phase_id!r}")

        _phase_dir_key_checked(phase_id)

        _non_empty(phase.title, f"{label}.title")
        _non_empty(phase.objective, f"{label}.objective")

        if phase.status != PHASE_STATUS_PLANNED:
            raise PhasePlanError(f"{label}.status must be 'planned' in a new phase plan")

        _string_list(phase.scope.in_scope, f"{label}.scope.in_scope", allow_empty=False)
        _string_list(phase.scope.out_of_scope, f"{label}.scope.out_of_scope", allow_empty=True)
        _string_list(phase.dependencies, f"{label}.dependencies", allow_empty=True)
        _string_list(phase.deliverables, f"{label}.deliverables", allow_empty=False)
        _string_list(phase.risks, f"{label}.risks", allow_empty=True)
        _string_list(phase.rollback, f"{label}.rollback", allow_empty=True)

        if not phase.criteria:
            raise PhasePlanError(f"{label}.criteria must contain at least one criterion")

        criterion_ids: set[str] = set()
        for criterion_index, criterion in enumerate(phase.criteria, start=1):
            criterion_label = f"{label}.criteria[{criterion_index}]"
            criterion_id = _non_empty(criterion.id, f"{criterion_label}.id")
            _non_empty(criterion.text, f"{criterion_label}.text")

            if criterion_id in criterion_ids:
                raise PhasePlanError(f"{label}.criteria contains duplicate id {criterion_id!r}")
            criterion_ids.add(criterion_id)

        for dependency in phase.dependencies:
            dependency_id = dependency.strip()

            if dependency_id == phase_id:
                raise PhasePlanError(
                    f"{label}.dependencies must not reference itself: {phase_id!r}"
                )

            if dependency_id in all_phase_ids and dependency_id not in seen_phase_ids:
                raise PhasePlanError(
                    f"{label}.dependencies references phase {dependency_id!r}, "
                    "which is not earlier in phase order"
                )

        seen_phase_ids.add(phase_id)

    return document


def _validate_phase_plan_metadata(
    document: PhasePlanDocument,
    *,
    expected_task_id: str,
    expected_request_snapshot_ref: str,
) -> None:
    if document.task_id != expected_task_id:
        raise PhasePlanError(
            f"phase plan task_id must be {expected_task_id!r}, got {document.task_id!r}"
        )

    if document.request_snapshot_ref != expected_request_snapshot_ref:
        raise PhasePlanError(
            "phase plan request_snapshot_ref must be "
            f"{expected_request_snapshot_ref!r}, got {document.request_snapshot_ref!r}"
        )


def _phase_from_plan_phase(phase: PhasePlanPhase) -> Phase:
    phase_id = phase.phase_id.strip()
    return Phase(
        id=phase_id,
        dir_key=_phase_dir_key_checked(phase_id),
        title=phase.title.strip(),
        objective=phase.objective.strip(),
        status=phase.status,
        scope=phase.scope,
        dependencies=[item.strip() for item in phase.dependencies],
        criteria=[
            PhaseCriterion(id=criterion.id.strip(), text=criterion.text.strip())
            for criterion in phase.criteria
        ],
        deliverables=[item.strip() for item in phase.deliverables],
        risks=[item.strip() for item in phase.risks],
        rollback=[item.strip() for item in phase.rollback],
    )


def _load_audit_result(
    raw: str,
    *,
    expected_task_id: str,
    expected_request_snapshot_ref: str,
) -> AuditResult:
    payload = _parse_audit_result_payload(raw)

    try:
        result = AuditResult.model_validate(payload)
    except ValidationError as exc:
        raise AuditResultError(f"audit result schema validation failed: {exc}") from exc

    if result.version != AUDIT_RESULT_VERSION:
        raise AuditResultError(
            f"audit result version must be {AUDIT_RESULT_VERSION}, got {result.version!r}"
        )

    if result.task_id != expected_task_id:
        raise AuditResultError(
            f"audit result task_id must be {expected_task_id!r}, got {result.task_id!r}"
        )

    if result.request_snapshot_ref != expected_request_snapshot_ref:
        raise AuditResultError(
            "audit result request_snapshot_ref must be "
            f"{expected_request_snapshot_ref!r}, got {result.request_snapshot_ref!r}"
        )

    if result.status not in AUDIT_STATUSES:
        raise AuditResultError(
            f"audit result status must be one of {sorted(AUDIT_STATUSES)}, got {result.status!r}"
        )

    _non_empty(result.summary, "audit_result.summary", error_cls=AuditResultError)

    seen_gap_ids: set[str] = set()
    for index, gap in enumerate(result.gaps, start=1):
        label = f"audit_result.gaps[{index}]"
        gap_id = _non_empty(gap.id, f"{label}.id", error_cls=AuditResultError)
        _non_empty(gap.summary, f"{label}.summary", error_cls=AuditResultError)
        _non_empty(gap.followup, f"{label}.followup", error_cls=AuditResultError)
        _string_list(
            gap.evidence,
            f"{label}.evidence",
            allow_empty=False,
            error_cls=AuditResultError,
        )

        if gap_id in seen_gap_ids:
            raise AuditResultError(f"audit result contains duplicate gap id {gap_id!r}")
        seen_gap_ids.add(gap_id)

        if gap.severity not in AUDIT_SEVERITIES:
            raise AuditResultError(
                f"{label}.severity must be one of {sorted(AUDIT_SEVERITIES)}, got {gap.severity!r}"
            )

    if result.status == AUDIT_STATUS_PASSED and result.gaps:
        raise AuditResultError("audit result status is 'passed' but unresolved gaps were reported")

    if result.status == AUDIT_STATUS_NEEDS_FOLLOWUP and not result.gaps:
        raise AuditResultError("audit result status is 'needs_followup' but no gaps were reported")

    return result


def _parse_audit_result_payload(raw: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AuditResultError(f"audit result must be valid JSON: {exc.msg}") from exc

    if not isinstance(payload, Mapping):
        raise AuditResultError("audit result must be a JSON object")

    return payload


def _checklist_issues(artifact, label: str) -> list[str]:
    if not artifact.exists():
        return [f"{label} checklist is missing: {artifact.path}"]

    try:
        text = artifact.read_text()
    except OSError as exc:
        return [f"{label} checklist could not be read: {artifact.path}: {exc}"]

    if not text.strip():
        return [f"{label} checklist is empty: {artifact.path}"]

    marks = [match.group("mark") for match in _CHECKBOX_RE.finditer(text)]
    if not marks:
        return [f"{label} checklist must contain at least one markdown checkbox"]

    unchecked_count = sum(1 for mark in marks if mark == " ")
    if unchecked_count:
        return [
            f"{label} checklist has {unchecked_count} unchecked item(s); "
            "all completion criteria must be checked before this route can continue"
        ]

    return []


def _non_empty_artifact_issues(artifact, label: str) -> list[str]:
    if not artifact.exists():
        return [f"{label} is missing: {artifact.path}"]

    try:
        text = artifact.read_text()
    except OSError as exc:
        return [f"{label} could not be read: {artifact.path}: {exc}"]

    if not text.strip():
        return [f"{label} is empty: {artifact.path}"]

    return []


def _set_phase_status(ctx, phase_id: str, status: str) -> None:
    payload = dict(_parse_phase_plan_payload(ctx.artifacts.phase_plan.read_text()))
    phases = payload.get("phases")

    if not isinstance(phases, list):
        raise PhasePlanError("phase plan must define a phases list before status can be updated")

    matched = False
    for item in phases:
        if not isinstance(item, dict):
            continue
        if str(item.get("phase_id", "")).strip() != phase_id:
            continue
        item["status"] = status
        matched = True
        break

    if not matched:
        raise PhasePlanError(f"cannot update unknown phase_id {phase_id!r}")

    payload["status"] = _aggregate_phase_plan_status(phases)
    ctx.artifacts.phase_plan.write_text(_dump_json(payload))

    for index, phase in enumerate(ctx.state.phases):
        if phase.id == phase_id:
            phase.status = status
            ctx.state.phases[index] = phase
            break

    if ctx.state.phase is not None and ctx.state.phase.id == phase_id:
        ctx.state.phase.status = status


def _set_phase_plan_status(ctx, status: str) -> None:
    payload = dict(_parse_phase_plan_payload(ctx.artifacts.phase_plan.read_text()))
    payload["status"] = status
    ctx.artifacts.phase_plan.write_text(_dump_json(payload))


def _aggregate_phase_plan_status(phases: Sequence[Mapping[str, Any]]) -> str:
    statuses = {
        str(item.get("status", "")).strip()
        for item in phases
        if isinstance(item, Mapping)
    }

    if statuses and statuses <= {PHASE_STATUS_COMPLETED, PHASE_STATUS_DEFERRED}:
        return PHASE_STATUS_COMPLETED
    if PHASE_STATUS_BLOCKED in statuses:
        return PHASE_STATUS_BLOCKED
    if PHASE_STATUS_IN_PROGRESS in statuses:
        return PHASE_STATUS_IN_PROGRESS
    return PHASE_STATUS_PLANNED


def _build_audit_evidence(ctx) -> str:
    lines: list[str] = [
        "# Devloop Audit Evidence",
        "",
        "## Request",
        "",
        "```text",
        ctx.request.text,
        "```",
        "",
        "## Runtime",
        "",
        f"- Task id: `{ctx.task_id}`",
        f"- Run id: `{ctx.run_id}`",
        f"- Task folder: `{ctx.task_folder}`",
        f"- Run folder: `{ctx.run_folder}`",
        f"- Workflow params: `{json.dumps(ctx.workflow_params, sort_keys=True, ensure_ascii=False)}`",
        "",
        "## Phase Plan",
        "",
        "```json",
        _read_artifact_text(ctx.artifacts.phase_plan, "phase plan").rstrip(),
        "```",
        "",
    ]

    for phase in ctx.state.phases:
        lines.extend(
            [
                f"## Phase: {phase.id}",
                "",
                f"- Title: {phase.title}",
                f"- Objective: {phase.objective}",
                f"- Status: {phase.status}",
                f"- Directory key: `{phase.dir_key}`",
                "",
                "### Acceptance criteria",
                "",
                *[f"- {criterion.id}: {criterion.text}" for criterion in phase.criteria],
                "",
            ]
        )

        impl_dir = ctx.task_folder / "implement" / "phases" / phase.dir_key
        test_dir = ctx.task_folder / "test" / "phases" / phase.dir_key

        _append_file_section(
            lines,
            impl_dir / "implementation_notes.md",
            f"Implementation notes for {phase.id}",
        )
        _append_file_section(
            lines,
            impl_dir / "criteria.md",
            f"Implementation criteria for {phase.id}",
        )
        _append_file_section(
            lines,
            impl_dir / "feedback.md",
            f"Implementation feedback for {phase.id}",
        )
        _append_file_section(
            lines,
            impl_dir / "completion_gate_feedback.md",
            f"Implementation completion gate feedback for {phase.id}",
        )
        _append_file_section(
            lines,
            test_dir / "test_strategy.md",
            f"Test strategy for {phase.id}",
        )
        _append_file_section(
            lines,
            test_dir / "criteria.md",
            f"Test criteria for {phase.id}",
        )
        _append_file_section(
            lines,
            test_dir / "feedback.md",
            f"Test feedback for {phase.id}",
        )
        _append_file_section(
            lines,
            test_dir / "completion_gate_feedback.md",
            f"Test completion gate feedback for {phase.id}",
        )

    _append_file_section(lines, ctx.task_folder / "decisions.txt", "Task decisions")
    _append_file_section(lines, ctx.task_folder / "raw_phase_log.md", "Task raw phase log")
    _append_file_section(lines, ctx.run_folder / "raw_phase_log.md", "Run raw phase log")
    _append_file_section(lines, ctx.run_folder / "events.jsonl", "Run events")

    return "\n".join(lines).rstrip() + "\n"


def _append_file_section(lines: list[str], path: Path, title: str) -> None:
    lines.extend(
        [
            f"## {title}",
            "",
            f"Path: `{path}`",
            "",
        ]
    )

    if not path.exists():
        lines.extend(["Missing.", ""])
        return

    try:
        text = path.read_text(encoding="utf-8").rstrip()
    except OSError as exc:
        lines.extend([f"Could not read file: {exc}", ""])
        return

    if not text:
        lines.extend(["Empty.", ""])
        return

    lines.extend(
        [
            "```text",
            text,
            "```",
            "",
        ]
    )


def _child_followup_payload(
    child_result,
    *,
    followup_depth: int,
    auto_followup_max_depth: int,
) -> dict[str, object]:
    last_event = getattr(child_result, "last_event", None)
    last_event_tag = getattr(last_event, "tag", None)
    status = getattr(child_result, "status", None)

    return {
        "status": FOLLOWUP_STATUS_STARTED if status == "success" else FOLLOWUP_STATUS_FAILED,
        "reason": None if status == "success" else "child_workflow_did_not_succeed",
        "followup_depth": followup_depth,
        "auto_followup_max_depth": auto_followup_max_depth,
        "child_workflow_name": getattr(child_result, "workflow_name", None),
        "child_run_id": getattr(child_result, "run_id", None),
        "child_status": status,
        "child_terminal": getattr(child_result, "terminal", None),
        "child_last_event": last_event_tag,
        "child_run_folder": _string_or_none(getattr(child_result, "run_folder", None)),
        "child_request_file": _string_or_none(getattr(child_result, "request_file", None)),
    }


def _dump_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _phase_dir_key_checked(phase_id: str) -> str:
    try:
        return phase_dir_key(phase_id)
    except ValueError as exc:
        raise PhasePlanError(str(exc)) from exc


def _read_artifact_text(
    artifact,
    label: str,
    *,
    error_cls: type[ValueError] = PhasePlanError,
) -> str:
    try:
        return artifact.read_text()
    except OSError as exc:
        raise error_cls(f"{label} could not be read: {artifact.path}: {exc}") from exc


def _non_empty(
    value: str,
    label: str,
    *,
    error_cls: type[ValueError] = PhasePlanError,
) -> str:
    normalized = value.strip()
    if not normalized:
        raise error_cls(f"{label} must be a non-empty string")
    return normalized


def _string_list(
    values: Sequence[str],
    label: str,
    *,
    allow_empty: bool,
    error_cls: type[ValueError] = PhasePlanError,
) -> None:
    if not allow_empty and not values:
        raise error_cls(f"{label} must contain at least one entry")

    for index, item in enumerate(values, start=1):
        if not item.strip():
            raise error_cls(f"{label}[{index}] must be a non-empty string")


def _safe_int(value: object, *, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    if value < 0:
        return default
    return value


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
