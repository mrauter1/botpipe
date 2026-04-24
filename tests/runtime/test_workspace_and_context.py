from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

from autoloop_v3.core.providers.fake import ScriptedLLMProvider
from autoloop_v3.runtime.runner import RunnerOptions, run_workflow_package
from autoloop_v3.runtime.workspace import list_workflow_run_summaries
from workflow.primitives import Outcome


def _clear_workflow_modules() -> None:
    importlib.invalidate_caches()
    for name in list(sys.modules):
        if name == "workflows" or name.startswith("workflows."):
            sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _isolate_generated_workflow_modules():
    _clear_workflow_modules()
    yield
    _clear_workflow_modules()


def test_run_creates_task_workflow_run_layout_and_immutable_request_snapshots(tmp_path: Path) -> None:
    _write_system_workflow_package(tmp_path, "snapshot_demo", "SnapshotWorkflow")

    first_result = run_workflow_package(
        "snapshot_demo",
        provider=ScriptedLLMProvider(),
        options=RunnerOptions(root=tmp_path, task_id="task-1", message="First message"),
    )

    task_dir = tmp_path / ".autoloop" / "tasks" / "task-1"
    workflow_dir = task_dir / "wf_snapshot_demo"
    runs_dir = workflow_dir / "runs"
    first_run_dir = next(runs_dir.iterdir())
    task_meta = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
    first_run_meta = json.loads((first_run_dir / "run.json").read_text(encoding="utf-8"))

    assert first_result.terminal == "SUCCESS"
    assert (task_dir / "messages.jsonl").exists()
    assert not (first_run_dir / "messages.jsonl").exists()
    assert (task_dir / "request.md").read_text(encoding="utf-8") == "First message\n"
    assert (first_run_dir / "request.md").read_text(encoding="utf-8") == "First message\n"
    assert (workflow_dir / "workflow.json").exists()
    assert task_meta["messages_file"] == ".autoloop/tasks/task-1/messages.jsonl"
    assert task_meta["request_file"] == ".autoloop/tasks/task-1/request.md"
    assert first_run_meta["status"] == "success"
    assert first_run_meta["task_folder"] == ".autoloop/tasks/task-1"
    assert first_run_meta["workflow_folder"] == ".autoloop/tasks/task-1/wf_snapshot_demo"
    assert first_run_meta["run_folder"] == f".autoloop/tasks/task-1/wf_snapshot_demo/runs/{first_run_dir.name}"
    assert first_run_meta["request_file"] == f".autoloop/tasks/task-1/wf_snapshot_demo/runs/{first_run_dir.name}/request.md"

    second_result = run_workflow_package(
        "snapshot_demo",
        provider=ScriptedLLMProvider(),
        options=RunnerOptions(root=tmp_path, task_id="task-1", message="Second message"),
    )

    run_dirs = sorted(path for path in runs_dir.iterdir() if path.is_dir())
    second_run_dir = next(path for path in run_dirs if path != first_run_dir)
    messages = [json.loads(line) for line in (task_dir / "messages.jsonl").read_text(encoding="utf-8").splitlines() if line]
    workflow_meta = json.loads((workflow_dir / "workflow.json").read_text(encoding="utf-8"))

    assert second_result.terminal == "SUCCESS"
    assert len(run_dirs) == 2
    assert [entry["message"] for entry in messages] == ["First message", "Second message"]
    assert all("intent_mode" not in entry for entry in messages)
    assert (task_dir / "request.md").read_text(encoding="utf-8") == "Second message\n"
    assert (first_run_dir / "request.md").read_text(encoding="utf-8") == "First message\n"
    assert (second_run_dir / "request.md").read_text(encoding="utf-8") == "Second message\n"
    assert workflow_meta["last_run_id"] == second_run_dir.name


def test_runtime_context_and_prompt_resolution_use_workflow_scope_and_package_root(tmp_path: Path) -> None:
    _write_llm_workflow_package(tmp_path, "context_demo", "ContextWorkflow")
    (tmp_path / "prompts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "prompts" / "ask.md").write_text("root-level prompt\n", encoding="utf-8")

    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: (
                request.artifacts.context_dump.write_text(
                    json.dumps(
                        {
                            "workflow_name": request.context.workflow_name,
                            "workflow_folder": str(request.context.workflow_folder),
                            "package_folder": str(request.context.package_folder),
                            "workflow_params": request.context.workflow_params,
                            "prompt_text": request.prompt.text,
                            "prompt_path": request.prompt.path,
                        }
                    ),
                ),
                request.artifacts.workflow_dump.write_text("workflow-scoped\n"),
                Outcome(raw_output="ok\n", tag="done"),
            )[2]
        ]
    )

    result = run_workflow_package(
        "context_demo",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="context-task",
            message="Inspect runtime context",
            workflow_params={"mode": "strict"},
        ),
    )

    task_dir = tmp_path / ".autoloop" / "tasks" / "context-task"
    workflow_dir = task_dir / "wf_context_demo"
    run_dir = next((workflow_dir / "runs").iterdir())
    payload = json.loads((run_dir / "context.json").read_text(encoding="utf-8"))
    run_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert result.terminal == "SUCCESS"
    assert payload["workflow_name"] == "context_demo"
    assert Path(payload["workflow_folder"]) == workflow_dir
    assert Path(payload["package_folder"]) == tmp_path / "workflows" / "context_demo"
    assert payload["workflow_params"] == {"mode": "strict"}
    assert payload["prompt_text"] == "package prompt\n"
    assert Path(payload["prompt_path"]) == tmp_path / "workflows" / "context_demo" / "prompts" / "ask.md"
    assert (workflow_dir / "workflow-note.txt").read_text(encoding="utf-8") == "workflow-scoped\n"
    assert run_meta["workflow_params"] == {"mode": "strict"}
    assert run_meta["workflow_folder"] == ".autoloop/tasks/context-task/wf_context_demo"


