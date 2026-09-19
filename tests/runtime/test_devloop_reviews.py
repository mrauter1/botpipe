from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from botpipe.core.primitives import Outcome
from botpipe.core.providers.fake import ScriptedLLMProvider
from botpipe.runtime.config import GitTrackingRuntimeConfig, RuntimeConfig
from botpipe.runtime.runner import RunnerOptions, run_workflow_package
from botpipe.workflows.devloop.reviews import (
    CriterionAssessment,
    PhaseCriterion,
    ReviewReport,
    ReviewRequest,
    finish_review,
    load_review,
)


class _SimulatedReviewCrash(BaseException):
    pass


class _JsonArtifact:
    def __init__(self, path: Path) -> None:
        self.path = path

    def read_text(self) -> str:
        return self.path.read_text(encoding="utf-8")

    def exists(self) -> bool:
        return self.path.exists()

    def validate(self):
        return SimpleNamespace(ok=True)


def _review_context(tmp_path: Path, payload: dict[str, object], *, step: str = "implement"):
    criteria = [
        PhaseCriterion(id="AC-1", text="The requested behavior is present."),
        PhaseCriterion(id="AC-2", text="The result is understandable to a reviewer."),
    ]
    request = ReviewRequest(id="review-current", step=step, phase_id="p01", criteria=criteria)
    path = tmp_path / "review.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    artifact_name = {
        "plan": "plan_review",
        "implement": "impl_review",
        "test": "test_review",
        "review_phase_item": "phase_item_review_report",
        "audit": "audit_review",
    }[step]
    return SimpleNamespace(
        state=SimpleNamespace(
            review=request,
            phase=SimpleNamespace(id="p01", criteria=criteria),
        ),
        artifacts=SimpleNamespace(**{artifact_name: _JsonArtifact(path)}),
        meta=SimpleNamespace(step=SimpleNamespace(name=step)),
        outcome=Outcome(raw_output="accepted", tag="implemented", payload={}),
    )


