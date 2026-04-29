from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from autoloop_v3.runtime.config import GitTrackingRuntimeConfig
from autoloop_v3.core.schema_registry import GIT_TRACKING_SCHEMA
from autoloop_v3.runtime.git_tracking import RuntimeGitTracker, RuntimeGitTrackingError


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def _init_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("baseline\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "init")


def _run_dir(root: Path) -> Path:
    return root / ".autoloop" / "tasks" / "task-1" / "wf_demo" / "runs" / "run-1"


def test_git_tracking_disabled_does_not_require_repo(tmp_path: Path) -> None:
    tracker = RuntimeGitTracker(
        root=tmp_path,
        run_dir=None,
        workflow_name="demo",
        task_id="task-1",
        run_id="run-1",
        config=GitTrackingRuntimeConfig(enabled=False),
    )

    payload = tracker.prepare_before_workspace_creation()

    assert payload == {
        "enabled": False,
        "eligible": False,
        "commit_policy": "step",
    }


def test_git_tracking_enabled_requires_repo_by_default(tmp_path: Path) -> None:
    tracker = RuntimeGitTracker(
        root=tmp_path,
        run_dir=None,
        workflow_name="demo",
        task_id="task-1",
        run_id="run-1",
        config=GitTrackingRuntimeConfig(),
    )

    with pytest.raises(RuntimeGitTrackingError, match="no git repository was found"):
        tracker.prepare_before_workspace_creation()


def test_git_tracking_enabled_requires_clean_repo_before_run_workspace_creation(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    tracker = RuntimeGitTracker(
        root=tmp_path,
        run_dir=None,
        workflow_name="demo",
        task_id="task-1",
        run_id="run-1",
        config=GitTrackingRuntimeConfig(),
    )

    with pytest.raises(RuntimeGitTrackingError, match="repository was dirty at run start"):
        tracker.prepare_before_workspace_creation()

    assert not _run_dir(tmp_path).exists()


def test_git_tracking_dirty_repo_failure_mode_ignore_disables_tracking_for_run(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    tracker = RuntimeGitTracker(
        root=tmp_path,
        run_dir=None,
        workflow_name="demo",
        task_id="task-1",
        run_id="run-1",
        config=GitTrackingRuntimeConfig(failure_mode="ignore"),
    )

    payload = tracker.prepare_before_workspace_creation()

    assert payload == {
        "enabled": False,
        "eligible": False,
        "commit_policy": "step",
        "error": "git tracking disabled because repository was dirty at run start",
    }


def test_git_tracking_run_policy_commits_at_run_boundaries(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    tracker = RuntimeGitTracker(
        root=tmp_path,
        run_dir=None,
        workflow_name="demo",
        task_id="task-1",
        run_id="run-1",
        config=GitTrackingRuntimeConfig(commit_policy="run"),
    )
    prepared = tracker.prepare_before_workspace_creation()
    run_dir = _run_dir(tmp_path)
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text("{}\n", encoding="utf-8")
    tracker.bind_run_dir(run_dir)

    init_payload = tracker.commit_run_initialized()
    head_after_init = _git(tmp_path, "rev-parse", "HEAD").strip()
    before_step = tracker.before_step(sequence=1, step_name="ask")
    (run_dir / "trace.jsonl").write_text("trace\n", encoding="utf-8")
    step_payload = tracker.after_step(sequence=1, step_name="ask", commit_before_step=before_step["commit_before_step"])
    (run_dir / "result.txt").write_text("done\n", encoding="utf-8")
    finish_payload = tracker.after_run(terminal="SUCCESS")

    log_messages = _git(tmp_path, "log", "--pretty=%s").splitlines()[:4]
    git_tracking_lines = [
        json.loads(line)
        for line in (run_dir / "git_tracking.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    run_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert prepared["commit_before_run"] != head_after_init
    assert init_payload["created_commit"] is True
    assert step_payload["event_type"] == "step_observed"
    assert step_payload["created_commit"] is False
    assert finish_payload["created_commit"] is True
    assert log_messages == [
        "autoloop: metadata demo run-1",
        "autoloop: finish demo run-1 FINISH",
        "autoloop: init demo run-1",
        "init",
    ]
    assert finish_payload["terminal"] == "FINISH"
    assert [record["event_type"] for record in git_tracking_lines] == [
        "run_initialized",
        "step_observed",
        "run_finished",
    ]
    assert run_meta["git_tracking"]["commit_after_run"] == finish_payload["commit_after_run"]
    assert "steps" not in run_meta["git_tracking"]
    assert _git(tmp_path, "status", "--porcelain=v1", "--untracked-files=all").strip() == ""


def test_git_tracking_step_policy_commits_after_each_step(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    tracker = RuntimeGitTracker(
        root=tmp_path,
        run_dir=None,
        workflow_name="demo",
        task_id="task-1",
        run_id="run-1",
        config=GitTrackingRuntimeConfig(commit_policy="step"),
    )
    tracker.prepare_before_workspace_creation()
    run_dir = _run_dir(tmp_path)
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text("{}\n", encoding="utf-8")
    tracker.bind_run_dir(run_dir)
    tracker.commit_run_initialized()

    before_step = tracker.before_step(sequence=1, step_name="ask")
    (run_dir / "step-1.txt").write_text("one\n", encoding="utf-8")
    after_step = tracker.after_step(sequence=1, step_name="ask", commit_before_step=before_step["commit_before_step"])
    (run_dir / "step-2.txt").write_text("two\n", encoding="utf-8")
    tracker.after_run(terminal="SUCCESS")

    log_messages = _git(tmp_path, "log", "--pretty=%s").splitlines()[:5]

    assert after_step["event_type"] == "step_committed"
    assert after_step["created_commit"] is True
    assert log_messages == [
        "autoloop: metadata demo run-1",
        "autoloop: finish demo run-1 FINISH",
        "autoloop: step demo run-1 1 ask",
        "autoloop: init demo run-1",
        "init",
    ]
    assert _git(tmp_path, "status", "--porcelain=v1", "--untracked-files=all").strip() == ""


def test_git_tracking_commit_all_tracks_untracked_files(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    tracker = RuntimeGitTracker(
        root=tmp_path,
        run_dir=None,
        workflow_name="demo",
        task_id="task-1",
        run_id="run-1",
        config=GitTrackingRuntimeConfig(commit_policy="run"),
    )
    tracker.prepare_before_workspace_creation()
    run_dir = _run_dir(tmp_path)
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text("{}\n", encoding="utf-8")
    (run_dir / "untracked.txt").write_text("capture me\n", encoding="utf-8")
    tracker.bind_run_dir(run_dir)

    tracker.commit_run_initialized()

    committed_files = {
        line.strip()
        for line in _git(tmp_path, "show", "--name-only", "--format=", "HEAD").splitlines()
        if line.strip()
    }
    assert ".autoloop/tasks/task-1/wf_demo/runs/run-1/untracked.txt" in committed_files


def test_git_tracking_runtime_failure_mode_ignore_disables_tracking_after_commit_error(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    tracker = RuntimeGitTracker(
        root=tmp_path,
        run_dir=None,
        workflow_name="demo",
        task_id="task-1",
        run_id="run-1",
        config=GitTrackingRuntimeConfig(commit_policy="run", failure_mode="ignore"),
    )
    tracker.prepare_before_workspace_creation()
    run_dir = _run_dir(tmp_path)
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text("{}\n", encoding="utf-8")
    tracker.bind_run_dir(run_dir)

    class _BrokenRepo:
        def commit_all(self, message: str) -> tuple[str, bool]:
            raise RuntimeError("commit rejected")

    tracker._repo = _BrokenRepo()  # type: ignore[assignment]

    payload = tracker.commit_run_initialized()
    run_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert payload["enabled"] is False
    assert payload["eligible"] is False
    assert "commit rejected" in payload["error"]
    assert run_meta["git_tracking"]["enabled"] is False
    assert "commit rejected" in run_meta["git_tracking"]["error"]


def test_git_tracking_noop_commit_returns_current_head(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    tracker = RuntimeGitTracker(
        root=tmp_path,
        run_dir=None,
        workflow_name="demo",
        task_id="task-1",
        run_id="run-1",
        config=GitTrackingRuntimeConfig(commit_policy="step"),
    )
    tracker.prepare_before_workspace_creation()
    run_dir = _run_dir(tmp_path)
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text("{}\n", encoding="utf-8")
    tracker.bind_run_dir(run_dir)
    tracker.commit_run_initialized()
    _git(tmp_path, "add", "--all")
    _git(tmp_path, "commit", "-m", "flush runtime metadata")

    before_step = tracker.before_step(sequence=1, step_name="ask")
    current_head = _git(tmp_path, "rev-parse", "HEAD").strip()
    payload = tracker.after_step(sequence=1, step_name="ask", commit_before_step=before_step["commit_before_step"])

    assert payload["created_commit"] is False
    assert payload["commit_before_step"] == current_head
    assert payload["commit_after_step"] == current_head


def test_git_tracking_jsonl_records_step_commit_metadata(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    tracker = RuntimeGitTracker(
        root=tmp_path,
        run_dir=None,
        workflow_name="demo",
        task_id="task-1",
        run_id="run-1",
        config=GitTrackingRuntimeConfig(commit_policy="step"),
    )
    tracker.prepare_before_workspace_creation()
    run_dir = _run_dir(tmp_path)
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text("{}\n", encoding="utf-8")
    tracker.bind_run_dir(run_dir)
    tracker.commit_run_initialized()

    before_step = tracker.before_step(sequence=3, step_name="assessment")
    (run_dir / "note.txt").write_text("observed\n", encoding="utf-8")
    payload = tracker.after_step(
        sequence=3,
        step_name="assessment",
        commit_before_step=before_step["commit_before_step"],
    )

    lines = [
        json.loads(line)
        for line in (run_dir / "git_tracking.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    run_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert lines[-1]["event_type"] == "step_committed"
    assert lines[-1]["sequence"] == 3
    assert lines[-1]["step_name"] == "assessment"
    assert lines[-1]["commit_before_step"] == payload["commit_before_step"]
    assert lines[-1]["commit_after_step"] == payload["commit_after_step"]
    assert run_meta["git_tracking"]["latest_step"]["sequence"] == 3


def test_git_tracking_resume_appends_without_overwriting(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    run_dir = _run_dir(tmp_path)
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text("{}\n", encoding="utf-8")
    existing_record = {
        "schema": GIT_TRACKING_SCHEMA,
        "event_type": "step_committed",
        "sequence": 1,
        "step_name": "existing",
    }
    (run_dir / "git_tracking.jsonl").write_text(json.dumps(existing_record) + "\n", encoding="utf-8")
    _git(tmp_path, "add", "--all")
    _git(tmp_path, "commit", "-m", "persist existing run evidence")

    tracker = RuntimeGitTracker(
        root=tmp_path,
        run_dir=None,
        workflow_name="demo",
        task_id="task-1",
        run_id="run-1",
        config=GitTrackingRuntimeConfig(commit_policy="step"),
    )
    tracker.prepare_before_workspace_creation()
    tracker.bind_run_dir(run_dir)
    tracker.commit_run_initialized()
    before_step = tracker.before_step(sequence=2, step_name="resume")
    (run_dir / "resume.txt").write_text("append\n", encoding="utf-8")
    tracker.after_step(sequence=2, step_name="resume", commit_before_step=before_step["commit_before_step"])

    lines = [
        json.loads(line)
        for line in (run_dir / "git_tracking.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert lines[0] == existing_record
    assert any(line.get("sequence") == 2 and line.get("step_name") == "resume" for line in lines)


def test_git_tracking_fatal_commits_and_records_run_metadata(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    tracker = RuntimeGitTracker(
        root=tmp_path,
        run_dir=None,
        workflow_name="demo",
        task_id="task-1",
        run_id="run-1",
        config=GitTrackingRuntimeConfig(commit_policy="step"),
    )
    tracker.prepare_before_workspace_creation()
    run_dir = _run_dir(tmp_path)
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text("{}\n", encoding="utf-8")
    tracker.bind_run_dir(run_dir)
    tracker.commit_run_initialized()
    (run_dir / "fatal.txt").write_text("boom\n", encoding="utf-8")

    payload = tracker.on_fatal(step_name="assessment", error=RuntimeError("boom"))

    log_messages = _git(tmp_path, "log", "--pretty=%s").splitlines()[:4]
    lines = [
        json.loads(line)
        for line in (run_dir / "git_tracking.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    run_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert payload["event_type"] == "fatal_committed"
    assert payload["step_name"] == "assessment"
    assert payload["error_type"] == "RuntimeError"
    assert payload["error_message"] == "boom"
    assert payload["created_commit"] is True
    assert lines[-1]["event_type"] == "fatal_committed"
    assert lines[-1]["commit_after_run"] == payload["commit_after_run"]
    assert run_meta["git_tracking"]["commit_after_run"] == payload["commit_after_run"]
    assert log_messages == [
        "autoloop: metadata demo run-1",
        "autoloop: fatal demo run-1",
        "autoloop: init demo run-1",
        "init",
    ]
    assert _git(tmp_path, "status", "--porcelain=v1", "--untracked-files=all").strip() == ""
