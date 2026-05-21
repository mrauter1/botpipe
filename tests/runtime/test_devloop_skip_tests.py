from __future__ import annotations

import json
from pathlib import Path

from botpipe.core.primitives import Outcome
from botpipe.core.providers.fake import ScriptedLLMProvider
from botpipe.runtime.config import GitTrackingRuntimeConfig, RuntimeConfig
from botpipe.runtime.runner import RunnerOptions, run_workflow_package


def _runner_options(root: Path, **kwargs: object) -> RunnerOptions:
    kwargs.setdefault(
        "runtime_config",
        RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
    )
    return RunnerOptions(root=root, **kwargs)


def _phase_plan_payload(
    request,
    *,
    objective: str = "Exercise the skipped-test devloop path.",
    out_of_scope: list[str] | None = None,
    risks: list[str] | None = None,
    rollback: list[str] | None = None,
) -> dict[str, object]:
    return {
        "version": 1,
        "task_id": request.context.task_id,
        "request_snapshot_ref": str(request.context.request.file),
        "status": "planned",
        "phases": [
            {
                "phase_id": "p01-demo",
                "title": "Demo Phase",
                "objective": objective,
                "status": "planned",
                "scope": {
                    "in_scope": ["Write implementation notes."],
                    "out_of_scope": out_of_scope or ["Run a test producer/verifier turn."],
                },
                "dependencies": [],
                "criteria": [
                    {
                        "id": "P01-AC1",
                        "text": "Implementation notes are present.",
                    }
                ],
                "deliverables": ["Implementation notes."],
                "risks": risks or ["Skipped tests reduce independent validation."],
                "rollback": rollback or ["Disable skip_test_phase and rerun the phase."],
            }
        ],
    }


