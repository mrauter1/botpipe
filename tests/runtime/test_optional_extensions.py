from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import botlane.extensions as workflow_extensions
import botlane.extensions.git as workflow_git_extensions
from botlane.core.errors import WorkflowExecutionError
from botlane.core.providers.fake import ScriptedLLMProvider
from botlane.runtime.config import GitTrackingRuntimeConfig, RuntimeConfig, TracingRuntimeConfig
from botlane.runtime.git_tracking import RuntimeGitTrackingError
from botlane.runtime.runner import RunnerOptions, run_workflow_package
from botlane.runtime.tracing import RuntimeTraceWriter
from botlane.core.primitives import Outcome

STATE_DIRNAME = ".botlane"


def _clear_workflow_modules() -> None:
    importlib.invalidate_caches()
    for name in list(sys.modules):
        if name == "workflows" or name.startswith("workflows.") or name == "botlane.workflows" or name.startswith("botlane.workflows."):
            sys.modules.pop(name, None)


def test_runtime_observability_can_be_disabled_without_workflow_declarations(tmp_path: Path) -> None:
    _clear_workflow_modules()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "botlane@example.com")
    _git(repo_root, "config", "user.name", "Botlane Tests")

    _write_workflow_package(
        repo_root,
        "plain_workflow",
        class_name="PlainWorkflow",
        prompt_text="plain prompt\n",
        workflow_source="""
from __future__ import annotations

from pydantic import BaseModel

from botlane import FINISH, Prompt, Raw, Workflow, step
from botlane.core.primitives import Outcome


class PlainWorkflow(Workflow):
    name = "plain_workflow"

    class State(BaseModel):
        note: str = ""

    note = Raw("note", path="{task_folder}/note.txt")
    ask = step(
        prompt=Prompt.file("prompts/ask.md"),
        writes=[note],
        routes={"done": FINISH},
    )
""".strip(),
    )
    _git(repo_root, "add", "workflows")
    _git(repo_root, "commit", "-m", "baseline")

    result = run_workflow_package(
        "plain_workflow",
        provider=ScriptedLLMProvider(
            llm_turns=[
                lambda request: (
                    request.artifacts.note.write_text("plain note\n"),
                    Outcome(raw_output="ok\n", tag="done"),
                )[1]
            ]
        ),
        options=RunnerOptions(
            root=repo_root,
            task_id="plain-task",
            message="Do it",
            runtime_config=RuntimeConfig(
                git_tracking=GitTrackingRuntimeConfig(enabled=False),
                tracing=TracingRuntimeConfig(enabled=False),
            ),
        ),
    )

    task_dir = repo_root / STATE_DIRNAME / "tasks" / "plain-task"
    run_dir = next((task_dir / "wf_plain_workflow" / "runs").iterdir())

    assert result.terminal == "FINISH"
    assert (run_dir / "events.jsonl").exists()
    assert not (run_dir / "trace.jsonl").exists()
    assert _git(repo_root, "log", "-1", "--pretty=%s").strip() == "baseline"


def test_workflow_extension_exports_drop_git_tracking_and_tracing_declarations() -> None:
    for removed in ("GitTracking", "GitTrackingConfig", "Tracing", "TracingConfig"):
        assert not hasattr(workflow_extensions, removed)

    for retained in ("GitPolicy", "GitDelta", "GitChange", "GitCommitPlan", "SessionPaths"):
        assert hasattr(workflow_extensions, retained)

    for retained in ("GitPolicy", "GitRepo", "GitRepoError"):
        assert hasattr(workflow_git_extensions, retained)


def test_removed_workflow_observability_declaration_modules_are_not_importable() -> None:
    for module_name in ("botlane.extensions.tracing", "botlane.extensions.git.declaration"):
        sys.modules.pop(module_name, None)
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module_name)


