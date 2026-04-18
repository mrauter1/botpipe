from __future__ import annotations

import json
import subprocess
from pathlib import Path

from autoloop_v3.runtime.runner import RunnerOptions, run_workflow
from autoloop_v3.workflow.primitives import Outcome
from autoloop_v3.workflow.providers.fake import ScriptedLLMProvider


def test_tracing_extension_writes_a_sidecar_trace_without_replacing_events_jsonl(tmp_path: Path) -> None:
    workflow_file = tmp_path / "traced_workflow.py"
    prompt_file = tmp_path / "ask.md"
    prompt_file.write_text("trace prompt\n", encoding="utf-8")
    workflow_file.write_text(
        """
from __future__ import annotations

from pydantic import BaseModel

from autoloop_v3.extensions import Tracing, TracingConfig
from workflow import LLMStep, SUCCESS, Workflow
from workflow.primitives import Outcome


class TracedWorkflow(Workflow):
    class State(BaseModel):
        note: str = ""

    extensions = (Tracing(config=TracingConfig(enabled=True, path="trace/steps.jsonl")),)
    ask = LLMStep(name="ask", producer="ask.md")
    entry = ask
    transitions = {ask: {"done": SUCCESS}}

    @staticmethod
    def on_ask(state: State, outcome: Outcome, artifacts):
        return state.model_copy(update={"note": outcome.raw_output})
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = run_workflow(
        workflow_file,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="traced\n", tag="done")]),
        options=RunnerOptions(root=tmp_path, task_id="trace-task", request_text="Trace it"),
    )

    task_dir = tmp_path / ".autoloop" / "tasks" / "trace-task"
    run_dir = next((task_dir / "runs").iterdir())
    trace_lines = [
        json.loads(line)
        for line in (run_dir / "trace" / "steps.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert result.terminal == "SUCCESS"
    assert (run_dir / "events.jsonl").exists()
    assert [item["event_type"] for item in trace_lines] == ["step_started", "step_finished", "terminal"]
    assert trace_lines[-1]["terminal"] == "SUCCESS"


def test_git_tracking_extension_runs_only_through_workflow_declared_opt_in(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "autoloop@example.com")
    _git(repo_root, "config", "user.name", "Autoloop Tests")

    workflow_file = repo_root / "git_workflow.py"
    prompt_file = repo_root / "ask.md"
    prompt_file.write_text("git prompt\n", encoding="utf-8")
    workflow_file.write_text(
        """
from __future__ import annotations

from pydantic import BaseModel

from autoloop_v3.extensions import GitCommitPlan, GitTracking, GitTrackingConfig
from workflow import Artifact, LLMStep, SUCCESS, Workflow
from workflow.primitives import Outcome


class AfterStepPolicy:
    def before_step(self, event):
        return ()

    def after_step(self, event, delta):
        if delta.is_empty():
            return ()
        return (GitCommitPlan(message=f"track {event.step_name}"),)

    def on_terminal(self, event, delta):
        return ()


class GitWorkflow(Workflow):
    class State(BaseModel):
        note: str = ""

    extensions = (
        GitTracking(
            policy=AfterStepPolicy(),
            config=GitTrackingConfig(enabled=True, track_task_workspace_artifacts=True),
        ),
    )
    note = Artifact("{task_folder}/note.txt")
    ask = LLMStep(name="ask", producer="ask.md", produces={"note": note})
    entry = ask
    transitions = {ask: {"done": SUCCESS}}

    @staticmethod
    def on_ask(state: State, outcome: Outcome, artifacts):
        return state.model_copy(update={"note": artifacts.note.read_text()})
""".strip()
        + "\n",
        encoding="utf-8",
    )
    _git(repo_root, "add", "git_workflow.py", "ask.md")
    _git(repo_root, "commit", "-m", "baseline")

    result = run_workflow(
        workflow_file,
        provider=ScriptedLLMProvider(
            llm_turns=[
                lambda request: (
                    request.artifacts.note.write_text("git tracked note\n"),
                    Outcome(raw_output="ok\n", tag="done"),
                )[1]
            ]
        ),
        options=RunnerOptions(root=repo_root, task_id="git-task", request_text="Track it"),
    )

    last_message = _git(repo_root, "log", "-1", "--pretty=%s").strip()
    changed_files = {
        line.strip()
        for line in _git(repo_root, "show", "--name-only", "--format=", "HEAD").splitlines()
        if line.strip()
    }

    assert result.terminal == "SUCCESS"
    assert last_message == "track ask"
    assert ".autoloop/tasks/git-task/note.txt" in changed_files


def test_extensions_remain_invisible_without_workflow_declarations(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "autoloop@example.com")
    _git(repo_root, "config", "user.name", "Autoloop Tests")

    workflow_file = repo_root / "plain_workflow.py"
    prompt_file = repo_root / "ask.md"
    prompt_file.write_text("plain prompt\n", encoding="utf-8")
    workflow_file.write_text(
        """
from __future__ import annotations

from pydantic import BaseModel

from workflow import Artifact, LLMStep, SUCCESS, Workflow
from workflow.primitives import Outcome


class PlainWorkflow(Workflow):
    class State(BaseModel):
        note: str = ""

    note = Artifact("{task_folder}/note.txt")
    ask = LLMStep(name="ask", producer="ask.md", produces={"note": note})
    entry = ask
    transitions = {ask: {"done": SUCCESS}}

    @staticmethod
    def on_ask(state: State, outcome: Outcome, artifacts):
        return state.model_copy(update={"note": artifacts.note.read_text()})
""".strip()
        + "\n",
        encoding="utf-8",
    )
    _git(repo_root, "add", "plain_workflow.py", "ask.md")
    _git(repo_root, "commit", "-m", "baseline")

    result = run_workflow(
        workflow_file,
        provider=ScriptedLLMProvider(
            llm_turns=[
                lambda request: (
                    request.artifacts.note.write_text("plain note\n"),
                    Outcome(raw_output="ok\n", tag="done"),
                )[1]
            ]
        ),
        options=RunnerOptions(root=repo_root, task_id="plain-task", request_text="Do it"),
    )

    task_dir = repo_root / ".autoloop" / "tasks" / "plain-task"
    run_dir = next((task_dir / "runs").iterdir())

    assert result.terminal == "SUCCESS"
    assert (run_dir / "events.jsonl").exists()
    assert not (run_dir / "trace").exists()
    assert _git(repo_root, "log", "-1", "--pretty=%s").strip() == "baseline"


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout
