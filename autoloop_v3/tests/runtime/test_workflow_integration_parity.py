from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from autoloop_v3.runtime.config import discover_config_file
from autoloop_v3.runtime.events import extract_clarifications, parse_decisions_headers
from autoloop_v3.runtime.runner import RunnerOptions, run_workflow
from autoloop_v3.runtime.stores.filesystem import load_session_payload
from autoloop_v3.runtime.workspace import phase_dir_key, resolve_resume_state_root
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


def test_autoloop_v1_explicit_multi_phase_run_preserves_phase_scoping_and_legacy_event_status(tmp_path: Path):
    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.phase_plan.write_text(
                    json.dumps(
                        {
                            "version": 1,
                            "task_id": request.context.task_id,
                            "request_snapshot_ref": "request.md",
                            "phases": [{"phase_id": "phase-a"}, {"phase_id": "Phase Two"}],
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
                request.artifacts.impl_notes.write_text("phase-two implementation notes\n"),
                "implement phase-two raw\n",
            )[1],
            lambda request: (
                request.artifacts.test_strat.write_text("phase-two test strategy\n"),
                "test phase-two raw\n",
            )[1],
        ],
        verifier_turns=[
            Outcome(raw_output="plan ok\n", tag="plan_ready"),
            Outcome(raw_output="implement phase-a ok\n", tag="implemented"),
            Outcome(raw_output="test phase-a ok\n", tag="phase_passed"),
            Outcome(raw_output="implement phase-two ok\n", tag="implemented"),
            Outcome(raw_output="test phase-two ok\n", tag="phase_passed"),
        ],
    )

    result = run_workflow(
        REPO_ROOT / "autoloop_v1.py",
        provider=provider,
        options=RunnerOptions(root=tmp_path, task_id="task-1", request_text="Ship it"),
    )

    task_dir, run_dir = _task_and_run_dirs(tmp_path, "task-1")
    encoded_phase_two = phase_dir_key("Phase Two")

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
    assert result.state.phase.id == "Phase Two"
    assert (task_dir / "plan" / "phase_plan.yaml").exists()
    assert (task_dir / "phases" / "phase-a" / "implement" / "implementation_notes.md").read_text(encoding="utf-8") == (
        "phase-a implementation notes\n"
    )
    assert (task_dir / "phases" / "phase-a" / "test" / "test_strategy.md").read_text(encoding="utf-8") == (
        "phase-a test strategy\n"
    )
    assert (
        task_dir / "phases" / encoded_phase_two / "implement" / "implementation_notes.md"
    ).read_text(encoding="utf-8") == "phase-two implementation notes\n"
    assert (task_dir / "phases" / encoded_phase_two / "test" / "test_strategy.md").read_text(encoding="utf-8") == (
        "phase-two test strategy\n"
    )
    assert (run_dir / "sessions" / "plan.json").exists()
    assert (run_dir / "sessions" / "phases" / "phase-a.json").exists()
    assert (run_dir / "sessions" / "phases" / f"{encoded_phase_two}.json").exists()

    events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines() if line]
    assert events[0]["event_type"] == "run_started"
    assert events[-1]["event_type"] == "run_finished"
    assert events[-1]["status"] == "success"
    assert legacy_autoloop.latest_run_status(run_dir / "events.jsonl") == "success"
    assert [call.prompt_path for call in provider.calls if call.kind == "producer"][0].endswith(
        "autoloop/src/autoloop/templates/plan_producer.md"
    )


def test_autoloop_v1_invalid_phase_plan_falls_back_to_implicit_phase(tmp_path: Path):
    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (request.artifacts.phase_plan.write_text("phases: [\n"), "plan raw\n")[1],
            lambda request: (
                request.artifacts.impl_notes.write_text("implicit implementation notes\n"),
                "implement raw\n",
            )[1],
            lambda request: (
                request.artifacts.test_strat.write_text("implicit test strategy\n"),
                "test raw\n",
            )[1],
        ],
        verifier_turns=[
            Outcome(raw_output="plan ok\n", tag="plan_ready"),
            Outcome(raw_output="implement ok\n", tag="implemented"),
            Outcome(raw_output="test ok\n", tag="phase_passed"),
        ],
    )

    result = run_workflow(
        REPO_ROOT / "autoloop_v1.py",
        provider=provider,
        options=RunnerOptions(root=tmp_path, task_id="implicit-task", request_text="Ship it"),
    )

    task_dir, run_dir = _task_and_run_dirs(tmp_path, "implicit-task")

    assert result.terminal == "SUCCESS"
    assert result.state.phase.id == "implicit-phase"
    assert (
        task_dir / "phases" / "implicit-phase" / "implement" / "implementation_notes.md"
    ).read_text(encoding="utf-8") == "implicit implementation notes\n"
    assert (
        task_dir / "phases" / "implicit-phase" / "test" / "test_strategy.md"
    ).read_text(encoding="utf-8") == "implicit test strategy\n"
    assert (run_dir / "sessions" / "phases" / "implicit-phase.json").exists()


