from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from autoloop_v3.runtime.runner import RunnerOptions, run_workflow
from autoloop_v3.workflow.primitives import Outcome
from autoloop_v3.workflow.providers.fake import ScriptedLLMProvider


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
    assert (task_dir / "phases" / "phase-a" / "implement" / "implementation_notes.md").read_text(encoding="utf-8") == (
        "phase-a implementation notes\n"
    )
    assert (task_dir / "phases" / "phase-b" / "test" / "test_strategy.md").read_text(encoding="utf-8") == (
        "phase-b test strategy\n"
    )
    assert (run_dir / "sessions" / "plan_session.json").exists()
    assert (run_dir / "sessions" / "scopes" / "phase-a" / "phase_session.json").exists()
    assert (run_dir / "sessions" / "scopes" / "phase-b" / "phase_session.json").exists()
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

    run_workflow(
        REPO_ROOT / "Ralph_loop.py",
        provider=provider,
        options=RunnerOptions(root=tmp_path, task_id="status-task", request_text="Do it"),
    )
    _task_dir, run_dir = _task_and_run_dirs(tmp_path, "status-task")
    assert legacy_autoloop.latest_run_status(run_dir / "events.jsonl") == "success"
