from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest
from pydantic import BaseModel

from botlane.core.compiler import compile_workflow
from botlane.core import FINISH, Workflow
from botlane.core.providers.fake import ScriptedLLMProvider
from botlane.core.providers.retries import ProviderRetryPolicy
from botlane.core.schema_registry import CHILD_RUN_SUMMARY_SCHEMA, RUN_METADATA_SCHEMA, WORKFLOW_TOPOLOGY_SCHEMA
from botlane.core.steps import PromptStep
from botlane.runtime.config import GitTrackingRuntimeConfig, RuntimeConfig
from botlane.core.errors import WorkflowExecutionError
from botlane.runtime.loader import WorkflowParameterError
from botlane.runtime.loader import resolve_workflow_reference
from botlane.runtime.inspection import (
    list_runs as inspection_list_runs,
    load_run_history as inspection_load_run_history,
    load_run_metadata as inspection_load_run_metadata,
    load_run_record as inspection_load_run_record,
    load_run_topology as inspection_load_run_topology,
)
from botlane.runtime.runner import RunnerOptions, run_workflow_package
from botlane.runtime.workspace import (
    create_run,
    ensure_workspace,
    ensure_workflow_workspace,
    list_run_records,
    list_task_operation_summaries,
    list_workflow_run_summaries,
    resolve_run_workflow_input,
)
from botlane.core.primitives import Outcome

LEGACY_PRODUCT = "auto" + "loop"
LEGACY_STATE_DIRNAME = "." + LEGACY_PRODUCT
LEGACY_WORKFLOWS_MODULE = LEGACY_PRODUCT + ".workflows"
LEGACY_TOPOLOGY_SCHEMA = LEGACY_PRODUCT + ".workflow_topology/v999"


def _clear_workflow_modules() -> None:
    importlib.invalidate_caches()
    for name in list(sys.modules):
        if (
            name == "workflows"
            or name.startswith("workflows.")
            or name == LEGACY_WORKFLOWS_MODULE
            or name.startswith(LEGACY_WORKFLOWS_MODULE + ".")
        ):
            sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _isolate_generated_workflow_modules():
    _clear_workflow_modules()
    yield
    _clear_workflow_modules()


def _runner_options(root: Path, **kwargs: object) -> RunnerOptions:
    kwargs.setdefault(
        "runtime_config",
        RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
    )
    return RunnerOptions(root=root, **kwargs)


def test_run_creates_task_workflow_run_layout_and_immutable_request_snapshots(tmp_path: Path) -> None:
    _write_system_workflow_package(tmp_path, "snapshot_demo", "SnapshotWorkflow")

    first_result = run_workflow_package(
        "snapshot_demo",
        provider=ScriptedLLMProvider(),
        options=_runner_options(tmp_path, task_id="task-1", message="First message"),
    )

    task_dir = tmp_path / ".botlane" / "tasks" / "task-1"
    workflow_dir = task_dir / "wf_snapshot_demo"
    runs_dir = workflow_dir / "runs"
    first_run_dir = next(runs_dir.iterdir())
    task_meta = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
    first_run_meta = json.loads((first_run_dir / "run.json").read_text(encoding="utf-8"))

    assert first_result.terminal == "FINISH"
    assert (task_dir / "messages.jsonl").exists()
    assert not (first_run_dir / "messages.jsonl").exists()
    assert (task_dir / "request.md").read_text(encoding="utf-8") == "First message\n"
    assert (first_run_dir / "request.md").read_text(encoding="utf-8") == "First message\n"
    assert (workflow_dir / "workflow.json").exists()
    assert task_meta["messages_file"] == ".botlane/tasks/task-1/messages.jsonl"
    assert task_meta["request_file"] == ".botlane/tasks/task-1/request.md"
    assert first_run_meta["status"] == "success"
    assert first_run_meta["task_folder"] == ".botlane/tasks/task-1"
    assert first_run_meta["workflow_folder"] == ".botlane/tasks/task-1/wf_snapshot_demo"
    assert first_run_meta["run_folder"] == f".botlane/tasks/task-1/wf_snapshot_demo/runs/{first_run_dir.name}"
    assert first_run_meta["request_file"] == f".botlane/tasks/task-1/wf_snapshot_demo/runs/{first_run_dir.name}/request.md"

    second_result = run_workflow_package(
        "snapshot_demo",
        provider=ScriptedLLMProvider(),
        options=_runner_options(tmp_path, task_id="task-1", message="Second message"),
    )

    run_dirs = sorted(path for path in runs_dir.iterdir() if path.is_dir())
    second_run_dir = next(path for path in run_dirs if path != first_run_dir)
    messages = [json.loads(line) for line in (task_dir / "messages.jsonl").read_text(encoding="utf-8").splitlines() if line]
    workflow_meta = json.loads((workflow_dir / "workflow.json").read_text(encoding="utf-8"))

    assert second_result.terminal == "FINISH"
    assert len(run_dirs) == 2
    assert [entry["message"] for entry in messages] == ["First message", "Second message"]
    assert all("intent_mode" not in entry for entry in messages)
    assert (task_dir / "request.md").read_text(encoding="utf-8") == "Second message\n"
    assert (first_run_dir / "request.md").read_text(encoding="utf-8") == "First message\n"
    assert (second_run_dir / "request.md").read_text(encoding="utf-8") == "Second message\n"
    assert workflow_meta["last_run_id"] == second_run_dir.name


def test_runner_full_auto_hides_default_question_route_from_provider_contract(tmp_path: Path) -> None:
    class FullAutoRunnerWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md", retry_policy=ProviderRetryPolicy(max_attempts=1))
        entry = ask
        transitions = {ask: {"done": FINISH}}

    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")])
    result = run_workflow_package(
        FullAutoRunnerWorkflow,
        provider=provider,
        options=_runner_options(
            tmp_path,
            task_id="full-auto-runner-task",
            message="Run in full auto.",
            runtime_config=RuntimeConfig(
                full_auto=True,
                git_tracking=GitTrackingRuntimeConfig(enabled=False),
            ),
        ),
    )

    assert result.terminal == FINISH
    assert len(provider.calls) == 1
    assert provider.calls[0].available_routes == ("done",)


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
                            "typed_params": request.context.params.model_dump(mode="python"),
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
        options=_runner_options(
            tmp_path,
            task_id="context-task",
            message="Inspect runtime context",
            workflow_params={"mode": "strict"},
        ),
    )

    task_dir = tmp_path / ".botlane" / "tasks" / "context-task"
    workflow_dir = task_dir / "wf_context_demo"
    run_dir = next((workflow_dir / "runs").iterdir())
    payload = json.loads((run_dir / "context.json").read_text(encoding="utf-8"))
    run_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert result.terminal == "FINISH"
    assert payload["workflow_name"] == "context_demo"
    assert Path(payload["workflow_folder"]) == workflow_dir
    assert Path(payload["package_folder"]) == tmp_path / "workflows" / "context_demo"
    assert payload["typed_params"] == {}
    assert payload["workflow_params"] == {"mode": "strict"}
    assert payload["prompt_text"] == "package prompt\n"
    assert Path(payload["prompt_path"]) == tmp_path / "workflows" / "context_demo" / "prompts" / "ask.md"
    assert (workflow_dir / "workflow-note.txt").read_text(encoding="utf-8") == "workflow-scoped\n"
    assert run_meta["workflow_params"] == {"mode": "strict"}
    assert run_meta["workflow_folder"] == ".botlane/tasks/context-task/wf_context_demo"


def test_run_metadata_records_topology_hashes_and_artifact_contract_paths(tmp_path: Path) -> None:
    _write_system_workflow_package(tmp_path, "topology_demo", "TopologyWorkflow")

    result = run_workflow_package(
        "topology_demo",
        provider=ScriptedLLMProvider(),
        options=_runner_options(tmp_path, task_id="task-topology", message="Record topology metadata"),
    )

    run_dir = next((tmp_path / ".botlane" / "tasks" / "task-topology" / "wf_topology_demo" / "runs").iterdir())
    run_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    topology = run_meta["topology"]

    assert result.terminal == "FINISH"
    assert isinstance(topology["source_hash"], str)
    assert isinstance(topology["topology_hash"], str)
    assert topology["entry"] == "start"
    assert topology["artifacts"]["topology"] == "topology.json"
    assert topology["artifacts"]["prompt_refs"] == "prompt_refs.json"
    assert (run_dir / topology["artifacts"]["topology"]).exists()


