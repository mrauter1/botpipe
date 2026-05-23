from __future__ import annotations

import json
from pathlib import Path

from botpipe.core.compiler import compile_workflow
from botpipe.core.primitives import Outcome
from botpipe.core.providers.fake import ScriptedLLMProvider
from botpipe.runtime.config import GitTrackingRuntimeConfig, RuntimeConfig
from botpipe.runtime.runner import RunnerOptions, run_workflow_package
from botpipe.workflows.devloop import DevLoop


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


def _two_phase_plan_payload(request) -> dict[str, object]:
    payload = _phase_plan_payload(
        request,
        objective="Complete the first phase before reviewing the second.",
        out_of_scope=["Second phase work."],
    )
    phases = payload["phases"]
    assert isinstance(phases, list)
    phases.append(
        {
            "phase_id": "p02-demo",
            "title": "Second Demo Phase",
            "objective": "Unexecutable placeholder that requires item review.",
            "status": "planned",
            "scope": {
                "in_scope": ["Resolve the reviewed second phase."],
                "out_of_scope": [],
            },
            "dependencies": ["p01-demo"],
            "criteria": [
                {
                    "id": "P02-AC1",
                    "text": "Second phase implementation notes are present.",
                }
            ],
            "deliverables": ["Second phase implementation notes."],
            "risks": ["The item may need review."],
            "rollback": ["Restore the prior second phase definition."],
        }
    )
    return payload


def _write_audit_passed(request, summary: str) -> str:
    request.artifacts.audit_result.write_json(
        {
            "version": 1,
            "task_id": request.context.task_id,
            "request_snapshot_ref": str(request.context.request.file),
            "status": "passed",
            "summary": summary,
            "gaps": [],
        }
    )
    request.artifacts.gap_report.write_text("# Gap Report\n\nNo gaps.\n")
    request.artifacts.revised_request.write_text("")
    return "audit ready"


def _review_second_phase(request) -> str:
    payload = json.loads(request.artifacts.phase_plan.read_text())
    second_phase = payload["phases"][1]
    second_phase["objective"] = "Write reviewed second phase implementation notes."
    second_phase["scope"]["in_scope"] = ["Write reviewed second phase implementation notes."]
    second_phase["criteria"][0]["text"] = "Reviewed second phase implementation notes are present."
    second_phase["deliverables"] = ["Reviewed second phase implementation notes."]
    request.artifacts.phase_plan.write_json(payload)
    request.artifacts.phase_item_review.write_text(
        "\n".join(
            (
                "# Phase Item Review: p02-demo",
                "",
                "## Decision",
                "Reviewed",
                "",
                "## Defect",
                "- The original second phase objective was not executable.",
                "",
                "## Phase-plan changes",
                "- Replaced the active objective and criterion with executable wording.",
                "",
                "## Preserved state",
                "- Prior completed phases preserved.",
                "- Active phase id preserved.",
                "- Active phase status remains `in_progress`.",
                "",
                "## Implementation guidance",
                "- Implement the reviewed second phase notes.",
                "",
            )
        )
    )
    return "reviewed"


def test_devloop_routes_use_rework_and_implementation_owned_item_review() -> None:
    compiled = compile_workflow(DevLoop)

    assert compiled.routes["plan"]["plan_ready"].target == "validate_plan_completion"
    assert compiled.routes["plan"]["needs_rework"].target == "plan"
    assert "needs_replan" not in compiled.routes["plan"]

    assert compiled.routes["implement"]["implemented"].target == "validate_implement_completion"
    assert compiled.routes["implement"]["needs_rework"].target == "implement"
    assert compiled.routes["implement"]["needs_phase_item_review"].target == "review_phase_item"
    assert "needs_replan" not in compiled.routes["implement"]

    assert compiled.routes["test"]["phase_passed"].target == "validate_test_completion"
    assert compiled.routes["test"]["needs_rework"].target == "implement"
    assert "needs_phase_item_review" not in compiled.routes["test"]
    assert "needs_replan" not in compiled.routes["test"]

    assert compiled.routes["review_phase_item"]["phase_item_reviewed"].target == "validate_phase_item_review"
    assert compiled.routes["review_phase_item"]["needs_rework"].target == "review_phase_item"
    assert compiled.routes["validate_phase_item_review"]["phase_item_review_checked"].target == "implement"
    assert compiled.routes["validate_phase_item_review"]["phase_item_review_needs_repair"].target == "review_phase_item"


def test_devloop_prompts_do_not_advertise_needs_replan() -> None:
    prompt_dir = Path(__file__).parents[2] / "botpipe" / "workflows" / "devloop" / "prompts"

    offenders = {
        path.name: path.read_text(encoding="utf-8")
        for path in prompt_dir.glob("*.md")
        if "needs_replan" in path.read_text(encoding="utf-8")
    }

    assert offenders == {}


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
                _write_audit_passed(request, "Skipped-test path completed."),
            )[0],
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
                _write_audit_passed(request, "Normal test path completed."),
            )[0],
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