def test_devloop_skip_test_phase_writes_explicit_artifacts_and_completes_phase(tmp_path: Path) -> None:
    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.phase_plan.write_json(_phase_plan_payload(request)),
                "plan ready",
            )[1],
            lambda request: (
                request.artifacts.impl_notes.write_text("# Implementation Notes\n\nImplemented.\n"),
                "implemented",
            )[1],
            lambda request: (
                request.artifacts.audit_result.write_json(
                    {
                        "version": 1,
                        "task_id": request.context.task_id,
                        "request_snapshot_ref": str(request.context.request.file),
                        "status": "passed",
                        "summary": "Skipped-test path completed.",
                        "gaps": [],
                    }
                ),
                request.artifacts.gap_report.write_text("# Gap Report\n\nNo gaps.\n"),
                request.artifacts.revised_request.write_text(""),
                "audit ready",
            )[-1],
        ],
        verifier_turns=[
            lambda request: (
                request.artifacts.plan_criteria.write_text("# Plan Criteria\n\n- [x] Plan is valid.\n"),
                request.artifacts.plan_feedback.write_text("# Plan Feedback\n\nAccepted.\n"),
                Outcome(raw_output="plan ready", tag="plan_ready", payload={}),
            )[2],
            lambda request: (
                request.artifacts.impl_criteria.write_text("# Implementation Criteria\n\n- [x] Implementation is valid.\n"),
                request.artifacts.impl_feedback.write_text("# Implementation Feedback\n\nAccepted.\n"),
                Outcome(raw_output="implemented", tag="implemented", payload={}),
            )[2],
            lambda request: (
                request.artifacts.audit_criteria.write_text("# Audit Criteria\n\n- [x] Audit is valid.\n"),
                request.artifacts.audit_feedback.write_text("# Audit Feedback\n\nAccepted.\n"),
                Outcome(raw_output="audit ready", tag="audit_ready", payload={}),
            )[2],
        ],
    )

    result = run_workflow_package(
        "devloop",
        provider=provider,
        options=_runner_options(
            tmp_path,
            task_id="task-skip-tests",
            message="Exercise skip test phase",
            workflow_params={"skip_test_phase": True, "auto_followup_max_depth": 0},
        ),
    )

    run_dir = next((tmp_path / ".botpipe" / "tasks" / "task-skip-tests" / "wf_devloop" / "runs").iterdir())
    test_dir = tmp_path / ".botpipe" / "tasks" / "task-skip-tests" / "test" / "phases" / "p01-demo"
    phase_plan = json.loads((tmp_path / ".botpipe" / "tasks" / "task-skip-tests" / "plan" / "phase_plan.json").read_text())
    events = [
        json.loads(line)
        for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert result.terminal == "FINISH"
    assert phase_plan["status"] == "completed"
    assert phase_plan["phases"][0]["status"] == "completed"
    assert "skip_test_phase=true" in (test_dir / "test_strategy.md").read_text(encoding="utf-8")
    assert "- [x] Test phase was intentionally skipped" in (test_dir / "criteria.md").read_text(encoding="utf-8")
    assert "reduced validation" in (test_dir / "feedback.md").read_text(encoding="utf-8")
    assert not (test_dir / "completion_gate_feedback.md").exists()
    assert [call.step_name for call in provider.calls] == [
        "plan",
        "plan",
        "implement",
        "implement",
        "audit",
        "audit",
    ]
    assert any(
        event.get("event_type") == "phase_completed" and event.get("phase_id") == "p01-demo"
        for event in events
    )


def test_devloop_runs_normal_test_phase_when_skip_test_phase_is_false(tmp_path: Path) -> None:
    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.phase_plan.write_json(
                    _phase_plan_payload(
                        request,
                        objective="Exercise the normal devloop test path.",
                        out_of_scope=["Skip the test producer/verifier turn."],
                        risks=["Normal tests may still be incomplete if evidence is weak."],
                        rollback=["Fix the failing phase and rerun devloop."],
                    )
                ),
                "plan ready",
            )[1],
            lambda request: (
                request.artifacts.impl_notes.write_text("# Implementation Notes\n\nImplemented.\n"),
                "implemented",
            )[1],
            lambda request: (
                request.artifacts.test_strat.write_text("# Test Strategy\n\nRan normal validation.\n"),
                "tests ready",
            )[1],
            lambda request: (
                request.artifacts.audit_result.write_json(
                    {
                        "version": 1,
                        "task_id": request.context.task_id,
                        "request_snapshot_ref": str(request.context.request.file),
                        "status": "passed",
                        "summary": "Normal test path completed.",
                        "gaps": [],
                    }
                ),
                request.artifacts.gap_report.write_text("# Gap Report\n\nNo gaps.\n"),
                request.artifacts.revised_request.write_text(""),
                "audit ready",
            )[-1],
        ],
        verifier_turns=[
            lambda request: (
                request.artifacts.plan_criteria.write_text("# Plan Criteria\n\n- [x] Plan is valid.\n"),
                request.artifacts.plan_feedback.write_text("# Plan Feedback\n\nAccepted.\n"),
                Outcome(raw_output="plan ready", tag="plan_ready", payload={}),
            )[2],
            lambda request: (
                request.artifacts.impl_criteria.write_text("# Implementation Criteria\n\n- [x] Implementation is valid.\n"),
                request.artifacts.impl_feedback.write_text("# Implementation Feedback\n\nAccepted.\n"),
                Outcome(raw_output="implemented", tag="implemented", payload={}),
            )[2],
            lambda request: (
                request.artifacts.test_criteria.write_text("# Test Criteria\n\n- [x] Normal validation passed.\n"),
                request.artifacts.test_feedback.write_text("# Test Feedback\n\nPhase passed.\n"),
                Outcome(raw_output="phase passed", tag="phase_passed", payload={}),
            )[2],
            lambda request: (
                request.artifacts.audit_criteria.write_text("# Audit Criteria\n\n- [x] Audit is valid.\n"),
                request.artifacts.audit_feedback.write_text("# Audit Feedback\n\nAccepted.\n"),
                Outcome(raw_output="audit ready", tag="audit_ready", payload={}),
            )[2],
        ],
    )

    result = run_workflow_package(
        "devloop",
        provider=provider,
        options=_runner_options(
            tmp_path,
            task_id="task-normal-tests",
            message="Exercise normal test phase",
            workflow_params={"auto_followup_max_depth": 0},
        ),
    )

    run_dir = next((tmp_path / ".botpipe" / "tasks" / "task-normal-tests" / "wf_devloop" / "runs").iterdir())
    test_dir = tmp_path / ".botpipe" / "tasks" / "task-normal-tests" / "test" / "phases" / "p01-demo"
    events = [
        json.loads(line)
        for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert result.terminal == "FINISH"
    assert "Ran normal validation." in (test_dir / "test_strategy.md").read_text(encoding="utf-8")
    assert "Normal validation passed." in (test_dir / "criteria.md").read_text(encoding="utf-8")
    assert "Phase passed." in (test_dir / "feedback.md").read_text(encoding="utf-8")
    assert "skip_test_phase=true" not in (test_dir / "test_strategy.md").read_text(encoding="utf-8")
    assert [call.step_name for call in provider.calls] == [
        "plan",
        "plan",
        "implement",
        "implement",
        "test",
        "test",
        "audit",
        "audit",
    ]
    assert any(
        event.get("event_type") == "phase_completed" and event.get("phase_id") == "p01-demo"
        for event in events
    )
