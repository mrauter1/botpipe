from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import BaseModel

import autoloop.simple as simple
import autoloop.sdk as sdk_module
from autoloop import (
    AWAIT_INPUT,
    FAIL,
    FINISH,
    ArtifactMap,
    Autoloop,
    InputRequest,
    InputRequired,
    InputResponseValidationError,
    RetentionPolicy,
    ResultArtifact,
    SDKDebugInfo,
    SDKExecutionError,
    StaticInput,
    TooManyPauses,
    WorkflowResult,
    WorkflowParameterError,
    WorkflowInputError,
)
from autoloop.core.primitives import Event, Outcome, RequestInput
from autoloop.core.routes import Route
from autoloop.core.providers.fake import ScriptedLLMProvider
from autoloop.core.steps import ChildWorkflowStep, PythonStep
from autoloop.runtime.config import GitTrackingRuntimeConfig, RuntimeConfig


class _SDKApprovalInput(BaseModel):
    approved: bool


class _SDKTypedInput(BaseModel):
    topic: str


class _SDKArtifactPayload(BaseModel):
    message: str
    topic: str


class _SDKResultState(BaseModel):
    observed: str = "ok"


class _SDKPauseWorkflow(simple.Workflow):
    class Input(BaseModel):
        topic: str

    class State(BaseModel):
        approved: bool | None = None

    snapshot = simple.Json("snapshot")

    @simple.python_step(writes=[snapshot], routes={"done": FINISH, "question": AWAIT_INPUT})
    def approve(ctx):
        if ctx.input_response is None:
            ctx.artifacts.snapshot.write_json(
                {
                    "message": ctx.message,
                    "input_message": ctx.input.message,
                    "topic": ctx.input.topic,
                    "dump": ctx.input.model_dump(mode="python"),
                    "input_fields": None if ctx.input_fields is None else ctx.input_fields.model_dump(mode="python"),
                }
            )
            return RequestInput(
                "Approve the release?",
                reason="Need operator approval.",
                best_supposition='{"approved": true}',
                input_schema=_SDKApprovalInput,
            )
        approved = ctx.input_response.approved if isinstance(ctx.input_response, _SDKApprovalInput) else False
        ctx.state = ctx.state.model_copy(update={"approved": approved})
        return Event("done")


class _SDKProviderQuestionWorkflow(simple.Workflow):
    class State(BaseModel):
        pass

    review = simple.step(
        "Review the request.",
        name="review",
        routes={"done": FINISH, "question": AWAIT_INPUT},
    )


class _SDKNoMessageWorkflow(simple.Workflow):
    class State(BaseModel):
        observed_message: str | None = None
        observed_input_message: str | None = None

    empty_message_snapshot = simple.Text(
        "empty_message_snapshot",
        path="{workflow_folder}/capture/{input.message}snapshot.txt",
    )

    @simple.python_step(writes=[empty_message_snapshot], routes={"done": FINISH})
    def capture(ctx):
        ctx.state = ctx.state.model_copy(
            update={
                "observed_message": ctx.message,
                "observed_input_message": ctx.input.message,
            }
        )
        ctx.artifacts.empty_message_snapshot.write_text("captured")
        return Event("done")


class _SDKParamsWorkflow(simple.Workflow):
    class Params(BaseModel):
        mode: str
        reviewers: list[str] = []

    class State(BaseModel):
        observed_mode: str | None = None

    params_snapshot = simple.Json("params_snapshot")

    @simple.python_step(writes=[params_snapshot], routes={"done": FINISH})
    def capture(ctx):
        ctx.state = ctx.state.model_copy(update={"observed_mode": ctx.params.mode})
        ctx.artifacts.params_snapshot.write_json(
            {
                "params": ctx.params.model_dump(mode="python"),
                "workflow_params": ctx.workflow_params,
                "input_dump": ctx.input.model_dump(mode="python"),
                "has_mode_on_input": hasattr(ctx.input, "mode"),
            }
        )
        return Event("done")


class _SDKFailWorkflow(simple.Workflow):
    class State(BaseModel):
        failure_reason: str | None = None

    @simple.python_step(routes={"failed": FAIL})
    def reject(ctx):
        ctx.state = ctx.state.model_copy(update={"failure_reason": "Rejected by policy."})
        return Event("failed", reason="Rejected by policy.")


