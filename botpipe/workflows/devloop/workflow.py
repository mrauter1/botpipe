"""Imperative plan, implement, test, and audit workflow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from botpipe import Artifact, Provider, Session, activity, current_run, workflow
from botpipe.workflows._reviews import save_review

from .conventions import phase_dir_key
from .reviews import (
    PROCESS_CRITERIA,
    PhaseCriterion,
    ReviewReport,
    StrictModel,
    validate_review,
)

PHASE_PLAN_VERSION = 1
AUDIT_RESULT_VERSION = 1
PHASE_STATUSES = {"planned", "in_progress", "completed", "blocked", "deferred"}
AUDIT_SEVERITIES = {"low", "medium", "high", "critical"}


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
    status: Literal["passed", "needs_followup"]
    summary: str
    gaps: list[AuditGap]


class DevLoopParams(BaseModel):
    followup_depth: int = Field(default=0, ge=0)
    auto_followup_max_depth: int = Field(default=3, ge=0)
    skip_test_phase: bool = False
    mode: Literal["devloop", "docloop"] = "devloop"


class FollowupRunResult(BaseModel):
    status: Literal["started", "skipped", "failed"]
    reason: str | None = None
    followup_depth: int
    auto_followup_max_depth: int
    child_status: str | None = None
    child_audit_result: str | None = None


class DevLoopResult(BaseModel):
    status: Literal["passed", "blocked", "needs_followup"]
    summary: str
    phase_plan_path: str
    audit_result_path: str | None = None
    followup_result_path: str | None = None
    completed_phases: list[str] = Field(default_factory=list)


class PhasePlanError(ValueError):
    pass


class AuditResultError(ValueError):
    pass


@activity
def _write_text(path: str, text: str) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return str(target)


@activity
def _write_json(path: str, payload: dict[str, Any]) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return str(target)


@activity
def _collect_audit_evidence(
    task_folder: str, run_folder: str, request: str, params: dict[str, Any]
) -> str:
    task = Path(task_folder)
    run = Path(run_folder)
    target = task / "audit" / "evidence.md"
    lines = [
        "# Devloop Audit Evidence",
        "",
        "## Request",
        "",
        request,
        "",
        "## Parameters",
        "",
        "```json",
        json.dumps(params, indent=2, sort_keys=True),
        "```",
        "",
    ]
    for root in (task / "plan", task / "implement", task / "test"):
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            lines.extend([f"## {path.relative_to(task)}", "", "```text"])
            try:
                lines.append(path.read_text(encoding="utf-8").rstrip())
            except OSError as exc:
                lines.append(f"Could not read: {exc}")
            lines.extend(["```", ""])
    events = run / "events.jsonl"
    if events.is_file():
        lines.extend(
            [
                "## Run events",
                "",
                "```text",
                events.read_text(encoding="utf-8").rstrip(),
                "```",
                "",
            ]
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return str(target)


def _process_criteria(stage: str) -> list[PhaseCriterion]:
    return [
        PhaseCriterion(id=key, text=value)
        for key, value in PROCESS_CRITERIA[stage].items()
    ]


def _phase_dict(phase: PhasePlanPhase) -> dict[str, Any]:
    return phase.model_dump(mode="json")


def _validate_phase_plan(
    raw: str, task_id: str, request_ref: str, *, live: bool = False
) -> PhasePlanDocument:
    try:
        document = PhasePlanDocument.model_validate_json(raw)
    except ValidationError as exc:
        raise PhasePlanError(f"phase plan schema validation failed: {exc}") from exc
    if document.version != PHASE_PLAN_VERSION:
        raise PhasePlanError(f"phase plan version must be {PHASE_PLAN_VERSION}")
    if document.task_id != task_id or document.request_snapshot_ref != request_ref:
        raise PhasePlanError(
            "phase plan task_id and request_snapshot_ref must match the declared input"
        )
    if document.status not in ({"planned"} if not live else PHASE_STATUSES):
        raise PhasePlanError("phase plan has an invalid root status")
    if not document.phases:
        raise PhasePlanError("phase plan must contain at least one phase")
    ids = [item.phase_id.strip() for item in document.phases]
    if any(not item for item in ids) or len(ids) != len(set(ids)):
        raise PhasePlanError("phase ids must be non-empty and unique")
    seen: set[str] = set()
    for index, phase in enumerate(document.phases, 1):
        phase_dir_key(phase.phase_id)
        if not phase.title.strip() or not phase.objective.strip():
            raise PhasePlanError(
                f"phase {phase.phase_id!r} needs a title and objective"
            )
        if phase.status not in ({"planned"} if not live else PHASE_STATUSES):
            raise PhasePlanError(f"phase {phase.phase_id!r} has invalid status")
        if not phase.scope.in_scope or not phase.criteria or not phase.deliverables:
            raise PhasePlanError(
                f"phase {phase.phase_id!r} needs scope, criteria, and deliverables"
            )
        criterion_ids = [criterion.id for criterion in phase.criteria]
        if len(criterion_ids) != len(set(criterion_ids)):
            raise PhasePlanError(
                f"phase {phase.phase_id!r} has duplicate criterion IDs"
            )
        for dependency in phase.dependencies:
            if dependency == phase.phase_id or dependency not in seen:
                raise PhasePlanError(
                    f"phase {phase.phase_id!r} dependency {dependency!r} must identify an earlier phase"
                )
        seen.add(phase.phase_id)
    return document


def _validate_audit(raw: str, task_id: str, request_ref: str) -> AuditResult:
    try:
        result = AuditResult.model_validate_json(raw)
    except ValidationError as exc:
        raise AuditResultError(f"audit result schema validation failed: {exc}") from exc
    if result.version != AUDIT_RESULT_VERSION:
        raise AuditResultError(f"audit result version must be {AUDIT_RESULT_VERSION}")
    if result.task_id != task_id or result.request_snapshot_ref != request_ref:
        raise AuditResultError(
            "audit result task_id and request_snapshot_ref must match the request"
        )
    if not result.summary.strip():
        raise AuditResultError("audit summary must be non-empty")
    if result.status == "passed" and result.gaps:
        raise AuditResultError("a passed audit cannot contain unresolved gaps")
    if result.status == "needs_followup" and not result.gaps:
        raise AuditResultError("needs_followup requires at least one gap")
    ids: set[str] = set()
    for gap in result.gaps:
        if (
            gap.id in ids
            or gap.severity not in AUDIT_SEVERITIES
            or not gap.evidence
            or not gap.followup.strip()
        ):
            raise AuditResultError(
                "audit gaps need unique ids, valid severity, evidence, and followup"
            )
        ids.add(gap.id)
    return result


def _aggregate_phase_status(phases: list[PhasePlanPhase]) -> str:
    statuses = {phase.status for phase in phases}
    if statuses and statuses <= {"completed", "deferred"}:
        return "completed"
    if "blocked" in statuses:
        return "blocked"
    if "in_progress" in statuses:
        return "in_progress"
    return "planned"


def _review_id(stage: str, phase_id: str | None, attempt: int) -> str:
    return f"{stage}:{phase_id or 'root'}:{attempt}"


def _review_input(
    *,
    request: str,
    stage: str,
    review_id: str,
    criteria: list[PhaseCriterion],
    phase: PhasePlanPhase | None = None,
) -> dict[str, Any]:
    return {
        "request": request,
        "stage": stage,
        "review_id": review_id,
        "criteria": [criterion.model_dump(mode="json") for criterion in criteria],
        "phase": _phase_dict(phase) if phase else None,
    }


def _blocked(
    plan_path: Path, report: ReviewReport, phases: list[PhasePlanPhase]
) -> DevLoopResult:
    return DevLoopResult(
        status="blocked",
        summary=report.summary
        or "; ".join(report.issues())
        or "Verifier blocked the workflow.",
        phase_plan_path=str(plan_path),
        completed_phases=[
            phase.phase_id for phase in phases if phase.status == "completed"
        ],
    )


PLAN_PRODUCER = """Create a strict phased implementation plan for the supplied request. Inspect the repository and
any feedback artifacts. Write the declared phase_plan JSON. Preserve the supplied task_id and request_snapshot_ref.
Each planned phase needs bounded scope, earlier-phase dependencies, concrete criteria, deliverables, risks, and rollback."""

PLAN_VERIFIER = """Independently audit the phase plan against the request and repository. Return the structured
ReviewReport without editing files. Cover exactly the supplied criteria and use the supplied review_id."""

IMPLEMENT_PRODUCER = """Implement only the supplied active phase. Read the current plan and all review feedback.
Edit the repository, validate the work, and write concrete implementation notes to the declared artifact."""

IMPLEMENT_VERIFIER = """Independently verify the active phase against every supplied criterion. Inspect repository
state and current evidence. Return ReviewReport without editing files. Set repair_target=phase_item
only when the phase definition itself must change; otherwise repair_target=candidate."""

PHASE_ITEM_PRODUCER = """Repair the active phase definition after an implementation review found it unexecutable.
Preserve completed phases, order, and the active phase id. Write the revised phase plan and an item review note."""

PHASE_ITEM_VERIFIER = """Verify that the revised plan preserves completed work and phase identity while making the
active phase executable. Return ReviewReport without editing files and cover the supplied process criteria."""

TEST_PRODUCER = """Test the supplied phase against its acceptance criteria and current implementation. Run suitable
checks, fix only test-harness defects, and write a test strategy containing commands and observed results."""

TEST_VERIFIER = """Independently verify the phase test evidence against every supplied criterion. Return ReviewReport
without editing files. Failed implementation behavior requires candidate rework."""

AUDIT_PRODUCER = """Perform a final audit of the original request using the completed phase plan and evidence bundle.
Write audit_result.json, gap_report.md, and revised_request.md. Use passed only when no gaps remain; otherwise write a
standalone constrained follow-up request and needs_followup. Treat skipped tests/docloop mode as reduced assurance."""

AUDIT_VERIFIER = """Independently verify that audit_result, gap_report, and revised_request accurately reflect the
request and evidence. A correct needs_followup decision can pass review. Return ReviewReport and cover the supplied
audit-process criteria using the supplied review_id."""


@workflow(name="devloop", version="1")
def devloop(
    request: str,
    *,
    followup_depth: int = 0,
    auto_followup_max_depth: int = 3,
    skip_test_phase: bool = False,
    mode: Literal["devloop", "docloop"] = "devloop",
) -> DevLoopResult:
    params = DevLoopParams(
        followup_depth=followup_depth,
        auto_followup_max_depth=auto_followup_max_depth,
        skip_test_phase=skip_test_phase,
        mode=mode,
    )
    ctx = current_run()
    # Top-level runs keep the historical task-facing layout. Nested follow-up
    # runs use their child folder so they cannot overwrite the parent's audit
    # result or phase evidence while the parent is still returning it.
    artifact_root = ctx.task_folder if ctx.scope == "root" else ctx.folder
    request_path = ctx.folder / "request.md"
    _write_text(str(request_path), request.rstrip() + "\n")
    request_artifact = Artifact.text(str(request_path), name="request", required=True)
    plan_path = artifact_root / "plan" / "phase_plan.json"
    plan_spec = Artifact.json(
        str(plan_path), name="phase_plan", schema=PhasePlanDocument, required=True
    )
    plan_review_spec = Artifact.json(
        str(artifact_root / "plan" / "review.json"),
        name="plan_review",
        schema=ReviewReport,
        required=True,
    )

    planner = Provider()
    plan_reviewer = planner.with_config(session=None)
    plan_feedback: tuple[Any, ...] = ()
    attempt = 0
    while True:
        attempt += 1
        planned = planner.run(
            PLAN_PRODUCER,
            input={
                "request": request,
                "task_id": ctx.task_id,
                "request_snapshot_ref": str(request_path),
                "mode": params.mode,
            },
            reads=(request_artifact.path, *plan_feedback),
            writes=(plan_spec,),
        )
        try:
            document = _validate_phase_plan(
                planned.artifacts.phase_plan.read_text(), ctx.task_id, str(request_path)
            )
        except PhasePlanError as exc:
            feedback_path = artifact_root / "plan" / "completion_gate_feedback.md"
            _write_text(str(feedback_path), f"# Plan completion gate\n\n{exc}\n")
            plan_feedback = (feedback_path,)
            continue
        review_id = _review_id("plan", None, attempt)
        criteria = _process_criteria("plan")
        reviewed = plan_reviewer.query(
            PLAN_VERIFIER,
            input=_review_input(
                request=request, stage="plan", review_id=review_id, criteria=criteria
            ),
            reads=(planned.artifacts.phase_plan,),
            returns=ReviewReport,
        )
        plan_review_path = save_review(str(plan_review_spec.path), reviewed.value)
        review = reviewed.value
        issues = validate_review(review, review_id, criteria)
        if review.verdict == "blocked":
            return _blocked(plan_path, review, document.phases)
        if not issues:
            break
        plan_feedback = (plan_review_path,)

    phases = document.phases
    latest_plan = planned.artifacts.phase_plan
    completed: list[str] = []

    phase_index = 0
    while phase_index < len(phases):
        phase = phases[phase_index]
        phase.status = "in_progress"
        document.status = "in_progress"
        _write_json(str(plan_path), document.model_dump(mode="json"))
        phase_dir = phase_dir_key(phase.phase_id)
        phase_provider = planner.with_config(session=Session())
        phase_verifier = planner.with_config(session=None)
        implementation_feedback: tuple[Any, ...] = ()
        stage_attempt = 0
        phase_done = False

        while not phase_done:
            stage_attempt += 1
            notes = Artifact.md(
                str(
                    artifact_root
                    / "implement"
                    / "phases"
                    / phase_dir
                    / "implementation_notes.md"
                ),
                name="impl_notes",
                required=True,
            )
            impl_review_spec = Artifact.json(
                str(artifact_root / "implement" / "phases" / phase_dir / "review.json"),
                name="impl_review",
                schema=ReviewReport,
                required=True,
            )
            implemented = phase_provider.run(
                IMPLEMENT_PRODUCER,
                input={
                    "request": request,
                    "phase": _phase_dict(phase),
                    "plan": document.model_dump(mode="json"),
                },
                reads=(latest_plan, *implementation_feedback),
                writes=(notes,),
            )
            review_id = _review_id("implement", phase.phase_id, stage_attempt)
            checked = phase_verifier.query(
                IMPLEMENT_VERIFIER,
                input=_review_input(
                    request=request,
                    stage="implement",
                    review_id=review_id,
                    criteria=phase.criteria,
                    phase=phase,
                ),
                reads=(latest_plan, implemented.artifacts.impl_notes),
                returns=ReviewReport,
            )
            impl_review_path = save_review(str(impl_review_spec.path), checked.value)
            report = checked.value
            issues = validate_review(report, review_id, phase.criteria)
            if report.verdict == "blocked":
                phase.status = "blocked"
                _write_json(str(plan_path), document.model_dump(mode="json"))
                return _blocked(plan_path, report, phases)
            if issues:
                if report.repair_target == "phase_item":
                    item_review = Artifact.md(
                        str(
                            artifact_root
                            / "plan"
                            / "phases"
                            / phase_dir
                            / "item_review.md"
                        ),
                        name="phase_item_review",
                        required=True,
                    )
                    item_report_spec = Artifact.json(
                        str(
                            artifact_root
                            / "plan"
                            / "phases"
                            / phase_dir
                            / "item_review.json"
                        ),
                        name="phase_item_review_report",
                        schema=ReviewReport,
                        required=True,
                    )
                    item_attempt = 0
                    while True:
                        item_attempt += 1
                        revised = phase_provider.run(
                            PHASE_ITEM_PRODUCER,
                            input={
                                "request": request,
                                "active_phase_index": phase_index,
                                "active_phase": _phase_dict(phase),
                                "plan": document.model_dump(mode="json"),
                            },
                            reads=(latest_plan, impl_review_path),
                            writes=(plan_spec, item_review),
                        )
                        try:
                            candidate = _validate_phase_plan(
                                revised.artifacts.phase_plan.read_text(),
                                ctx.task_id,
                                str(request_path),
                                live=True,
                            )
                            if phase_index >= len(candidate.phases):
                                raise PhasePlanError(
                                    "phase item review removed the active phase"
                                )
                            for prior_index in range(phase_index):
                                if (
                                    candidate.phases[prior_index].phase_id
                                    != phases[prior_index].phase_id
                                ):
                                    raise PhasePlanError(
                                        "phase item review changed completed phase order or identity"
                                    )
                                if (
                                    phases[prior_index].status == "completed"
                                    and candidate.phases[prior_index].status
                                    != "completed"
                                ):
                                    raise PhasePlanError(
                                        "phase item review demoted a completed phase"
                                    )
                            if candidate.phases[phase_index].phase_id != phase.phase_id:
                                raise PhasePlanError(
                                    "phase item review changed the active phase id"
                                )
                            if candidate.phases[phase_index].status != "in_progress":
                                raise PhasePlanError(
                                    "phase item review must keep the active phase in_progress"
                                )
                            if candidate.status != _aggregate_phase_status(
                                candidate.phases
                            ):
                                raise PhasePlanError(
                                    "phase item review root status does not match its phase statuses"
                                )
                        except PhasePlanError:
                            continue
                        process = _process_criteria("phase_item")
                        item_review_id = _review_id(
                            "phase_item", phase.phase_id, item_attempt
                        )
                        item_checked = phase_verifier.query(
                            PHASE_ITEM_VERIFIER,
                            input=_review_input(
                                request=request,
                                stage="phase_item",
                                review_id=item_review_id,
                                criteria=process,
                                phase=candidate.phases[phase_index],
                            ),
                            reads=(
                                revised.artifacts.phase_plan,
                                revised.artifacts.phase_item_review,
                            ),
                            returns=ReviewReport,
                        )
                        item_report_path = save_review(
                            str(item_report_spec.path), item_checked.value
                        )
                        if item_checked.value.verdict == "blocked":
                            return _blocked(plan_path, item_checked.value, phases)
                        if not validate_review(
                            item_checked.value, item_review_id, process
                        ):
                            document = candidate
                            phases = document.phases
                            phase = phases[phase_index]
                            latest_plan = revised.artifacts.phase_plan
                            implementation_feedback = (
                                item_report_path,
                            )
                            break
                    continue
                implementation_feedback = (impl_review_path,)
                continue

            effective_skip = params.skip_test_phase or params.mode == "docloop"
            test_dir = artifact_root / "test" / "phases" / phase_dir
            if effective_skip:
                reason = (
                    "docloop mode"
                    if params.mode == "docloop"
                    else "skip_test_phase=true"
                )
                _write_text(
                    str(test_dir / "test_strategy.md"),
                    f"# Test Strategy: {phase.phase_id}\n\nThe test producer/verifier was intentionally skipped ({reason}).\n"
                    "This is reduced assurance and is not passing test evidence.\n",
                )
                phase_done = True
                continue

            test_strategy = Artifact.md(
                str(test_dir / "test_strategy.md"), name="test_strat", required=True
            )
            test_review_spec = Artifact.json(
                str(test_dir / "review.json"),
                name="test_review",
                schema=ReviewReport,
                required=True,
            )
            tested = phase_provider.run(
                TEST_PRODUCER,
                input={"request": request, "phase": _phase_dict(phase)},
                reads=(latest_plan, implemented.artifacts.impl_notes),
                writes=(test_strategy,),
            )
            test_review_id = _review_id("test", phase.phase_id, stage_attempt)
            test_checked = phase_verifier.query(
                TEST_VERIFIER,
                input=_review_input(
                    request=request,
                    stage="test",
                    review_id=test_review_id,
                    criteria=phase.criteria,
                    phase=phase,
                ),
                reads=(implemented.artifacts.impl_notes, tested.artifacts.test_strat),
                returns=ReviewReport,
            )
            test_review_path = save_review(
                str(test_review_spec.path), test_checked.value
            )
            if test_checked.value.verdict == "blocked":
                phase.status = "blocked"
                _write_json(str(plan_path), document.model_dump(mode="json"))
                return _blocked(plan_path, test_checked.value, phases)
            test_issues = validate_review(
                test_checked.value, test_review_id, phase.criteria
            )
            if test_issues:
                implementation_feedback = (test_review_path,)
                continue
            phase_done = True

        phase.status = "completed"
        completed.append(phase.phase_id)
        document.status = (
            "completed" if phase_index == len(phases) - 1 else "in_progress"
        )
        _write_json(str(plan_path), document.model_dump(mode="json"))
        phase_index += 1

    evidence_path = _collect_audit_evidence(
        str(artifact_root), str(ctx.folder), request, params.model_dump(mode="json")
    )
    evidence = Artifact.md(evidence_path, name="audit_evidence", required=True)
    audit_result_spec = Artifact.json(
        str(artifact_root / "audit" / "audit_result.json"),
        name="audit_result",
        schema=AuditResult,
        required=True,
    )
    gap_report = Artifact.md(
        str(artifact_root / "audit" / "gap_report.md"), name="gap_report", required=True
    )
    revised_request = Artifact.md(
        str(artifact_root / "audit" / "revised_request.md"),
        name="revised_request",
        required=False,
    )
    audit_review_spec = Artifact.json(
        str(artifact_root / "audit" / "review.json"),
        name="audit_review",
        schema=ReviewReport,
        required=True,
    )
    audit_provider = planner.with_config(session=Session())
    audit_verifier = planner.with_config(session=None)
    audit_feedback: tuple[Any, ...] = ()
    audit_attempt = 0
    while True:
        audit_attempt += 1
        produced_audit = audit_provider.run(
            AUDIT_PRODUCER,
            input={
                "request": request,
                "task_id": ctx.task_id,
                "request_snapshot_ref": str(request_path),
                "mode": params.mode,
                "skip_test_phase": params.skip_test_phase,
                "phase_plan": document.model_dump(mode="json"),
            },
            reads=(latest_plan, evidence.path, *audit_feedback),
            writes=(audit_result_spec, gap_report, revised_request),
        )
        try:
            audit_result = _validate_audit(
                produced_audit.artifacts.audit_result.read_text(),
                ctx.task_id,
                str(request_path),
            )
        except AuditResultError as exc:
            feedback_path = artifact_root / "audit" / "completion_gate_feedback.md"
            _write_text(str(feedback_path), f"# Audit completion gate\n\n{exc}\n")
            audit_feedback = (feedback_path,)
            continue
        audit_criteria = _process_criteria("audit")
        audit_review_id = _review_id("audit", None, audit_attempt)
        audit_reads = [
            produced_audit.artifacts.audit_result,
            produced_audit.artifacts.gap_report,
            evidence.path,
        ]
        if "revised_request" in produced_audit.artifacts:
            audit_reads.append(produced_audit.artifacts.revised_request)
        checked_audit = audit_verifier.query(
            AUDIT_VERIFIER,
            input=_review_input(
                request=request,
                stage="audit",
                review_id=audit_review_id,
                criteria=audit_criteria,
            ),
            reads=tuple(audit_reads),
            returns=ReviewReport,
        )
        audit_review_path = save_review(
            str(audit_review_spec.path), checked_audit.value
        )
        if checked_audit.value.verdict == "blocked":
            return _blocked(plan_path, checked_audit.value, phases)
        if not validate_review(checked_audit.value, audit_review_id, audit_criteria):
            break
        audit_feedback = (audit_review_path,)

    audit_path = produced_audit.artifacts.audit_result.source_path
    if audit_result.status == "passed":
        return DevLoopResult(
            status="passed",
            summary=audit_result.summary,
            phase_plan_path=str(plan_path),
            audit_result_path=str(audit_path),
            completed_phases=completed,
        )

    followup_path = artifact_root / "audit" / "followup_result.json"
    if params.followup_depth >= params.auto_followup_max_depth:
        followup = FollowupRunResult(
            status="skipped",
            reason="auto_followup_max_depth_reached",
            followup_depth=params.followup_depth,
            auto_followup_max_depth=params.auto_followup_max_depth,
        )
    else:
        if "revised_request" not in produced_audit.artifacts:
            raise AuditResultError("needs_followup requires revised_request.md")
        revised = produced_audit.artifacts.revised_request.read_text().strip()
        if not revised:
            raise AuditResultError(
                "needs_followup requires a non-empty revised_request.md"
            )
        child = devloop(
            revised,
            followup_depth=params.followup_depth + 1,
            auto_followup_max_depth=params.auto_followup_max_depth,
            skip_test_phase=params.skip_test_phase,
            mode=params.mode,
        )
        followup = FollowupRunResult(
            status="started",
            followup_depth=params.followup_depth,
            auto_followup_max_depth=params.auto_followup_max_depth,
            child_status=child.status,
            child_audit_result=child.audit_result_path,
        )
    _write_json(str(followup_path), followup.model_dump(mode="json"))
    return DevLoopResult(
        status="needs_followup",
        summary=audit_result.summary,
        phase_plan_path=str(plan_path),
        audit_result_path=str(audit_path),
        followup_result_path=str(followup_path),
        completed_phases=completed,
    )


DevLoop = devloop
Params = DevLoopParams

__all__ = [
    "AuditGap",
    "AuditResult",
    "AuditResultError",
    "DevLoop",
    "DevLoopParams",
    "DevLoopResult",
    "FollowupRunResult",
    "Params",
    "PhasePlanDocument",
    "PhasePlanError",
    "PhasePlanPhase",
    "PhaseScope",
    "devloop",
]