def _complete_report(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "review_id": "review-current",
        "criteria": [
            {
                "id": "AC-1",
                "verdict": "passed",
                "evidence": ["The artifact directly shows the requested behavior."],
                "reason": "The criterion is satisfied.",
            },
            {
                "id": "AC-2",
                "verdict": "passed",
                "evidence": ["The written result is clear on inspection."],
                "reason": "The qualitative criterion is satisfied.",
            },
        ],
        "findings": [],
        "summary": "The candidate satisfies the requested criteria.",
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (ReviewRequest, {"id": "", "step": "implement", "phase_id": None, "criteria": []}),
        (ReviewRequest, {"id": "review", "step": " ", "phase_id": None, "criteria": []}),
        (PhaseCriterion, {"id": "", "text": "criterion"}),
        (PhaseCriterion, {"id": "AC-1", "text": " "}),
        (
            CriterionAssessment,
            {"id": "", "verdict": "failed", "evidence": [], "reason": "Not met."},
        ),
        (
            CriterionAssessment,
            {"id": "AC-1", "verdict": "failed", "evidence": [], "reason": ""},
        ),
        (
            CriterionAssessment,
            {"id": "AC-1", "verdict": "passed", "evidence": [], "reason": "Met."},
        ),
    ],
)
def test_review_models_reject_empty_contract_fields(model, payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize(
    ("criteria", "message"),
    [
        (
            [_complete_report()["criteria"][0]],
            "missing=['AC-2']",
        ),
        (
            [
                *_complete_report()["criteria"],
                {
                    "id": "AC-OTHER",
                    "verdict": "passed",
                    "evidence": ["Irrelevant evidence."],
                    "reason": "Irrelevant criterion.",
                },
            ],
            "unknown=['AC-OTHER']",
        ),
        (
            [*_complete_report()["criteria"], _complete_report()["criteria"][0]],
            "duplicate criterion IDs",
        ),
    ],
)
def test_load_review_requires_exactly_one_assessment_per_requested_criterion(
    tmp_path: Path,
    criteria: list[object],
    message: str,
) -> None:
    ctx = _review_context(tmp_path, _complete_report(criteria=criteria))

    with pytest.raises(ValueError, match=message.replace("[", r"\[").replace("]", r"\]")):
        load_review(ctx, "implement")


def test_failed_additional_finding_overrides_falsely_successful_verifier_outcome(tmp_path: Path) -> None:
    payload = _complete_report(
        findings=[
            {
                "verdict": "failed",
                "evidence": ["The candidate introduces an unrelated behavior."],
                "reason": "An out-of-list defect still prevents acceptance.",
            }
        ]
    )
    ctx = _review_context(tmp_path, payload)

    assert load_review(ctx, "implement").verdict == "failed"
    assert finish_review(ctx) == "needs_rework"


def test_qualitative_criterion_can_pass_with_reviewable_evidence(tmp_path: Path) -> None:
    payload = _complete_report()
    payload.pop("summary")
    ctx = _review_context(tmp_path, payload)

    report = load_review(ctx, "implement")

    assert report.verdict == "passed"
    assert report.summary == ""
    assert finish_review(ctx) == "implemented"


def test_blocked_report_becomes_blocked_runtime_control(tmp_path: Path) -> None:
    payload = _complete_report()
    payload["criteria"][0].update(
        verdict="blocked",
        evidence=["The required dependency is unavailable."],
        reason="Waiting for the required dependency.",
    )
    ctx = _review_context(tmp_path, payload)

    event = finish_review(ctx)

    assert event.tag == "blocked"
    assert "Waiting for the required dependency" in event.reason


def test_stale_successful_report_is_rejected_after_new_candidate(tmp_path: Path) -> None:
    stale_report: dict[str, object] = {}

    def write_plan(request) -> str:
        request.artifacts.phase_plan.write_json(_phase_plan(request))
        return "plan ready"

    def review_plan(request) -> Outcome:
        _write_live_review(request, verdict="passed")
        return Outcome(raw_output="plan ready", tag="plan_ready", payload={})

    def reject_first_candidate(request) -> Outcome:
        nonlocal stale_report
        stale_report = _write_live_review(request, verdict="failed")
        return Outcome(raw_output="implemented", tag="implemented", payload={})

    def reuse_stale_success(request) -> Outcome:
        payload = json.loads(json.dumps(stale_report))
        for criterion in payload["criteria"]:
            criterion.update(
                verdict="passed",
                evidence=["Evidence copied from the previous candidate."],
                reason="Claimed to pass.",
            )
        request.artifacts.impl_review.write_json(payload)
        return Outcome(raw_output="implemented", tag="implemented", payload={})

    provider = ScriptedLLMProvider(
        producer_turns=[
            write_plan,
            lambda request: (
                request.artifacts.impl_notes.write_text("# Notes\n\nFirst candidate.\n"),
                "implemented",
            )[1],
            lambda request: (
                request.artifacts.impl_notes.write_text("# Notes\n\nSecond candidate.\n"),
                "implemented",
            )[1],
            lambda request: (
                request.artifacts.impl_notes.write_text("# Notes\n\nAwaiting correction.\n"),
                "implemented",
            )[1],
        ],
        verifier_turns=[
            review_plan,
            reject_first_candidate,
            reuse_stale_success,
            Outcome(raw_output="blocked", tag="blocked", reason="Stop after proving rejection."),
        ],
    )

    result = run_workflow_package(
        "devloop",
        provider=provider,
        options=_runner_options(
            tmp_path,
            task_id="task-stale-review",
            message="Reject a stale review",
            workflow_params={"skip_test_phase": True, "auto_followup_max_depth": 0},
        ),
    )

    assert result.terminal == "AWAIT_INPUT"
    assert [call.step_name for call in provider.calls].count("implement") == 6
    assert not any(call.step_name == "audit" for call in provider.calls)
    gate_feedback = (
        tmp_path
        / ".botpipe/tasks/task-stale-review/implement/phases/p01/completion_gate_feedback.md"
    ).read_text(encoding="utf-8")
    assert "Stale review" in gate_feedback
    events_path = next(
        (tmp_path / ".botpipe/tasks/task-stale-review/wf_devloop/runs").iterdir()
    ) / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    assert not any(event.get("event_type") == "phase_completed" for event in events)


def test_review_token_survives_verifier_interrupt_and_resume(tmp_path: Path) -> None:
    def crash_verifier(_request):
        raise _SimulatedReviewCrash("crash inside verifier")

    with pytest.raises(_SimulatedReviewCrash, match="crash inside verifier"):
        run_workflow_package(
            "devloop",
            provider=ScriptedLLMProvider(
                producer_turns=[
                    lambda request: (
                        request.artifacts.phase_plan.write_json(_phase_plan(request)),
                        "plan ready",
                    )[1]
                ],
                verifier_turns=[crash_verifier],
            ),
            options=_runner_options(
                tmp_path,
                task_id="task-review-resume",
                run_id="run-review-resume",
                message="Preserve the review token",
                workflow_params={"skip_test_phase": True, "auto_followup_max_depth": 0},
            ),
        )

    checkpoint_path = (
        tmp_path
        / ".botpipe/tasks/task-review-resume/wf_devloop/runs/run-review-resume/checkpoint.json"
    )
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    review_id = checkpoint["state"]["review"]["id"]
    resumed_review_ids: list[str] = []

    def block_resumed_verifier(request) -> Outcome:
        resumed_review_ids.append(request.context.state.review.id)
        return Outcome(raw_output="blocked", tag="blocked", reason="Pause after resumed verification.")

    resumed_provider = ScriptedLLMProvider(verifier_turns=[block_resumed_verifier])
    resumed = run_workflow_package(
        "devloop",
        provider=resumed_provider,
        options=_runner_options(
            tmp_path,
            task_id="task-review-resume",
            run_id="run-review-resume",
            resume=True,
        ),
    )

    assert resumed.terminal == "AWAIT_INPUT"
    assert resumed_review_ids == [review_id]
    assert [(call.kind, call.step_name) for call in resumed_provider.calls] == [("verifier", "plan")]
    assert not (tmp_path / ".botpipe/tasks/task-review-resume/plan/review.json").exists()


def test_legacy_verifier_resume_without_review_request_forces_fresh_candidate(tmp_path: Path) -> None:
    def crash_verifier(_request):
        raise _SimulatedReviewCrash("legacy checkpoint interruption")

    with pytest.raises(_SimulatedReviewCrash):
        run_workflow_package(
            "devloop",
            provider=ScriptedLLMProvider(
                producer_turns=[
                    lambda request: (
                        request.artifacts.phase_plan.write_json(_phase_plan(request)),
                        "plan ready",
                    )[1]
                ],
                verifier_turns=[crash_verifier],
            ),
            options=_runner_options(
                tmp_path,
                task_id="task-legacy-review-resume",
                run_id="run-legacy-review-resume",
                message="Recover a legacy verifier checkpoint",
                workflow_params={"skip_test_phase": True, "auto_followup_max_depth": 0},
            ),
        )

    checkpoint_path = (
        tmp_path
        / ".botpipe/tasks/task-legacy-review-resume/wf_devloop/runs/run-legacy-review-resume/checkpoint.json"
    )
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    old_review_id = checkpoint["state"].pop("review")["id"]
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2) + "\n", encoding="utf-8")

    marker: dict[str, object] = {
        "review_id": "unassigned",
        "criteria": [],
        "findings": [
            {
                "verdict": "failed",
                "evidence": ["Persisted checkpoint has no current runtime review request."],
                "reason": "A fresh producer/verifier execution is required.",
            }
        ],
        "summary": "Review assignment unavailable; rerun this stage.",
    }
    rendered_fallback_prompts: list[str] = []
    fresh_review_ids: list[str] = []

    def write_legacy_marker(request) -> Outcome:
        assert request.context.state.review is None
        rendered_fallback_prompts.append(request.verifier_prompt.text or "")
        request.artifacts.plan_review.write_json(marker)
        return Outcome(raw_output="plan ready", tag="plan_ready")

    def block_fresh_review(request) -> Outcome:
        fresh_review_ids.append(request.context.state.review.id)
        return Outcome(raw_output="blocked", tag="blocked", reason="Stop after fresh assignment.")

    resumed_provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.phase_plan.write_json(_phase_plan(request)),
                "plan ready",
            )[1]
        ],
        verifier_turns=[write_legacy_marker, block_fresh_review],
    )
    resumed = run_workflow_package(
        "devloop",
        provider=resumed_provider,
        options=_runner_options(
            tmp_path,
            task_id="task-legacy-review-resume",
            run_id="run-legacy-review-resume",
            resume=True,
        ),
    )

    assert resumed.terminal == "AWAIT_INPUT"
    assert "Missing legacy review assignment" in rendered_fallback_prompts[0]
    assert "Do not inspect, evaluate, or accept the candidate" in rendered_fallback_prompts[0]
    assert fresh_review_ids and fresh_review_ids[0] not in {"unassigned", old_review_id}
    assert [(call.kind, call.step_name) for call in resumed_provider.calls] == [
        ("verifier", "plan"),
        ("producer", "plan"),
        ("verifier", "plan"),
    ]
    gate_feedback = (
        tmp_path / ".botpipe/tasks/task-legacy-review-resume/plan/completion_gate_feedback.md"
    ).read_text(encoding="utf-8")
    assert "No current plan review request" in gate_feedback
    plan = json.loads(
        (tmp_path / ".botpipe/tasks/task-legacy-review-resume/plan/phase_plan.json").read_text(encoding="utf-8")
    )
    assert plan["status"] == "planned"


