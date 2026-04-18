from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from autoloop_v3.runtime.runner import RunnerOptions, run_workflow
from autoloop_v3.runtime.stores.filesystem import load_session_payload
from autoloop_v3.workflow.errors import WorkflowExecutionError
from autoloop_v3.workflow.primitives import Outcome
from autoloop_v3.workflow.providers.fake import ScriptedLLMProvider
from autoloop_v3.workflows import run_autoloop_v1


REPO_ROOT = Path(__file__).resolve().parents[3]
LEGACY_SRC = REPO_ROOT / "autoloop" / "src"
if str(LEGACY_SRC) not in sys.path:
    sys.path.insert(0, str(LEGACY_SRC))

import autoloop.main as legacy_autoloop


def _task_and_run_dirs(root: Path, task_id: str) -> tuple[Path, Path]:
    task_dir = root / ".autoloop" / "tasks" / task_id
    run_dir = next((task_dir / "runs").iterdir())
    return task_dir, run_dir


def test_autoloop_v1_runs_with_generic_runtime_and_explicit_prompt_paths(tmp_path: Path):
    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.phase_plan.write_text(
                    json.dumps(
                        {
                            "version": 1,
                            "task_id": request.context.task_id,
                            "request_snapshot_ref": "request.md",
                            "phases": [{"phase_id": "phase-a"}, {"phase_id": "phase-b"}],
                        }
                    )
                ),
                "plan raw\n",
            )[1],
            lambda request: (
                request.artifacts.impl_notes.write_text("phase-a implementation notes\n"),
                "implement phase-a raw\n",
            )[1],
            lambda request: (
                request.artifacts.test_strat.write_text("phase-a test strategy\n"),
                "test phase-a raw\n",
            )[1],
            lambda request: (
                request.artifacts.impl_notes.write_text("phase-b implementation notes\n"),
                "implement phase-b raw\n",
            )[1],
            lambda request: (
                request.artifacts.test_strat.write_text("phase-b test strategy\n"),
                "test phase-b raw\n",
            )[1],
        ],
        verifier_turns=[
            Outcome(raw_output="plan ok\n", tag="plan_ready"),
            Outcome(raw_output="implement phase-a ok\n", tag="implemented"),
            Outcome(raw_output="test phase-a ok\n", tag="phase_passed"),
            Outcome(raw_output="implement phase-b ok\n", tag="implemented"),
            Outcome(raw_output="test phase-b ok\n", tag="phase_passed"),
        ],
    )

    result = run_workflow(
        REPO_ROOT / "autoloop_v1.py",
        provider=provider,
        options=RunnerOptions(root=tmp_path, task_id="task-1", request_text="Ship it"),
    )

    task_dir, run_dir = _task_and_run_dirs(tmp_path, "task-1")
    events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines() if line]

    assert result.terminal == "SUCCESS"
    assert result.history == (
        "plan",
        "activate_next_phase",
        "implement",
        "test",
        "activate_next_phase",
        "implement",
        "test",
        "activate_next_phase",
    )
    assert result.state.phase.id == "phase-b"
    assert (task_dir / "plan" / "phase_plan.yaml").exists()
    assert (task_dir / "implement" / "phases" / "phase-a" / "implementation_notes.md").read_text(encoding="utf-8") == (
        "phase-a implementation notes\n"
    )
    assert (task_dir / "test" / "phases" / "phase-b" / "test_strategy.md").read_text(encoding="utf-8") == (
        "phase-b test strategy\n"
    )
    assert (run_dir / "sessions" / "plan.json").exists()
    assert (run_dir / "sessions" / "phases" / "phase-a.json").exists()
    assert (run_dir / "sessions" / "phases" / "phase-b.json").exists()
    assert not (run_dir / "sessions" / "scopes").exists()
    assert events[0]["event_type"] == "run_started"
    assert events[-1]["event_type"] == "run_finished"
    assert events[-1]["status"] == "success"
    assert legacy_autoloop.latest_run_status(run_dir / "events.jsonl") == "success"
    assert [call.prompt_path for call in provider.calls if call.kind == "producer"][0].endswith(
        "autoloop/src/autoloop/templates/plan_producer.md"
    )