def test_resume_preserves_persisted_workflow_params_when_not_resupplied(tmp_path: Path) -> None:
    _write_pause_resume_workflow_package(tmp_path, "resume_params_demo", "ResumeParamsWorkflow")
    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: (
                request.artifacts.context_dump.write_text(
                    json.dumps(
                        {
                            "workflow_params": request.context.workflow_params,
                            "answer": request.context.answer,
                        }
                    ),
                ),
                Outcome(raw_output="Need answer", tag="question", question="What value?"),
            )[1],
            lambda request: (
                request.artifacts.context_dump.write_text(
                    json.dumps(
                        {
                            "workflow_params": request.context.workflow_params,
                            "answer": request.context.answer,
                        }
                    ),
                ),
                Outcome(
                    raw_output="Answered",
                    tag="answered",
                    payload={"answer": request.context.answer},
                ),
            )[1],
        ]
    )

    paused = run_workflow_package(
        "resume_params_demo",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="task-params",
            message="Need workflow parameters",
            workflow_params={"mode": "strict"},
        ),
    )

    workflow_dir = tmp_path / ".autoloop" / "tasks" / "task-params" / "wf_resume_params_demo"
    run_dir = next((workflow_dir / "runs").iterdir())
    paused_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    resumed = run_workflow_package(
        "resume_params_demo",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="task-params",
            run_id=run_dir.name,
            resume=True,
            answer="42",
        ),
    )

    resumed_context = json.loads((run_dir / "context.json").read_text(encoding="utf-8"))
    resumed_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert paused.terminal == "PAUSE"
    assert paused_meta["workflow_params"] == {"mode": "strict"}
    assert resumed.terminal == "SUCCESS"
    assert resumed_context["workflow_params"] == {"mode": "strict"}
    assert resumed_context["answer"] == "42"
    assert resumed_meta["workflow_params"] == {"mode": "strict"}


def test_resume_ignores_explicit_workflow_param_override_for_existing_run(tmp_path: Path) -> None:
    _write_pause_resume_workflow_package(tmp_path, "resume_override_demo", "ResumeOverrideWorkflow")
    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: (
                request.artifacts.context_dump.write_text(
                    json.dumps(
                        {
                            "workflow_params": request.context.workflow_params,
                            "answer": request.context.answer,
                        }
                    ),
                ),
                Outcome(raw_output="Need answer", tag="question", question="What value?"),
            )[1],
            lambda request: (
                request.artifacts.context_dump.write_text(
                    json.dumps(
                        {
                            "workflow_params": request.context.workflow_params,
                            "answer": request.context.answer,
                        }
                    ),
                ),
                Outcome(
                    raw_output="Answered",
                    tag="answered",
                    payload={"answer": request.context.answer},
                ),
            )[1],
        ]
    )

    paused = run_workflow_package(
        "resume_override_demo",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="task-override",
            message="Need workflow parameters",
            workflow_params={"mode": "strict"},
        ),
    )

    workflow_dir = tmp_path / ".autoloop" / "tasks" / "task-override" / "wf_resume_override_demo"
    run_dir = next((workflow_dir / "runs").iterdir())

    resumed = run_workflow_package(
        "resume_override_demo",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="task-override",
            run_id=run_dir.name,
            resume=True,
            answer="42",
            workflow_params={"mode": "loose"},
        ),
    )

    resumed_context = json.loads((run_dir / "context.json").read_text(encoding="utf-8"))
    resumed_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert paused.terminal == "PAUSE"
    assert resumed.terminal == "SUCCESS"
    assert resumed_context["workflow_params"] == {"mode": "strict"}
    assert resumed_context["answer"] == "42"
    assert resumed_meta["workflow_params"] == {"mode": "strict"}