def test_blocked_test_report_overrides_phase_passed_without_completing_phase(tmp_path: Path) -> None:
    def block_test(request) -> Outcome:
        payload = _write_live_review(request, verdict="blocked")
        for criterion in payload["criteria"]:
            criterion["evidence"] = ["The external validation dependency is unavailable."]
            criterion["reason"] = "Testing is blocked until the external dependency is available."
        request.artifacts.test_review.write_json(payload)
        return Outcome(raw_output="phase passed", tag="phase_passed")

    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.phase_plan.write_json(_phase_plan(request)),
                "plan ready",
            )[1],
            lambda request: (
                request.artifacts.impl_notes.write_text("# Notes\n\nImplemented.\n"),
                "implemented",
            )[1],
            lambda request: (
                request.artifacts.test_strat.write_text("# Test Strategy\n\nValidate externally.\n"),
                "tests ready",
            )[1],
        ],
        verifier_turns=[
            lambda request: (_write_live_review(request), Outcome(raw_output="ready", tag="plan_ready"))[1],
            lambda request: (_write_live_review(request), Outcome(raw_output="done", tag="implemented"))[1],
            block_test,
        ],
    )

    result = run_workflow_package(
        "devloop",
        provider=provider,
        options=_runner_options(
            tmp_path,
            task_id="task-blocked-test-review",
            message="Stop when validation is blocked",
            workflow_params={"auto_followup_max_depth": 0},
        ),
    )

    assert result.terminal == "AWAIT_INPUT"
    assert result.last_event is not None
    assert result.last_event.tag == "blocked"
    assert "external dependency" in result.last_event.reason
    assert not any(call.step_name == "audit" for call in provider.calls)
    plan = json.loads(
        (tmp_path / ".botpipe/tasks/task-blocked-test-review/plan/phase_plan.json").read_text(encoding="utf-8")
    )
    assert plan["phases"][0]["status"] == "in_progress"
    events_path = next(
        (tmp_path / ".botpipe/tasks/task-blocked-test-review/wf_devloop/runs").iterdir()
    ) / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    assert not any(event.get("event_type") == "phase_completed" for event in events)