def test_resume_answer_injection_writes_legacy_compatible_clarification_artifacts(tmp_path: Path):
    first_provider = ScriptedLLMProvider(
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
        verifier_turns=[Outcome(raw_output="need approval\n", tag="question", question="Approve plan?")],
    )

    paused = run_workflow(
        REPO_ROOT / "autoloop_v1.py",
        provider=first_provider,
        options=RunnerOptions(root=tmp_path, task_id="resume-task", request_text="Ship it"),
    )

    task_dir, run_dir = _task_and_run_dirs(tmp_path, "resume-task")

    assert paused.terminal == "PAUSE"
    assert paused.checkpoint is not None
    assert paused.checkpoint.pending_question == "Approve plan?"

    resumed_provider = ScriptedLLMProvider(
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
                "plan raw resumed\n",
            )[1],
            lambda request: (
                request.artifacts.impl_notes.write_text("implementation notes\n"),
                "implement raw\n",
            )[1],
            lambda request: (
                request.artifacts.test_strat.write_text("test strategy\n"),
                "test raw\n",
            )[1],
        ],
        verifier_turns=[
            Outcome(raw_output="plan ok\n", tag="plan_ready"),
            Outcome(raw_output="implement ok\n", tag="implemented"),
            Outcome(raw_output="test ok\n", tag="phase_passed"),
        ],
    )

    resumed = run_workflow(
        REPO_ROOT / "autoloop_v1.py",
        provider=resumed_provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="resume-task",
            run_id=run_dir.name,
            resume=True,
            answer="Yes",
        ),
    )

    decisions_text = (task_dir / "decisions.txt").read_text(encoding="utf-8")
    decision_blocks = parse_decisions_headers(decisions_text)
    legacy_blocks = legacy_autoloop.parse_decisions_headers(decisions_text)
    run_raw_log = run_dir / "raw_phase_log.md"
    expected_note = "Question:\nApprove plan?\n\nAnswer:\nYes"
    session_payload = load_session_payload(run_dir / "sessions" / "plan.json", "persistent", "codex")
    legacy_session = legacy_autoloop.load_session_state(run_dir / "sessions" / "plan.json", "persistent")

    assert resumed.terminal == "SUCCESS"
    assert [block.attrs["entry"] for block in decision_blocks] == ["questions", "answers"]
    assert decision_blocks[0].attrs["turn_seq"] == decision_blocks[1].attrs["turn_seq"]
    assert decision_blocks[0].attrs["qa_seq"] == decision_blocks[1].attrs["qa_seq"]
    assert [(block.attrs, block.body) for block in decision_blocks] == [
        (block.attrs, block.body) for block in legacy_blocks
    ]
    assert extract_clarifications(run_raw_log) == [("Approve plan?", "Yes")]
    assert legacy_autoloop.extract_clarifications(run_raw_log) == [("Approve plan?", "Yes")]
    assert "entry=clarification" in run_raw_log.read_text(encoding="utf-8")
    assert session_payload["metadata"]["pending_clarification_note"] == expected_note
    assert legacy_session.pending_clarification_note == expected_note


def test_ralph_loop_executes_with_legacy_shims_and_persistent_main_session(tmp_path: Path):
    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: (request.artifacts.scratchpad.write_text("understanding\n"), Outcome(raw_output="u raw\n", tag="understood"))[1],
            Outcome(
                raw_output="plan raw\n",
                tag="action_planned",
                payload={"type": "shell", "command": "echo hi"},
            ),
            lambda request: (request.artifacts.scratchpad.write_text("reflection\n"), Outcome(raw_output="reflect raw\n", tag="goal_met"))[1],
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
    assert (task_dir / "action_log.md").read_text(encoding="utf-8") == "u raw\nplan raw\nreflect raw\n"
    assert (run_dir / "sessions" / "main_session.json").exists()
    assert [call.prompt_path for call in provider.calls if call.kind == "llm"] == [
        "ralph/understand.md",
        "ralph/plan_action.md",
        "ralph/reflect.md",
    ]


def test_runtime_compatibility_helpers_match_legacy_runtime(tmp_path: Path):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "autoloop.config").write_text("{}", encoding="utf-8")
    (tmp_path / ".superloop" / "tasks" / "legacy-task" / "runs" / "legacy-run").mkdir(parents=True)

    decisions_text = (
        '<autoloop-decisions-header version="1" block_seq="1" owner="runtime" phase_id="task-global" '
        'pair="plan" turn_seq="1" run_id="run-1" ts="2026-04-17T00:00:00+00:00" entry="questions" '
        'qa_seq="1" source="runtime-runner" />\n'
        "Question?\n"
        '<autoloop-decisions-header version="1" block_seq="2" owner="runtime" phase_id="task-global" '
        'pair="plan" turn_seq="1" run_id="run-1" ts="2026-04-17T00:00:01+00:00" entry="answers" '
        'qa_seq="1" source="runtime-runner" />\n'
        "Answer.\n"
    )

    assert discover_config_file(workspace_root) == legacy_autoloop.discover_config_file(workspace_root)
    assert resolve_resume_state_root(tmp_path, task_id="legacy-task") == legacy_autoloop.resolve_resume_state_root(
        tmp_path,
        task_id="legacy-task",
    )
    assert [(block.attrs, block.body) for block in parse_decisions_headers(decisions_text)] == [
        (block.attrs, block.body) for block in legacy_autoloop.parse_decisions_headers(decisions_text)
    ]


def test_runner_emits_fatal_error_status_for_legacy_latest_run_status_compatibility(tmp_path: Path):
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


def test_legacy_latest_run_status_reads_v3_success_run(tmp_path: Path):
    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: (request.artifacts.scratchpad.write_text("understanding\n"), Outcome(raw_output="u raw\n", tag="understood"))[1],
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