def test_normal_run_writes_runtime_observability_artifacts_without_workflow_declarations(tmp_path: Path) -> None:
    _clear_workflow_modules()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "botlane@example.com")
    _git(repo_root, "config", "user.name", "Botlane Tests")

    _write_workflow_package(
        repo_root,
        "plain_runtime_observability",
        class_name="PlainRuntimeObservabilityWorkflow",
        prompt_text="plain prompt\n",
        workflow_source="""
from __future__ import annotations

from pydantic import BaseModel

from botlane import FINISH, Prompt, Raw, Workflow, step
from botlane.core.primitives import Outcome


class PlainRuntimeObservabilityWorkflow(Workflow):
    name = "plain_runtime_observability"

    class State(BaseModel):
        note: str = ""

    note = Raw("note", path="{task_folder}/note.txt")
    ask = step(
        prompt=Prompt.file("prompts/ask.md"),
        writes=[note],
        routes={"done": FINISH},
    )
""".strip(),
    )
    _git(repo_root, "add", "workflows")
    _git(repo_root, "commit", "-m", "baseline")

    result = run_workflow_package(
        "plain_runtime_observability",
        provider=ScriptedLLMProvider(
            llm_turns=[
                lambda request: (
                    request.artifacts.note.write_text("plain note\n"),
                    Outcome(raw_output="ok\n", tag="done"),
                )[1]
            ]
        ),
        options=RunnerOptions(root=repo_root, task_id="plain-runtime-observability-task", message="Do it"),
    )

    run_dir = next(
        (
            repo_root
            / STATE_DIRNAME
            / "tasks"
            / "plain-runtime-observability-task"
            / "wf_plain_runtime_observability"
            / "runs"
        ).iterdir()
    )
    run_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert result.terminal == "FINISH"
    assert (run_dir / "run.json").exists()
    assert (run_dir / "events.jsonl").exists()
    assert (run_dir / "trace.jsonl").exists()
    assert (run_dir / "git_tracking.jsonl").exists()
    assert (run_dir / "static_step_graph.json").exists()
    assert (run_dir / "raw").is_dir()
    assert (run_dir / "raw" / "000001_ask_step.txt").exists()
    assert run_meta["git_tracking"]["enabled"] is True
    assert run_meta["tracing"]["enabled"] is True
    assert run_meta["tracing"]["raw_dir"] == "raw"
    assert run_meta["tracing"]["static_step_graph_file"] == "static_step_graph.json"


def test_runtime_fatal_tracing_propagate_policy_propagates_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_workflow_modules()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "botlane@example.com")
    _git(repo_root, "config", "user.name", "Botlane Tests")

    _write_workflow_package(
        repo_root,
        "fatal_trace_workflow",
        class_name="FatalTraceWorkflow",
        prompt_text="fatal prompt\n",
        workflow_source="""
from __future__ import annotations

from pydantic import BaseModel

from botlane import FINISH, Prompt, Workflow, step
from botlane.core.primitives import Outcome


class FatalTraceWorkflow(Workflow):
    name = "fatal_trace_workflow"

    class State(BaseModel):
        note: str = ""

    ask = step(prompt=Prompt.file("prompts/ask.md"), routes={"done": FINISH})
""".strip(),
    )
    _git(repo_root, "add", "workflows")
    _git(repo_root, "commit", "-m", "baseline")

    def _broken_fatal(self, *, event, error) -> None:
        raise RuntimeError("fatal trace append failed")

    monkeypatch.setattr(RuntimeTraceWriter, "fatal", _broken_fatal)

    with pytest.raises(RuntimeError, match="fatal trace append failed") as excinfo:
        run_workflow_package(
            "fatal_trace_workflow",
            provider=ScriptedLLMProvider(
                llm_turns=[lambda request: (_ for _ in ()).throw(RuntimeError("workflow boom"))]
            ),
            options=RunnerOptions(
                root=repo_root,
                task_id="fatal-trace-task",
                message="Fail it",
                runtime_config=RuntimeConfig(
                    git_tracking=GitTrackingRuntimeConfig(commit_policy="run"),
                    tracing=TracingRuntimeConfig(failure_policy="propagate"),
                ),
            ),
        )

    assert isinstance(excinfo.value.__cause__, WorkflowExecutionError)
    assert str(excinfo.value.__cause__) == "workflow boom"