def test_passing_review_allows_audit_to_report_actionable_followup(tmp_path: Path) -> None:
    def write_followup_audit(request) -> str:
        request.artifacts.audit_result.write_json(
            {
                "version": 1,
                "task_id": request.context.task_id,
                "request_snapshot_ref": str(request.context.request.file),
                "status": "needs_followup",
                "summary": "The requested change is complete; one separate improvement remains.",
                "gaps": [
                    {
                        "id": "GAP-1",
                        "severity": "low",
                        "summary": "A separate documentation improvement remains.",
                        "evidence": ["The implementation evidence does not include that optional document."],
                        "followup": "Add the optional document in a separate run.",
                    }
                ],
            }
        )
        request.artifacts.gap_report.write_text("# Gap Report\n\n- GAP-1: optional documentation.\n")
        request.artifacts.revised_request.write_text("Add the optional document.\n")
        return "audit ready"

    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.phase_plan.write_json(_phase_plan(request)),
                "plan ready",
            )[1],
            lambda request: (
                request.artifacts.impl_notes.write_text("# Notes\n\nImplemented.\n"),
                "implemented",
            )[1],
            write_followup_audit,
        ],
        verifier_turns=[
            lambda request: (_write_live_review(request), Outcome(raw_output="ready", tag="plan_ready"))[1],
            lambda request: (_write_live_review(request), Outcome(raw_output="done", tag="implemented"))[1],
            lambda request: (_write_live_review(request), Outcome(raw_output="ready", tag="audit_ready"))[1],
        ],
    )

    result = run_workflow_package(
        "devloop",
        provider=provider,
        options=_runner_options(
            tmp_path,
            task_id="task-audit-followup",
            message="Complete the task and identify separate follow-up",
            workflow_params={"skip_test_phase": True, "auto_followup_max_depth": 0},
        ),
    )

    assert result.terminal == "FINISH"
    followup_result = json.loads(
        (tmp_path / ".botpipe/tasks/task-audit-followup/audit/followup_result.json").read_text(encoding="utf-8")
    )
    assert followup_result["status"] == "skipped"
    assert followup_result["reason"] == "auto_followup_max_depth_reached"