def test_ralph_loop_executes_with_generic_runtime_and_persistent_main_session(tmp_path: Path):
    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: (
                request.artifacts.scratchpad.write_text("understanding\n"),
                Outcome(raw_output="u raw\n", tag="understood"),
            )[1],
            Outcome(
                raw_output="plan raw\n",
                tag="action_planned",
                payload={"type": "shell", "command": "echo hi"},
            ),
            lambda request: (
                request.artifacts.scratchpad.write_text("reflection\n"),
                Outcome(raw_output="reflect raw\n", tag="goal_met"),
            )[1],
        ]
    )

    result = run_workflow(
        REPO_ROOT / "Ralph_loop.py",
        provider=provider,
        options=RunnerOptions(root=tmp_path, task_id="ralph-task", request_text="Do it"),
    )

    task_dir, run_dir = _task_and_run_dirs(tmp_path, "ralph-task")

    assert result.terminal == "SUCCESS"
    assert result.state.goal_met is True
    assert result.state.iteration == 1
    assert result.state.action.type == "shell"
    assert result.state.action.payload == "echo hi"
    assert result.state.action.result == "Executed shell: echo hi"
    assert (task_dir / "action_log.md").read_text(encoding="utf-8") == (
        "u raw\nplan raw\n[1] Executed shell: echo hi\nreflect raw\n"
    )
    assert (run_dir / "sessions" / "main_session.json").exists()
    assert [call.prompt_path for call in provider.calls if call.kind == "llm"] == [
        "ralph/understand.md",
        "ralph/plan_action.md",
        "ralph/reflect.md",
    ]


def test_runner_emits_fatal_error_status_for_legacy_status_reader_compatibility(tmp_path: Path):
    with pytest.raises(RuntimeError, match="scripted provider exhausted"):
        run_workflow(
            REPO_ROOT / "Ralph_loop.py",
            provider=ScriptedLLMProvider(),
            options=RunnerOptions(root=tmp_path, task_id="fatal-task", request_text="Do it"),
        )

    _task_dir, run_dir = _task_and_run_dirs(tmp_path, "fatal-task")
    events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines() if line]

    assert events[-1]["event_type"] == "run_finished"
    assert events[-1]["status"] == "fatal_error"
    assert legacy_autoloop.latest_run_status(run_dir / "events.jsonl") == "fatal_error"


def test_legacy_latest_run_status_reads_generic_runtime_success_run(tmp_path: Path):
    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: (
                request.artifacts.scratchpad.write_text("understanding\n"),
                Outcome(raw_output="u raw\n", tag="understood"),
            )[1],
            Outcome(raw_output="plan raw\n", tag="goal_met"),
        ]
    )

    result = run_workflow(
        REPO_ROOT / "Ralph_loop.py",
        provider=provider,
        options=RunnerOptions(root=tmp_path, task_id="status-task", request_text="Do it"),
    )
    task_dir, run_dir = _task_and_run_dirs(tmp_path, "status-task")
    assert result.history == ("understand", "plan_action")
    assert result.state.goal_met is True
    assert result.state.iteration == 0
    assert result.state.action.result == ""
    assert (task_dir / "action_log.md").read_text(encoding="utf-8") == "u raw\nplan raw\n"
    assert [call.prompt_path for call in provider.calls if call.kind == "llm"] == [
        "ralph/understand.md",
        "ralph/plan_action.md",
    ]
    assert legacy_autoloop.latest_run_status(run_dir / "events.jsonl") == "success"


