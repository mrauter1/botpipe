from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from botlane.core.context import ChildWorkflowResult, Context
from botlane.core.primitives import Event
from botlane.core.run_paths import RunIdentity, RunPaths
from botlane.core.stores import InMemorySessionStore


class _State(BaseModel):
    status: str = "new"


def test_run_paths_normalizes_paths_and_identity_is_optional() -> None:
    run_paths = RunPaths(
        root="repo",
        task_folder="repo/.botlane/tasks/task-1",
        workflow_folder="repo/.botlane/tasks/task-1/wf_demo",
        run_folder="repo/.botlane/tasks/task-1/wf_demo/runs/run-1",
        package_folder="repo/workflows/demo",
        request_file="repo/.botlane/tasks/task-1/wf_demo/runs/run-1/request.md",
        task_request_file="repo/.botlane/tasks/task-1/request.md",
        run_meta_file="repo/.botlane/tasks/task-1/wf_demo/runs/run-1/run.json",
        events_file="repo/.botlane/tasks/task-1/wf_demo/runs/run-1/events.jsonl",
        checkpoint_file="repo/.botlane/tasks/task-1/wf_demo/runs/run-1/checkpoint.json",
        sessions_dir="repo/.botlane/tasks/task-1/wf_demo/runs/run-1/sessions",
        trace_file="repo/.botlane/tasks/task-1/wf_demo/runs/run-1/trace.jsonl",
        raw_dir="repo/.botlane/tasks/task-1/wf_demo/runs/run-1/raw",
    )
    identity = RunIdentity(task_id="task-1", run_id="run-1", workflow_name="demo")

    assert isinstance(run_paths.task_folder, Path)
    assert isinstance(run_paths.workflow_folder, Path)
    assert isinstance(run_paths.run_folder, Path)
    assert isinstance(run_paths.package_folder, Path)
    assert identity.paths is None


def test_context_synthesizes_internal_run_identity_from_existing_constructor_args(tmp_path: Path) -> None:
    task_folder = tmp_path / ".botlane" / "tasks" / "task-1"
    workflow_folder = task_folder / "wf_demo"
    run_folder = workflow_folder / "runs" / "run-1"
    package_folder = tmp_path / "workflows" / "demo"
    for path in (task_folder, workflow_folder, run_folder, package_folder):
        path.mkdir(parents=True, exist_ok=True)
    request_file = run_folder / "request.md"
    request_file.write_text("hello\n", encoding="utf-8")

    ctx = Context(
        root=tmp_path,
        task_id="task-1",
        run_id="run-1",
        workflow_name="demo",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        request_file=request_file,
        state=_State(),
        session_store=InMemorySessionStore(),
    )

    assert ctx.message == "hello"
    assert ctx._run_identity.task_id == "task-1"
    assert ctx._run_identity.run_id == "run-1"
    assert ctx._run_identity.workflow_name == "demo"
    assert ctx._run_identity.paths is not None
    assert ctx._run_identity.paths.task_folder == task_folder
    assert ctx._run_identity.paths.workflow_folder == workflow_folder
    assert ctx._run_identity.paths.run_folder == run_folder
    assert ctx._run_identity.paths.package_folder == package_folder
    assert ctx._run_identity.paths.request_file == request_file


def test_child_workflow_result_keeps_legacy_path_fields() -> None:
    result = ChildWorkflowResult(
        workflow_name="demo",
        run_id="run-1",
        terminal="FINISH",
        status="completed",
        last_event=Event("done"),
        output_metadata={},
        output_artifacts={"report": Path("report.md")},
        task_folder=Path("task"),
        workflow_folder=Path("task/wf_demo"),
        run_folder=Path("task/wf_demo/runs/run-1"),
        package_folder=Path("workflows/demo"),
        request_file=Path("task/wf_demo/runs/run-1/request.md"),
        run_meta_file=Path("task/wf_demo/runs/run-1/run.json"),
        events_file=Path("task/wf_demo/runs/run-1/events.jsonl"),
        checkpoint_file=Path("task/wf_demo/runs/run-1/checkpoint.json"),
        sessions_dir=Path("task/wf_demo/runs/run-1/sessions"),
        trace_file=Path("task/wf_demo/runs/run-1/trace.jsonl"),
        raw_dir=Path("task/wf_demo/runs/run-1/raw"),
        parent_file=Path("task/wf_demo/runs/run-1/parent.json"),
    )

    assert result.task_folder == Path("task")
    assert result.workflow_folder == Path("task/wf_demo")
    assert result.run_folder == Path("task/wf_demo/runs/run-1")
    assert result.package_folder == Path("workflows/demo")
    assert result.artifacts == {"report": Path("report.md")}