def test_runtime_inspection_loaders_filter_status_and_require_disambiguation(tmp_path: Path) -> None:
    _write_pause_resume_workflow_package(tmp_path, "inspection_demo", "InspectionWorkflow")
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="Need answer", tag="question", question="What value?"),
            Outcome(raw_output="Need answer", tag="question", question="What value?"),
        ]
    )

    first = run_workflow_package(
        "inspection_demo",
        provider=provider,
        options=_runner_options(
            tmp_path,
            task_id="inspection-task-1",
            run_id="shared-run",
            message="Pause task one",
        ),
    )
    second = run_workflow_package(
        "inspection_demo",
        provider=provider,
        options=_runner_options(
            tmp_path,
            task_id="inspection-task-2",
            run_id="shared-run",
            message="Pause task two",
        ),
    )

    records = inspection_list_runs(tmp_path, workflow_name="inspection_demo", status="awaiting_input")

    assert first.terminal == "AWAIT_INPUT"
    assert second.terminal == "AWAIT_INPUT"
    assert {record.task_id for record in records} == {"inspection-task-1", "inspection-task-2"}
    assert all(record.normalized_status == "awaiting_input" for record in records)

    with pytest.raises(ValueError, match="ambiguous"):
        inspection_load_run_record(
            tmp_path,
            workflow_name="inspection_demo",
            run_id="shared-run",
        )

    record = inspection_load_run_record(
        tmp_path,
        workflow_name="inspection_demo",
        task_id="inspection-task-1",
        run_id="shared-run",
    )
    metadata = inspection_load_run_metadata(record)
    topology = inspection_load_run_topology(record)
    history = inspection_load_run_history(record)

    assert record.task_id == "inspection-task-1"
    assert metadata["status"] == "awaiting_input"
    assert metadata["pending_input"]["question"] == "What value?"
    assert topology["workflow_name"] == "inspection_demo"
    assert topology["entry"] == "ask"
    assert history.events()
    assert history.trace()

    with pytest.raises(FileNotFoundError, match="missing-run"):
        inspection_load_run_record(
            tmp_path,
            workflow_name="inspection_demo",
            run_id="missing-run",
        )


def test_runtime_inspection_loaders_migrate_schema_less_run_metadata_and_topology(tmp_path: Path) -> None:
    run_dir = tmp_path / ".botlane" / "tasks" / "task-1" / "wf_demo" / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps({"workflow_name": "demo", "run_id": "run-1"}, indent=2) + "\n",
        encoding="utf-8",
    )
    (run_dir / "topology.json").write_text(
        json.dumps({"workflow_name": "demo", "entry": "ask", "topology_hash": "hash"}, indent=2) + "\n",
        encoding="utf-8",
    )

    metadata = inspection_load_run_metadata(run_dir)
    topology = inspection_load_run_topology(run_dir)

    assert metadata["schema"] == RUN_METADATA_SCHEMA
    assert topology["schema"] == WORKFLOW_TOPOLOGY_SCHEMA


def test_resume_warns_and_continues_when_saved_topology_hash_differs(tmp_path: Path) -> None:
    _write_pause_resume_workflow_package(tmp_path, "resume_topology_demo", "ResumeTopologyWorkflow")
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="Need answer", tag="question", question="What value?"),
            Outcome(raw_output="Answered", tag="answered", payload={"answer": "42"}),
        ]
    )

    paused = run_workflow_package(
        "resume_topology_demo",
        provider=provider,
        options=_runner_options(tmp_path, task_id="task-topology-resume", message="Pause first"),
    )

    run_dir = next(
        (tmp_path / ".botlane" / "tasks" / "task-topology-resume" / "wf_resume_topology_demo" / "runs").iterdir()
    )
    (run_dir / "topology.json").unlink()
    run_meta_file = run_dir / "run.json"
    run_meta = json.loads(run_meta_file.read_text(encoding="utf-8"))
    embedded_topology = dict(run_meta["topology"])
    embedded_topology.pop("schema", None)
    run_meta["topology"] = embedded_topology
    run_meta_file.write_text(json.dumps(run_meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    workflow_file = tmp_path / "workflows" / "resume_topology_demo" / "workflow.py"
    workflow_file.write_text(
        """
from __future__ import annotations

from pydantic import BaseModel

from botlane import AWAIT_INPUT, FINISH, Prompt, Raw, Workflow, python_step, step


class ResumeTopologyWorkflow(Workflow):
    name = "resume_topology_demo"

    class State(BaseModel):
        answer: str | None = None

    context_dump = Raw("context_dump", path="{run_folder}/context.json")
    ask = step(
        prompt=Prompt.file("prompts/ask.md"),
        writes=[context_dump],
        routes={"answered": FINISH, "question": AWAIT_INPUT},
    )

    @python_step(name="archive", routes={"done": FINISH})
    def archive(ctx):
        return "done"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    _clear_workflow_modules()

    assert paused.terminal == "AWAIT_INPUT"
    resumed = run_workflow_package(
        "resume_topology_demo",
        provider=provider,
        options=_runner_options(
            tmp_path,
            task_id="task-topology-resume",
            run_id=run_dir.name,
            resume=True,
            answer="42",
        ),
    )

    run_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert resumed.terminal == "FINISH"
    assert run_meta["warnings"][-1]["event_type"] == "runtime_resume_topology_mismatch"
    assert "saved_topology" in run_meta["warnings"][-1]["message"]


def test_resume_rejects_unsupported_embedded_topology_schema_when_topology_file_is_missing(tmp_path: Path) -> None:
    _write_pause_resume_workflow_package(tmp_path, "resume_topology_schema_demo", "ResumeTopologySchemaWorkflow")
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="Need answer", tag="question", question="What value?"),
            Outcome(raw_output="Answered", tag="answered", payload={"answer": "42"}),
        ]
    )

    paused = run_workflow_package(
        "resume_topology_schema_demo",
        provider=provider,
        options=_runner_options(tmp_path, task_id="task-topology-schema", message="Pause first"),
    )

    run_dir = next(
        (tmp_path / ".botlane" / "tasks" / "task-topology-schema" / "wf_resume_topology_schema_demo" / "runs").iterdir()
    )
    (run_dir / "topology.json").unlink()
    run_meta_file = run_dir / "run.json"
    run_meta = json.loads(run_meta_file.read_text(encoding="utf-8"))
    embedded_topology = dict(run_meta["topology"])
    embedded_topology["schema"] = LEGACY_TOPOLOGY_SCHEMA
    run_meta["topology"] = embedded_topology
    run_meta_file.write_text(json.dumps(run_meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    assert paused.terminal == "AWAIT_INPUT"
    with pytest.raises(ValueError, match="unsupported schema"):
        run_workflow_package(
            "resume_topology_schema_demo",
            provider=provider,
            options=_runner_options(
                tmp_path,
                task_id="task-topology-schema",
                run_id=run_dir.name,
                resume=True,
                answer="42",
            ),
        )


def test_resume_topology_mismatch_can_fail_in_strict_mode(tmp_path: Path) -> None:
    _write_pause_resume_workflow_package(tmp_path, "resume_topology_strict_demo", "ResumeTopologyStrictWorkflow")
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="Need answer", tag="question", question="What value?"),
            Outcome(raw_output="Answered", tag="answered", payload={"answer": "42"}),
        ]
    )

    paused = run_workflow_package(
        "resume_topology_strict_demo",
        provider=provider,
        options=_runner_options(tmp_path, task_id="task-topology-strict", message="Pause first"),
    )

    run_dir = next(
        (tmp_path / ".botlane" / "tasks" / "task-topology-strict" / "wf_resume_topology_strict_demo" / "runs").iterdir()
    )
    workflow_file = tmp_path / "workflows" / "resume_topology_strict_demo" / "workflow.py"
    workflow_file.write_text(
        """
from __future__ import annotations

from pydantic import BaseModel

from botlane import AWAIT_INPUT, FINISH, Prompt, Raw, Workflow, python_step, step


class ResumeTopologyStrictWorkflow(Workflow):
    name = "resume_topology_strict_demo"

    class State(BaseModel):
        answer: str | None = None

    context_dump = Raw("context_dump", path="{run_folder}/context.json")
    ask = step(
        prompt=Prompt.file("prompts/ask.md"),
        writes=[context_dump],
        routes={"answered": FINISH, "question": AWAIT_INPUT},
    )

    @python_step(name="archive", routes={"done": FINISH})
    def archive(ctx):
        return "done"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    _clear_workflow_modules()

    assert paused.terminal == "AWAIT_INPUT"
    with pytest.raises(WorkflowExecutionError, match="saved-contract mismatch"):
        run_workflow_package(
            "resume_topology_strict_demo",
            provider=provider,
            options=_runner_options(
                tmp_path,
                task_id="task-topology-strict",
                run_id=run_dir.name,
                resume=True,
                answer="42",
                runtime_config=RuntimeConfig(
                    git_tracking=GitTrackingRuntimeConfig(enabled=False),
                    resume_topology_mismatch_behavior="fail",
                ),
            ),
        )


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
        options=_runner_options(
            tmp_path,
            task_id="task-params",
            message="Need workflow parameters",
            workflow_params={"mode": "strict"},
        ),
    )

    workflow_dir = tmp_path / ".botlane" / "tasks" / "task-params" / "wf_resume_params_demo"
    run_dir = next((workflow_dir / "runs").iterdir())
    paused_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    resumed = run_workflow_package(
        "resume_params_demo",
        provider=provider,
        options=_runner_options(
            tmp_path,
            task_id="task-params",
            run_id=run_dir.name,
            resume=True,
            answer="42",
        ),
    )

    resumed_context = json.loads((run_dir / "context.json").read_text(encoding="utf-8"))
    resumed_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert paused.terminal == "AWAIT_INPUT"
    assert paused_meta["workflow_params"] == {"mode": "strict"}
    assert resumed.terminal == "FINISH"
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
        options=_runner_options(
            tmp_path,
            task_id="task-override",
            message="Need workflow parameters",
            workflow_params={"mode": "strict"},
        ),
    )

    workflow_dir = tmp_path / ".botlane" / "tasks" / "task-override" / "wf_resume_override_demo"
    run_dir = next((workflow_dir / "runs").iterdir())

    resumed = run_workflow_package(
        "resume_override_demo",
        provider=provider,
        options=_runner_options(
            tmp_path,
            task_id="task-override",
            run_id=run_dir.name,
            resume=True,
            answer="42",
            workflow_params={"mode": "loose"},
        ),
    )

    resumed_context = json.loads((run_dir / "context.json").read_text(encoding="utf-8"))
    resumed_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert paused.terminal == "AWAIT_INPUT"
    assert resumed.terminal == "FINISH"
    assert resumed_context["workflow_params"] == {"mode": "strict"}
    assert resumed_context["answer"] == "42"
    assert resumed_meta["workflow_params"] == {"mode": "strict"}


def test_resume_context_message_uses_run_local_request_snapshot_not_mutated_task_request(tmp_path: Path) -> None:
    _write_pause_resume_workflow_package(tmp_path, "resume_message_demo", "ResumeMessageWorkflow")
    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: (
                request.artifacts.context_dump.write_text(
                    json.dumps(
                        {
                            "message": request.context.message,
                            "request_file": str(request.context.request_file),
                            "task_request_file": None
                            if request.context.request.task_file is None
                            else str(request.context.request.task_file),
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
                            "message": request.context.message,
                            "request_file": str(request.context.request_file),
                            "task_request_file": None
                            if request.context.request.task_file is None
                            else str(request.context.request.task_file),
                            "answer": request.context.answer,
                        }
                    ),
                ),
                Outcome(raw_output="Answered", tag="answered", payload={"answer": request.context.answer}),
            )[1],
        ]
    )

    paused = run_workflow_package(
        "resume_message_demo",
        provider=provider,
        options=_runner_options(
            tmp_path,
            task_id="task-message",
            message="Original request",
        ),
    )

    workflow_dir = tmp_path / ".botlane" / "tasks" / "task-message" / "wf_resume_message_demo"
    task_dir = tmp_path / ".botlane" / "tasks" / "task-message"
    run_dir = next((workflow_dir / "runs").iterdir())
    paused_context = json.loads((run_dir / "context.json").read_text(encoding="utf-8"))

    (task_dir / "request.md").write_text("Mutated task request\n", encoding="utf-8")

    resumed = run_workflow_package(
        "resume_message_demo",
        provider=provider,
        options=_runner_options(
            tmp_path,
            task_id="task-message",
            run_id=run_dir.name,
            resume=True,
            answer="42",
        ),
    )

    resumed_context = json.loads((run_dir / "context.json").read_text(encoding="utf-8"))

    assert paused.terminal == "AWAIT_INPUT"
    assert paused_context == {
        "message": "Original request",
        "request_file": str(run_dir / "request.md"),
        "task_request_file": str(task_dir / "request.md"),
        "answer": None,
    }
    assert resumed.terminal == "FINISH"
    assert resumed_context == {
        "message": "Original request",
        "request_file": str(run_dir / "request.md"),
        "task_request_file": str(task_dir / "request.md"),
        "answer": "42",
    }
    assert (run_dir / "request.md").read_text(encoding="utf-8") == "Original request\n"