class _SDKSchemaArtifactWorkflow(simple.Workflow):
    class Input(BaseModel):
        topic: str

    artifact_snapshot = simple.Json("artifact_snapshot", schema=_SDKArtifactPayload)

    @simple.python_step(writes=[artifact_snapshot], routes={"done": FINISH})
    def capture(ctx):
        ctx.artifacts.artifact_snapshot.write_model(
            _SDKArtifactPayload(message=ctx.input.message or "", topic=ctx.input.topic)
        )
        return Event("done")


def _sdk_client(tmp_path: Path, provider: object) -> Autoloop:
    return Autoloop(
        root=tmp_path,
        provider=provider,
        state_dir=tmp_path / ".autoloop",
        runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False, commit_policy="off")),
    )


def _sdk_client_at_root(tmp_path: Path, provider: object, *, retention: RetentionPolicy | None = None) -> Autoloop:
    return Autoloop(
        root=tmp_path,
        provider=provider,
        state_dir=tmp_path / ".autoloop",
        runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False, commit_policy="off")),
        retention=retention,
    )


def test_sdk_run_handles_typed_input_pause_loop_and_debug_artifacts(tmp_path: Path) -> None:
    client = _sdk_client(tmp_path, ScriptedLLMProvider())
    seen: list[InputRequest] = []

    def approve(request: InputRequest):
        seen.append(request)
        assert request.pause_index == 0
        assert request.question == "Approve the release?"
        assert request.reason == "Need operator approval."
        assert request.best_supposition == '{"approved": true}'
        assert request.partial.status == "awaiting_input"
        assert request.input_schema_model is not None
        return {"approved": True}

    result = client.run(
        _SDKPauseWorkflow,
        "Ship the release safely.",
        _SDKPauseWorkflow.Input(topic="release"),
        on_input=approve,
    )

    assert result.ok is True
    assert result.status == "completed"
    assert result.state.approved is True
    assert len(seen) == 1
    assert len(result.handled_inputs) == 1
    assert result.handled_inputs[0].response == {"approved": True}
    assert isinstance(result.artifacts, ArtifactMap)
    assert isinstance(result.artifacts.snapshot, ResultArtifact)
    assert result.artifacts.snapshot.read_json() == {
        "message": "Ship the release safely.",
        "input_message": "Ship the release safely.",
        "topic": "release",
        "dump": {"message": "Ship the release safely.", "topic": "release"},
        "input_fields": {"topic": "release"},
    }
    assert result.debug.task_id.startswith("sdk-")
    assert "pause-workflow" in result.debug.task_id
    assert result.debug.run_id.startswith("run-")
    assert result.retention is not None
    assert result.retention.task_scratch_deleted is True
    assert result.debug.task_dir.exists() is False


def test_sdk_run_preserves_explicit_none_message(tmp_path: Path) -> None:
    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    result = client.run(_SDKNoMessageWorkflow, None)

    assert result.ok is True
    assert result.state.observed_message is None
    assert result.state.observed_input_message is None
    assert result.artifacts.empty_message_snapshot.path.name == "snapshot.txt"
    assert result.artifacts.empty_message_snapshot.read_text() == "captured"


def test_sdk_run_rejects_plain_dict_third_argument(tmp_path: Path) -> None:
    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    with pytest.raises(WorkflowInputError, match="received dict"):
        client.run(_SDKPauseWorkflow, "Ship it.", {"topic": "release"})  # type: ignore[arg-type]


def test_sdk_run_wraps_resume_schema_mismatch_as_input_response_validation_error(tmp_path: Path) -> None:
    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    with pytest.raises(InputResponseValidationError, match="Approve the release"):
        client.run(
            _SDKPauseWorkflow,
            "Ship the release safely.",
            _SDKPauseWorkflow.Input(topic="release"),
            on_input=StaticInput({"approved": "yes"}),
        )


def test_sdk_provider_questions_default_to_handler_presence(tmp_path: Path) -> None:
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="Need approval", tag="question", question="Proceed?"),
            Outcome(raw_output="Approved", tag="done"),
        ]
    )
    client = _sdk_client(tmp_path, provider)

    result = client.run(
        _SDKProviderQuestionWorkflow,
        "Review the rollout.",
        on_input=StaticInput("yes"),
    )

    assert result.status == "completed"
    assert len(result.handled_inputs) == 1
    assert result.handled_inputs[0].request.question == "Proceed?"