def test_devloop_implementation_rework_loops_to_implementation_not_plan(tmp_path: Path) -> None:
    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.phase_plan.write_json(_phase_plan_payload(request)),
                "plan ready",
            )[1],
            lambda request: (
                request.artifacts.impl_notes.write_text("# Implementation Notes\n\nIncomplete.\n"),
                "implemented",
            )[1],
            lambda request: (
                request.artifacts.impl_notes.write_text("# Implementation Notes\n\nImplemented after rework.\n"),
                "implemented",
            )[1],
            lambda request: (
                _write_audit_passed(request, "Implementation rework path completed."),
            )[0],
        ],
        verifier_turns=[
            lambda request: (
                request.artifacts.plan_criteria.write_text("# Plan Criteria\n\n- [x] Plan is valid.\n"),
                request.artifacts.plan_feedback.write_text("# Plan Feedback\n\nAccepted.\n"),
                Outcome(raw_output="plan ready", tag="plan_ready", payload={}),
            )[2],
            lambda request: (
                request.artifacts.impl_criteria.write_text(
                    "# Implementation Criteria\n\n- [ ] Implementation is incomplete.\n"
                ),
                request.artifacts.impl_feedback.write_text(
                    "# Implementation Feedback\n\n## Decision\nNeeds rework\n"
                ),
                Outcome(raw_output="needs rework", tag="needs_rework", payload={}),
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
            task_id="task-impl-rework",
            message="Exercise implementation rework",
            workflow_params={"skip_test_phase": True, "auto_followup_max_depth": 0},
        ),
    )

    assert result.terminal == "FINISH"
    assert [call.step_name for call in provider.calls] == [
        "plan",
        "plan",
        "implement",
        "implement",
        "implement",
        "implement",
        "audit",
        "audit",
    ]


def test_devloop_phase_item_review_validates_live_plan_and_refreshes_phase_state(tmp_path: Path) -> None:
    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.phase_plan.write_json(_two_phase_plan_payload(request)),
                "plan ready",
            )[1],
            lambda request: (
                request.artifacts.impl_notes.write_text("# Implementation Notes: p01-demo\n\nImplemented.\n"),
                "implemented",
            )[1],
            lambda request: (
                request.artifacts.impl_notes.write_text("# Implementation Notes: p02-demo\n\nBlocked by bad item.\n"),
                "blocked",
            )[1],
            _review_second_phase,
            lambda request: (
                request.artifacts.impl_notes.write_text(
                    "# Implementation Notes: p02-demo\n\nImplemented after item review.\n"
                ),
                "implemented",
            )[1],
            lambda request: (
                _write_audit_passed(request, "Phase item review path completed."),
            )[0],
        ],
        verifier_turns=[
            lambda request: (
                request.artifacts.plan_criteria.write_text("# Plan Criteria\n\n- [x] Plan is valid.\n"),
                request.artifacts.plan_feedback.write_text("# Plan Feedback\n\nAccepted.\n"),
                Outcome(raw_output="plan ready", tag="plan_ready", payload={}),
            )[2],
            lambda request: (
                request.artifacts.impl_criteria.write_text("# Implementation Criteria\n\n- [x] P01 is valid.\n"),
                request.artifacts.impl_feedback.write_text("# Implementation Feedback\n\nAccepted.\n"),
                Outcome(raw_output="implemented", tag="implemented", payload={}),
            )[2],
            lambda request: (
                request.artifacts.impl_criteria.write_text(
                    "# Implementation Criteria\n\n- [ ] Active item is not executable.\n"
                ),
                request.artifacts.impl_feedback.write_text(
                    "# Implementation Feedback: p02-demo\n\n## Decision\nNeeds phase item review\n"
                ),
                Outcome(
                    raw_output="needs phase item review",
                    tag="needs_phase_item_review",
                    payload={},
                ),
            )[2],
            lambda request: (
                request.artifacts.phase_item_review_criteria.write_text(
                    "# Phase Item Review Criteria: p02-demo\n\n"
                    "- [x] The active phase id is preserved.\n"
                    "- [x] Completed prior phases are preserved.\n"
                    "- [x] The active item is executable after the review.\n"
                    "- [x] Live phase-plan statuses are consistent.\n"
                    "- [x] `item_review.md` explains the defect and changes.\n"
                ),
                request.artifacts.phase_item_review_feedback.write_text(
                    "# Phase Item Review Feedback: p02-demo\n\n## Decision\nReviewed\n"
                ),
                Outcome(raw_output="phase item reviewed", tag="phase_item_reviewed", payload={}),
            )[2],
            lambda request: (
                request.artifacts.impl_criteria.write_text("# Implementation Criteria\n\n- [x] P02 is valid.\n"),
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
            task_id="task-phase-item-review",
            message="Exercise phase item review",
            workflow_params={"skip_test_phase": True, "auto_followup_max_depth": 0},
        ),
    )

    phase_plan_path = tmp_path / ".botpipe" / "tasks" / "task-phase-item-review" / "plan" / "phase_plan.json"
    phase_plan = json.loads(phase_plan_path.read_text(encoding="utf-8"))
    item_review = (
        tmp_path
        / ".botpipe"
        / "tasks"
        / "task-phase-item-review"
        / "plan"
        / "phases"
        / "p02-demo"
        / "item_review.md"
    )

    assert result.terminal == "FINISH"
    assert phase_plan["status"] == "completed"
    assert phase_plan["phases"][0]["phase_id"] == "p01-demo"
    assert phase_plan["phases"][0]["status"] == "completed"
    assert phase_plan["phases"][1]["phase_id"] == "p02-demo"
    assert phase_plan["phases"][1]["status"] == "completed"
    assert phase_plan["phases"][1]["objective"] == "Write reviewed second phase implementation notes."
    assert "original second phase objective was not executable" in item_review.read_text(encoding="utf-8")
    assert [call.step_name for call in provider.calls] == [
        "plan",
        "plan",
        "implement",
        "implement",
        "implement",
        "implement",
        "review_phase_item",
        "review_phase_item",
        "implement",
        "implement",
        "audit",
        "audit",
    ]