def test_workspace_lists_grouped_workflow_run_summaries_with_deterministic_filters(tmp_path: Path) -> None:
    paused_dir = _write_run_summary_record(
        tmp_path,
        task_id="task-1",
        workflow_name="release_candidate_to_go_no_go",
        run_id="run-paused",
        status="paused",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:03:00+00:00",
        request_text="  Investigate the paused release gate.\nNeed owner confirmation.\n",
        pending_question="Who owns the gate?",
    )
    _write_run_summary_record(
        tmp_path,
        task_id="task-2",
        workflow_name="release_candidate_to_go_no_go",
        run_id="run-failed",
        status="failed",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:02:00+00:00",
        request_text="Investigate the failed release gate.\n",
        terminal="FAIL",
        error="verification mismatch",
    )
    _write_run_summary_record(
        tmp_path,
        task_id="task-3",
        workflow_name="release_candidate_to_go_no_go",
        run_id="run-success",
        status="success",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:01:00+00:00",
        request_text="Routine release check.\n",
    )
    _write_run_summary_record(
        tmp_path,
        task_id="task-4",
        workflow_name="incident_to_hardening_program",
        run_id="run-incident-success",
        status="success",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:04:00+00:00",
        request_text="No incident action needed.\n",
    )

    summaries = list_workflow_run_summaries(
        tmp_path,
        workflow_names=["release_candidate_to_go_no_go", "incident_to_hardening_program"],
        statuses=(status for status in ["failed", "paused", "failed"]),
        max_runs_per_workflow=1,
    )

    assert summaries == (
        {
            "latest_run_id": None,
            "latest_updated_at": None,
            "recent_runs": [],
            "run_count": 0,
            "status_counts": {},
            "workflow_name": "incident_to_hardening_program",
        },
        {
            "latest_run_id": "run-paused",
            "latest_updated_at": "2026-04-24T06:03:00+00:00",
            "recent_runs": [
                {
                    "created_at": "2026-04-24T06:00:00+00:00",
                    "error": None,
                    "pending_question": "Who owns the gate?",
                    "request_excerpt": "Investigate the paused release gate. Need owner confirmation.",
                    "request_file": str(paused_dir / "request.md"),
                    "run_folder": str(paused_dir),
                    "run_id": "run-paused",
                    "status": "paused",
                    "task_id": "task-1",
                    "terminal": None,
                    "updated_at": "2026-04-24T06:03:00+00:00",
                }
            ],
            "run_count": 2,
            "status_counts": {"failed": 1, "paused": 1},
            "workflow_name": "release_candidate_to_go_no_go",
        },
    )

    with pytest.raises(ValueError, match="workflow_names entries must be non-empty strings"):
        list_workflow_run_summaries(tmp_path, workflow_names=["release_candidate_to_go_no_go", "  "])
    with pytest.raises(ValueError, match="statuses entries must be non-empty strings"):
        list_workflow_run_summaries(tmp_path, statuses=["failed", "  "])
    with pytest.raises(ValueError, match="positive integer"):
        list_workflow_run_summaries(tmp_path, max_runs_per_workflow=0)