def test_audit_repair_route_retries_as_missing_required_review_not_normal_rework(tmp_path: Path) -> None:
    def write_passed_audit(request) -> str:
        request.artifacts.audit_result.write_json(
            {
                "version": 1,
                "task_id": request.context.task_id,
                "request_snapshot_ref": str(request.context.request.file),
                "status": "passed",
                "summary": "The task is complete.",
                "gaps": [],
            }
        )
        request.artifacts.gap_report.write_text("# Gap Report\n\nNo gaps.\n")
        request.artifacts.revised_request.write_text("")
        return "audit ready"

    retry_feedback: list[str] = []

    def pass_retried_audit(request) -> Outcome:
        retry_feedback.append(request.retry_feedback or "")
        _write_live_review(request)
        return Outcome(raw_output="audit ready", tag="audit_ready")

    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.phase_plan.write_json(_phase_plan(request)),
                "plan ready",
            )[1],
            lambda request: (
                request.artifacts.impl_notes.write_text("# Notes\n\nImplemented.\n"),
                "implemented",
            )[1],
            write_passed_audit,
            write_passed_audit,
        ],
        verifier_turns=[
            lambda request: (_write_live_review(request), Outcome(raw_output="ready", tag="plan_ready"))[1],
            lambda request: (_write_live_review(request), Outcome(raw_output="done", tag="implemented"))[1],
            Outcome(raw_output="repair", tag="audit_needs_repair", reason="Audit needs repair."),
            pass_retried_audit,
        ],
    )

    result = run_workflow_package(
        "devloop",
        provider=provider,
        options=_runner_options(
            tmp_path,
            task_id="task-audit-report-required",
            message="Require a report before audit repair",
            workflow_params={"skip_test_phase": True, "auto_followup_max_depth": 0},
        ),
    )

    assert result.terminal == "FINISH"
    audit_calls = [call for call in provider.calls if call.step_name == "audit"]
    assert [(call.kind, call.attempt) for call in audit_calls] == [
        ("producer", 1),
        ("verifier", 1),
        ("producer", 2),
        ("verifier", 2),
    ]
    assert retry_feedback and "audit_review" in retry_feedback[0]
    events_path = next(
        (tmp_path / ".botpipe/tasks/task-audit-report-required/wf_devloop/runs").iterdir()
    ) / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    assert any(
        event.get("event_type") == "artifact_validation_failed"
        and event.get("artifact_name") == "audit_review"
        and event.get("validation_kind") == "missing_required_artifact"
        for event in events
    )


def _runner_options(root: Path, **kwargs: object) -> RunnerOptions:
    kwargs.setdefault(
        "runtime_config",
        RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
    )
    return RunnerOptions(root=root, **kwargs)


def _phase_plan(request) -> dict[str, object]:
    return {
        "version": 1,
        "task_id": request.context.task_id,
        "request_snapshot_ref": str(request.context.request.file),
        "status": "planned",
        "phases": [
            {
                "phase_id": "p01",
                "title": "Qualitative review",
                "objective": "Produce a clear implementation note.",
                "status": "planned",
                "scope": {"in_scope": ["Implementation note."], "out_of_scope": []},
                "dependencies": [],
                "criteria": [
                    {
                        "id": "AC-QUAL",
                        "text": "The implementation note clearly explains the result.",
                    }
                ],
                "deliverables": ["Implementation note."],
                "risks": ["The explanation could be unclear."],
                "rollback": ["Restore the previous note."],
            }
        ],
    }


def _write_live_review(request, *, verdict: str = "passed") -> dict[str, object]:
    review = request.context.state.review
    artifacts = {
        "plan": "plan_review",
        "implement": "impl_review",
        "test": "test_review",
        "review_phase_item": "phase_item_review_report",
        "audit": "audit_review",
    }
    payload: dict[str, object] = {
        "review_id": review.id,
        "criteria": [
            {
                "id": criterion.id,
                "verdict": verdict,
                "evidence": [f"Directly inspected evidence for {criterion.id}."] if verdict == "passed" else [],
                "reason": "The criterion is satisfied." if verdict == "passed" else "The criterion is not satisfied.",
            }
            for criterion in review.criteria
        ],
        "findings": [],
        "summary": f"The candidate {verdict} review.",
    }
    getattr(request.artifacts, artifacts[request.step_name]).write_json(payload)
    return payload