def test_dirty_repo_fails_before_runner_creates_run_workspace(tmp_path: Path) -> None:
    _clear_workflow_modules()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "botlane@example.com")
    _git(repo_root, "config", "user.name", "Botlane Tests")

    _write_workflow_package(
        repo_root,
        "dirty_workflow",
        class_name="DirtyWorkflow",
        prompt_text="dirty prompt\n",
        workflow_source="""
from __future__ import annotations

from pydantic import BaseModel

from botlane import FINISH, Prompt, Workflow, step
from botlane.core.primitives import Outcome


class DirtyWorkflow(Workflow):
    name = "dirty_workflow"

    class State(BaseModel):
        note: str = ""

    ask = step(prompt=Prompt.file("prompts/ask.md"), routes={"done": FINISH})
""".strip(),
    )
    _git(repo_root, "add", "workflows")
    _git(repo_root, "commit", "-m", "baseline")
    (repo_root / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")

    with pytest.raises(RuntimeGitTrackingError, match="repository was dirty at run start"):
        run_workflow_package(
            "dirty_workflow",
            provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok\n", tag="done")]),
            options=RunnerOptions(root=repo_root, task_id="dirty-task", message="Run it"),
        )

    assert not (repo_root / STATE_DIRNAME / "tasks" / "dirty-task" / "wf_dirty_workflow" / "runs").exists()


def test_paused_git_tracked_run_stays_clean_and_resumes_successfully(tmp_path: Path) -> None:
    _clear_workflow_modules()
    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
    _write_pause_resume_workflow(repo_root)

    runtime_config = RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(commit_policy="run"))
    paused = run_workflow_package(
        "pause_resume_workflow",
        provider=ScriptedLLMProvider(),
        options=RunnerOptions(
            root=repo_root,
            task_id="pause-task",
            message="Pause this run",
            runtime_config=runtime_config,
        ),
    )

    run_dir = next((repo_root / STATE_DIRNAME / "tasks" / "pause-task" / "wf_pause_resume_workflow" / "runs").iterdir())
    paused_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert paused.terminal == "AWAIT_INPUT"
    assert paused_meta["git_tracking"]["commit_after_run"]
    assert _git(repo_root, "status", "--porcelain=v1", "--untracked-files=all").strip() == ""

    resumed = run_workflow_package(
        "pause_resume_workflow",
        provider=ScriptedLLMProvider(),
        options=RunnerOptions(
            root=repo_root,
            task_id="pause-task",
            run_id=run_dir.name,
            resume=True,
            answer="approved",
            runtime_config=runtime_config,
        ),
    )

    resumed_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert resumed.terminal == "FINISH"
    assert resumed_meta["git_tracking"]["commit_after_run"]
    assert _git(repo_root, "status", "--porcelain=v1", "--untracked-files=all").strip() == ""