def test_resume_context_preserves_run_message_and_raw_input_fields(tmp_path: Path) -> None:
    _write_typed_input_pause_resume_workflow_package(
        tmp_path,
        "resume_typed_input_demo",
        "ResumeTypedInputWorkflow",
    )
    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: (
                request.artifacts.context_dump.write_text(
                    json.dumps(
                        {
                            "message": request.context.message,
                            "input_has_message": request.context.input_fields is not None
                            and "message" in type(request.context.input_fields).model_fields,
                            "input_model_dump": request.context.input.model_dump(mode="python"),
                            "input_topic": request.context.input.topic,
                            "input_fields": None
                            if request.context.input_fields is None
                            else request.context.input_fields.model_dump(mode="python"),
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
                            "message": request.context.message,
                            "input_has_message": request.context.input_fields is not None
                            and "message" in type(request.context.input_fields).model_fields,
                            "input_model_dump": request.context.input.model_dump(mode="python"),
                            "input_topic": request.context.input.topic,
                            "input_fields": None
                            if request.context.input_fields is None
                            else request.context.input_fields.model_dump(mode="python"),
                            "answer": request.context.answer,
                        }
                    ),
                ),
                Outcome(raw_output="Answered", tag="answered", payload={"answer": request.context.answer}),
            )[1],
        ]
    )

    paused = run_workflow_package(
        "resume_typed_input_demo",
        provider=provider,
        options=_runner_options(
            tmp_path,
            task_id="task-typed-input-message",
            message="Original request",
            workflow_input={"topic": "release"},
        ),
    )

    workflow_dir = tmp_path / ".botlane" / "tasks" / "task-typed-input-message" / "wf_resume_typed_input_demo"
    task_dir = tmp_path / ".botlane" / "tasks" / "task-typed-input-message"
    run_dir = next((workflow_dir / "runs").iterdir())
    paused_context = json.loads((run_dir / "context.json").read_text(encoding="utf-8"))
    paused_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    (task_dir / "request.md").write_text("Mutated task request\n", encoding="utf-8")

    resumed = run_workflow_package(
        "resume_typed_input_demo",
        provider=provider,
        options=_runner_options(
            tmp_path,
            task_id="task-typed-input-message",
            run_id=run_dir.name,
            resume=True,
            answer="42",
        ),
    )

    resumed_context = json.loads((run_dir / "context.json").read_text(encoding="utf-8"))
    resumed_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert paused.terminal == "AWAIT_INPUT"
    assert paused_context == {
        "message": "Original request",
        "input_has_message": False,
        "input_model_dump": {"message": "Original request", "topic": "release"},
        "input_topic": "release",
        "input_fields": {"topic": "release"},
        "answer": None,
    }
    assert paused_meta["workflow_input"] == {"topic": "release"}
    assert "message" not in paused_meta["workflow_input"]
    assert resumed.terminal == "FINISH"
    assert resumed_context == {
        "message": "Original request",
        "input_has_message": False,
        "input_model_dump": {"message": "Original request", "topic": "release"},
        "input_topic": "release",
        "input_fields": {"topic": "release"},
        "answer": "42",
    }
    assert resumed_meta["workflow_input"] == {"topic": "release"}
    assert "message" not in resumed_meta["workflow_input"]


def test_create_run_persists_workflow_input_and_resolve_run_workflow_input_handles_fresh_and_stored_paths(
    tmp_path: Path,
) -> None:
    package_dir = tmp_path / "workflows" / "child_input_workspace_demo"
    package_dir.mkdir(parents=True, exist_ok=True)

    task_workspace = ensure_workspace(tmp_path, "child-input-workspace-task", message="Parent request")
    workflow_workspace = ensure_workflow_workspace(
        task_workspace,
        "child_input_workspace_demo",
        package_dir=package_dir,
        reference="child_input_workspace_demo",
    )

    provided_input = {"topic": "alpha", "urgency": 2}
    run_workspace = create_run(
        workflow_workspace,
        message="Run typed child",
        workflow_input=provided_input,
    )

    run_meta = json.loads(run_workspace.run_meta_file.read_text(encoding="utf-8"))

    assert run_meta["workflow_input"] == provided_input
    assert resolve_run_workflow_input(run_workspace, None) == provided_input
    assert resolve_run_workflow_input(run_workspace, {"topic": "beta", "urgency": 9}) == provided_input

    run_meta.pop("workflow_input", None)
    run_workspace.run_meta_file.write_text(json.dumps(run_meta, ensure_ascii=False) + "\n", encoding="utf-8")

    fallback_input = {"topic": "gamma", "urgency": 3}
    assert resolve_run_workflow_input(run_workspace, fallback_input) == fallback_input


def test_context_exposes_typed_params_on_new_runs(tmp_path: Path) -> None:
    _write_pause_resume_workflow_package(
        tmp_path,
        "typed_params_demo",
        "TypedParamsWorkflow",
        export_parameters=True,
        parameters_source="""
from pydantic import BaseModel


class Params(BaseModel):
    mode: str = "strict"
    reviewers: list[str] = []
""".strip(),
    )
    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: (
                request.artifacts.context_dump.write_text(
                    json.dumps(
                        {
                            "typed_mode": request.context.params.mode,
                            "typed_params": request.context.params.model_dump(mode="python"),
                            "workflow_params": request.context.workflow_params,
                        }
                    ),
                ),
                Outcome(raw_output="Need answer", tag="question", question="What value?"),
            )[1],
        ]
    )

    paused = run_workflow_package(
        "typed_params_demo",
        provider=provider,
        options=_runner_options(
            tmp_path,
            task_id="task-typed-new",
            message="Need typed params",
            workflow_params={"mode": "focused", "reviewers": ["alice", "bob"]},
        ),
    )

    workflow_dir = tmp_path / ".botlane" / "tasks" / "task-typed-new" / "wf_typed_params_demo"
    run_dir = next((workflow_dir / "runs").iterdir())
    payload = json.loads((run_dir / "context.json").read_text(encoding="utf-8"))

    assert paused.terminal == "AWAIT_INPUT"
    assert payload["typed_mode"] == "focused"
    assert payload["typed_params"] == {"mode": "focused", "reviewers": ["alice", "bob"]}
    assert payload["workflow_params"] == {"mode": "focused", "reviewers": ["alice", "bob"]}