def test_context_invoke_workflow_accepts_imported_main_workflow_classes_and_records_child_metadata(tmp_path: Path) -> None:
    _write_child_success_workflow_package(tmp_path)
    _write_parent_class_invoker_workflow_package(tmp_path)

    result = run_workflow_package(
        "parent_class",
        provider=ScriptedLLMProvider(
            llm_turns=[
                lambda request: (
                    request.artifacts.child_dump.write_text(
                        json.dumps(
                            {
                                "answer": request.context.answer,
                                "workflow_params": request.context.workflow_params,
                                "session_id": request.session.session_id if request.session is not None else None,
                            }
                        ),
                    ),
                    Outcome(raw_output="child complete\n", tag="done", payload={"summary": "child complete"}),
                )[1]
            ]
        ),
        options=RunnerOptions(root=tmp_path, task_id="subworkflow-class-task", message="Parent request"),
    )

    task_dir = tmp_path / ".autoloop" / "tasks" / "subworkflow-class-task"
    parent_run_dir = next((task_dir / "wf_parent_class" / "runs").iterdir())
    child_run_dir = next((task_dir / "wf_child_success" / "runs").iterdir())
    parent_payload = json.loads((parent_run_dir / "summary.json").read_text(encoding="utf-8"))
    child_payload = json.loads((child_run_dir / "child.json").read_text(encoding="utf-8"))
    child_parent = json.loads((child_run_dir / "parent.json").read_text(encoding="utf-8"))
    task_messages = [
        json.loads(line)
        for line in (task_dir / "messages.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    child_records = [
        json.loads(line)
        for line in (parent_run_dir / "children.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert result.terminal == "SUCCESS"
    assert parent_payload["child_workflow"] == "child_success"
    assert parent_payload["child_status"] == "success"
    assert parent_payload["child_last_event"] == "done"
    assert parent_payload["child_output_metadata"] == {"summary": "child complete"}
    assert Path(parent_payload["child_run_folder"]) == child_run_dir
    assert Path(parent_payload["child_request_file"]) == child_run_dir / "request.md"
    assert Path(parent_payload["child_artifacts"]["child_dump"]) == child_run_dir / "child.json"
    assert (task_dir / "request.md").read_text(encoding="utf-8") == "Parent request\n"
    assert (child_run_dir / "request.md").read_text(encoding="utf-8") == "Run child from class\n"
    assert [entry["message"] for entry in task_messages] == ["Parent request"]
    assert child_payload["answer"] is None
    assert child_payload["workflow_params"] == {"mode": "strict"}
    assert (child_run_dir / "sessions" / "main.json").exists()
    assert child_parent["workflow_name"] == "parent_class"
    assert child_parent["run_id"] == parent_run_dir.name
    assert child_records == [
        {
            "workflow_name": "child_success",
            "run_id": child_run_dir.name,
            "terminal": "SUCCESS",
            "status": "success",
            "last_event": {"tag": "done", "reason": "", "question": None},
            "output_metadata": {"summary": "child complete"},
            "output_artifacts": {"child_dump": str(child_run_dir / "child.json")},
            "task_folder": str(task_dir),
            "workflow_folder": str(task_dir / "wf_child_success"),
            "run_folder": str(child_run_dir),
            "package_folder": str(tmp_path / "workflows" / "child_success"),
            "request_file": str(child_run_dir / "request.md"),
            "run_meta_file": str(child_run_dir / "run.json"),
            "events_file": str(child_run_dir / "events.jsonl"),
            "checkpoint_file": str(child_run_dir / "checkpoint.json"),
            "sessions_dir": str(child_run_dir / "sessions"),
            "trace_file": str(child_run_dir / "trace.jsonl"),
            "raw_dir": str(child_run_dir / "raw"),
            "parent_file": str(child_run_dir / "parent.json"),
            "ts": child_records[0]["ts"],
        }
    ]


def test_composition_helpers_keep_child_invocation_explicit_and_adopt_selected_artifacts_into_parent_workflow_folder(
    tmp_path: Path,
) -> None:
    _write_child_success_workflow_package(tmp_path)
    _write_parent_composition_helper_workflow_package(tmp_path)

    result = run_workflow_package(
        "parent_composed",
        provider=ScriptedLLMProvider(
            llm_turns=[
                lambda request: (
                    request.artifacts.child_dump.write_text(
                        json.dumps(
                            {
                                "answer": request.context.answer,
                                "workflow_params": request.context.workflow_params,
                                "session_id": request.session.session_id if request.session is not None else None,
                            }
                        ),
                    ),
                    Outcome(raw_output="child complete\n", tag="done", payload={"summary": "child complete"}),
                )[1]
            ]
        ),
        options=RunnerOptions(root=tmp_path, task_id="subworkflow-helper-task", message="Parent request"),
    )

    task_dir = tmp_path / ".autoloop" / "tasks" / "subworkflow-helper-task"
    parent_workflow_dir = task_dir / "wf_parent_composed"
    parent_run_dir = next((parent_workflow_dir / "runs").iterdir())
    child_run_dir = next((task_dir / "wf_child_success" / "runs").iterdir())
    adopted_path = parent_workflow_dir / "adopted" / "child-evidence.json"
    parent_payload = json.loads((parent_run_dir / "summary.json").read_text(encoding="utf-8"))
    child_payload = json.loads((child_run_dir / "child.json").read_text(encoding="utf-8"))
    child_parent = json.loads((child_run_dir / "parent.json").read_text(encoding="utf-8"))
    task_messages = [
        json.loads(line)
        for line in (task_dir / "messages.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    child_records = [
        json.loads(line)
        for line in (parent_run_dir / "children.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert result.terminal == "SUCCESS"
    assert parent_payload["child_workflow"] == "child_success"
    assert parent_payload["child_status"] == "success"
    assert parent_payload["child_last_event"] == "done"
    assert parent_payload["child_output_metadata"] == {"summary": "child complete"}
    assert parent_payload["adopted_artifacts"] == {"child_dump": str(adopted_path)}
    assert adopted_path.read_text(encoding="utf-8") == (child_run_dir / "child.json").read_text(encoding="utf-8")
    assert (task_dir / "request.md").read_text(encoding="utf-8") == "Parent request\n"
    assert (child_run_dir / "request.md").read_text(encoding="utf-8") == "Run child via helper\n"
    assert [entry["message"] for entry in task_messages] == ["Parent request"]
    assert child_payload["answer"] is None
    assert child_payload["workflow_params"] == {"mode": "strict"}
    assert child_parent["workflow_name"] == "parent_composed"
    assert child_parent["run_id"] == parent_run_dir.name
    assert len(child_records) == 1
    assert child_records[0]["workflow_name"] == "child_success"
    assert child_records[0]["status"] == "success"
    assert child_records[0]["output_artifacts"] == {"child_dump": str(child_run_dir / "child.json")}


def test_context_invoke_workflow_by_name_creates_isolated_child_runs_without_inheriting_parent_answers(tmp_path: Path) -> None:
    _write_child_pause_workflow_package(tmp_path)
    _write_parent_name_invoker_workflow_package(tmp_path)

    paused_parent = run_workflow_package(
        "parent_name",
        provider=ScriptedLLMProvider(),
        options=RunnerOptions(root=tmp_path, task_id="subworkflow-name-task", message="Parent request"),
    )

    task_dir = tmp_path / ".autoloop" / "tasks" / "subworkflow-name-task"
    parent_run_dir = next((task_dir / "wf_parent_name" / "runs").iterdir())

    resumed_parent = run_workflow_package(
        "parent_name",
        provider=ScriptedLLMProvider(
            llm_turns=[
                lambda request: (
                    request.artifacts.child_dump.write_text(
                        json.dumps(
                            {
                                "answer": request.context.answer,
                                "workflow_params": request.context.workflow_params,
                            }
                        ),
                    ),
                    Outcome(raw_output="Need child answer\n", tag="question", question="Child question?"),
                )[1]
            ]
        ),
        options=RunnerOptions(
            root=tmp_path,
            task_id="subworkflow-name-task",
            run_id=parent_run_dir.name,
            resume=True,
            answer="Proceed parent",
        ),
    )

    child_run_dir = next((task_dir / "wf_child_pause" / "runs").iterdir())
    parent_payload = json.loads((parent_run_dir / "summary.json").read_text(encoding="utf-8"))
    child_payload = json.loads((child_run_dir / "child.json").read_text(encoding="utf-8"))
    child_meta = json.loads((child_run_dir / "run.json").read_text(encoding="utf-8"))
    child_parent = json.loads((child_run_dir / "parent.json").read_text(encoding="utf-8"))
    task_messages = [
        json.loads(line)
        for line in (task_dir / "messages.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    child_records = [
        json.loads(line)
        for line in (parent_run_dir / "children.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert paused_parent.terminal == "PAUSE"
    assert resumed_parent.terminal == "SUCCESS"
    assert (task_dir / "request.md").read_text(encoding="utf-8") == "Parent request\n"
    assert [entry["message"] for entry in task_messages] == ["Parent request"]
    assert parent_payload["parent_answer"] == "Proceed parent"
    assert parent_payload["child_workflow"] == "child_pause"
    assert parent_payload["child_status"] == "paused"
    assert parent_payload["child_last_event"] == "question"
    assert Path(parent_payload["child_checkpoint_file"]) == child_run_dir / "checkpoint.json"
    assert child_payload["answer"] is None
    assert child_payload["workflow_params"] == {"mode": "strict"}
    assert child_meta["status"] == "paused"
    assert child_meta["pending_question"] == "Child question?"
    assert (child_run_dir / "checkpoint.json").exists()
    assert child_parent["workflow_name"] == "parent_name"
    assert child_parent["run_id"] == parent_run_dir.name
    assert child_records[0]["workflow_name"] == "child_pause"
    assert child_records[0]["status"] == "paused"
    assert child_records[0]["last_event"] == {"tag": "question", "reason": "", "question": "Child question?"}


def test_context_invoke_workflow_records_stable_child_metadata_shape_for_fatal_children(tmp_path: Path) -> None:
    _write_child_failing_workflow_package(tmp_path)
    _write_parent_failing_invoker_workflow_package(tmp_path)

    with pytest.raises(RuntimeError, match="child boom"):
        run_workflow_package(
            "parent_failing",
            provider=ScriptedLLMProvider(),
            options=RunnerOptions(root=tmp_path, task_id="subworkflow-fatal-task", message="Parent request"),
        )

    task_dir = tmp_path / ".autoloop" / "tasks" / "subworkflow-fatal-task"
    parent_run_dir = next((task_dir / "wf_parent_failing" / "runs").iterdir())
    child_run_dir = next((task_dir / "wf_child_failing" / "runs").iterdir())
    task_messages = [
        json.loads(line)
        for line in (task_dir / "messages.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    child_records = [
        json.loads(line)
        for line in (parent_run_dir / "children.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert len(child_records) == 1
    assert (task_dir / "request.md").read_text(encoding="utf-8") == "Parent request\n"
    assert [entry["message"] for entry in task_messages] == ["Parent request"]
    assert child_records[0]["workflow_name"] == "child_failing"
    assert child_records[0]["run_id"] == child_run_dir.name
    assert child_records[0]["terminal"] == "fatal"
    assert child_records[0]["status"] == "fatal_error"
    assert child_records[0]["last_event"] is None
    assert child_records[0]["package_folder"] == str(tmp_path / "workflows" / "child_failing")
    assert child_records[0]["run_folder"] == str(child_run_dir)
    assert child_records[0]["request_file"] == str(child_run_dir / "request.md")
    assert child_records[0]["parent_file"] == str(child_run_dir / "parent.json")
    assert child_records[0]["error"] == "child boom"


def _write_run_summary_record(
    root: Path,
    *,
    task_id: str,
    workflow_name: str,
    run_id: str,
    status: str,
    created_at: str,
    updated_at: str,
    request_text: str,
    terminal: str | None = None,
    error: str | None = None,
    pending_question: str | None = None,
) -> Path:
    task_dir = root / ".autoloop" / "tasks" / task_id
    workflow_dir = task_dir / f"wf_{workflow_name}"
    run_dir = workflow_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "request.md").write_text(request_text, encoding="utf-8")
    payload = {
        "created_at": created_at,
        "run_id": run_id,
        "status": status,
        "task_id": task_id,
        "updated_at": updated_at,
        "workflow_name": workflow_name,
    }
    if terminal is not None:
        payload["terminal"] = terminal
    if error is not None:
        payload["error"] = error
    if pending_question is not None:
        payload["pending_question"] = pending_question
    (run_dir / "run.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return run_dir


def _write_system_workflow_package(root: Path, workflow_name: str, class_name: str) -> Path:
    package_dir = root / "workflows" / workflow_name
    package_dir.mkdir(parents=True, exist_ok=True)
    (root / "workflows" / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    (package_dir / "__init__.py").write_text(f"from .workflow import {class_name}\n__all__ = [{class_name!r}]\n", encoding="utf-8")
    (package_dir / "workflow.toml").write_text(f'name = "{workflow_name}"\n', encoding="utf-8")
    (package_dir / "prompts").mkdir(exist_ok=True)
    (package_dir / "assets").mkdir(exist_ok=True)
    (package_dir / "workflow.py").write_text(
        f"""
from __future__ import annotations

from pydantic import BaseModel

from workflow import SUCCESS, SystemStep, Workflow
from workflow.primitives import Event
from workflow.primitives import Event


class {class_name}(Workflow):
    name = "{workflow_name}"

    class State(BaseModel):
        done: bool = False

    start = SystemStep(name="start")
    entry = start
    transitions = {{start: {{"done": SUCCESS}}}}

    @staticmethod
    def on_start(state: State, ctx):
        return state.model_copy(update={{"done": True}}), Event("done")
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return package_dir / "workflow.py"


def _write_llm_workflow_package(root: Path, workflow_name: str, class_name: str) -> Path:
    package_dir = root / "workflows" / workflow_name
    package_dir.mkdir(parents=True, exist_ok=True)
    (root / "workflows" / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    (package_dir / "__init__.py").write_text(f"from .workflow import {class_name}\n__all__ = [{class_name!r}]\n", encoding="utf-8")
    (package_dir / "workflow.toml").write_text(f'name = "{workflow_name}"\n', encoding="utf-8")
    (package_dir / "prompts").mkdir(exist_ok=True)
    (package_dir / "assets").mkdir(exist_ok=True)
    (package_dir / "prompts" / "ask.md").write_text("package prompt\n", encoding="utf-8")
    (package_dir / "workflow.py").write_text(
        f"""
from __future__ import annotations

from pydantic import BaseModel

from workflow import Artifact, LLMStep, SUCCESS, Workflow


class {class_name}(Workflow):
    name = "{workflow_name}"

    class State(BaseModel):
        note: str = ""

    context_dump = Artifact("{{run_folder}}/context.json")
    workflow_dump = Artifact("{{workflow_folder}}/workflow-note.txt")
    ask = LLMStep(
        name="ask",
        producer="prompts/ask.md",
        produces={{"context_dump": context_dump, "workflow_dump": workflow_dump}},
    )
    entry = ask
    transitions = {{ask: {{"done": SUCCESS}}}}

    @staticmethod
    def on_ask(state: State, outcome, artifacts):
        return state.model_copy(update={{"note": artifacts.workflow_dump.read_text().strip()}})
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return package_dir / "workflow.py"


def _write_pause_resume_workflow_package(root: Path, workflow_name: str, class_name: str) -> Path:
    package_dir = root / "workflows" / workflow_name
    package_dir.mkdir(parents=True, exist_ok=True)
    (root / "workflows" / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    (package_dir / "__init__.py").write_text(f"from .workflow import {class_name}\n__all__ = [{class_name!r}]\n", encoding="utf-8")
    (package_dir / "workflow.toml").write_text(f'name = "{workflow_name}"\n', encoding="utf-8")
    (package_dir / "prompts").mkdir(exist_ok=True)
    (package_dir / "assets").mkdir(exist_ok=True)
    (package_dir / "prompts" / "ask.md").write_text("package prompt\n", encoding="utf-8")
    (package_dir / "workflow.py").write_text(
        f"""
from __future__ import annotations

from pydantic import BaseModel

from workflow import Artifact, LLMStep, SUCCESS, Workflow
from workflow.primitives import Event, Outcome


class {class_name}(Workflow):
    name = "{workflow_name}"

    class State(BaseModel):
        answer: str | None = None

    context_dump = Artifact("{{run_folder}}/context.json")
    ask = LLMStep(
        name="ask",
        producer="prompts/ask.md",
        produces={{"context_dump": context_dump}},
    )
    entry = ask
    transitions = {{ask: {{"answered": SUCCESS, "question": "PAUSE"}}}}

    @staticmethod
    def on_ask(state: State, outcome: Outcome, artifacts):
        return state.model_copy(update={{"answer": outcome.payload.get("answer")}})

    @staticmethod
    def on_outcome(state: State, outcome: Outcome):
        if outcome.tag == "question":
            return Event("question", question=outcome.question)
        return None
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return package_dir / "workflow.py"


def _write_child_success_workflow_package(root: Path) -> None:
    package_dir = root / "workflows" / "child_success"
    package_dir.mkdir(parents=True, exist_ok=True)
    (root / "workflows" / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    (package_dir / "__init__.py").write_text(
        "from .workflow import ChildWorkflow\nfrom .params import Parameters\n__all__ = ['ChildWorkflow', 'Parameters']\n",
        encoding="utf-8",
    )
    (package_dir / "workflow.toml").write_text('name = "child_success"\n', encoding="utf-8")
    (package_dir / "prompts").mkdir(exist_ok=True)
    (package_dir / "assets").mkdir(exist_ok=True)
    (package_dir / "prompts" / "ask.md").write_text("child prompt\n", encoding="utf-8")
    (package_dir / "params.py").write_text(
        """
from pydantic import BaseModel


class Parameters(BaseModel):
    mode: str = "strict"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (package_dir / "workflow.py").write_text(
        """
from __future__ import annotations

from pydantic import BaseModel

from workflow import Artifact, LLMStep, Session, SUCCESS, Workflow


class ChildWorkflow(Workflow):
    name = "child_success"

    class State(BaseModel):
        note: str = ""

    main = Session()
    child_dump = Artifact("{run_folder}/child.json")
    ask = LLMStep(name="ask", producer="prompts/ask.md", session=main, produces={"child_dump": child_dump})
    entry = ask
    transitions = {ask: {"done": SUCCESS}}

    def on_start(self, ctx):
        ctx.open_session(self.main)

    @staticmethod
    def on_ask(state: State, outcome, artifacts):
        return state.model_copy(update={"note": outcome.payload.get("summary", "")})
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _write_parent_class_invoker_workflow_package(root: Path) -> None:
    package_dir = root / "workflows" / "parent_class"
    package_dir.mkdir(parents=True, exist_ok=True)
    (root / "workflows" / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    (package_dir / "__init__.py").write_text("from .workflow import ParentClassWorkflow\n__all__ = ['ParentClassWorkflow']\n", encoding="utf-8")
    (package_dir / "workflow.toml").write_text('name = "parent_class"\n', encoding="utf-8")
    (package_dir / "prompts").mkdir(exist_ok=True)
    (package_dir / "assets").mkdir(exist_ok=True)
    (package_dir / "workflow.py").write_text(
        """
from __future__ import annotations

import json

from pydantic import BaseModel

from workflow import Session, SUCCESS, SystemStep, Workflow
from workflow.primitives import Event
from workflows.child_success import ChildWorkflow


class ParentClassWorkflow(Workflow):
    name = "parent_class"

    class State(BaseModel):
        finished: bool = False

    main = Session()
    launch = SystemStep(name="launch")
    entry = launch
    transitions = {launch: {"done": SUCCESS}}

    def on_start(self, ctx):
        ctx.open_session(self.main)

    @staticmethod
    def on_launch(state: State, ctx):
        result = ctx.invoke_workflow(ChildWorkflow, message="Run child from class", parameters={"mode": "strict"})
        payload = {
            "child_workflow": result.workflow_name,
            "child_run_id": result.run_id,
            "child_status": result.status,
            "child_last_event": None if result.last_event is None else result.last_event.tag,
            "child_output_metadata": result.output_metadata,
            "child_artifacts": {name: str(path) for name, path in result.output_artifacts.items()},
            "child_run_folder": str(result.run_folder),
            "child_request_file": str(result.request_file),
            "parent_session_id": ctx.get_session("main").session_id,
        }
        (ctx.run_folder / "summary.json").write_text(json.dumps(payload), encoding="utf-8")
        return state.model_copy(update={"finished": True}), Event("done")
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _write_parent_composition_helper_workflow_package(root: Path) -> None:
    package_dir = root / "workflows" / "parent_composed"
    package_dir.mkdir(parents=True, exist_ok=True)
    (root / "workflows" / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    (package_dir / "__init__.py").write_text(
        "from .workflow import ParentCompositionHelperWorkflow\n__all__ = ['ParentCompositionHelperWorkflow']\n",
        encoding="utf-8",
    )
    (package_dir / "workflow.toml").write_text('name = "parent_composed"\n', encoding="utf-8")
    (package_dir / "prompts").mkdir(exist_ok=True)
    (package_dir / "assets").mkdir(exist_ok=True)
    (package_dir / "workflow.py").write_text(
        """
from __future__ import annotations

import json

from pydantic import BaseModel

from autoloop_v3.stdlib import adopt_child_artifacts, require_child_workflow_result, run_child_workflow
from workflow import SUCCESS, SystemStep, Workflow
from workflow.primitives import Event


class ParentCompositionHelperWorkflow(Workflow):
    name = "parent_composed"

    class State(BaseModel):
        finished: bool = False

    launch = SystemStep(name="launch")
    entry = launch
    transitions = {launch: {"done": SUCCESS}}

    @staticmethod
    def on_launch(state: State, ctx):
        child = run_child_workflow(
            ctx,
            "child_success",
            message="Run child via helper",
            parameters={"mode": "strict"},
        )
        require_child_workflow_result(
            child,
            status="success",
            last_event="done",
            required_artifacts=("child_dump",),
        )
        adopted = adopt_child_artifacts(
            ctx,
            child,
            mapping={"child_dump": "adopted/child-evidence.json"},
        )
        payload = {
            "child_workflow": child.workflow_name,
            "child_run_id": child.run_id,
            "child_status": child.status,
            "child_last_event": None if child.last_event is None else child.last_event.tag,
            "child_output_metadata": child.output_metadata,
            "child_artifacts": {name: str(path) for name, path in child.output_artifacts.items()},
            "adopted_artifacts": {name: str(path) for name, path in adopted.items()},
            "child_run_folder": str(child.run_folder),
            "child_request_file": str(child.request_file),
        }
        (ctx.run_folder / "summary.json").write_text(json.dumps(payload), encoding="utf-8")
        return state.model_copy(update={"finished": True}), Event("done")
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _write_child_pause_workflow_package(root: Path) -> None:
    package_dir = root / "workflows" / "child_pause"
    package_dir.mkdir(parents=True, exist_ok=True)
    (root / "workflows" / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    (package_dir / "__init__.py").write_text(
        "from .workflow import ChildPauseWorkflow\nfrom .params import Parameters\n__all__ = ['ChildPauseWorkflow', 'Parameters']\n",
        encoding="utf-8",
    )
    (package_dir / "workflow.toml").write_text('name = "child_pause"\n', encoding="utf-8")
    (package_dir / "prompts").mkdir(exist_ok=True)
    (package_dir / "assets").mkdir(exist_ok=True)
    (package_dir / "prompts" / "ask.md").write_text("child pause prompt\n", encoding="utf-8")
    (package_dir / "params.py").write_text(
        """
from pydantic import BaseModel


class Parameters(BaseModel):
    mode: str = "strict"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (package_dir / "workflow.py").write_text(
        """
from __future__ import annotations

from pydantic import BaseModel

from workflow import Artifact, LLMStep, Session, Workflow
from workflow.primitives import Event


class ChildPauseWorkflow(Workflow):
    name = "child_pause"

    class State(BaseModel):
        note: str = ""

    main = Session()
    child_dump = Artifact("{run_folder}/child.json")
    ask = LLMStep(name="ask", producer="prompts/ask.md", session=main, produces={"child_dump": child_dump})
    entry = ask
    transitions = {ask: {"question": "PAUSE"}}

    def on_start(self, ctx):
        ctx.open_session(self.main)

    @staticmethod
    def on_ask(state: State, outcome, artifacts):
        return state

    @staticmethod
    def on_outcome(state: State, outcome):
        if outcome.tag == "question":
            return Event("question", question=outcome.question)
        return None
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _write_parent_name_invoker_workflow_package(root: Path) -> None:
    package_dir = root / "workflows" / "parent_name"
    package_dir.mkdir(parents=True, exist_ok=True)
    (root / "workflows" / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    (package_dir / "__init__.py").write_text("from .workflow import ParentNameWorkflow\n__all__ = ['ParentNameWorkflow']\n", encoding="utf-8")
    (package_dir / "workflow.toml").write_text('name = "parent_name"\n', encoding="utf-8")
    (package_dir / "prompts").mkdir(exist_ok=True)
    (package_dir / "assets").mkdir(exist_ok=True)
    (package_dir / "workflow.py").write_text(
        """
from __future__ import annotations

import json

from pydantic import BaseModel

from workflow import PAUSE, SUCCESS, SystemStep, Workflow
from workflow.primitives import Event


class ParentNameWorkflow(Workflow):
    name = "parent_name"

    class State(BaseModel):
        finished: bool = False

    wait = SystemStep(name="wait")
    entry = wait
    transitions = {wait: {"question": PAUSE, "done": SUCCESS}}

    @staticmethod
    def on_wait(state: State, ctx):
        if ctx.answer is None:
            return state, Event("question", question="Parent question?")
        result = ctx.invoke_workflow("child_pause", message="Run child by name", parameters={"mode": "strict"})
        payload = {
            "parent_answer": ctx.answer,
            "child_workflow": result.workflow_name,
            "child_run_id": result.run_id,
            "child_status": result.status,
            "child_last_event": None if result.last_event is None else result.last_event.tag,
            "child_checkpoint_file": str(result.checkpoint_file),
        }
        (ctx.run_folder / "summary.json").write_text(json.dumps(payload), encoding="utf-8")
        return state.model_copy(update={"finished": True}), Event("done")
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _write_child_failing_workflow_package(root: Path) -> None:
    package_dir = root / "workflows" / "child_failing"
    package_dir.mkdir(parents=True, exist_ok=True)
    (root / "workflows" / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    (package_dir / "__init__.py").write_text(
        "from .workflow import ChildFailingWorkflow\n__all__ = ['ChildFailingWorkflow']\n",
        encoding="utf-8",
    )
    (package_dir / "workflow.toml").write_text('name = "child_failing"\n', encoding="utf-8")
    (package_dir / "prompts").mkdir(exist_ok=True)
    (package_dir / "assets").mkdir(exist_ok=True)
    (package_dir / "workflow.py").write_text(
        """
from __future__ import annotations

from pydantic import BaseModel
from workflow import SUCCESS, SystemStep, Workflow


class ChildFailingWorkflow(Workflow):
    name = "child_failing"

    class State(BaseModel):
        note: str = ""

    explode = SystemStep(name="explode")
    entry = explode
    transitions = {explode: {"done": SUCCESS}}

    @staticmethod
    def on_explode(state: State, ctx):
        raise RuntimeError("child boom")
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _write_parent_failing_invoker_workflow_package(root: Path) -> None:
    package_dir = root / "workflows" / "parent_failing"
    package_dir.mkdir(parents=True, exist_ok=True)
    (root / "workflows" / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    (package_dir / "__init__.py").write_text(
        "from .workflow import ParentFailingWorkflow\n__all__ = ['ParentFailingWorkflow']\n",
        encoding="utf-8",
    )
    (package_dir / "workflow.toml").write_text('name = "parent_failing"\n', encoding="utf-8")
    (package_dir / "prompts").mkdir(exist_ok=True)
    (package_dir / "assets").mkdir(exist_ok=True)
    (package_dir / "workflow.py").write_text(
        """
from __future__ import annotations

from pydantic import BaseModel
from workflow import SUCCESS, SystemStep, Workflow
from workflow.primitives import Event


class ParentFailingWorkflow(Workflow):
    name = "parent_failing"

    class State(BaseModel):
        note: str = ""

    launch = SystemStep(name="launch")
    entry = launch
    transitions = {launch: {"done": SUCCESS}}

    @staticmethod
    def on_launch(state: State, ctx):
        ctx.invoke_workflow("child_failing", message="Run child fatal")
        return state, Event("done")
""".strip()
        + "\n",
        encoding="utf-8",
    )