def test_sdk_run_suppresses_provider_questions_without_handler_by_default(tmp_path: Path) -> None:
    provider = ScriptedLLMProvider(
        llm_turns=[Outcome(raw_output="Need approval", tag="question", question="Proceed?")]
    )
    client = _sdk_client(tmp_path, provider)

    with pytest.raises(SDKExecutionError, match="question"):
        client.run(_SDKProviderQuestionWorkflow, "Review the rollout.")


def test_sdk_run_explicit_provider_questions_true_allows_handlerless_pause(tmp_path: Path) -> None:
    provider = ScriptedLLMProvider(
        llm_turns=[Outcome(raw_output="Need approval", tag="question", question="Proceed?")]
    )
    client = _sdk_client(tmp_path, provider)

    with pytest.raises(InputRequired, match="Proceed\\?") as exc_info:
        client.run(
            _SDKProviderQuestionWorkflow,
            "Review the rollout.",
            provider_questions=True,
        )
    assert exc_info.value.partial.retention is not None
    assert exc_info.value.partial.retention.task_scratch_retained is True
    assert exc_info.value.partial.debug.task_dir.exists()


def test_sdk_run_keeps_direct_request_input_when_provider_questions_disabled(tmp_path: Path) -> None:
    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    with pytest.raises(InputRequired, match="Approve the release") as exc_info:
        client.run(
            _SDKPauseWorkflow,
            "Ship the release safely.",
            _SDKPauseWorkflow.Input(topic="release"),
            provider_questions=False,
        )
    assert exc_info.value.partial.retention is not None
    assert exc_info.value.partial.retention.task_scratch_retained is True
    assert exc_info.value.partial.debug.task_dir.exists()


def test_sdk_run_explicit_provider_questions_false_suppresses_provider_questions_even_with_handler(tmp_path: Path) -> None:
    provider = ScriptedLLMProvider(
        llm_turns=[Outcome(raw_output="Need approval", tag="question", question="Proceed?")]
    )
    client = _sdk_client(tmp_path, provider)

    with pytest.raises(SDKExecutionError, match="question"):
        client.run(
            _SDKProviderQuestionWorkflow,
            "Review the rollout.",
            on_input=StaticInput("yes"),
            provider_questions=False,
        )


def test_sdk_llm_and_classify_delegate_to_operation_path(tmp_path: Path) -> None:
    provider = ScriptedLLMProvider(operation_turns=["summary", "incident"])
    client = _sdk_client(tmp_path, provider)

    summary = client.llm("Summarize this.")
    label = client.classify("Customer cannot check out.", choices=["incident", "question"])

    assert summary == "summary"
    assert label == "incident"
    assert [call.kind for call in provider.calls] == ["operation", "operation"]


@pytest.mark.parametrize(
    ("params_value", "expected"),
    [
        ({"mode": "strict", "reviewers": ["alice"]}, {"mode": "strict", "reviewers": ["alice"]}),
        (_SDKParamsWorkflow.Params(mode="focused", reviewers=["bob"]), {"mode": "focused", "reviewers": ["bob"]}),
    ],
)
def test_sdk_run_exposes_params_without_leaking_them_into_ctx_input(
    tmp_path: Path,
    params_value: BaseModel | dict[str, object],
    expected: dict[str, object],
) -> None:
    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    result = client.run(
        _SDKParamsWorkflow,
        "Check params handling.",
        params=params_value,
    )

    assert result.ok is True
    assert result.state.observed_mode == expected["mode"]
    assert result.artifacts.params_snapshot.read_json() == {
        "params": expected,
        "workflow_params": expected,
        "input_dump": {"message": "Check params handling."},
        "has_mode_on_input": False,
    }


def test_sdk_run_wraps_invalid_params_at_the_sdk_boundary(tmp_path: Path) -> None:
    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    with pytest.raises(WorkflowParameterError, match="unknown workflow parameter 'unknown'"):
        client.run(
            _SDKParamsWorkflow,
            "Check params handling.",
            params={"mode": "strict", "unknown": "value"},
        )


def test_sdk_run_maps_failed_terminal_to_failed_result_status(tmp_path: Path) -> None:
    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    result = client.run(_SDKFailWorkflow, "Reject this request.")

    assert result.ok is False
    assert result.status == "failed"
    assert result.terminal == FAIL
    assert result.state.failure_reason == "Rejected by policy."
    assert result.last_event is not None
    assert result.last_event.tag == "failed"
    assert result.retention is not None
    assert result.retention.task_scratch_retained is True
    assert result.debug.task_dir.exists()


def test_sdk_step_executes_synthetic_simple_operation_workflow(tmp_path: Path) -> None:
    provider = ScriptedLLMProvider(operation_turns=["summary"])
    client = _sdk_client(tmp_path, provider)

    result = client.step(
        simple.llm.step(prompt="Summarize the request.", name="summarize"),
        "Summarize the incident.",
    )

    assert result.ok is True
    assert result.status == "completed"
    assert result.route == "done"
    assert result.value is None
    assert result.workflow_result.status == "completed"


def test_sdk_step_supports_core_python_step_instances(tmp_path: Path) -> None:
    snapshot = simple.Json("snapshot")

    def handler(ctx):
        ctx.artifacts.snapshot.write_json(ctx.input.model_dump(mode="python"))
        return Event("done")

    declaration = PythonStep(
        name="capture",
        handler=handler,
        writes={"snapshot": snapshot.materialize("capture")},
    )
    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    result = client.step(
        declaration,
        "Handle the typed request.",
        _SDKTypedInput(topic="release"),
    )

    assert result.ok is True
    assert result.artifacts.snapshot.read_json() == {"message": "Handle the typed request.", "topic": "release"}


def test_sdk_step_supports_core_python_steps_with_explicit_terminal_route_metadata(tmp_path: Path) -> None:
    def handler(_ctx):
        return Event("approved")

    declaration = PythonStep(
        name="approve",
        handler=handler,
        route_metadata={"approved": Route(summary="approved cleanly")},
    )
    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    result = client.step(declaration, "Approve the rollout.")

    assert result.ok is True
    assert result.status == "completed"
    assert result.route == "approved"
    assert result.value is None
    assert result.workflow_result.status == "completed"


def test_sdk_step_supports_directly_resolvable_strict_child_workflow_steps(tmp_path: Path) -> None:
    class ChildWorkflow(simple.Workflow):
        class State(BaseModel):
            observed_message: str | None = None

        @simple.python_step(routes={"done": FINISH})
        def capture(ctx):
            ctx.state = ctx.state.model_copy(update={"observed_message": ctx.message})
            return Event("done")

    declaration = ChildWorkflowStep(
        name="launch",
        workflow=ChildWorkflow,
        message="{ctx.message}",
    )
    client = Autoloop(
        root=tmp_path,
        provider=ScriptedLLMProvider(),
        state_dir=tmp_path / ".autoloop",
        runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False, commit_policy="off")),
    )

    result = client.step(declaration, "Run the child workflow.")

    assert result.ok is True
    assert result.route == "done"
    assert result.workflow_result.status == "completed"


def test_sdk_step_rejects_unresolved_strict_child_workflow_steps(tmp_path: Path) -> None:
    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    with pytest.raises(SDKExecutionError, match=r"child workflow reference could not be resolved for client\.step"):
        client.step(
            ChildWorkflowStep(name="launch", workflow="missing_child_workflow"),
            "Run the child workflow.",
        )


def test_sdk_step_rejects_worklist_scoped_strict_child_workflow_steps(tmp_path: Path) -> None:
    class ChildWorkflow(simple.Workflow):
        @simple.python_step(routes={"done": FINISH})
        def capture(_ctx):
            return Event("done")

    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    with pytest.raises(SDKExecutionError, match="worklist-scoped"):
        client.step(
            ChildWorkflowStep(name="launch", workflow=ChildWorkflow, scope="items"),
            "Run the child workflow.",
        )


def test_sdk_step_rejects_branch_group_declarations(tmp_path: Path) -> None:
    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    with pytest.raises(SDKExecutionError, match="branch-group"):
        client.step(
            simple.parallel(
                name="review",
                branches={"one": simple.step("Review one item.", name="review_one")},
            ),
            "Review the rollout.",
        )