def test_new_runs_persist_normalized_workflow_params_snapshot(tmp_path: Path) -> None:
    _write_pause_resume_workflow_package(
        tmp_path,
        "typed_normalized_demo",
        "TypedNormalizedWorkflow",
        export_parameters=True,
        parameters_source="""
from pydantic import BaseModel


class Params(BaseModel):
    retries: int = 2
    mode: str = "strict"
""".strip(),
    )
    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: (
                request.artifacts.context_dump.write_text(
                    json.dumps(
                        {
                            "typed_params": request.context.params.model_dump(mode="python"),
                            "workflow_params": request.context.workflow_params,
                        }
                    ),
                ),
                Outcome(raw_output="Need answer", tag="question", question="What value?"),
            )[1],
        ]
    )

    paused = run_workflow_package(
        "typed_normalized_demo",
        provider=provider,
        options=_runner_options(
            tmp_path,
            task_id="task-typed-normalized",
            message="Need normalized typed params",
            workflow_params={"retries": "5"},
        ),
    )

    workflow_dir = tmp_path / ".botlane" / "tasks" / "task-typed-normalized" / "wf_typed_normalized_demo"
    run_dir = next((workflow_dir / "runs").iterdir())
    payload = json.loads((run_dir / "context.json").read_text(encoding="utf-8"))
    run_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert paused.terminal == "AWAIT_INPUT"
    assert payload["typed_params"] == {"retries": 5, "mode": "strict"}
    assert payload["workflow_params"] == {"retries": 5, "mode": "strict"}
    assert run_meta["workflow_params"] == {"retries": 5, "mode": "strict"}


def test_resume_restores_typed_params_from_persisted_run_metadata(tmp_path: Path) -> None:
    _write_pause_resume_workflow_package(
        tmp_path,
        "typed_resume_demo",
        "TypedResumeWorkflow",
        export_parameters=True,
        parameters_source="""
from pydantic import BaseModel


class Params(BaseModel):
    mode: str = "strict"
""".strip(),
    )
    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: (
                request.artifacts.context_dump.write_text(
                    json.dumps(
                        {
                            "typed_mode": request.context.params.mode,
                            "typed_params": request.context.params.model_dump(mode="python"),
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
                            "typed_mode": request.context.params.mode,
                            "typed_params": request.context.params.model_dump(mode="python"),
                            "workflow_params": request.context.workflow_params,
                            "answer": request.context.answer,
                        }
                    ),
                ),
                Outcome(raw_output="Answered", tag="answered", payload={"answer": request.context.answer}),
            )[1],
        ]
    )

    paused = run_workflow_package(
        "typed_resume_demo",
        provider=provider,
        options=_runner_options(
            tmp_path,
            task_id="task-typed-resume",
            message="Need typed params",
            workflow_params={"mode": "strict"},
        ),
    )

    workflow_dir = tmp_path / ".botlane" / "tasks" / "task-typed-resume" / "wf_typed_resume_demo"
    run_dir = next((workflow_dir / "runs").iterdir())

    resumed = run_workflow_package(
        "typed_resume_demo",
        provider=provider,
        options=_runner_options(
            tmp_path,
            task_id="task-typed-resume",
            run_id=run_dir.name,
            resume=True,
            answer="42",
            workflow_params={"mode": "loose"},
        ),
    )

    payload = json.loads((run_dir / "context.json").read_text(encoding="utf-8"))

    assert paused.terminal == "AWAIT_INPUT"
    assert resumed.terminal == "FINISH"
    assert payload["typed_mode"] == "strict"
    assert payload["typed_params"] == {"mode": "strict"}
    assert payload["workflow_params"] == {"mode": "strict"}
    assert payload["answer"] == "42"


def test_new_runs_validate_workflow_params_before_persisting_run_metadata(tmp_path: Path) -> None:
    _write_pause_resume_workflow_package(
        tmp_path,
        "typed_invalid_demo",
        "TypedInvalidWorkflow",
        export_parameters=True,
        parameters_source="""
from pydantic import BaseModel


class Params(BaseModel):
    mode: str = "strict"
""".strip(),
    )

    with pytest.raises(WorkflowParameterError, match="unknown workflow parameter 'unknown'"):
        run_workflow_package(
            "typed_invalid_demo",
            provider=ScriptedLLMProvider(),
            options=_runner_options(
                tmp_path,
                task_id="task-invalid-params",
                message="Need typed params",
                workflow_params={"unknown": "value"},
            ),
        )

    assert not (tmp_path / ".botlane").exists()


def test_list_run_records_normalizes_legacy_paused_status_for_public_filters(tmp_path: Path) -> None:
    _write_run_summary_record(
        tmp_path,
        task_id="task-1",
        workflow_name="release_candidate_to_go_no_go",
        run_id="run-paused",
        status="paused",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:03:00+00:00",
        request_text="Investigate the paused release gate.\n",
        pending_question="Who owns the gate?",
    )
    _write_run_summary_record(
        tmp_path,
        task_id="task-1",
        workflow_name="release_candidate_to_go_no_go",
        run_id="run-success",
        status="success",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:04:00+00:00",
        request_text="Routine release check.\n",
    )

    records = list_run_records(
        tmp_path,
        workflow_name="release_candidate_to_go_no_go",
        task_id="task-1",
        status="awaiting_input",
    )

    assert [record.run_id for record in records] == ["run-paused"]
    assert records[0].status == "paused"
    assert records[0].normalized_status == "awaiting_input"
    assert records[0].awaiting_input is True
    assert records[0].paused is True


def test_run_metadata_keeps_blocked_status_distinct_from_awaiting_input(tmp_path: Path) -> None:
    _write_blocked_route_workflow_package(tmp_path, "blocked_demo", "BlockedWorkflow")

    result = run_workflow_package(
        "blocked_demo",
        provider=ScriptedLLMProvider(
            llm_turns=[Outcome(raw_output="Dependency missing", tag="blocked", reason="Waiting on external approval.")]
        ),
        options=_runner_options(tmp_path, task_id="blocked-task", message="Check dependency status"),
    )

    run_dir = next((tmp_path / ".botlane" / "tasks" / "blocked-task" / "wf_blocked_demo" / "runs").iterdir())
    run_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    blocked_records = list_run_records(
        tmp_path,
        workflow_name="blocked_demo",
        task_id="blocked-task",
        status="blocked",
    )
    awaiting_records = list_run_records(
        tmp_path,
        workflow_name="blocked_demo",
        task_id="blocked-task",
        status="awaiting_input",
    )

    assert result.terminal == "AWAIT_INPUT"
    assert run_meta["status"] == "blocked"
    assert [record.run_id for record in blocked_records] == [run_dir.name]
    assert blocked_records[0].status == "blocked"
    assert blocked_records[0].normalized_status == "blocked"
    assert blocked_records[0].awaiting_input is False
    assert awaiting_records == ()


def test_run_record_projects_legacy_pending_question_as_pending_input(tmp_path: Path) -> None:
    _write_run_summary_record(
        tmp_path,
        task_id="task-1",
        workflow_name="release_candidate_to_go_no_go",
        run_id="run-paused",
        status="paused",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:03:00+00:00",
        request_text="Investigate the paused release gate.\n",
        pending_question="Who owns the gate?",
    )

    records = list_run_records(
        tmp_path,
        workflow_name="release_candidate_to_go_no_go",
        task_id="task-1",
    )

    assert len(records) == 1
    assert records[0].pending_input == {"question": "Who owns the gate?"}
    assert records[0].pending_question == "Who owns the gate?"


def test_list_run_records_reads_legacy_state_root_when_botlane_root_is_absent(tmp_path: Path) -> None:
    task_dir = tmp_path / LEGACY_STATE_DIRNAME / "tasks" / "legacy-task"
    workflow_dir = task_dir / "wf_legacy_demo"
    run_dir = workflow_dir / "runs" / "run-legacy"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "request.md").write_text("Legacy run.\n", encoding="utf-8")
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "created_at": "2026-05-01T00:00:00+00:00",
                "run_id": "run-legacy",
                "status": "success",
                "task_id": "legacy-task",
                "updated_at": "2026-05-01T00:01:00+00:00",
                "workflow_name": "legacy_demo",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    records = list_run_records(tmp_path, workflow_name="legacy_demo", task_id="legacy-task")

    assert len(records) == 1
    assert records[0].run_dir == run_dir