def test_autoloop_v1_parity_harness_preserves_legacy_workspace_logs_and_sessions(tmp_path: Path):
    session_ids: list[tuple[str, str]] = []
    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.phase_plan.write_text(
                    json.dumps(
                        {
                            "version": 1,
                            "task_id": request.context.task_id,
                            "request_snapshot_ref": "request.md",
                            "phases": [{"phase_id": "phase-a"}, {"phase_id": "phase-b"}],
                        }
                    )
                ),
                "plan raw\n",
            )[1],
            lambda request: (
                request.artifacts.impl_notes.write_text("phase-a implementation notes\n"),
                "implement phase-a raw\n",
            )[1],
            lambda request: (
                request.artifacts.test_strat.write_text("phase-a test strategy\n"),
                "test phase-a raw\n",
            )[1],
            lambda request: (
                request.artifacts.impl_notes.write_text("phase-b implementation notes\n"),
                "implement phase-b raw\n",
            )[1],
            lambda request: (
                request.artifacts.test_strat.write_text("phase-b test strategy\n"),
                "test phase-b raw\n",
            )[1],
        ],
        verifier_turns=[
            lambda request: (session_ids.append(("plan", request.session.session_id)), Outcome(raw_output="plan ok\n", tag="plan_ready"))[1],
            lambda request: (
                session_ids.append(("implement-a", request.session.session_id)),
                Outcome(raw_output="implement phase-a ok\n", tag="implemented"),
            )[1],
            lambda request: (
                session_ids.append(("test-a", request.session.session_id)),
                Outcome(raw_output="test phase-a ok\n", tag="phase_passed"),
            )[1],
            lambda request: (
                session_ids.append(("implement-b", request.session.session_id)),
                Outcome(raw_output="implement phase-b ok\n", tag="implemented"),
            )[1],
            lambda request: (
                session_ids.append(("test-b", request.session.session_id)),
                Outcome(raw_output="test phase-b ok\n", tag="phase_passed"),
            )[1],
        ],
    )

    result = run_autoloop_v1(
        REPO_ROOT / "autoloop_v1.py",
        provider=provider,
        options=RunnerOptions(root=tmp_path, task_id="parity-task", request_text="Ship it"),
    )

    task_dir, run_dir = _task_and_run_dirs(tmp_path, "parity-task")
    events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines() if line]
    run_raw = (run_dir / "raw_phase_log.md").read_text(encoding="utf-8")
    task_raw = (task_dir / "raw_phase_log.md").read_text(encoding="utf-8")

    assert result.terminal == "SUCCESS"
    assert (task_dir / "decisions.txt").exists()
    assert (task_dir / "raw_phase_log.md").exists()
    assert (run_dir / "raw_phase_log.md").exists()
    assert (run_dir / "sessions" / "plan.json").exists()
    assert (run_dir / "sessions" / "phases" / "phase-a.json").exists()
    assert (run_dir / "sessions" / "phases" / "phase-b.json").exists()
    assert (task_dir / "implement" / "phases" / "phase-a" / "implementation_notes.md").read_text(encoding="utf-8") == (
        "phase-a implementation notes\n"
    )
    assert (task_dir / "test" / "phases" / "phase-b" / "test_strategy.md").read_text(encoding="utf-8") == (
        "phase-b test strategy\n"
    )
    assert "entry=phase_output | pair=plan | phase=producer" in run_raw
    assert "entry=phase_output | pair=implement | phase=verifier" in run_raw
    assert "entry=phase_output | pair=test | phase=verifier" in task_raw
    assert events[0]["event_type"] == "run_started"
    assert events[-1]["event_type"] == "run_finished"
    assert events[-1]["status"] == "success"
    assert legacy_autoloop.latest_run_status(run_dir / "events.jsonl") == "success"
    assert [(event["step_name"], event.get("phase_id")) for event in events if event["event_type"] == "step_executed"] == [
        ("plan", None),
        ("activate_next_phase", "phase-a"),
        ("implement", "phase-a"),
        ("test", "phase-a"),
        ("activate_next_phase", "phase-b"),
        ("implement", "phase-b"),
        ("test", "phase-b"),
        ("activate_next_phase", "phase-b"),
    ]
    assert [event["phase_id"] for event in events if event["event_type"] == "phase_started"] == ["phase-a", "phase-b"]
    assert [event["phase_id"] for event in events if event["event_type"] == "phase_completed"] == ["phase-a", "phase-b"]
    phase_a_started = next(event["seq"] for event in events if event["event_type"] == "phase_started" and event["phase_id"] == "phase-a")
    phase_a_implement = next(
        event["seq"]
        for event in events
        if event["event_type"] == "step_executed" and event.get("phase_id") == "phase-a" and event["step_name"] == "implement"
    )
    phase_a_test = next(
        event["seq"]
        for event in events
        if event["event_type"] == "step_executed" and event.get("phase_id") == "phase-a" and event["step_name"] == "test"
    )
    phase_a_completed = next(
        event["seq"] for event in events if event["event_type"] == "phase_completed" and event["phase_id"] == "phase-a"
    )
    assert phase_a_started < phase_a_implement
    assert phase_a_test < phase_a_completed

    observed = dict(session_ids)
    assert observed["plan"].startswith("plan_session:global:")
    assert observed["implement-a"] == observed["test-a"]
    assert observed["implement-b"] == observed["test-b"]
    assert observed["implement-a"] != observed["implement-b"]


