from __future__ import annotations

import json
from pathlib import Path

from autoloop_v3.core.providers.fake import ScriptedLLMProvider
from autoloop_v3.runtime.runner import RunnerOptions, run_workflow
from autoloop_v3.workflow.primitives import Outcome


def test_run_creates_task_workflow_run_layout_and_immutable_request_snapshots(tmp_path: Path) -> None:
    workflow_file = _write_system_workflow_package(tmp_path, "snapshot_demo", "SnapshotWorkflow")

    first_result = run_workflow(
        workflow_file,
        provider=ScriptedLLMProvider(),
        options=RunnerOptions(root=tmp_path, task_id="task-1", request_text="First message"),
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

    second_result = run_workflow(
        workflow_file,
        provider=ScriptedLLMProvider(),
        options=RunnerOptions(root=tmp_path, task_id="task-1", request_text="Second message"),
    )

    run_dirs = sorted(path for path in runs_dir.iterdir() if path.is_dir())
    second_run_dir = next(path for path in run_dirs if path != first_run_dir)
    messages = [json.loads(line) for line in (task_dir / "messages.jsonl").read_text(encoding="utf-8").splitlines() if line]
    workflow_meta = json.loads((workflow_dir / "workflow.json").read_text(encoding="utf-8"))

    assert second_result.terminal == "SUCCESS"
    assert len(run_dirs) == 2
    assert [entry["message"] for entry in messages] == ["First message", "Second message"]
    assert (task_dir / "request.md").read_text(encoding="utf-8") == "Second message\n"
    assert (first_run_dir / "request.md").read_text(encoding="utf-8") == "First message\n"
    assert (second_run_dir / "request.md").read_text(encoding="utf-8") == "Second message\n"
    assert workflow_meta["last_run_id"] == second_run_dir.name


def test_runtime_context_and_prompt_resolution_use_workflow_scope_and_package_root(tmp_path: Path) -> None:
    workflow_file = _write_llm_workflow_package(tmp_path, "context_demo", "ContextWorkflow")
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

    result = run_workflow(
        workflow_file,
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="context-task",
            request_text="Inspect runtime context",
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
    assert Path(payload["package_folder"]) == workflow_file.parent
    assert payload["workflow_params"] == {"mode": "strict"}
    assert payload["prompt_text"] == "package prompt\n"
    assert Path(payload["prompt_path"]) == workflow_file.parent / "prompts" / "ask.md"
    assert (workflow_dir / "workflow-note.txt").read_text(encoding="utf-8") == "workflow-scoped\n"
    assert run_meta["workflow_params"] == {"mode": "strict"}
    assert run_meta["workflow_folder"] == ".autoloop/tasks/context-task/wf_context_demo"


def test_resume_preserves_persisted_workflow_params_when_not_resupplied(tmp_path: Path) -> None:
    workflow_file = _write_pause_resume_workflow_package(tmp_path, "resume_params_demo", "ResumeParamsWorkflow")
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

    paused = run_workflow(
        workflow_file,
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="task-params",
            request_text="Need workflow parameters",
            workflow_params={"mode": "strict"},
        ),
    )

    workflow_dir = tmp_path / ".autoloop" / "tasks" / "task-params" / "wf_resume_params_demo"
    run_dir = next((workflow_dir / "runs").iterdir())
    paused_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    resumed = run_workflow(
        workflow_file,
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
    workflow_file = _write_pause_resume_workflow_package(tmp_path, "resume_override_demo", "ResumeOverrideWorkflow")
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

    paused = run_workflow(
        workflow_file,
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="task-override",
            request_text="Need workflow parameters",
            workflow_params={"mode": "strict"},
        ),
    )

    workflow_dir = tmp_path / ".autoloop" / "tasks" / "task-override" / "wf_resume_override_demo"
    run_dir = next((workflow_dir / "runs").iterdir())

    resumed = run_workflow(
        workflow_file,
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