def test_resume_without_run_id_uses_latest_run_across_botlane_and_legacy_state_roots(tmp_path: Path) -> None:
    _write_pause_resume_workflow_package(tmp_path, "mixed_root_resume_demo", "MixedRootResumeWorkflow")
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="Need answer", tag="question", question="Botlane run?"),
            Outcome(raw_output="Need answer", tag="question", question="Legacy run?"),
            Outcome(raw_output="Answered", tag="answered", payload={"answer": "legacy-answer"}),
        ]
    )

    first = run_workflow_package(
        "mixed_root_resume_demo",
        provider=provider,
        options=_runner_options(
            tmp_path,
            task_id="task-mixed-root",
            message="Create botlane run first",
        ),
    )
    botlane_workflow_dir = tmp_path / ".botlane" / "tasks" / "task-mixed-root" / "wf_mixed_root_resume_demo"
    botlane_run_dir = next((botlane_workflow_dir / "runs").iterdir())

    second = run_workflow_package(
        "mixed_root_resume_demo",
        provider=provider,
        options=_runner_options(
            tmp_path,
            task_id="task-mixed-root",
            message="Create legacy run second",
            state_dir=tmp_path / LEGACY_STATE_DIRNAME,
        ),
    )
    legacy_workflow_dir = tmp_path / LEGACY_STATE_DIRNAME / "tasks" / "task-mixed-root" / "wf_mixed_root_resume_demo"
    legacy_run_dir = next((legacy_workflow_dir / "runs").iterdir())

    resumed = run_workflow_package(
        "mixed_root_resume_demo",
        provider=provider,
        options=_runner_options(
            tmp_path,
            task_id="task-mixed-root",
            resume=True,
            answer="legacy-answer",
        ),
    )

    assert first.terminal == "AWAIT_INPUT"
    assert second.terminal == "AWAIT_INPUT"
    assert resumed.terminal == "FINISH"
    legacy_record = inspection_load_run_record(
        tmp_path,
        workflow_name="mixed_root_resume_demo",
        task_id="task-mixed-root",
        run_id=legacy_run_dir.name,
    )
    botlane_record = inspection_load_run_record(
        tmp_path,
        workflow_name="mixed_root_resume_demo",
        task_id="task-mixed-root",
        run_id=botlane_run_dir.name,
    )

    assert inspection_load_run_metadata(legacy_record)["terminal"] == "FINISH"
    assert inspection_load_run_metadata(botlane_record)["terminal"] == "AWAIT_INPUT"


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
                    "finalization": None,
                    "pending_input": {"question": "Who owns the gate?"},
                    "request_excerpt": "Investigate the paused release gate. Need owner confirmation.",
                    "request_file": str(paused_dir / "request.md"),
                    "run_folder": str(paused_dir),
                    "run_id": "run-paused",
                    "status": "awaiting_input",
                    "task_id": "task-1",
                    "terminal": None,
                    "updated_at": "2026-04-24T06:03:00+00:00",
                }
            ],
            "run_count": 2,
            "status_counts": {"awaiting_input": 1, "failed": 1},
            "workflow_name": "release_candidate_to_go_no_go",
        },
    )

    with pytest.raises(ValueError, match="workflow_names entries must be non-empty strings"):
        list_workflow_run_summaries(tmp_path, workflow_names=["release_candidate_to_go_no_go", "  "])
    with pytest.raises(ValueError, match="statuses entries must be non-empty strings"):
        list_workflow_run_summaries(tmp_path, statuses=["failed", "  "])
    with pytest.raises(ValueError, match="positive integer"):
        list_workflow_run_summaries(tmp_path, max_runs_per_workflow=0)


def test_list_task_operation_summaries_publish_bounded_task_history_and_filtered_workflow_telemetry(
    tmp_path: Path,
) -> None:
    task_one_dir = _write_task_operation_record(
        tmp_path,
        task_id="task-1",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:04:00+00:00",
        request_text="Investigate the paused release gate for the reporting hotfix.\n",
        messages=[
            (
                "2026-04-24T06:01:00+00:00",
                "Customer escalation: reporting exports still disagree with the dashboard totals for the enterprise rollout and the release gate is blocked until that discrepancy is explained to operations.",
            ),
            (
                "2026-04-24T06:02:00+00:00",
                "Need go/no-go owner before we can close the release gate for 2026.04.",
            ),
            (
                "2026-04-24T06:03:00+00:00",
                "Waiting on the release manager confirmation.",
            ),
        ],
    )
    _write_task_operation_record(
        tmp_path,
        task_id="task-2",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:05:00+00:00",
        request_text="Routine release check.\n",
        messages=[
            (
                "2026-04-24T06:05:00+00:00",
                "Routine confirmation only.",
            ),
        ],
    )
    _write_run_summary_record(
        tmp_path,
        task_id="task-1",
        workflow_name="release_candidate_to_go_no_go",
        run_id="run-failed",
        status="failed",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:02:00+00:00",
        request_text="Investigate the failed release gate.\n",
        terminal="FAIL",
        error="missing evidence",
    )
    paused_dir = _write_run_summary_record(
        tmp_path,
        task_id="task-1",
        workflow_name="release_candidate_to_go_no_go",
        run_id="run-paused",
        status="paused",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:04:00+00:00",
        request_text="Investigate the paused release gate. Need owner confirmation.\n",
        pending_question="Who owns the gate?",
    )
    _write_run_summary_record(
        tmp_path,
        task_id="task-2",
        workflow_name="release_candidate_to_go_no_go",
        run_id="run-success",
        status="success",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:05:00+00:00",
        request_text="Routine release check.\n",
    )

    summaries = list_task_operation_summaries(
        tmp_path,
        workflow_names=["release_candidate_to_go_no_go", "incident_to_hardening_program"],
        statuses=(status for status in ["failed", "paused", "failed"]),
        max_runs_per_workflow=1,
        max_messages_per_task=2,
    )

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary["task_id"] == "task-1"
    assert summary["created_at"] == "2026-04-24T06:00:00+00:00"
    assert summary["updated_at"] == "2026-04-24T06:04:00+00:00"
    assert summary["request_updated_at"] == "2026-04-24T06:03:00+00:00"
    assert summary["latest_activity_at"] == "2026-04-24T06:04:00+00:00"
    assert summary["message_count"] == 3
    assert summary["request_excerpt"] == "Investigate the paused release gate for the reporting hotfix."
    assert summary["source_paths"] == {
        "messages_file": str(task_one_dir / "messages.jsonl"),
        "request_file": str(task_one_dir / "request.md"),
        "task_dir": str(task_one_dir),
        "task_meta_file": str(task_one_dir / "task.json"),
    }
    assert summary["recent_messages"][0] == {
        "message_excerpt": "Waiting on the release manager confirmation.",
        "ts": "2026-04-24T06:03:00+00:00",
    }
    assert summary["recent_messages"][1] == {
        "message_excerpt": "Need go/no-go owner before we can close the release gate for 2026.04.",
        "ts": "2026-04-24T06:02:00+00:00",
    }
    assert summary["workflow_run_summaries"] == [
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
            "latest_updated_at": "2026-04-24T06:04:00+00:00",
            "recent_runs": [
                {
                    "created_at": "2026-04-24T06:00:00+00:00",
                    "error": None,
                    "finalization": None,
                    "pending_input": {"question": "Who owns the gate?"},
                    "request_excerpt": "Investigate the paused release gate. Need owner confirmation.",
                    "request_file": str(paused_dir / "request.md"),
                    "run_folder": str(paused_dir),
                    "run_id": "run-paused",
                    "status": "awaiting_input",
                    "task_id": "task-1",
                    "terminal": None,
                    "updated_at": "2026-04-24T06:04:00+00:00",
                }
            ],
            "run_count": 2,
            "status_counts": {"awaiting_input": 1, "failed": 1},
            "workflow_name": "release_candidate_to_go_no_go",
        },
    ]

    with pytest.raises(ValueError, match="task_ids entries must be non-empty strings"):
        list_task_operation_summaries(tmp_path, task_ids=["task-1", "  "])
    with pytest.raises(ValueError, match="workflow_names entries must be non-empty strings"):
        list_task_operation_summaries(tmp_path, workflow_names=["release_candidate_to_go_no_go", "  "])
    with pytest.raises(ValueError, match="statuses entries must be non-empty strings"):
        list_task_operation_summaries(tmp_path, statuses=["failed", "  "])
    with pytest.raises(ValueError, match="positive integer"):
        list_task_operation_summaries(tmp_path, max_tasks=0)
    with pytest.raises(ValueError, match="positive integer"):
        list_task_operation_summaries(tmp_path, max_messages_per_task=0)