def test_autoloop_v1_parity_harness_requires_explicit_session_paths_before_creating_workspace(tmp_path: Path):
    workflow_file = tmp_path / "missing_session_paths_autoloop.py"
    workflow_file.write_text(
        """
from __future__ import annotations

from pydantic import BaseModel

from workflow import LLMStep, SUCCESS, Workflow
from workflow.primitives import Outcome


class MissingSessionPathsAutoloop(Workflow):
    class State(BaseModel):
        done: bool = False

    plan = LLMStep(name="plan", producer="ask.md")
    entry = plan
    transitions = {plan: {"done": SUCCESS}}

    @staticmethod
    def on_plan(state: State, outcome: Outcome, artifacts):
        return state.model_copy(update={"done": True})
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        WorkflowExecutionError,
        match="autoloop_v1 parity harness requires the workflow to declare SessionPaths",
    ):
        run_autoloop_v1(
            workflow_file,
            provider=ScriptedLLMProvider(),
            options=RunnerOptions(root=tmp_path, task_id="missing-session-path-task", request_text="Ship it"),
        )

    assert not (tmp_path / ".autoloop" / "tasks" / "missing-session-path-task").exists()


def test_autoloop_v1_parity_harness_preserves_exact_legacy_phase_dir_encoding_for_unsafe_phase_ids(tmp_path: Path):
    unsafe_phase_id = "Phase / One"
    expected_dir_key = "_pid-5068617365202f204f6e65"
    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.phase_plan.write_text(
                    json.dumps(
                        {
                            "version": 1,
                            "task_id": request.context.task_id,
                            "request_snapshot_ref": "request.md",
                            "phases": [{"phase_id": unsafe_phase_id}],
                        }
                    )
                ),
                "plan raw\n",
            )[1],
            lambda request: (
                request.artifacts.impl_notes.write_text("unsafe phase implementation notes\n"),
                "implement raw\n",
            )[1],
            lambda request: (
                request.artifacts.test_strat.write_text("unsafe phase test strategy\n"),
                "test raw\n",
            )[1],
        ],
        verifier_turns=[
            Outcome(raw_output="plan ok\n", tag="plan_ready"),
            Outcome(raw_output="implemented\n", tag="implemented"),
            Outcome(raw_output="phase passed\n", tag="phase_passed"),
        ],
    )

    result = run_autoloop_v1(
        REPO_ROOT / "autoloop_v1.py",
        provider=provider,
        options=RunnerOptions(root=tmp_path, task_id="unsafe-phase-task", request_text="Ship it"),
    )

    task_dir, run_dir = _task_and_run_dirs(tmp_path, "unsafe-phase-task")
    events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines() if line]

    assert result.terminal == "SUCCESS"
    assert result.state.phase.id == unsafe_phase_id
    assert result.state.phase.dir_key == expected_dir_key
    assert (task_dir / "implement" / "phases" / expected_dir_key / "implementation_notes.md").read_text(
        encoding="utf-8"
    ) == "unsafe phase implementation notes\n"
    assert (task_dir / "test" / "phases" / expected_dir_key / "test_strategy.md").read_text(encoding="utf-8") == (
        "unsafe phase test strategy\n"
    )
    assert (run_dir / "sessions" / "phases" / f"{expected_dir_key}.json").exists()
    assert not (run_dir / "sessions" / "scopes").exists()
    assert [event["phase_id"] for event in events if event["event_type"] == "phase_started"] == [unsafe_phase_id]
    assert [event["phase_id"] for event in events if event["event_type"] == "phase_completed"] == [unsafe_phase_id]
    assert legacy_autoloop.latest_run_status(run_dir / "events.jsonl") == "success"


def test_autoloop_v1_parity_harness_persists_clarifications_and_resumes(tmp_path: Path):
    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.phase_plan.write_text(
                    json.dumps(
                        {
                            "version": 1,
                            "task_id": request.context.task_id,
                            "request_snapshot_ref": "request.md",
                            "phases": [{"phase_id": "phase-a"}],
                        }
                    )
                ),
                "plan raw\n",
            )[1],
            lambda request: (
                request.artifacts.impl_notes.write_text("phase-a initial implementation notes\n"),
                "implement phase-a raw\n",
            )[1],
            lambda request: (
                request.artifacts.phase_plan.write_text(
                    json.dumps(
                        {
                            "version": 1,
                            "task_id": request.context.task_id,
                            "request_snapshot_ref": "request.md",
                            "phases": [{"phase_id": "phase-a"}],
                        }
                    )
                ),
                "plan raw retry\n",
            )[1],
            lambda request: (
                request.artifacts.phase_plan.write_text(
                    json.dumps(
                        {
                            "version": 1,
                            "task_id": request.context.task_id,
                            "request_snapshot_ref": "request.md",
                            "phases": [{"phase_id": "phase-a"}],
                        }
                    )
                ),
                "plan raw answered\n",
            )[1],
            lambda request: (
                request.artifacts.impl_notes.write_text("phase-a implementation notes\n"),
                "implement phase-a raw\n",
            )[1],
            lambda request: (
                request.artifacts.test_strat.write_text("phase-a test strategy\n"),
                "test phase-a raw\n",
            )[1],
        ],
        verifier_turns=[
            Outcome(raw_output="plan ok\n", tag="plan_ready"),
            Outcome(raw_output="Need replanning\n", tag="needs_replan"),
            Outcome(raw_output="Need clarification\n", tag="question", question="Need confirmation?"),
            Outcome(raw_output="plan ok after answer\n", tag="plan_ready"),
            Outcome(raw_output="implement ok\n", tag="implemented"),
            Outcome(raw_output="test ok\n", tag="phase_passed"),
        ],
    )

    paused = run_autoloop_v1(
        REPO_ROOT / "autoloop_v1.py",
        provider=provider,
        options=RunnerOptions(root=tmp_path, task_id="clarify-task", request_text="Ship it"),
    )

    task_dir, run_dir = _task_and_run_dirs(tmp_path, "clarify-task")
    paused_events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines() if line]

    assert paused.terminal == "PAUSE"
    assert paused.checkpoint is not None
    assert paused.checkpoint.pending_question == "Need confirmation?"
    assert any(event["event_type"] == "question" for event in paused_events)
    assert paused_events[-1]["status"] == "paused"

    resumed = run_autoloop_v1(
        REPO_ROOT / "autoloop_v1.py",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="clarify-task",
            run_id=run_dir.name,
            resume=True,
            answer="Proceed",
        ),
    )

    decisions_text = (task_dir / "decisions.txt").read_text(encoding="utf-8")
    run_raw = (run_dir / "raw_phase_log.md").read_text(encoding="utf-8")
    plan_payload = load_session_payload(run_dir / "sessions" / "plan.json", "persistent", "codex")
    resumed_events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines() if line]

    assert resumed.terminal == "SUCCESS"
    assert not (run_dir / "checkpoint.json").exists()
    assert 'entry="questions"' in decisions_text
    assert 'entry="answers"' in decisions_text
    assert "Need confirmation?" in decisions_text
    assert "Proceed" in decisions_text
    assert "entry=question | pair=plan | phase=verifier | cycle=2 | attempt=1" in run_raw
    assert "entry=clarification" in run_raw
    assert "entry=clarification | pair=plan | phase=verifier | cycle=2 | attempt=1 | source=resume" in run_raw
    assert "Question:\nNeed confirmation?\n\nAnswer:\nProceed" in run_raw
    assert plan_payload["metadata"]["pending_clarification_note"] == "Question:\nNeed confirmation?\n\nAnswer:\nProceed"
    assert resumed_events[-1]["status"] == "success"
    assert legacy_autoloop.latest_run_status(run_dir / "events.jsonl") == "success"


def test_autoloop_v1_parity_harness_maps_blocked_pause_to_legacy_status(tmp_path: Path):
    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.phase_plan.write_text(
                    json.dumps(
                        {
                            "version": 1,
                            "task_id": request.context.task_id,
                            "request_snapshot_ref": "request.md",
                            "phases": [{"phase_id": "phase-a"}],
                        }
                    )
                ),
                "plan raw\n",
            )[1],
            lambda request: (
                request.artifacts.impl_notes.write_text("phase-a implementation notes\n"),
                "implement raw cycle 1\n",
            )[1],
            lambda request: (
                request.artifacts.test_strat.write_text("phase-a test strategy\n"),
                "test raw cycle 1\n",
            )[1],
            lambda request: (
                request.artifacts.impl_notes.write_text("phase-a rework notes\n"),
                "implement raw cycle 2\n",
            )[1],
        ],
        verifier_turns=[
            Outcome(raw_output="plan ok\n", tag="plan_ready"),
            Outcome(raw_output="implemented\n", tag="implemented"),
            Outcome(raw_output="Need rework\n", tag="needs_rework"),
            Outcome(raw_output="Blocked on dependency\n", tag="blocked", reason="waiting on dependency"),
        ],
    )

    result = run_autoloop_v1(
        REPO_ROOT / "autoloop_v1.py",
        provider=provider,
        options=RunnerOptions(root=tmp_path, task_id="blocked-task", request_text="Ship it"),
    )

    _task_dir, run_dir = _task_and_run_dirs(tmp_path, "blocked-task")
    events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines() if line]
    run_raw = (run_dir / "raw_phase_log.md").read_text(encoding="utf-8")

    assert result.terminal == "PAUSE"
    assert result.last_event is not None and result.last_event.tag == "blocked"
    assert (run_dir / "checkpoint.json").exists()
    assert any(event["event_type"] == "blocked" for event in events)
    assert events[-1]["status"] == "blocked"
    assert legacy_autoloop.latest_run_status(run_dir / "events.jsonl") == "blocked"
    assert "entry=blocked | pair=implement | phase=verifier | cycle=2 | attempt=1" in run_raw
    assert [event["phase_id"] for event in events if event["event_type"] == "phase_started"] == ["phase-a"]
    assert not any(event["event_type"] == "phase_completed" for event in events)


def test_autoloop_v1_parity_harness_maps_failed_terminal_to_legacy_status(tmp_path: Path):
    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.phase_plan.write_text(
                    json.dumps(
                        {
                            "version": 1,
                            "task_id": request.context.task_id,
                            "request_snapshot_ref": "request.md",
                            "phases": [{"phase_id": "phase-a"}],
                        }
                    )
                ),
                "plan raw\n",
            )[1]
        ],
        verifier_turns=[Outcome(raw_output="Plan failed\n", tag="failed", reason="verification failed")],
    )

    result = run_autoloop_v1(
        REPO_ROOT / "autoloop_v1.py",
        provider=provider,
        options=RunnerOptions(root=tmp_path, task_id="failed-task", request_text="Ship it"),
    )

    _task_dir, run_dir = _task_and_run_dirs(tmp_path, "failed-task")
    events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines() if line]
    run_raw = (run_dir / "raw_phase_log.md").read_text(encoding="utf-8")

    assert result.terminal == "FAIL"
    assert result.last_event is not None and result.last_event.tag == "failed"
    assert (run_dir / "checkpoint.json").exists()
    assert any(event["event_type"] == "failed" for event in events)
    assert events[-1]["status"] == "failed"
    assert legacy_autoloop.latest_run_status(run_dir / "events.jsonl") == "failed"
    assert "entry=failed" in run_raw