def test_sdk_sync_entrypoints_normalize_active_event_loop_failures(tmp_path: Path) -> None:
    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    async def invoke() -> None:
        for call in (
            lambda: client.run(_SDKPauseWorkflow, "Ship it.", _SDKPauseWorkflow.Input(topic="release")),
            lambda: client.step(simple.python_step(lambda _ctx: Event("done"), name="noop"), "Ship it."),
        ):
            with pytest.raises(SDKExecutionError, match="active event loop"):
                call()

    asyncio.run(invoke())


def test_sdk_constructor_rejects_unknown_provider_name(tmp_path: Path) -> None:
    with pytest.raises(SDKExecutionError, match="could not resolve SDK provider"):
        Autoloop(root=tmp_path, provider="not-a-provider")


def test_sdk_run_exposes_result_artifact_metadata_and_helpers(tmp_path: Path) -> None:
    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    result = client.run(
        _SDKSchemaArtifactWorkflow,
        "Ship the release safely.",
        _SDKSchemaArtifactWorkflow.Input(topic="release"),
    )

    artifact = result.artifact("artifact_snapshot")

    assert isinstance(artifact, ResultArtifact)
    assert artifact.kind == "json"
    assert artifact.schema is _SDKArtifactPayload
    assert artifact.source_path is not None
    assert artifact.source_path != artifact.path
    assert artifact.promoted is True
    assert artifact.required is False
    assert artifact.qualified_name == "capture.artifact_snapshot"
    assert artifact.read_json() == {"message": "Ship the release safely.", "topic": "release"}
    assert artifact.read_model() == _SDKArtifactPayload(message="Ship the release safely.", topic="release")

    materialized = artifact.materialize(tmp_path / "materialized" / "artifact_snapshot.json")

    assert materialized.read_text(encoding="utf-8") == artifact.read_text()


def test_result_artifact_read_model_rejects_missing_or_non_model_schema(tmp_path: Path) -> None:
    path = tmp_path / "artifact_snapshot.json"
    path.write_text('{"message":"Ship the release safely.","topic":"release"}\n', encoding="utf-8")

    without_schema = ResultArtifact(name="artifact_snapshot", path=path, kind="json")
    with_dict_schema = ResultArtifact(name="artifact_snapshot", path=path, kind="json", schema={"type": "object"})

    with pytest.raises(TypeError, match="artifact has no schema"):
        without_schema.read_model()

    with pytest.raises(TypeError, match="supports Pydantic BaseModel schemas"):
        with_dict_schema.read_model()


def test_sdk_step_result_value_stays_none_even_when_workflow_result_has_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _sdk_client(tmp_path, ScriptedLLMProvider())
    fake_result = WorkflowResult(
        ok=True,
        status="completed",
        terminal=FINISH,
        state=_SDKResultState(),
        output={"summary": "should-not-leak"},
        output_validation_error=None,
        artifacts=ArtifactMap({}),
        history=(),
        last_event=Event("done"),
        last_outcome=None,
        handled_inputs=(),
        debug=SDKDebugInfo(
            task_id="sdk-noop",
            run_id="run-1",
            task_dir=tmp_path / ".autoloop" / "tasks" / "sdk-noop",
            workflow_dir=tmp_path / ".autoloop" / "tasks" / "sdk-noop" / "workflow",
            run_dir=tmp_path / ".autoloop" / "tasks" / "sdk-noop" / "runs" / "run-1",
            events_file=tmp_path / ".autoloop" / "tasks" / "sdk-noop" / "runs" / "run-1" / "events.jsonl",
            trace_file=None,
            checkpoint_file=None,
        ),
        retention=None,
    )
    monkeypatch.setattr(client, "run", lambda *args, **kwargs: fake_result)

    result = client.step(simple.python_step(lambda _ctx: Event("done"), name="noop"), "Ship it.")

    assert result.route == "done"
    assert result.status == "completed"
    assert result.workflow_result.output == {"summary": "should-not-leak"}
    assert result.value is None