def test_list_task_operation_summaries_keep_explicit_task_ids_even_when_filtered_telemetry_is_empty(
    tmp_path: Path,
) -> None:
    task_one_dir = _write_task_operation_record(
        tmp_path,
        task_id="task-1",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:04:00+00:00",
        request_text="Release recovery task.\n",
        messages=[
            (
                "2026-04-24T06:03:00+00:00",
                "Need owner confirmation for the release recovery path.",
            ),
        ],
    )
    task_two_dir = _write_task_operation_record(
        tmp_path,
        task_id="task-2",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:05:00+00:00",
        request_text="Incident review task.\n",
        messages=[
            (
                "2026-04-24T06:05:00+00:00",
                "Waiting for incident commander confirmation.",
            ),
        ],
    )
    _write_run_summary_record(
        tmp_path,
        task_id="task-1",
        workflow_name="release_candidate_to_go_no_go",
        run_id="run-success",
        status="success",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:04:00+00:00",
        request_text="Release recovery task.\n",
    )

    summaries = list_task_operation_summaries(
        tmp_path,
        task_ids=["task-1", "task-2"],
        workflow_names=["incident_to_hardening_program"],
        statuses=["paused"],
        max_runs_per_workflow=1,
        max_messages_per_task=1,
    )

    assert len(summaries) == 2
    assert [summary["task_id"] for summary in summaries] == ["task-2", "task-1"]
    assert summaries[0]["source_paths"] == {
        "messages_file": str(task_two_dir / "messages.jsonl"),
        "request_file": str(task_two_dir / "request.md"),
        "task_dir": str(task_two_dir),
        "task_meta_file": str(task_two_dir / "task.json"),
    }
    assert summaries[1]["source_paths"] == {
        "messages_file": str(task_one_dir / "messages.jsonl"),
        "request_file": str(task_one_dir / "request.md"),
        "task_dir": str(task_one_dir),
        "task_meta_file": str(task_one_dir / "task.json"),
    }
    for summary in summaries:
        assert summary["workflow_run_summaries"] == [
            {
                "latest_run_id": None,
                "latest_updated_at": None,
                "recent_runs": [],
                "run_count": 0,
                "status_counts": {},
                "workflow_name": "incident_to_hardening_program",
            }
        ]


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
        options=_runner_options(tmp_path, task_id="subworkflow-class-task", message="Parent request"),
    )

    task_dir = tmp_path / ".botlane" / "tasks" / "subworkflow-class-task"
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

    assert result.terminal == "FINISH"
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
    expected_finalization = {
        "candidate_route": "done",
        "final_route": "done",
        "runtime_control": None,
        "pending_input_id": None,
        "target_step": None,
        "terminal": None,
        "provider_attributable": True,
        "provider_attempted": True,
        "producer_attempted": None,
        "verifier_attempted": None,
        "source_hook": None,
        "source_phase": None,
        "hook_route_redirects": [],
    }
    assert child_records == [
        {
            "schema": CHILD_RUN_SUMMARY_SCHEMA,
            "workflow_name": "child_success",
            "run_id": child_run_dir.name,
            "terminal": "FINISH",
            "status": "success",
            "last_event": {"tag": "done", "reason": "", "question": None, "handoff": None},
            "finalization": expected_finalization,
            "output_metadata": {"summary": "child complete"},
            "output_artifacts": {
                "ask.child_dump": str(child_run_dir / "child.json"),
                "child_dump": str(child_run_dir / "child.json"),
            },
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
            "output": None,
            "artifacts": {
                "ask.child_dump": str(child_run_dir / "child.json"),
                "child_dump": str(child_run_dir / "child.json"),
            },
            "metadata": {"finalization": expected_finalization},
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
        options=_runner_options(tmp_path, task_id="subworkflow-helper-task", message="Parent request"),
    )

    task_dir = tmp_path / ".botlane" / "tasks" / "subworkflow-helper-task"
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

    assert result.terminal == "FINISH"
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
    assert child_records[0]["output"] is None
    assert child_records[0]["output_artifacts"] == {
        "ask.child_dump": str(child_run_dir / "child.json"),
        "child_dump": str(child_run_dir / "child.json"),
    }
    assert child_records[0]["artifacts"] == child_records[0]["output_artifacts"]
    assert child_records[0]["metadata"]["finalization"] == {
        "candidate_route": "done",
        "final_route": "done",
        "hook_route_redirects": [],
        "provider_attributable": True,
        "provider_attempted": True,
        "producer_attempted": None,
        "verifier_attempted": None,
        "pending_input_id": None,
        "runtime_control": None,
        "source_hook": None,
        "source_phase": None,
        "target_step": None,
        "terminal": None,
    }


def test_context_invoke_workflow_by_name_creates_isolated_child_runs_without_inheriting_parent_answers(tmp_path: Path) -> None:
    _write_child_pause_workflow_package(tmp_path)
    _write_parent_name_invoker_workflow_package(tmp_path)

    paused_parent = run_workflow_package(
        "parent_name",
        provider=ScriptedLLMProvider(),
        options=_runner_options(tmp_path, task_id="subworkflow-name-task", message="Parent request"),
    )

    task_dir = tmp_path / ".botlane" / "tasks" / "subworkflow-name-task"
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
        options=_runner_options(
            tmp_path,
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

    assert paused_parent.terminal == "AWAIT_INPUT"
    assert resumed_parent.terminal == "FINISH"
    assert (task_dir / "request.md").read_text(encoding="utf-8") == "Parent request\n"
    assert [entry["message"] for entry in task_messages] == ["Parent request"]
    assert parent_payload["parent_answer"] == "Proceed parent"
    assert parent_payload["child_workflow"] == "child_pause"
    assert parent_payload["child_status"] == "awaiting_input"
    assert parent_payload["child_last_event"] == "question"
    assert Path(parent_payload["child_checkpoint_file"]) == child_run_dir / "checkpoint.json"
    assert child_payload["answer"] is None
    assert child_payload["workflow_params"] == {"mode": "strict"}
    assert child_meta["status"] == "awaiting_input"
    assert child_meta["pending_input"]["pending_input_id"]
    assert child_meta["pending_input"]["question"] == "Child question?"
    assert child_meta["pending_input"]["source_phase"] == "provider"
    assert (child_run_dir / "checkpoint.json").exists()
    assert child_parent["workflow_name"] == "parent_name"
    assert child_parent["run_id"] == parent_run_dir.name
    assert child_records[0]["workflow_name"] == "child_pause"
    assert child_records[0]["status"] == "awaiting_input"
    assert child_records[0]["last_event"] == {
        "tag": "question",
        "reason": "",
        "question": "Child question?",
        "handoff": None,
    }
    finalization = child_records[0]["finalization"]
    assert finalization["candidate_route"] == "question"
    assert finalization["final_route"] == "question"
    assert finalization["runtime_control"] is None
    assert finalization["provider_attributable"] is True
    assert finalization["provider_attempted"] is True
    assert finalization["producer_attempted"] is None
    assert finalization["verifier_attempted"] is None
    assert finalization["source_hook"] is None
    assert finalization["source_phase"] is None
    assert finalization["hook_route_redirects"] == []


def test_context_invoke_workflow_records_stable_child_metadata_shape_for_fatal_children(tmp_path: Path) -> None:
    _write_child_failing_workflow_package(tmp_path)
    _write_parent_failing_invoker_workflow_package(tmp_path)

    with pytest.raises(RuntimeError, match="child boom"):
        run_workflow_package(
            "parent_failing",
            provider=ScriptedLLMProvider(),
            options=_runner_options(tmp_path, task_id="subworkflow-fatal-task", message="Parent request"),
        )

    task_dir = tmp_path / ".botlane" / "tasks" / "subworkflow-fatal-task"
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


def test_context_invoke_workflow_supports_typed_child_input_and_output(tmp_path: Path) -> None:
    _write_child_typed_workflow_package(tmp_path, package_name="child_typed")
    _write_parent_typed_invoker_workflow_package(
        tmp_path,
        package_name="parent_typed",
        child_package_name="child_typed",
    )

    result = run_workflow_package(
        "parent_typed",
        provider=ScriptedLLMProvider(),
        options=_runner_options(tmp_path, task_id="subworkflow-typed-task", message="Parent request"),
    )

    task_dir = tmp_path / ".botlane" / "tasks" / "subworkflow-typed-task"
    parent_run_dir = next((task_dir / "wf_parent_typed" / "runs").iterdir())
    child_run_dir = next((task_dir / "wf_child_typed" / "runs").iterdir())
    parent_payload = json.loads((parent_run_dir / "summary.json").read_text(encoding="utf-8"))
    child_payload = json.loads((child_run_dir / "typed-child.json").read_text(encoding="utf-8"))
    child_records = [
        json.loads(line)
        for line in (parent_run_dir / "children.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    child_meta = json.loads((child_run_dir / "run.json").read_text(encoding="utf-8"))

    assert result.terminal == "FINISH"
    assert parent_payload["child_workflow"] == "child_typed"
    assert parent_payload["child_status"] == "success"
    assert parent_payload["child_output"] == {"summary": "alpha:strict:2", "ready": True}
    assert parent_payload["child_output_metadata"] == {}
    assert parent_payload["child_artifacts"] == {
        "child_dump": str(child_run_dir / "typed-child.json"),
        "plan.child_dump": str(child_run_dir / "typed-child.json"),
    }
    assert parent_payload["child_artifacts_alias"] == parent_payload["child_artifacts"]
    assert parent_payload["child_metadata"]["typed_output"]["declared"] is True
    assert parent_payload["child_metadata"]["typed_output"]["available"] is True
    assert parent_payload["child_metadata"]["typed_output"]["validation_error"] is None
    assert child_payload == {"topic": "alpha", "urgency": 2, "mode": "strict"}
    assert child_meta["workflow_input"] == {"topic": "alpha", "urgency": 2}
    assert child_meta["typed_output"]["available"] is True
    assert child_meta["typed_output"]["validation_error"] is None
    assert len(child_records) == 1
    assert child_records[0]["output"] == {"summary": "alpha:strict:2", "ready": True}
    assert child_records[0]["output_metadata"] == {}
    assert child_records[0]["output_artifacts"] == {
        "child_dump": str(child_run_dir / "typed-child.json"),
        "plan.child_dump": str(child_run_dir / "typed-child.json"),
    }
    assert child_records[0]["artifacts"] == child_records[0]["output_artifacts"]
    assert child_records[0]["metadata"]["typed_output"]["available"] is True


def test_context_invoke_workflow_records_typed_child_output_validation_failures(tmp_path: Path) -> None:
    _write_child_typed_workflow_package(tmp_path, package_name="child_typed_invalid", invalid_output=True)
    _write_parent_typed_invoker_workflow_package(
        tmp_path,
        package_name="parent_typed_invalid",
        child_package_name="child_typed_invalid",
    )

    result = run_workflow_package(
        "parent_typed_invalid",
        provider=ScriptedLLMProvider(),
        options=_runner_options(tmp_path, task_id="subworkflow-typed-invalid-task", message="Parent request"),
    )

    task_dir = tmp_path / ".botlane" / "tasks" / "subworkflow-typed-invalid-task"
    parent_run_dir = next((task_dir / "wf_parent_typed_invalid" / "runs").iterdir())
    child_run_dir = next((task_dir / "wf_child_typed_invalid" / "runs").iterdir())
    parent_payload = json.loads((parent_run_dir / "summary.json").read_text(encoding="utf-8"))
    child_records = [
        json.loads(line)
        for line in (parent_run_dir / "children.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    child_meta = json.loads((child_run_dir / "run.json").read_text(encoding="utf-8"))

    assert result.terminal == "FINISH"
    assert parent_payload["child_workflow"] == "child_typed_invalid"
    assert parent_payload["child_status"] == "success"
    assert parent_payload["child_output"] is None
    assert child_meta["workflow_input"] == {"topic": "alpha", "urgency": 2}
    assert parent_payload["child_metadata"]["typed_output"]["declared"] is True
    assert parent_payload["child_metadata"]["typed_output"]["available"] is False
    assert "typed output validation failed" in parent_payload["child_metadata"]["typed_output"]["validation_error"]
    assert child_meta["typed_output"]["available"] is False
    assert "typed output validation failed" in child_meta["typed_output"]["validation_error"]
    assert len(child_records) == 1
    assert child_records[0]["output"] is None
    assert child_records[0]["metadata"]["typed_output"]["available"] is False
    assert "typed output validation failed" in child_records[0]["metadata"]["typed_output"]["validation_error"]


def test_temporary_workspace_workflow_packages_keep_ctx_only_python_step_handlers(tmp_path: Path) -> None:
    _write_parent_class_invoker_workflow_package(tmp_path)
    _write_parent_composition_helper_workflow_package(tmp_path)
    _write_parent_name_invoker_workflow_package(tmp_path)
    _write_child_failing_workflow_package(tmp_path)
    _write_child_typed_workflow_package(tmp_path, package_name="child_typed_ctx_contract")
    _write_parent_typed_invoker_workflow_package(
        tmp_path,
        package_name="parent_typed_ctx_contract",
        child_package_name="child_typed_ctx_contract",
    )

    expected_signatures = {
        "parent_class": "def launch(ctx):",
        "parent_composed": "def launch(ctx):",
        "parent_name": "def wait(ctx):",
        "child_failing": "def explode(ctx):",
        "child_typed_ctx_contract": "def plan(ctx):",
        "parent_typed_ctx_contract": "def launch(ctx):",
    }

    for package_name, signature in expected_signatures.items():
        source = (tmp_path / "workflows" / package_name / "workflow.py").read_text(encoding="utf-8")
        assert signature in source
        assert "(state, ctx)" not in source

    typed_child_source = (tmp_path / "workflows" / "child_typed_ctx_contract" / "workflow.py").read_text(encoding="utf-8")
    assert "def build_output(state: State, ctx):" in typed_child_source


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
    task_dir = root / ".botlane" / "tasks" / task_id
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


def _write_task_operation_record(
    root: Path,
    *,
    task_id: str,
    created_at: str,
    updated_at: str,
    request_text: str,
    messages: list[tuple[str, str]],
) -> Path:
    task_dir = root / ".botlane" / "tasks" / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "request.md").write_text(request_text, encoding="utf-8")
    (task_dir / "messages.jsonl").write_text(
        "".join(
            json.dumps({"message": message, "ts": ts}, sort_keys=True) + "\n"
            for ts, message in messages
        ),
        encoding="utf-8",
    )
    (task_dir / "task.json").write_text(
        json.dumps(
            {
                "created_at": created_at,
                "messages_file": str(Path(".botlane") / "tasks" / task_id / "messages.jsonl"),
                "request_file": str(Path(".botlane") / "tasks" / task_id / "request.md"),
                "request_updated_at": messages[-1][0] if messages else updated_at,
                "task_id": task_id,
                "updated_at": updated_at,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return task_dir


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

from botlane import FINISH, Workflow, python_step


class {class_name}(Workflow):
    name = "{workflow_name}"

    class State(BaseModel):
        done: bool = False

    @python_step(name="start", routes={{"done": FINISH}})
    def start(ctx):
        ctx.state = ctx.state.model_copy(update={{"done": True}})
        return "done"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return package_dir / "workflow.py"


def test_compile_workflow_recompiles_when_source_changes(tmp_path: Path) -> None:
    _write_system_workflow_package(tmp_path, "compile_cache_demo", "CompileCacheWorkflow")

    first_resolved = resolve_workflow_reference(tmp_path, "compile_cache_demo")
    first = compile_workflow(first_resolved.workflow_cls)

    workflow_file = tmp_path / "workflows" / "compile_cache_demo" / "workflow.py"
    workflow_file.write_text(
        """
from __future__ import annotations

from pydantic import BaseModel

from botlane import FINISH, Workflow, python_step


class CompileCacheWorkflow(Workflow):
    name = "compile_cache_demo"

    class State(BaseModel):
        done: bool = False
        archived: bool = False

    @python_step(name="start", routes={"done": FINISH})
    def start(ctx):
        ctx.state = ctx.state.model_copy(update={"done": True})
        return "done"

    @python_step(name="archive", routes={"done": FINISH})
    def archive(ctx):
        ctx.state = ctx.state.model_copy(update={"archived": True})
        return "done"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    _clear_workflow_modules()

    second_resolved = resolve_workflow_reference(tmp_path, "compile_cache_demo")
    second = compile_workflow(second_resolved.workflow_cls)

    assert first is not second
    assert first.source_hash != second.source_hash
    assert first.topology_hash != second.topology_hash


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

from botlane import Prompt, Raw, Workflow, step


class {class_name}(Workflow):
    name = "{workflow_name}"

    class State(BaseModel):
        note: str = ""

    context_dump = Raw("context_dump", path="{{run_folder}}/context.json")
    workflow_dump = Raw("workflow_dump", path="{{workflow_folder}}/workflow-note.txt")
    ask = step(
        prompt=Prompt.file("prompts/ask.md"),
        writes=[context_dump, workflow_dump],
    )
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return package_dir / "workflow.py"


def _write_pause_resume_workflow_package(
    root: Path,
    workflow_name: str,
    class_name: str,
    *,
    export_parameters: bool = False,
    parameters_source: str | None = None,
) -> Path:
    package_dir = root / "workflows" / workflow_name
    package_dir.mkdir(parents=True, exist_ok=True)
    (root / "workflows" / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    init_lines = [f"from .workflow import {class_name}"]
    exports = [class_name]
    if export_parameters:
        init_lines.append("from .params import Params")
        exports.append("Params")
    init_lines.append(f"__all__ = {exports!r}")
    (package_dir / "__init__.py").write_text("\n".join(init_lines) + "\n", encoding="utf-8")
    (package_dir / "workflow.toml").write_text(f'name = "{workflow_name}"\n', encoding="utf-8")
    (package_dir / "prompts").mkdir(exist_ok=True)
    (package_dir / "assets").mkdir(exist_ok=True)
    (package_dir / "prompts" / "ask.md").write_text("package prompt\n", encoding="utf-8")
    if export_parameters:
        source = parameters_source or """
from pydantic import BaseModel


class Params(BaseModel):
    mode: str = "strict"
""".strip()
        (package_dir / "params.py").write_text(source + "\n", encoding="utf-8")
    (package_dir / "workflow.py").write_text(
        f"""
from __future__ import annotations

from pydantic import BaseModel

from botlane import AWAIT_INPUT, FINISH, Prompt, Raw, Workflow, step


class {class_name}(Workflow):
    name = "{workflow_name}"

    class State(BaseModel):
        answer: str | None = None

    context_dump = Raw("context_dump", path="{{run_folder}}/context.json")
    ask = step(
        prompt=Prompt.file("prompts/ask.md"),
        writes=[context_dump],
        routes={{"answered": FINISH, "question": AWAIT_INPUT}},
    )
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return package_dir / "workflow.py"


def _write_typed_input_pause_resume_workflow_package(
    root: Path,
    workflow_name: str,
    class_name: str,
) -> Path:
    package_dir = root / "workflows" / workflow_name
    package_dir.mkdir(parents=True, exist_ok=True)
    (root / "workflows" / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    (package_dir / "__init__.py").write_text(
        f"from .workflow import {class_name}\n__all__ = ['{class_name}']\n",
        encoding="utf-8",
    )
    (package_dir / "workflow.toml").write_text(f'name = "{workflow_name}"\n', encoding="utf-8")
    (package_dir / "prompts").mkdir(exist_ok=True)
    (package_dir / "assets").mkdir(exist_ok=True)
    (package_dir / "prompts" / "ask.md").write_text("package prompt\n", encoding="utf-8")
    (package_dir / "workflow.py").write_text(
        f"""
from __future__ import annotations

from pydantic import BaseModel

from botlane import AWAIT_INPUT, FINISH, Prompt, Raw, Workflow, step


class {class_name}(Workflow):
    name = "{workflow_name}"

    class Input(BaseModel):
        topic: str

    class State(BaseModel):
        answer: str | None = None

    context_dump = Raw("context_dump", path="{{run_folder}}/context.json")
    ask = step(
        prompt=Prompt.file("prompts/ask.md"),
        writes=[context_dump],
        routes={{"answered": FINISH, "question": AWAIT_INPUT}},
    )
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return package_dir / "workflow.py"


def _write_blocked_route_workflow_package(root: Path, workflow_name: str, class_name: str) -> Path:
    package_dir = root / "workflows" / workflow_name
    package_dir.mkdir(parents=True, exist_ok=True)
    (root / "workflows" / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    (package_dir / "__init__.py").write_text(
        f"from .workflow import {class_name}\n__all__ = ['{class_name}']\n",
        encoding="utf-8",
    )
    (package_dir / "workflow.toml").write_text(f'name = "{workflow_name}"\n', encoding="utf-8")
    (package_dir / "prompts").mkdir(exist_ok=True)
    (package_dir / "prompts" / "ask.md").write_text("package prompt\n", encoding="utf-8")
    (package_dir / "workflow.py").write_text(
        f"""
from __future__ import annotations

from pydantic import BaseModel

from botlane import AWAIT_INPUT, Prompt, Workflow, step


class {class_name}(Workflow):
    name = "{workflow_name}"

    class State(BaseModel):
        pass

    ask = step(
        prompt=Prompt.file("prompts/ask.md"),
        routes={{"blocked": AWAIT_INPUT}},
    )
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
        "from .workflow import ChildWorkflow\nfrom .params import Params\n__all__ = ['ChildWorkflow', 'Params']\n",
        encoding="utf-8",
    )
    (package_dir / "workflow.toml").write_text('name = "child_success"\n', encoding="utf-8")
    (package_dir / "prompts").mkdir(exist_ok=True)
    (package_dir / "assets").mkdir(exist_ok=True)
    (package_dir / "prompts" / "ask.md").write_text("child prompt\n", encoding="utf-8")
    (package_dir / "params.py").write_text(
        """
from pydantic import BaseModel


class Params(BaseModel):
    mode: str = "strict"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (package_dir / "workflow.py").write_text(
        """
from __future__ import annotations

from pydantic import BaseModel

from botlane import Prompt, Raw, Session, Workflow, step


class ChildWorkflow(Workflow):
    name = "child_success"

    class State(BaseModel):
        note: str = ""

    main = Session(open=True)
    child_dump = Raw("child_dump", path="{run_folder}/child.json")
    ask = step(prompt=Prompt.file("prompts/ask.md"), session=main, writes=[child_dump])
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

from botlane import Event, FINISH, Session, Workflow, python_step
from workflows.child_success import ChildWorkflow


class ParentClassWorkflow(Workflow):
    name = "parent_class"

    class State(BaseModel):
        finished: bool = False

    main = Session()

    @python_step(name="launch", routes={"done": FINISH})
    def launch(ctx):
        ctx.open_session("main")
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

        ctx.state = ctx.state.model_copy(update={"finished": True})
        return Event("done")
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

from botlane import Event, FINISH, Workflow, python_step
from botlane.stdlib import adopt_child_artifacts, require_child_workflow_result, run_child_workflow


class ParentCompositionHelperWorkflow(Workflow):
    name = "parent_composed"

    class State(BaseModel):
        finished: bool = False

    @python_step(name="launch", routes={"done": FINISH})
    def launch(ctx):
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

        ctx.state = ctx.state.model_copy(update={"finished": True})
        return Event("done")
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _write_child_pause_workflow_package(root: Path) -> None:
    package_dir = root / "workflows" / "child_pause"
    package_dir.mkdir(parents=True, exist_ok=True)
    (root / "workflows" / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    (package_dir / "__init__.py").write_text(
        "from .workflow import ChildPauseWorkflow\nfrom .params import Params\n__all__ = ['ChildPauseWorkflow', 'Params']\n",
        encoding="utf-8",
    )
    (package_dir / "workflow.toml").write_text('name = "child_pause"\n', encoding="utf-8")
    (package_dir / "prompts").mkdir(exist_ok=True)
    (package_dir / "assets").mkdir(exist_ok=True)
    (package_dir / "prompts" / "ask.md").write_text("child pause prompt\n", encoding="utf-8")
    (package_dir / "params.py").write_text(
        """
from pydantic import BaseModel


class Params(BaseModel):
    mode: str = "strict"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (package_dir / "workflow.py").write_text(
        """
from __future__ import annotations

from pydantic import BaseModel

from botlane import AWAIT_INPUT, Prompt, Raw, Session, Workflow, step


class ChildPauseWorkflow(Workflow):
    name = "child_pause"

    class State(BaseModel):
        note: str = ""

    main = Session(open=True)
    child_dump = Raw("child_dump", path="{run_folder}/child.json")
    ask = step(
        prompt=Prompt.file("prompts/ask.md"),
        session=main,
        writes=[child_dump],
        routes={"question": AWAIT_INPUT},
    )
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

from botlane import AWAIT_INPUT, Event, FINISH, Workflow, python_step


class ParentNameWorkflow(Workflow):
    name = "parent_name"

    class State(BaseModel):
        finished: bool = False

    @python_step(name="wait", routes={"question": AWAIT_INPUT, "done": FINISH})
    def wait(ctx):
        if ctx.answer is None:
            return Event("question", question="Parent question?")
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

        ctx.state = ctx.state.model_copy(update={"finished": True})
        return Event("done")
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

from botlane import FINISH, Workflow, python_step


class ChildFailingWorkflow(Workflow):
    name = "child_failing"

    class State(BaseModel):
        note: str = ""

    @python_step(name="explode", routes={"done": FINISH})
    def explode(ctx):
        raise RuntimeError("child boom")
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _write_child_typed_workflow_package(root: Path, *, package_name: str, invalid_output: bool = False) -> None:
    package_dir = root / "workflows" / package_name
    package_dir.mkdir(parents=True, exist_ok=True)
    (root / "workflows" / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    (package_dir / "__init__.py").write_text(
        "from .workflow import ChildTypedWorkflow\nfrom .params import Params\n__all__ = ['ChildTypedWorkflow', 'Params']\n",
        encoding="utf-8",
    )
    (package_dir / "workflow.toml").write_text(f'name = "{package_name}"\n', encoding="utf-8")
    (package_dir / "prompts").mkdir(exist_ok=True)
    (package_dir / "assets").mkdir(exist_ok=True)
    (package_dir / "params.py").write_text(
        """
from pydantic import BaseModel


class Params(BaseModel):
    mode: str = "strict"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    output_expr = (
        "{'summary': f\"{ctx.input.topic}:{ctx.params.mode}:{ctx.input.urgency}\", 'ready': 'yes'}"
        if invalid_output
        else "ChildTypedWorkflow.Output(summary=f\"{ctx.input.topic}:{ctx.params.mode}:{ctx.input.urgency}\", ready=True)"
    )
    (package_dir / "workflow.py").write_text(
        f"""
from __future__ import annotations

import json

from pydantic import BaseModel

from botlane import Event, FINISH, Raw, Workflow, python_step


class ChildTypedWorkflow(Workflow):
    name = "{package_name}"

    class State(BaseModel):
        topic: str = ""
        mode: str = ""

    class Input(BaseModel):
        topic: str
        urgency: int = 1

    class Output(BaseModel):
        summary: str
        ready: bool

    child_dump = Raw("child_dump", path="{{run_folder}}/typed-child.json")

    @python_step(name="plan", writes=[child_dump], routes={{"done": FINISH}})
    def plan(ctx):
        payload = {{
            "topic": ctx.input.topic,
            "urgency": ctx.input.urgency,
            "mode": ctx.params.mode,
        }}
        (ctx.run_folder / "typed-child.json").write_text(json.dumps(payload), encoding="utf-8")

        ctx.state = ctx.state.model_copy(update={{"topic": ctx.input.topic, "mode": ctx.params.mode}})
        return Event("done")

    @staticmethod
    def build_output(state: State, ctx):
        return {output_expr}
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _write_parent_typed_invoker_workflow_package(root: Path, *, package_name: str, child_package_name: str) -> None:
    package_dir = root / "workflows" / package_name
    package_dir.mkdir(parents=True, exist_ok=True)
    (root / "workflows" / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    (package_dir / "__init__.py").write_text(
        "from .workflow import ParentTypedInvokerWorkflow\n__all__ = ['ParentTypedInvokerWorkflow']\n",
        encoding="utf-8",
    )
    (package_dir / "workflow.toml").write_text(f'name = "{package_name}"\n', encoding="utf-8")
    (package_dir / "prompts").mkdir(exist_ok=True)
    (package_dir / "assets").mkdir(exist_ok=True)
    (package_dir / "workflow.py").write_text(
        f"""
from __future__ import annotations

import json

from pydantic import BaseModel

from botlane import Event, FINISH, Workflow, python_step
from workflows.{child_package_name} import ChildTypedWorkflow


class ParentTypedInvokerWorkflow(Workflow):
    name = "{package_name}"

    class State(BaseModel):
        finished: bool = False

    @python_step(name="launch", routes={{"done": FINISH}})
    def launch(ctx):
        child = ctx.invoke_workflow(
            ChildTypedWorkflow,
            message="Run typed child",
            parameters={{"mode": "strict"}},
            input=ChildTypedWorkflow.Input(topic="alpha", urgency=2),
        )
        payload = {{
            "child_workflow": child.workflow_name,
            "child_status": child.status,
            "child_output": None if child.output is None else child.output.model_dump(mode="python"),
            "child_output_metadata": child.output_metadata,
            "child_artifacts": {{name: str(path) for name, path in child.output_artifacts.items()}},
            "child_artifacts_alias": {{name: str(path) for name, path in child.artifacts.items()}},
            "child_metadata": child.metadata,
        }}
        (ctx.run_folder / "summary.json").write_text(json.dumps(payload), encoding="utf-8")

        ctx.state = ctx.state.model_copy(update={{"finished": True}})
        return Event("done")
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

from botlane import Event, FINISH, Workflow, python_step


class ParentFailingWorkflow(Workflow):
    name = "parent_failing"

    class State(BaseModel):
        note: str = ""

    @python_step(name="launch", routes={"done": FINISH})
    def launch(ctx):
        ctx.invoke_workflow("child_failing", message="Run child fatal")
        return Event("done")
""".strip()
        + "\n",
        encoding="utf-8",
    )