def test_resume_with_git_tracking_disabled_after_tracked_segment_records_warning_without_backfill(tmp_path: Path) -> None:
    _clear_workflow_modules()
    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
    _write_pause_resume_workflow(repo_root)

    tracked_runtime = RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(commit_policy="run"))
    paused = run_workflow_package(
        "pause_resume_workflow",
        provider=ScriptedLLMProvider(),
        options=RunnerOptions(
            root=repo_root,
            task_id="pause-task",
            message="Pause this run",
            runtime_config=tracked_runtime,
        ),
    )

    run_dir = next((repo_root / STATE_DIRNAME / "tasks" / "pause-task" / "wf_pause_resume_workflow" / "runs").iterdir())
    git_tracking_file = run_dir / "git_tracking.jsonl"
    initial_lines = git_tracking_file.read_text(encoding="utf-8").splitlines()

    resumed = run_workflow_package(
        "pause_resume_workflow",
        provider=ScriptedLLMProvider(),
        options=RunnerOptions(
            root=repo_root,
            task_id="pause-task",
            run_id=run_dir.name,
            resume=True,
            answer="approved",
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    run_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    resumed_lines = git_tracking_file.read_text(encoding="utf-8").splitlines()

    assert paused.terminal == "AWAIT_INPUT"
    assert resumed.terminal == "FINISH"
    assert run_meta["warnings"][-1]["event_type"] == "runtime_git_tracking_disabled_on_resume"
    assert resumed_lines == initial_lines


def test_resume_with_git_tracking_enabled_after_untracked_segment_starts_from_resume_point(tmp_path: Path) -> None:
    _clear_workflow_modules()
    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
    _write_pause_resume_workflow(repo_root)

    untracked_runtime = RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False))
    paused = run_workflow_package(
        "pause_resume_workflow",
        provider=ScriptedLLMProvider(),
        options=RunnerOptions(
            root=repo_root,
            task_id="pause-task",
            message="Pause this run",
            runtime_config=untracked_runtime,
        ),
    )

    run_dir = next((repo_root / STATE_DIRNAME / "tasks" / "pause-task" / "wf_pause_resume_workflow" / "runs").iterdir())
    assert not (run_dir / "git_tracking.jsonl").exists()
    _git(repo_root, "add", "--all")
    _git(repo_root, "commit", "-m", "persist untracked paused run")

    resumed = run_workflow_package(
        "pause_resume_workflow",
        provider=ScriptedLLMProvider(),
        options=RunnerOptions(
            root=repo_root,
            task_id="pause-task",
            run_id=run_dir.name,
            resume=True,
            answer="approved",
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(commit_policy="run")),
        ),
    )

    lines = [
        json.loads(line)
        for line in (run_dir / "git_tracking.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    run_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert paused.terminal == "AWAIT_INPUT"
    assert resumed.terminal == "FINISH"
    assert lines[0]["event_type"] == "run_initialized"
    assert lines[-1]["event_type"] == "run_finished"
    assert run_meta["git_tracking"]["enabled"] is True
    assert run_meta.get("warnings") in (None, [])


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=_git_env(),
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


def _git_env() -> dict[str, str]:
    blocked = {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CEILING_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_DIR",
        "GIT_INDEX_FILE",
        "GIT_NAMESPACE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_PREFIX",
        "GIT_SUPER_PREFIX",
        "GIT_WORK_TREE",
    }
    return {key: value for key, value in os.environ.items() if key not in blocked}


def _init_repo(repo_root: Path) -> None:
    repo_root.mkdir()
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "botlane@example.com")
    _git(repo_root, "config", "user.name", "Botlane Tests")


def _write_pause_resume_workflow(root: Path) -> None:
    _write_workflow_package(
        root,
        "pause_resume_workflow",
        class_name="PauseResumeWorkflow",
        prompt_text="unused prompt\n",
        workflow_source="""
from __future__ import annotations

from pydantic import BaseModel

from botlane import AWAIT_INPUT, Event, FINISH, Workflow, python_step


class PauseResumeWorkflow(Workflow):
    name = "pause_resume_workflow"

    class State(BaseModel):
        answer: str | None = None

    @python_step(name="wait", routes={"question": AWAIT_INPUT, "answered": FINISH})
    def wait(state: State, ctx):
        if ctx.answer is None:
            return Event("question", question="Need approval?")

        ctx.state = state.model_copy(update={"answer": ctx.answer})
        return Event("answered")
""".strip(),
    )
    _git(root, "add", "workflows")
    _git(root, "commit", "-m", "baseline")


def _write_workflow_package(
    root: Path,
    workflow_name: str,
    *,
    class_name: str,
    prompt_text: str,
    workflow_source: str,
) -> Path:
    workflows_root = root / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    (workflows_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")

    package_dir = workflows_root / workflow_name
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "__init__.py").write_text(
        f"from .workflow import {class_name}\n__all__ = [{class_name!r}]\n",
        encoding="utf-8",
    )
    (package_dir / "workflow.toml").write_text(f'name = "{workflow_name}"\n', encoding="utf-8")
    (package_dir / "prompts").mkdir(exist_ok=True)
    (package_dir / "assets").mkdir(exist_ok=True)
    (package_dir / "prompts" / "ask.md").write_text(prompt_text, encoding="utf-8")
    (package_dir / "assets" / ".gitkeep").write_text("", encoding="utf-8")
    (package_dir / "workflow.py").write_text(workflow_source + "\n", encoding="utf-8")
    return package_dir