def test_sdk_run_default_retention_promotes_task_local_declared_writes_and_keeps_workspace_writes(tmp_path: Path) -> None:
    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider())
    workspace_output = tmp_path / "workspace-output.txt"
    task_local_artifact = simple.Text("task_local", path="{task_folder}/exports/report.txt")
    workspace_artifact = simple.Text("workspace", path=workspace_output)

    class RetentionWorkflow(simple.Workflow):
        task_local = task_local_artifact
        workspace = workspace_artifact

        @simple.python_step(writes=[task_local_artifact, workspace_artifact], routes={"done": FINISH})
        def emit(ctx):
            ctx.artifacts.task_local.write_text("task-local")
            ctx.artifacts.workspace.write_text("workspace")
            (ctx.task_folder / "scratch.tmp").write_text("scratch", encoding="utf-8")
            return Event("done")

    result = client.run(RetentionWorkflow, "Retain declared writes.")

    assert result.retention is not None
    assert result.retention.task_scratch_deleted is True
    assert result.retention.promoted_artifacts == ("task_local",)
    assert result.debug.task_dir.exists() is False
    assert result.artifacts.task_local.promoted is True
    assert result.artifacts.task_local.read_text() == "task-local"
    assert result.artifacts.task_local.source_path is not None
    assert result.artifacts.task_local.source_path.parent.name == "exports"
    assert result.artifacts.workspace.promoted is False
    assert result.artifacts.workspace.path == workspace_output
    assert workspace_output.read_text(encoding="utf-8") == "workspace"


def test_sdk_step_default_retention_deletes_task_scratch_on_success(tmp_path: Path) -> None:
    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider())
    report = simple.Text("report", path="{task_folder}/report.txt")

    declaration = simple.python_step(
        lambda ctx: (ctx.artifacts.report.write_text("from-step"), Event("done"))[1],
        name="emit",
        writes=[report],
        routes={"done": FINISH},
    )

    result = client.step(declaration, "Step retention.")

    assert result.workflow_result.retention is not None
    assert result.workflow_result.retention.task_scratch_deleted is True
    assert result.workflow_result.debug.task_dir.exists() is False
    assert result.artifacts.report.read_text() == "from-step"


def test_sdk_run_retention_keep_all_and_ephemeral_modes(tmp_path: Path) -> None:
    workspace_output = tmp_path / "workspace-output.txt"
    task_local_artifact = simple.Text("task_local", path="{task_folder}/exports/report.txt")
    workspace_artifact = simple.Text("workspace", path=workspace_output)

    class RetentionWorkflow(simple.Workflow):
        task_local = task_local_artifact
        workspace = workspace_artifact

        @simple.python_step(writes=[task_local_artifact, workspace_artifact], routes={"done": FINISH})
        def emit(ctx):
            ctx.artifacts.task_local.write_text("task-local")
            ctx.artifacts.workspace.write_text("workspace")
            return Event("done")

    keep_all_client = _sdk_client_at_root(tmp_path / "keep_all", ScriptedLLMProvider(), retention=RetentionPolicy.keep_all())
    keep_all_result = keep_all_client.run(RetentionWorkflow, "Keep task scratch.")

    assert keep_all_result.retention is not None
    assert keep_all_result.retention.task_scratch_retained is True
    assert keep_all_result.debug.task_dir.exists()
    assert keep_all_result.artifacts.task_local.promoted is False
    assert keep_all_result.artifacts.task_local.path.exists()

    ephemeral_client = _sdk_client_at_root(tmp_path / "ephemeral", ScriptedLLMProvider(), retention=RetentionPolicy.ephemeral())
    ephemeral_result = ephemeral_client.run(RetentionWorkflow, "Delete task-local writes.")

    assert ephemeral_result.retention is not None
    assert ephemeral_result.retention.task_scratch_deleted is True
    assert "task_local" not in ephemeral_result.artifacts
    assert ephemeral_result.artifacts.workspace.path.exists()
    assert ephemeral_result.debug.task_dir.exists() is False


def test_sdk_run_too_many_pauses_keeps_task_scratch_by_default(tmp_path: Path) -> None:
    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    with pytest.raises(TooManyPauses, match="max_pauses=0") as exc_info:
        client.run(
            _SDKPauseWorkflow,
            "Ship the release safely.",
            _SDKPauseWorkflow.Input(topic="release"),
            on_input=StaticInput({"approved": True}),
            max_pauses=0,
        )

    assert exc_info.value.partial is not None
    assert exc_info.value.partial.retention is not None
    assert exc_info.value.partial.retention.task_scratch_retained is True
    assert exc_info.value.partial.debug.task_dir.exists()


def test_sdk_cleanup_only_targets_valid_completed_sdk_task_directories(tmp_path: Path) -> None:
    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider())
    tasks_root = tmp_path / ".autoloop" / "tasks"
    valid = tasks_root / "sdk-completed"
    failed = tasks_root / "sdk-failed"
    invalid = tasks_root / "manual-task"

    def seed_task(task_dir: Path, *, status: str, terminal: str, task_id: str | None = None) -> None:
        task_dir.mkdir(parents=True, exist_ok=True)
        sentinel = {
            "schema": "autoloop.sdk_task/v1",
            "generated_by": "autoloop.sdk",
            "task_id": task_id or task_dir.name,
            "created_at": "2026-05-01T00:00:00Z",
            "retention_mode": "delete_task_scratch",
        }
        (task_dir / ".autoloop-sdk-task.json").write_text(json.dumps(sentinel) + "\n", encoding="utf-8")
        run_dir = task_dir / "wf_test" / "runs" / "run-1"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.json").write_text(json.dumps({"status": status, "terminal": terminal}) + "\n", encoding="utf-8")

    seed_task(valid, status="completed", terminal=FINISH)
    seed_task(failed, status="failed", terminal=FAIL)
    invalid.mkdir(parents=True, exist_ok=True)

    dry_run = client.cleanup(dry_run=True)

    assert valid in dry_run.deleted
    assert failed in dry_run.skipped
    assert invalid in dry_run.skipped
    assert valid.exists()

    result = client.cleanup()

    assert valid in result.deleted
    assert valid.exists() is False
    assert failed.exists()
    assert invalid.exists()


def test_safe_delete_sdk_task_dir_refuses_unsafe_candidates(tmp_path: Path) -> None:
    tasks_root = tmp_path / ".autoloop" / "tasks"
    tasks_root.mkdir(parents=True, exist_ok=True)

    non_sdk = tasks_root / "manual-task"
    non_sdk.mkdir()
    (non_sdk / ".autoloop-sdk-task.json").write_text(
        json.dumps(
            {
                "schema": "autoloop.sdk_task/v1",
                "generated_by": "autoloop.sdk",
                "task_id": "manual-task",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(SDKExecutionError, match="refusing to delete"):
        sdk_module._safe_delete_sdk_task_dir(task_dir=non_sdk, task_id="manual-task", tasks_root=tasks_root)

    missing_sentinel = tasks_root / "sdk-missing"
    missing_sentinel.mkdir()
    with pytest.raises(SDKExecutionError, match="refusing to delete"):
        sdk_module._safe_delete_sdk_task_dir(task_dir=missing_sentinel, task_id="sdk-missing", tasks_root=tasks_root)

    mismatched = tasks_root / "sdk-mismatched"
    mismatched.mkdir()
    (mismatched / ".autoloop-sdk-task.json").write_text(
        json.dumps(
            {
                "schema": "autoloop.sdk_task/v1",
                "generated_by": "autoloop.sdk",
                "task_id": "sdk-other",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(SDKExecutionError, match="refusing to delete"):
        sdk_module._safe_delete_sdk_task_dir(task_dir=mismatched, task_id="sdk-mismatched", tasks_root=tasks_root)

    outside = tmp_path / "sdk-outside"
    outside.mkdir()
    (outside / ".autoloop-sdk-task.json").write_text(
        json.dumps(
            {
                "schema": "autoloop.sdk_task/v1",
                "generated_by": "autoloop.sdk",
                "task_id": "sdk-outside",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(SDKExecutionError, match="refusing to delete"):
        sdk_module._safe_delete_sdk_task_dir(task_dir=outside, task_id="sdk-outside", tasks_root=tasks_root)


def test_sdk_runtime_prompt_rendering_supports_input_and_ctx_message(tmp_path: Path) -> None:
    seen: list[str] = []

    def record_prompt(request):
        seen.append(request.prompt.text)
        return Outcome(raw_output="ok", tag="done")

    provider = ScriptedLLMProvider(llm_turns=[record_prompt, record_prompt])
    client = _sdk_client(tmp_path, provider)

    client.step(simple.step("Echo {input.message}", name="echo_input"), "hello")
    client.step(simple.step("Echo {ctx.message}", name="echo_ctx"), "hello")

    assert seen == ["Echo hello", "Echo hello"]
