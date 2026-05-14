from __future__ import annotations

import asyncio
import inspect
import json
import os
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import BaseModel

import botpipe
import botpipe.simple as simple
import botpipe.sdk as sdk_module
from botpipe import (
    AWAIT_INPUT,
    FAIL,
    FINISH,
    SELF,
    ArtifactMap,
    Botpipe,
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
from botpipe.policy import ModelEffort, Policy
from botpipe.core.primitives import Event, Outcome, RequestInput
from botpipe.core.prompts import Prompt
from botpipe.core.providers.retries import ProviderRetryPolicy
from botpipe.core.routes import Route
from botpipe.core.schema_registry import CHECKPOINT_SCHEMA
from botpipe.core.providers.fake import ScriptedLLMProvider
from botpipe.core.steps import ChildWorkflowStep, ProduceVerifyStep, PromptStep, PythonStep
from botpipe.runtime.config import GitTrackingRuntimeConfig, RuntimeConfig


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
        observed_input_is_none: bool | None = None

    empty_message_snapshot = simple.Text(
        "empty_message_snapshot",
        path="{{ workflow.folder }}/capture/{{ message }}snapshot.txt",
    )

    @simple.python_step(writes=[empty_message_snapshot], routes={"done": FINISH})
    def capture(ctx):
        ctx.state = ctx.state.model_copy(
            update={
                "observed_message": ctx.message,
                "observed_input_is_none": ctx.input is None,
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
                "input_is_none": ctx.input is None,
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
            _SDKArtifactPayload(message=ctx.message or "", topic=ctx.input.topic)
        )
        return Event("done")


class _SDKDeclaredWriteContextWorkflow(simple.Workflow):
    class Params(BaseModel):
        mode: str

    report = simple.Text("report", path="{{ workflow.folder }}/exports/{{ params.mode }}-{{ workflow_params.mode }}.txt")

    @simple.python_step(writes=[report], routes={"done": FINISH})
    def capture(ctx):
        ctx.artifacts.report.write_text(f"{ctx.params.mode}:{ctx.workflow_params['mode']}")
        return Event("done")


def _sdk_client(tmp_path: Path, provider: object) -> Botpipe:
    return Botpipe(
        workspace=tmp_path,
        provider=provider,
        state_dir=tmp_path / ".botpipe",
        runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False, commit_policy="off")),
    )


def _sdk_client_at_root(tmp_path: Path, provider: object, *, retention: RetentionPolicy | None = None) -> Botpipe:
    return Botpipe(
        workspace=tmp_path,
        provider=provider,
        state_dir=tmp_path / ".botpipe",
        runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False, commit_policy="off")),
        retention=retention,
    )


def test_sdk_result_artifacts_omit_branch_scoped_writes_without_crashing(tmp_path: Path) -> None:
    class BranchArtifactWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        assess = simple.fan_out(
            step=simple.python_step(
                lambda ctx: (ctx.artifacts.report.write_text(ctx.branch.name), Event("done"))[1],
                name="write_one",
                writes=[simple.Md("report", path="reports/{{ branch.name }}.md")],
                routes={"done": FINISH},
            ),
            branches={"security": {"area": "security"}, "cost": {"area": "cost"}},
        )

    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    result = client.run(BranchArtifactWorkflow, "Assess branches.")

    assert result.ok is True
    assert "report" not in result.artifacts


def test_sdk_result_artifacts_omit_worklist_selection_writes_without_crashing(tmp_path: Path) -> None:
    class WorklistArtifactWorkflow(simple.Workflow):
        gate = simple.Worklist.from_items(
            name="gate",
            items=({"id": "alpha", "title": "Alpha"},),
        )
        report = simple.Md("report", path="reports/{{ worklists.gate.current.id }}.md")

        @simple.python_step(writes=[report], routes={"done": FINISH})
        def write(ctx):
            ctx.artifacts.report.write_text("alpha")
            return Event("done")

    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider())

    result = client.run(WorklistArtifactWorkflow, "Write the current worklist report.")

    assert result.ok is True
    assert "report" not in result.artifacts


async def _collect_async_records(stream) -> list[dict[str, object]]:
    return [record async for record in stream]


def _seed_durable_run_record(
    root: Path,
    *,
    task_id: str = "task-42",
    workflow_name: str = "review",
    run_id: str = "run-1",
    status: str = "success",
) -> Path:
    task_dir = root / ".botpipe" / "tasks" / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.json").write_text(
        json.dumps(
            {
                "created_at": "2026-05-01T00:00:00+00:00",
                "task_id": task_id,
                "updated_at": "2026-05-01T00:00:00+00:00",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    run_dir = task_dir / f"wf_{workflow_name}" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "created_at": "2026-05-01T00:00:00+00:00",
                "run_id": run_id,
                "status": status,
                "task_id": task_id,
                "updated_at": "2026-05-01T00:01:00+00:00",
                "workflow_name": workflow_name,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "events.jsonl").write_text(json.dumps({"event_type": "seeded"}) + "\n", encoding="utf-8")
    (run_dir / "trace.jsonl").write_text(json.dumps({"event_type": "trace_seeded"}) + "\n", encoding="utf-8")
    return run_dir


def _write_minimal_checkpoint(run_dir: Path, *, stage: str, state: dict[str, object]) -> None:
    (run_dir / "checkpoint.json").write_text(
        json.dumps(
            {
                "schema": CHECKPOINT_SCHEMA,
                "stage": stage,
                "state": state,
                "session_bindings": {
                    "bindings": [],
                    "active_keys_by_slot": {},
                    "active_scopes": {},
                },
                "values": {},
                "step_states": {},
                "item_states": {},
                "step_item_states": {},
                "worklist_selections": {},
                "pending_handoffs": [],
                "pending_input": None,
                "pending_answer": None,
                "failure_context": None,
                "resume_cursor": None,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _update_run_metadata_fields(run_dir: Path, **fields: object) -> None:
    run_meta_file = run_dir / "run.json"
    payload = json.loads(run_meta_file.read_text(encoding="utf-8"))
    payload.update(fields)
    run_meta_file.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _write_step_started_trace(run_dir: Path, *, step_name: str = "approve", state: dict[str, object] | None = None) -> None:
    (run_dir / "trace.jsonl").write_text(
        json.dumps(
            {
                "event_type": "step_started",
                "sequence": 1,
                "step_name": step_name,
                "step_kind": "python",
                "step_execution_id": f"{step_name}#1",
                "state": {"approved": None} if state is None else state,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def test_sdk_entrypoint_signatures_are_frozen() -> None:
    def signature_items(method: object) -> tuple[tuple[str, inspect._ParameterKind], ...]:
        return tuple((name, parameter.kind) for name, parameter in inspect.signature(method).parameters.items())

    assert signature_items(Botpipe.run) == (
        ("self", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        ("workflow", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        ("message", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        ("policy", inspect.Parameter.KEYWORD_ONLY),
        ("input", inspect.Parameter.KEYWORD_ONLY),
        ("params", inspect.Parameter.KEYWORD_ONLY),
        ("on_input", inspect.Parameter.KEYWORD_ONLY),
        ("max_pauses", inspect.Parameter.KEYWORD_ONLY),
        ("max_steps", inspect.Parameter.KEYWORD_ONLY),
        ("provider_questions", inspect.Parameter.KEYWORD_ONLY),
        ("options", inspect.Parameter.KEYWORD_ONLY),
        ("retention", inspect.Parameter.KEYWORD_ONLY),
        ("on_event", inspect.Parameter.KEYWORD_ONLY),
    )
    assert signature_items(Botpipe.step) == (
        ("self", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        ("step_def", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        ("message", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        ("policy", inspect.Parameter.KEYWORD_ONLY),
        ("input", inspect.Parameter.KEYWORD_ONLY),
        ("params", inspect.Parameter.KEYWORD_ONLY),
        ("routes", inspect.Parameter.KEYWORD_ONLY),
        ("on_input", inspect.Parameter.KEYWORD_ONLY),
        ("max_pauses", inspect.Parameter.KEYWORD_ONLY),
        ("max_steps", inspect.Parameter.KEYWORD_ONLY),
        ("provider_questions", inspect.Parameter.KEYWORD_ONLY),
        ("retention", inspect.Parameter.KEYWORD_ONLY),
    )
    assert signature_items(Botpipe.prompt_step) == (
        ("self", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        ("prompt", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        ("message", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        ("input", inspect.Parameter.KEYWORD_ONLY),
        ("name", inspect.Parameter.KEYWORD_ONLY),
        ("writes", inspect.Parameter.KEYWORD_ONLY),
        ("reads", inspect.Parameter.KEYWORD_ONLY),
        ("requires", inspect.Parameter.KEYWORD_ONLY),
        ("routes", inspect.Parameter.KEYWORD_ONLY),
        ("session", inspect.Parameter.KEYWORD_ONLY),
        ("retry", inspect.Parameter.KEYWORD_ONLY),
        ("policy", inspect.Parameter.KEYWORD_ONLY),
        ("on_input", inspect.Parameter.KEYWORD_ONLY),
        ("max_pauses", inspect.Parameter.KEYWORD_ONLY),
        ("max_steps", inspect.Parameter.KEYWORD_ONLY),
        ("provider_questions", inspect.Parameter.KEYWORD_ONLY),
        ("retention", inspect.Parameter.KEYWORD_ONLY),
    )
    assert signature_items(Botpipe.produce_verify_step) == (
        ("self", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        ("producer", inspect.Parameter.KEYWORD_ONLY),
        ("verifier", inspect.Parameter.KEYWORD_ONLY),
        ("message", inspect.Parameter.KEYWORD_ONLY),
        ("input", inspect.Parameter.KEYWORD_ONLY),
        ("name", inspect.Parameter.KEYWORD_ONLY),
        ("writes", inspect.Parameter.KEYWORD_ONLY),
        ("verifier_writes", inspect.Parameter.KEYWORD_ONLY),
        ("reads", inspect.Parameter.KEYWORD_ONLY),
        ("requires", inspect.Parameter.KEYWORD_ONLY),
        ("verifier_requires", inspect.Parameter.KEYWORD_ONLY),
        ("routes", inspect.Parameter.KEYWORD_ONLY),
        ("session", inspect.Parameter.KEYWORD_ONLY),
        ("verifier_session", inspect.Parameter.KEYWORD_ONLY),
        ("retry", inspect.Parameter.KEYWORD_ONLY),
        ("policy", inspect.Parameter.KEYWORD_ONLY),
        ("on_input", inspect.Parameter.KEYWORD_ONLY),
        ("max_pauses", inspect.Parameter.KEYWORD_ONLY),
        ("max_steps", inspect.Parameter.KEYWORD_ONLY),
        ("provider_questions", inspect.Parameter.KEYWORD_ONLY),
        ("retention", inspect.Parameter.KEYWORD_ONLY),
    )
    assert signature_items(Botpipe.python_step) == (
        ("self", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        ("handler", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        ("message", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        ("input", inspect.Parameter.KEYWORD_ONLY),
        ("name", inspect.Parameter.KEYWORD_ONLY),
        ("writes", inspect.Parameter.KEYWORD_ONLY),
        ("reads", inspect.Parameter.KEYWORD_ONLY),
        ("requires", inspect.Parameter.KEYWORD_ONLY),
        ("routes", inspect.Parameter.KEYWORD_ONLY),
        ("policy", inspect.Parameter.KEYWORD_ONLY),
        ("on_input", inspect.Parameter.KEYWORD_ONLY),
        ("max_pauses", inspect.Parameter.KEYWORD_ONLY),
        ("max_steps", inspect.Parameter.KEYWORD_ONLY),
        ("retention", inspect.Parameter.KEYWORD_ONLY),
    )
    assert signature_items(Botpipe.workflow_step) == (
        ("self", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        ("workflow", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        ("message", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        ("input", inspect.Parameter.KEYWORD_ONLY),
        ("child_message", inspect.Parameter.KEYWORD_ONLY),
        ("name", inspect.Parameter.KEYWORD_ONLY),
        ("params", inspect.Parameter.KEYWORD_ONLY),
        ("writes", inspect.Parameter.KEYWORD_ONLY),
        ("reads", inspect.Parameter.KEYWORD_ONLY),
        ("requires", inspect.Parameter.KEYWORD_ONLY),
        ("routes", inspect.Parameter.KEYWORD_ONLY),
        ("policy", inspect.Parameter.KEYWORD_ONLY),
        ("on_input", inspect.Parameter.KEYWORD_ONLY),
        ("max_pauses", inspect.Parameter.KEYWORD_ONLY),
        ("max_steps", inspect.Parameter.KEYWORD_ONLY),
        ("provider_questions", inspect.Parameter.KEYWORD_ONLY),
        ("retention", inspect.Parameter.KEYWORD_ONLY),
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
        message="Ship the release safely.",
        input=_SDKPauseWorkflow.Input(topic="release"),
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
        "topic": "release",
        "dump": {"topic": "release"},
        "input_fields": {"topic": "release"},
    }
    assert result.debug.task_id.startswith("sdk-")
    assert "pause-workflow" in result.debug.task_id
    assert result.debug.run_id.startswith("run-")
    assert result.retention is not None
    assert result.retention.task_scratch_deleted is True
    assert result.debug.task_dir.exists() is False


def test_sdk_run_accepts_mapping_input_keyword(tmp_path: Path) -> None:
    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    result = client.run(
        _SDKPauseWorkflow,
        message="Ship the release safely.",
        input={"topic": "release"},
        on_input=StaticInput({"approved": True}),
    )

    assert result.ok is True
    assert result.state.approved is True


def test_sdk_run_preserves_explicit_none_message(tmp_path: Path) -> None:
    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    result = client.run(_SDKNoMessageWorkflow, None)

    assert result.ok is True
    assert result.state.observed_message is None
    assert result.state.observed_input_is_none is True
    assert result.artifacts.empty_message_snapshot.path.name == "snapshot.txt"
    assert result.artifacts.empty_message_snapshot.read_text() == "captured"


def test_sdk_run_rejects_removed_third_positional_input(tmp_path: Path) -> None:
    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    with pytest.raises(TypeError, match="positional"):
        client.run(_SDKPauseWorkflow, "Ship it.", {"topic": "release"})  # type: ignore[arg-type]


def test_sdk_run_wraps_resume_schema_mismatch_as_input_response_validation_error(tmp_path: Path) -> None:
    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    with pytest.raises(InputResponseValidationError, match="Approve the release"):
        client.run(
            _SDKPauseWorkflow,
            message="Ship the release safely.",
            input=_SDKPauseWorkflow.Input(topic="release"),
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
            message="Ship the release safely.",
            input=_SDKPauseWorkflow.Input(topic="release"),
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
        "input_is_none": True,
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


def test_sdk_step_executes_simple_operation_declaration(tmp_path: Path) -> None:
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
        message="Handle the typed request.",
        input=_SDKTypedInput(topic="release"),
    )

    assert result.ok is True
    assert result.artifacts.snapshot.read_json() == {"topic": "release"}


@pytest.mark.parametrize(
    ("params_value", "expected"),
    [
        ({"mode": "strict", "reviewers": ["alice"]}, {"mode": "strict", "reviewers": ["alice"]}),
        (_SDKParamsWorkflow.Params(mode="focused", reviewers=["bob"]), {"mode": "focused", "reviewers": ["bob"]}),
    ],
)
def test_sdk_step_accepts_input_and_params_for_single_step_execution(
    tmp_path: Path,
    params_value: BaseModel | dict[str, object],
    expected: dict[str, object],
) -> None:
    snapshot = simple.Json("snapshot")

    @simple.python_step(writes=[snapshot], routes={"done": FINISH})
    def capture(ctx):
        ctx.artifacts.snapshot.write_json(
            {
                "params": ctx.params.model_dump(mode="python"),
                "workflow_params": ctx.workflow_params,
                "input_dump": ctx.input.model_dump(mode="python"),
            }
        )
        return Event("done")

    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    result = client.step(
        capture,
        message="Handle the typed request.",
        input=_SDKTypedInput(topic="release"),
        params=params_value,
    )

    assert result.ok is True
    assert result.artifacts.snapshot.read_json() == {
        "params": expected,
        "workflow_params": expected,
        "input_dump": {"topic": "release"},
    }


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


def test_sdk_step_applies_invocation_local_policy_without_mutating_supplied_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _sdk_client(tmp_path, ScriptedLLMProvider())
    authored_policy = Policy(effort=ModelEffort.LOW)
    invocation_policy = Policy(effort=ModelEffort.HIGH)
    declaration = PythonStep(
        name="capture",
        handler=lambda _ctx: Event("done"),
        provider_policy=authored_policy,
    )
    captured: dict[str, object] = {}
    fake_result = WorkflowResult(
        ok=True,
        status="completed",
        terminal=FINISH,
        state=_SDKResultState(),
        output=None,
        output_validation_error=None,
        artifacts=ArtifactMap({}),
        history=(),
        last_event=Event("done"),
        last_outcome=None,
        handled_inputs=(),
        debug=SDKDebugInfo(
            task_id="sdk-policy",
            run_id="run-1",
            task_dir=tmp_path / ".botpipe" / "tasks" / "sdk-policy",
            workflow_dir=tmp_path / ".botpipe" / "tasks" / "sdk-policy" / "workflow",
            run_dir=tmp_path / ".botpipe" / "tasks" / "sdk-policy" / "workflow" / "runs" / "run-1",
            events_file=tmp_path / ".botpipe" / "tasks" / "sdk-policy" / "workflow" / "runs" / "run-1" / "events.jsonl",
            trace_file=None,
            checkpoint_file=None,
        ),
        retention=None,
    )

    original_build = sdk_module._build_single_step_execution_plan

    def fake_build_single_step_execution_plan(root, step_def, input, params, *, routes, workflow_policy=None):
        captured["root"] = root
        captured["step_def"] = step_def
        captured["input"] = input
        captured["params"] = params
        captured["routes"] = routes
        captured["workflow_policy"] = workflow_policy
        return original_build(root, step_def, input, params, routes=routes, workflow_policy=workflow_policy)

    monkeypatch.setattr(sdk_module, "_build_single_step_execution_plan", fake_build_single_step_execution_plan)
    monkeypatch.setattr(client, "_run_compiled_plan", lambda *args, **kwargs: fake_result)

    result = client.step(
        declaration,
        "Handle the request.",
        policy=invocation_policy,
        input=_SDKTypedInput(topic="release"),
    )

    assert result.ok is True
    assert result.workflow_result is fake_result
    assert declaration.provider_policy is authored_policy
    assert declaration.provider_policy.to_layer_payload() == {"effort": "low"}
    assert captured["step_def"] is not declaration
    assert isinstance(captured["step_def"], PythonStep)
    assert captured["workflow_policy"] is authored_policy
    assert captured["routes"] is None
    layered_step = captured["step_def"]
    assert isinstance(layered_step, PythonStep)
    assert layered_step.provider_policy is invocation_policy
    assert layered_step.provider_policy.to_layer_payload() == {"effort": "high"}


def test_sdk_step_preserves_explicit_routes_for_core_steps(tmp_path: Path) -> None:
    step_def = PromptStep(name="prompt", producer=Prompt.inline("Prompt"))
    routes = {
        "retry": SELF,
        "done": FINISH,
        "question": AWAIT_INPUT,
        "failed": FAIL,
        "repair": Route(target=SELF, summary="retry once"),
    }

    _single_step_plan, workflow_plan = sdk_module._build_single_step_execution_plan(
        tmp_path,
        step_def,
        None,
        None,
        routes=routes,
    )
    route_table = workflow_plan.routes[step_def.name]

    assert route_table["retry"].target.step_name == step_def.name
    assert route_table["done"].target == FINISH
    assert route_table["question"].target == AWAIT_INPUT
    assert route_table["failed"].target == FAIL
    assert route_table["repair"].target.step_name == step_def.name
    assert route_table["repair"].summary == "retry once"


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
        message="{{ message }}",
    )
    client = Botpipe(
        workspace=tmp_path,
        provider=ScriptedLLMProvider(),
        state_dir=tmp_path / ".botpipe",
        runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False, commit_policy="off")),
    )

    result = client.step(declaration, "Run the child workflow.")

    assert result.ok is True
    assert result.route == "done"
    assert result.workflow_result.status == "completed"


def test_sdk_run_wraps_invalid_child_workflow_message_placeholder(tmp_path: Path) -> None:
    class ChildWorkflow(simple.Workflow):
        note = simple.step("Child note.")

    class ParentWorkflow(simple.Workflow):
        class State(BaseModel):
            status: str = "draft"

        launch = simple.workflow_step(ChildWorkflow, message="{{ state.missing }}")

    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    with pytest.raises(
        SDKExecutionError,
        match=r"workflow step 'launch' message template <inline prompt template>: undefined Jinja value: .*missing",
    ):
        client.run(ParentWorkflow, message="Run the child workflow.")


def test_sdk_step_wraps_invalid_child_workflow_message_placeholder(tmp_path: Path) -> None:
    class ChildWorkflow(simple.Workflow):
        note = simple.step("Child note.")

    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    with pytest.raises(
        SDKExecutionError,
        match=r"workflow step 'launch' message template <inline prompt template>: undefined Jinja value: .*missing",
    ):
        client.step(
            ChildWorkflowStep(name="launch", workflow=ChildWorkflow, message="{{ state.missing }}"),
            "Run the child workflow.",
        )


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
            lambda: client.run(_SDKPauseWorkflow, "Ship it.", input=_SDKPauseWorkflow.Input(topic="release")),
            lambda: client.step(simple.python_step(lambda _ctx: Event("done"), name="noop"), "Ship it."),
        ):
            with pytest.raises(SDKExecutionError, match="active event loop"):
                call()

    asyncio.run(invoke())


def test_sdk_constructor_rejects_unknown_provider_name(tmp_path: Path) -> None:
    with pytest.raises(SDKExecutionError, match="could not resolve SDK provider"):
        Botpipe(workspace=tmp_path, provider="not-a-provider")


def test_sdk_runs_namespace_lists_shows_and_resumes_durable_runs(tmp_path: Path) -> None:
    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider(), retention=RetentionPolicy.keep_all())

    with pytest.raises(InputRequired) as exc_info:
        client.run(
            _SDKPauseWorkflow,
            "Ship it.",
            input=_SDKPauseWorkflow.Input(topic="release"),
            max_pauses=0,
        )

    partial = exc_info.value.partial
    records = client.runs.list(task_id=partial.debug.task_id, status="awaiting_input")
    shown = client.runs.show(_SDKPauseWorkflow, partial.debug.task_id)

    assert [record.run_id for record in records] == [partial.debug.run_id]
    assert shown.run_id == partial.debug.run_id
    assert shown.awaiting_input is True
    assert shown.resumable is True

    resumed = client.runs.resume(_SDKPauseWorkflow, partial.debug.task_id, run_id=partial.debug.run_id)

    assert resumed.debug.run_id == partial.debug.run_id
    assert resumed.status == "awaiting_input"

    answered = client.runs.resume(
        _SDKPauseWorkflow,
        partial.debug.task_id,
        run_id=partial.debug.run_id,
        answer={"approved": True},
    )

    assert answered.debug.run_id == partial.debug.run_id
    assert answered.status == "completed"


def test_sdk_runs_resume_reports_missing_and_non_resumable_runs(tmp_path: Path) -> None:
    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider())
    workflow_name = sdk_module._resolve_sdk_workflow_name(tmp_path, _SDKPauseWorkflow)
    run_dir = _seed_durable_run_record(tmp_path, task_id="task-nonresumable", workflow_name=workflow_name)

    with pytest.raises(SDKExecutionError, match="is not resumable"):
        client.runs.resume(_SDKPauseWorkflow, "task-nonresumable", run_id=run_dir.name)

    with pytest.raises(SDKExecutionError, match="no resumable run exists"):
        client.runs.resume(_SDKPauseWorkflow, "task-missing")


def test_sdk_runs_resume_rejects_schema_valid_but_unloadable_checkpoint(tmp_path: Path) -> None:
    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider())
    workflow_name = sdk_module._resolve_sdk_workflow_name(tmp_path, _SDKPauseWorkflow)
    run_dir = _seed_durable_run_record(
        tmp_path,
        task_id="task-unloadable-checkpoint",
        workflow_name=workflow_name,
        run_id="run-unloadable",
        status="running",
    )
    _write_minimal_checkpoint(run_dir, stage="approve", state={"approved": {"not": "a bool"}})

    shown = client.runs.show(_SDKPauseWorkflow, "task-unloadable-checkpoint", run_id="run-unloadable")
    listed = client.runs.list(workflow=_SDKPauseWorkflow, task_id="task-unloadable-checkpoint")

    assert shown.resumable is False
    assert shown.checkpoint_valid is False
    assert shown.checkpoint_error is None
    assert shown.checkpoint_load_error is not None
    assert listed == (shown,)

    with pytest.raises(SDKExecutionError) as exc_info:
        client.runs.resume(_SDKPauseWorkflow, "task-unloadable-checkpoint", run_id="run-unloadable")

    message = str(exc_info.value)
    assert "is not resumable" in message
    assert "checkpoint_valid=False" in message
    assert "checkpoint_load_error=" in message


def test_sdk_runs_resume_without_run_id_skips_newer_unloadable_checkpoint(tmp_path: Path) -> None:
    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider())
    workflow_name = sdk_module._resolve_sdk_workflow_name(tmp_path, _SDKPauseWorkflow)
    task_id = "task-implicit-loadable-selection"
    older_run = _seed_durable_run_record(
        tmp_path,
        task_id=task_id,
        workflow_name=workflow_name,
        run_id="run-older-loadable-live",
        status="running",
    )
    _update_run_metadata_fields(
        older_run,
        updated_at="2026-05-01T00:02:00+00:00",
        lease={
            "host": socket.gethostname(),
            "pid": os.getpid(),
            "heartbeat_at": "2026-05-01T00:02:00+00:00",
        },
    )
    _write_minimal_checkpoint(older_run, stage="approve", state={"approved": None})

    newer_run = _seed_durable_run_record(
        tmp_path,
        task_id=task_id,
        workflow_name=workflow_name,
        run_id="run-newer-unloadable",
        status="running",
    )
    _update_run_metadata_fields(newer_run, updated_at="2026-05-01T00:03:00+00:00")
    _write_minimal_checkpoint(newer_run, stage="approve", state={"approved": {"not": "a bool"}})

    with pytest.raises(SDKExecutionError) as exc_info:
        client.runs.resume(_SDKPauseWorkflow, task_id)

    message = str(exc_info.value)
    assert "run-older-loadable-live" in message
    assert "still running" in message


def test_sdk_runs_resume_without_run_id_reports_latest_loadable_live_run(tmp_path: Path) -> None:
    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider())
    workflow_name = sdk_module._resolve_sdk_workflow_name(tmp_path, _SDKPauseWorkflow)
    task_id = "task-implicit-live-selection"
    older_run = _seed_durable_run_record(
        tmp_path,
        task_id=task_id,
        workflow_name=workflow_name,
        run_id="run-older-loadable",
        status="success",
    )
    _update_run_metadata_fields(older_run, updated_at="2026-05-01T00:02:00+00:00")
    _write_minimal_checkpoint(older_run, stage="approve", state={"approved": None})

    newer_run = _seed_durable_run_record(
        tmp_path,
        task_id=task_id,
        workflow_name=workflow_name,
        run_id="run-newer-loadable-live",
        status="running",
    )
    _update_run_metadata_fields(
        newer_run,
        updated_at="2026-05-01T00:03:00+00:00",
        lease={
            "host": socket.gethostname(),
            "pid": os.getpid(),
            "heartbeat_at": "2026-05-01T00:03:00+00:00",
        },
    )
    _write_minimal_checkpoint(newer_run, stage="approve", state={"approved": None})

    with pytest.raises(SDKExecutionError) as exc_info:
        client.runs.resume(_SDKPauseWorkflow, task_id)

    message = str(exc_info.value)
    assert "run-newer-loadable-live" in message
    assert "still running" in message


def test_sdk_run_record_reports_stale_running_resume_diagnostics(tmp_path: Path) -> None:
    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider())
    workflow_name = sdk_module._resolve_sdk_workflow_name(tmp_path, _SDKPauseWorkflow)
    run_dir = _seed_durable_run_record(
        tmp_path,
        task_id="task-stale-running",
        workflow_name=workflow_name,
        run_id="run-stale",
        status="running",
    )
    run_meta_file = run_dir / "run.json"
    run_meta = json.loads(run_meta_file.read_text(encoding="utf-8"))
    run_meta["lease"] = {
        "host": "remote-host",
        "pid": 999999999,
        "heartbeat_at": "2026-05-01T00:00:00+00:00",
    }
    run_meta_file.write_text(json.dumps(run_meta, sort_keys=True) + "\n", encoding="utf-8")
    (run_dir / "events.jsonl").write_text(
        json.dumps(
            {
                "seq": 4,
                "event_type": "provider_turn_started",
                "step_name": "ask",
                "step_execution_id": "ask#1",
                "turn_kind": "llm",
                "attempt": 1,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    record = client.runs.show(_SDKPauseWorkflow, "task-stale-running", run_id="run-stale")

    assert record.running_live is False
    assert record.stale_running is True
    assert record.resumable is False

    with pytest.raises(SDKExecutionError) as exc_info:
        client.runs.resume(_SDKPauseWorkflow, "task-stale-running", run_id="run-stale")

    message = str(exc_info.value)
    assert "is not resumable" in message
    assert "status='running'" in message
    assert "checkpoint_exists=False" in message
    assert "checkpoint_valid=False" in message
    assert "checkpoint_error='missing'" in message
    assert "running_state=stale" in message
    assert "last_event={'event_type': 'provider_turn_started'" in message
    assert "'step_name': 'ask'" in message


def test_sdk_runs_repair_reconstructs_checkpoint_from_trace_snapshot(tmp_path: Path) -> None:
    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider())
    workflow_name = sdk_module._resolve_sdk_workflow_name(tmp_path, _SDKPauseWorkflow)
    run_dir = _seed_durable_run_record(
        tmp_path,
        task_id="task-repair",
        workflow_name=workflow_name,
        run_id="run-repair",
        status="running",
    )
    (run_dir / "trace.jsonl").write_text(
        json.dumps(
            {
                "event_type": "step_started",
                "sequence": 1,
                "step_name": "approve",
                "step_kind": "python",
                "step_execution_id": "approve#1",
                "state": {"approved": None},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "events.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "event_type": "provider_attempt_started",
                        "step_name": "approve",
                        "step_execution_id": "approve#1",
                        "turn_kind": "llm",
                        "attempt": 1,
                        "max_attempts": 3,
                    },
                    sort_keys=True,
                ),
                json.dumps(
                    {
                        "event_type": "provider_turn_started",
                        "step_name": "approve",
                        "step_execution_id": "approve#1",
                        "turn_kind": "llm",
                        "attempt": 1,
                        "prompt_fingerprint": "abc123",
                        "expected_response": "outcome_json",
                    },
                    sort_keys=True,
                ),
                json.dumps(
                    {
                        "event_type": "provider_session_known",
                        "step_name": "approve",
                        "step_execution_id": "approve#1",
                        "turn_kind": "llm",
                        "attempt": 1,
                        "provider_target": "codex",
                        "session_id": "codex-session-1",
                    },
                    sort_keys=True,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = client.runs.repair(_SDKPauseWorkflow, "task-repair", run_id="run-repair")

    assert result["repaired"] is True
    assert result["stage"] == "approve"
    assert result["resume_cursor"] == {
        "phase": "provider_attempt",
        "step_name": "approve",
        "step_execution_id": "approve#1",
        "turn_kind": "llm",
        "attempt": 1,
        "max_attempts": 3,
        "expected_response": "outcome_json",
        "prompt_fingerprint": "abc123",
        "provider_target": "codex",
        "provider_session_id": "codex-session-1",
    }
    checkpoint = json.loads((run_dir / "checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["stage"] == "approve"
    assert checkpoint["state"] == {"approved": None}
    assert checkpoint["failure_context"]["kind"] == "checkpoint_repaired_from_trace"
    assert client.runs.show(_SDKPauseWorkflow, "task-repair", run_id="run-repair").resumable is True


def test_sdk_runs_repair_repairs_schema_valid_but_unloadable_checkpoint(tmp_path: Path) -> None:
    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider())
    workflow_name = sdk_module._resolve_sdk_workflow_name(tmp_path, _SDKPauseWorkflow)
    run_dir = _seed_durable_run_record(
        tmp_path,
        task_id="task-repair-unloadable-checkpoint",
        workflow_name=workflow_name,
        run_id="run-repair-unloadable",
        status="running",
    )
    _write_minimal_checkpoint(run_dir, stage="approve", state={"approved": {"not": "a bool"}})
    _write_step_started_trace(run_dir)

    result = client.runs.repair(_SDKPauseWorkflow, "task-repair-unloadable-checkpoint", run_id="run-repair-unloadable")

    assert result["repaired"] is True
    checkpoint = json.loads((run_dir / "checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["stage"] == "approve"
    assert checkpoint["state"] == {"approved": None}
    assert client.runs.show(
        _SDKPauseWorkflow,
        "task-repair-unloadable-checkpoint",
        run_id="run-repair-unloadable",
    ).resumable is True


def test_sdk_runs_repair_keeps_loadable_checkpoint_without_force(tmp_path: Path) -> None:
    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider())
    workflow_name = sdk_module._resolve_sdk_workflow_name(tmp_path, _SDKPauseWorkflow)
    run_dir = _seed_durable_run_record(
        tmp_path,
        task_id="task-repair-loadable-checkpoint",
        workflow_name=workflow_name,
        run_id="run-repair-loadable",
        status="running",
    )
    _write_minimal_checkpoint(run_dir, stage="approve", state={"approved": None})

    result = client.runs.repair(_SDKPauseWorkflow, "task-repair-loadable-checkpoint", run_id="run-repair-loadable")

    assert result["repaired"] is False
    assert result["reason"] == "checkpoint_already_valid"


def test_sdk_runs_repair_force_overwrites_loadable_checkpoint_from_trace(tmp_path: Path) -> None:
    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider())
    workflow_name = sdk_module._resolve_sdk_workflow_name(tmp_path, _SDKPauseWorkflow)
    run_dir = _seed_durable_run_record(
        tmp_path,
        task_id="task-force-repair-loadable-checkpoint",
        workflow_name=workflow_name,
        run_id="run-force-repair-loadable",
        status="running",
    )
    _write_minimal_checkpoint(run_dir, stage="approve", state={"approved": True})
    _write_step_started_trace(run_dir, state={"approved": None})

    result = client.runs.repair(
        _SDKPauseWorkflow,
        "task-force-repair-loadable-checkpoint",
        run_id="run-force-repair-loadable",
        force=True,
    )

    assert result["repaired"] is True
    checkpoint = json.loads((run_dir / "checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["state"] == {"approved": None}


def test_sdk_runs_repair_refuses_workflow_state_reconstruction_for_worklists(tmp_path: Path) -> None:
    class WorklistRepairWorkflow(simple.Workflow):
        gates = simple.Worklist.from_items(
            name="gates",
            items=({"id": "alpha", "title": "Alpha"},),
        )

        review = simple.step(
            "Review {{ worklists.gates.current.title }}.",
            scope=gates,
            routes={"done": FINISH},
        )

    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider())
    workflow_name = sdk_module._resolve_sdk_workflow_name(tmp_path, WorklistRepairWorkflow)
    run_dir = _seed_durable_run_record(
        tmp_path,
        task_id="task-worklist-repair",
        workflow_name=workflow_name,
        run_id="run-worklist-repair",
        status="running",
    )
    (run_dir / "trace.jsonl").write_text(
        json.dumps(
            {
                "event_type": "step_started",
                "sequence": 1,
                "step_name": "review",
                "step_execution_id": "review#1",
                "state": {},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(SDKExecutionError, match="workflows with worklists"):
        client.runs.repair(WorklistRepairWorkflow, "task-worklist-repair", run_id="run-worklist-repair")


def test_sdk_runs_repair_refuses_workflow_state_reconstruction_for_sessions(tmp_path: Path) -> None:
    class SessionRepairWorkflow(simple.Workflow):
        main = simple.Session.fresh()

        review = simple.step(
            "Review.",
            session=main,
            routes={"done": FINISH},
        )

    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider())
    workflow_name = sdk_module._resolve_sdk_workflow_name(tmp_path, SessionRepairWorkflow)
    run_dir = _seed_durable_run_record(
        tmp_path,
        task_id="task-session-repair",
        workflow_name=workflow_name,
        run_id="run-session-repair",
        status="running",
    )
    (run_dir / "trace.jsonl").write_text(
        json.dumps(
            {
                "event_type": "step_started",
                "sequence": 1,
                "step_name": "review",
                "step_execution_id": "review#1",
                "state": {},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(SDKExecutionError, match="declared or open sessions"):
        client.runs.repair(SessionRepairWorkflow, "task-session-repair", run_id="run-session-repair")


def test_sdk_runs_repair_refuses_scoped_trace_snapshot(tmp_path: Path) -> None:
    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider())
    workflow_name = sdk_module._resolve_sdk_workflow_name(tmp_path, _SDKPauseWorkflow)
    run_dir = _seed_durable_run_record(
        tmp_path,
        task_id="task-scoped-repair",
        workflow_name=workflow_name,
        run_id="run-scoped-repair",
        status="running",
    )
    (run_dir / "trace.jsonl").write_text(
        json.dumps(
            {
                "event_type": "step_started",
                "sequence": 1,
                "step_name": "approve",
                "step_execution_id": "approve#1",
                "scope": "items",
                "item_id": "alpha",
                "state": {"approved": None},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(SDKExecutionError, match="scoped to a worklist item"):
        client.runs.repair(_SDKPauseWorkflow, "task-scoped-repair", run_id="run-scoped-repair")


def test_sdk_runs_events_and_trace_iterate_existing_jsonl_records(tmp_path: Path) -> None:
    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider(), retention=RetentionPolicy.keep_all())

    with pytest.raises(InputRequired) as exc_info:
        client.run(_SDKPauseWorkflow, "Ship it.", input={"topic": "release"}, max_pauses=0)

    partial = exc_info.value.partial
    events = asyncio.run(
        _collect_async_records(client.runs.events(_SDKPauseWorkflow, partial.debug.task_id, run_id=partial.debug.run_id))
    )
    trace = asyncio.run(
        _collect_async_records(client.runs.trace(_SDKPauseWorkflow, partial.debug.task_id, run_id=partial.debug.run_id))
    )

    assert events[0]["event_type"] == "run_started"
    assert trace
    assert "step_started" in {record["event_type"] for record in trace}


def test_sdk_run_on_event_receives_run_step_and_provider_events(tmp_path: Path) -> None:
    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="Done", tag="done")])
    client = _sdk_client_at_root(tmp_path, provider, retention=RetentionPolicy.keep_all())
    events: list[dict[str, object]] = []

    result = client.run(
        _SDKProviderQuestionWorkflow,
        "Review the rollout.",
        on_event=lambda event: events.append(dict(event)),
    )

    event_types = {event["event_type"] for event in events}
    assert result.status == "completed"
    assert {"run_started", "step_started", "provider_attempt_started", "provider_attempt_finished", "step_finished", "run_finished"} <= event_types
    assert events[0]["event_type"] == "run_started"
    assert events[0]["trace_enabled"] is True
    assert "trace_file" in events[0]


def test_sdk_runs_resume_on_event_receives_runtime_events(tmp_path: Path) -> None:
    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider(), retention=RetentionPolicy.keep_all())

    with pytest.raises(InputRequired) as exc_info:
        client.run(_SDKPauseWorkflow, "Ship it.", input={"topic": "release"}, max_pauses=0)

    partial = exc_info.value.partial
    events: list[dict[str, object]] = []
    result = client.runs.resume(
        _SDKPauseWorkflow,
        partial.debug.task_id,
        run_id=partial.debug.run_id,
        on_event=lambda event: events.append(dict(event)),
    )

    event_types = {event["event_type"] for event in events}
    assert result.status == "awaiting_input"
    assert {"run_resumed", "step_started", "step_finished", "run_finished"} <= event_types


def test_sdk_on_event_exceptions_do_not_fail_run(tmp_path: Path) -> None:
    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider(), retention=RetentionPolicy.keep_all())

    def raise_from_observer(event: dict[str, object]) -> None:
        raise RuntimeError(f"observer failed on {event['event_type']}")

    result = client.run(_SDKNoMessageWorkflow, None, on_event=raise_from_observer)

    assert result.status == "completed"


def test_sdk_child_workflow_on_event_includes_parent_run_metadata(tmp_path: Path) -> None:
    class ChildWorkflow(simple.Workflow):
        @simple.python_step(routes={"done": FINISH})
        def capture(ctx):
            return Event("done")

    class ParentWorkflow(simple.Workflow):
        launch = simple.workflow_step(ChildWorkflow, message="Run child")

    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider(), retention=RetentionPolicy.keep_all())
    events: list[dict[str, object]] = []

    result = client.run(ParentWorkflow, "Run parent", on_event=lambda event: events.append(dict(event)))
    child_starts = [
        event
        for event in events
        if event.get("event_type") == "run_started" and event.get("parent_run_id") == result.debug.run_id
    ]

    assert result.status == "completed"
    assert child_starts
    assert child_starts[0]["parent_workflow"] == "parent_workflow"


def test_sdk_runs_events_follow_observes_appended_records(tmp_path: Path) -> None:
    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider())
    run_dir = _seed_durable_run_record(tmp_path, task_id="task-follow", run_id="run-follow")
    events_file = run_dir / "events.jsonl"
    events_file.write_text("", encoding="utf-8")

    async def observe() -> dict[str, object]:
        stream = client.runs.events("task-follow", follow=True, poll_interval=0.01)
        pending = asyncio.create_task(anext(stream))
        await asyncio.sleep(0.03)
        with events_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"event_type": "appended"}) + "\n")
        record = await asyncio.wait_for(pending, timeout=1)
        await stream.aclose()
        return record

    assert asyncio.run(observe()) == {"event_type": "appended"}


def test_sdk_runs_events_and_trace_handle_empty_missing_and_malformed_files(tmp_path: Path) -> None:
    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider())
    run_dir = _seed_durable_run_record(tmp_path, task_id="task-logs", run_id="run-logs")
    events_file = run_dir / "events.jsonl"
    trace_file = run_dir / "trace.jsonl"

    events_file.write_text("", encoding="utf-8")
    assert asyncio.run(_collect_async_records(client.runs.events("task-logs", run_id="run-logs"))) == []

    trace_file.unlink()
    with pytest.raises(SDKExecutionError, match="trace log is missing"):
        asyncio.run(_collect_async_records(client.runs.trace("task-logs", run_id="run-logs")))

    events_file.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(SDKExecutionError, match="malformed JSON"):
        asyncio.run(_collect_async_records(client.runs.events("task-logs", run_id="run-logs")))


def test_sdk_tasks_namespace_lists_durable_tasks(tmp_path: Path) -> None:
    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider())
    _seed_durable_run_record(tmp_path, task_id="task-one")
    _seed_durable_run_record(tmp_path, task_id="task-two")

    assert [record.task_id for record in client.tasks.list(task_ids=["task-one"])] == ["task-one"]
    assert {record.task_id for record in client.tasks.list()} == {"task-one", "task-two"}


def test_sdk_constructor_uses_workspace_and_rejects_root_keyword(tmp_path: Path) -> None:
    client = Botpipe(
        workspace=tmp_path,
        provider=ScriptedLLMProvider(),
        state_dir=tmp_path / ".botpipe",
        runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False, commit_policy="off")),
    )

    assert client.workspace == tmp_path.resolve()
    assert client.state_dir == (tmp_path / ".botpipe").resolve()

    with pytest.raises(TypeError, match="root"):
        Botpipe(root=tmp_path)  # type: ignore[call-arg]


def test_sdk_constructor_rejects_invalid_default_policy_with_public_wording(tmp_path: Path) -> None:
    with pytest.raises(
        TypeError,
        match=r"default_policy must be a Policy or core provider policy object, or None",
    ):
        Botpipe(
            workspace=tmp_path,
            default_policy="ask",  # type: ignore[arg-type]
            provider=ScriptedLLMProvider(),
            state_dir=tmp_path / ".botpipe",
            runtime_config=RuntimeConfig(
                git_tracking=GitTrackingRuntimeConfig(enabled=False, commit_policy="off")
            ),
        )


def test_sdk_run_rejects_removed_typed_input_and_parameters_keywords(tmp_path: Path) -> None:
    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    with pytest.raises(TypeError, match="typed_input"):
        client.run(  # type: ignore[call-arg]
            _SDKPauseWorkflow,
            "Ship it.",
            typed_input=_SDKPauseWorkflow.Input(topic="release"),
        )
    with pytest.raises(TypeError, match="parameters"):
        client.run(  # type: ignore[call-arg]
            _SDKParamsWorkflow,
            "Ship it.",
            parameters={"mode": "strict"},
        )
    with pytest.raises(TypeError, match="typed_input"):
        client.step(  # type: ignore[call-arg]
            simple.python_step(lambda _ctx: Event("done"), name="noop"),
            "Ship it.",
            typed_input=_SDKPauseWorkflow.Input(topic="release"),
        )
    with pytest.raises(TypeError, match="parameters"):
        client.step(  # type: ignore[call-arg]
            simple.python_step(lambda _ctx: Event("done"), name="noop"),
            "Ship it.",
            parameters={"mode": "strict"},
        )


def test_sdk_public_docstrings_encode_workspace_policy_and_runtime_behavior_contract() -> None:
    init_doc = Botpipe.__init__.__doc__
    run_doc = Botpipe.run.__doc__
    step_doc = Botpipe.step.__doc__
    llm_doc = Botpipe.llm.__doc__
    classify_doc = Botpipe.classify.__doc__
    prompt_step_doc = Botpipe.prompt_step.__doc__
    workflow_step_doc = Botpipe.workflow_step.__doc__

    assert init_doc is not None
    assert "actual project or repository working directory" in init_doc
    assert "`.botpipe` state directory" in init_doc
    assert "SDK client-level" in init_doc
    assert "not a hard security cap" in init_doc

    assert run_doc is not None
    assert "`message` is the task or run request" in run_doc
    assert "`input` is typed workflow input" in run_doc
    assert "`params` are workflow parameters" in run_doc
    assert "`provider_questions` is an SDK/runtime" in run_doc
    assert "distinct from simple" in run_doc

    assert step_doc is not None
    assert "`policy` applies only to this SDK step invocation" in step_doc
    assert "not mutated" in step_doc
    assert "`provider_questions` is an" in step_doc
    assert "`control_routes`" in step_doc

    assert llm_doc is not None
    assert "`prompt` is the provider instruction" in llm_doc
    assert "runtime config defaults" in llm_doc
    assert "SDK client default policy" in llm_doc

    assert classify_doc is not None
    assert "`prompt` is the provider instruction" in classify_doc
    assert "runtime config defaults" in classify_doc
    assert "SDK client default policy" in classify_doc

    assert prompt_step_doc is not None
    assert "`prompt` is the provider instruction" in prompt_step_doc
    assert "`message` is the" in prompt_step_doc

    assert workflow_step_doc is not None
    assert "`child_message` is the child workflow request" in workflow_step_doc


def test_sdk_public_exports_include_revised_sdk_surface() -> None:
    assert botpipe.Step is sdk_module.Step
    assert botpipe.PromptStep is PromptStep
    assert botpipe.ProduceVerifyStep is ProduceVerifyStep
    assert botpipe.PythonStep is PythonStep
    assert botpipe.ChildWorkflowStep is ChildWorkflowStep
    assert botpipe.ResultArtifact is ResultArtifact
    assert botpipe.RetentionPolicy is RetentionPolicy
    assert botpipe.RetentionInfo is sdk_module.RetentionInfo
    assert botpipe.CleanupResult is sdk_module.CleanupResult


def test_sdk_result_dataclasses_keep_positional_construction_compatibility(tmp_path: Path) -> None:
    debug = SDKDebugInfo(
        "sdk-demo",
        "run-1",
        tmp_path / ".botpipe" / "tasks" / "sdk-demo",
        tmp_path / ".botpipe" / "tasks" / "sdk-demo" / "workflow",
        tmp_path / ".botpipe" / "tasks" / "sdk-demo" / "workflow" / "runs" / "run-1",
        tmp_path / ".botpipe" / "tasks" / "sdk-demo" / "workflow" / "runs" / "run-1" / "events.jsonl",
        tmp_path / ".botpipe" / "tasks" / "sdk-demo" / "workflow" / "runs" / "run-1" / "trace.jsonl",
        tmp_path / ".botpipe" / "tasks" / "sdk-demo" / "workflow" / "runs" / "run-1" / "checkpoint.json",
    )
    retention = sdk_module.RetentionInfo(
        RetentionPolicy.keep_all(),
        True,
        False,
        ("report",),
        tmp_path / ".botpipe" / "tasks" / "sdk-demo",
    )
    workflow_result = WorkflowResult(
        True,
        "completed",
        FINISH,
        _SDKResultState(),
        {"summary": "ok"},
        None,
        ArtifactMap({}),
        ("capture",),
        Event("done"),
        None,
        (),
        debug,
        retention,
    )
    input_request = InputRequest(
        "pending-1",
        "Approve the rollout?",
        "Need operator confirmation.",
        '{"approved": true}',
        "capture",
        "before",
        "provider",
        {"type": "object"},
        "ApprovalInput",
        0,
        workflow_result,
    )
    handled = sdk_module.HandledInput(input_request, {"approved": True})
    cleanup = sdk_module.CleanupResult(
        (tmp_path / "deleted",),
        (tmp_path / "skipped",),
        {tmp_path / "error": "permission denied"},
        False,
    )
    step_result = sdk_module.StepResult(
        True,
        "completed",
        "done",
        None,
        _SDKResultState(),
        ArtifactMap({}),
        workflow_result,
    )

    assert workflow_result.debug is debug
    assert workflow_result.retention is retention
    assert input_request.partial is workflow_result
    assert handled.request is input_request
    assert cleanup.deleted == (tmp_path / "deleted",)
    assert step_result.value is None
    assert step_result.workflow_result is workflow_result


def test_sdk_run_exposes_result_artifact_metadata_and_helpers(tmp_path: Path) -> None:
    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    result = client.run(
        _SDKSchemaArtifactWorkflow,
        message="Ship the release safely.",
        input=_SDKSchemaArtifactWorkflow.Input(topic="release"),
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
            task_dir=tmp_path / ".botpipe" / "tasks" / "sdk-noop",
            workflow_dir=tmp_path / ".botpipe" / "tasks" / "sdk-noop" / "workflow",
            run_dir=tmp_path / ".botpipe" / "tasks" / "sdk-noop" / "runs" / "run-1",
            events_file=tmp_path / ".botpipe" / "tasks" / "sdk-noop" / "runs" / "run-1" / "events.jsonl",
            trace_file=None,
            checkpoint_file=None,
        ),
        retention=None,
    )
    monkeypatch.setattr(client, "_run_compiled_plan", lambda *args, **kwargs: fake_result)

    result = client.step(simple.python_step(lambda _ctx: Event("done"), name="noop"), "Ship it.")

    assert result.route == "done"
    assert result.status == "completed"
    assert result.workflow_result.output == {"summary": "should-not-leak"}
    assert result.value is None


def test_sdk_helper_entrypoints_build_core_steps_and_delegate_to_client_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ChildWorkflow(simple.Workflow):
        @simple.python_step(routes={"done": FINISH})
        def capture(_ctx):
            return Event("done")

    client = _sdk_client(tmp_path, ScriptedLLMProvider())
    typed_input = _SDKTypedInput(topic="release")
    retention = RetentionPolicy.keep_all()
    sentinel = object()
    captured: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    def fake_step(step_def, *args, **kwargs):
        captured.append((step_def, args, kwargs))
        return sentinel

    monkeypatch.setattr(client, "step", fake_step)

    assert (
        client.prompt_step(
            "Prompt {{ message }}",
            "Ship it.",
            input=typed_input,
            name="prompt_helper",
            writes=(simple.Md("report"),),
            routes={"done": FINISH},
            retry=5,
            policy=Policy(effort=ModelEffort.LOW),
            retention=retention,
        )
        is sentinel
    )
    assert (
        client.produce_verify_step(
            producer="Draft",
            verifier="Review",
            message="Ship it.",
            input=typed_input,
            name="pair_helper",
            routes={"accepted": FINISH, "needs_rework": SELF},
            retry=ProviderRetryPolicy(max_attempts=4),
            policy=Policy(effort=ModelEffort.HIGH),
            retention=retention,
        )
        is sentinel
    )
    assert (
        client.python_step(
            lambda _ctx: Event("done"),
            "Ship it.",
            input=typed_input,
            name="python_helper",
            routes={"done": FINISH},
            policy=Policy(effort=ModelEffort.MEDIUM),
            retention=retention,
        )
        is sentinel
    )
    assert (
        client.workflow_step(
            ChildWorkflow,
            "Outer message",
            input=typed_input,
            child_message="Child message",
            name="workflow_helper",
            params={"mode": "review"},
            routes={"done": FINISH},
            policy=Policy(read_only=True),
            retention=retention,
        )
        is sentinel
    )

    prompt_step, prompt_args, prompt_kwargs = captured[0]
    assert isinstance(prompt_step, PromptStep)
    assert prompt_step.name == "prompt_helper"
    assert prompt_step.producer.text == "Prompt {{ message }}"
    assert isinstance(prompt_step.retry_policy, ProviderRetryPolicy)
    assert prompt_step.retry_policy.max_attempts == 5
    assert isinstance(prompt_step.provider_policy, Policy)
    assert prompt_step.provider_policy.to_layer_payload() == {"effort": "low"}
    assert "report" in prompt_step.writes
    assert prompt_args == ()
    assert prompt_kwargs["message"] == "Ship it."
    assert prompt_kwargs["input"] is typed_input
    assert prompt_kwargs["routes"] == {"done": FINISH}
    assert prompt_kwargs["retention"] is retention

    pair_step, pair_args, pair_kwargs = captured[1]
    assert isinstance(pair_step, ProduceVerifyStep)
    assert pair_step.name == "pair_helper"
    assert pair_step.producer.text == "Draft"
    assert pair_step.verifier.text == "Review"
    assert pair_step.retry_policy == ProviderRetryPolicy(max_attempts=4)
    assert isinstance(pair_step.provider_policy, Policy)
    assert pair_step.provider_policy.to_layer_payload() == {"effort": "high"}
    assert pair_args == ()
    assert pair_kwargs["message"] == "Ship it."
    assert pair_kwargs["input"] is typed_input
    assert pair_kwargs["routes"] == {"accepted": FINISH, "needs_rework": SELF}
    assert pair_kwargs["retention"] is retention

    python_step, python_args, python_kwargs = captured[2]
    assert isinstance(python_step, PythonStep)
    assert python_step.name == "python_helper"
    assert isinstance(python_step.provider_policy, Policy)
    assert python_step.provider_policy.to_layer_payload() == {"effort": "medium"}
    assert python_args == ()
    assert python_kwargs["message"] == "Ship it."
    assert python_kwargs["input"] is typed_input
    assert python_kwargs["routes"] == {"done": FINISH}
    assert python_kwargs["retention"] is retention

    workflow_step, workflow_args, workflow_kwargs = captured[3]
    assert isinstance(workflow_step, ChildWorkflowStep)
    assert workflow_step.name == "workflow_helper"
    assert workflow_step.workflow is ChildWorkflow
    assert workflow_step.message == "Child message"
    assert workflow_step.input is typed_input
    assert workflow_step.params == {"mode": "review"}
    assert isinstance(workflow_step.provider_policy, Policy)
    assert workflow_step.provider_policy.to_layer_payload() == {"read_only": True}
    assert workflow_args == ()
    assert workflow_kwargs["message"] == "Outer message"
    assert workflow_kwargs["input"] is typed_input
    assert workflow_kwargs["routes"] == {"done": FINISH}
    assert workflow_kwargs["retention"] is retention


def test_sdk_run_default_retention_promotes_task_local_declared_writes_and_keeps_workspace_writes(tmp_path: Path) -> None:
    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider())
    workspace_output = tmp_path / "workspace-output.txt"
    task_local_artifact = simple.Text("task_local", path="{{ task.folder }}/exports/report.txt")
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
    report = simple.Text("report", path="{{ task.folder }}/report.txt")

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
    task_local_artifact = simple.Text("task_local", path="{{ task.folder }}/exports/report.txt")
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


def test_sdk_run_custom_promoted_writes_dir_uniquifies_collisions(tmp_path: Path) -> None:
    shared_promotions = tmp_path / "shared-promotions"
    task_local_artifact = simple.Text("task_local", path="{{ task.folder }}/exports/report.txt")

    class RetentionWorkflow(simple.Workflow):
        task_local = task_local_artifact

        @simple.python_step(writes=[task_local_artifact], routes={"done": FINISH})
        def emit(ctx):
            ctx.artifacts.task_local.write_text(ctx.message or "")
            return Event("done")

    policy = RetentionPolicy(promoted_writes_dir=shared_promotions)
    first_client = _sdk_client_at_root(tmp_path / "first", ScriptedLLMProvider(), retention=policy)
    second_client = _sdk_client_at_root(tmp_path / "second", ScriptedLLMProvider(), retention=policy)

    first_result = first_client.run(RetentionWorkflow, "first")
    second_result = second_client.run(RetentionWorkflow, "second")

    assert first_result.artifacts.task_local.path.exists()
    assert second_result.artifacts.task_local.path.exists()
    assert first_result.artifacts.task_local.path != second_result.artifacts.task_local.path
    assert first_result.artifacts.task_local.read_text() == "first"
    assert second_result.artifacts.task_local.read_text() == "second"


def test_sdk_run_retention_collects_declared_writes_with_runtime_param_context(tmp_path: Path) -> None:
    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider())

    result = client.run(
        _SDKDeclaredWriteContextWorkflow,
        "Retain the report.",
        params={"mode": "strict"},
    )

    assert result.ok is True
    assert result.retention is not None
    assert result.retention.task_scratch_deleted is True
    assert result.artifacts.report.read_text() == "strict:strict"
    assert result.artifacts.report.path.name == "strict-strict.txt"
    assert result.artifacts.report.source_path is not None
    assert result.artifacts.report.source_path.name == "strict-strict.txt"


def test_sdk_run_too_many_pauses_keeps_task_scratch_by_default(tmp_path: Path) -> None:
    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    with pytest.raises(TooManyPauses, match="max_pauses=0") as exc_info:
        client.run(
            _SDKPauseWorkflow,
            message="Ship the release safely.",
            input=_SDKPauseWorkflow.Input(topic="release"),
            on_input=StaticInput({"approved": True}),
            max_pauses=0,
        )

    assert exc_info.value.partial is not None
    assert exc_info.value.partial.retention is not None
    assert exc_info.value.partial.retention.task_scratch_retained is True
    assert exc_info.value.partial.debug.task_dir.exists()


def test_sdk_cleanup_only_targets_valid_completed_sdk_task_directories(tmp_path: Path) -> None:
    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider())
    tasks_root = tmp_path / ".botpipe" / "tasks"
    valid = tasks_root / "sdk-completed"
    failed = tasks_root / "sdk-failed"
    invalid = tasks_root / "manual-task"

    def seed_task(task_dir: Path, *, status: str, terminal: str, task_id: str | None = None) -> None:
        task_dir.mkdir(parents=True, exist_ok=True)
        sentinel = {
            "schema": "botpipe.sdk_task/v1",
            "generated_by": "botpipe.sdk",
            "task_id": task_id or task_dir.name,
            "created_at": "2026-05-01T00:00:00Z",
            "retention_mode": "delete_task_scratch",
        }
        (task_dir / ".botpipe-sdk-task.json").write_text(json.dumps(sentinel) + "\n", encoding="utf-8")
        run_dir = task_dir / "wf_test" / "runs" / "run-1"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.json").write_text(json.dumps({"status": status, "terminal": terminal}) + "\n", encoding="utf-8")

    seed_task(valid, status="completed", terminal=FINISH)
    seed_task(failed, status="failed", terminal=FAIL)
    invalid.mkdir(parents=True, exist_ok=True)

    dry_run = client.tasks.cleanup(dry_run=True)

    assert valid in dry_run.deleted
    assert failed in dry_run.skipped
    assert invalid in dry_run.skipped
    assert valid.exists()

    result = client.cleanup()

    assert valid in result.deleted
    assert valid.exists() is False
    assert failed.exists()
    assert invalid.exists()


def test_sdk_cleanup_honors_older_than_and_include_failed_opt_in(tmp_path: Path) -> None:
    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider())
    tasks_root = tmp_path / ".botpipe" / "tasks"
    old_completed = tasks_root / "sdk-old-completed"
    new_completed = tasks_root / "sdk-new-completed"
    old_failed = tasks_root / "sdk-old-failed"
    now = datetime.now(timezone.utc)

    def seed_task(task_dir: Path, *, status: str, terminal: str, created_at: str) -> None:
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / ".botpipe-sdk-task.json").write_text(
            json.dumps(
                {
                    "schema": "botpipe.sdk_task/v1",
                    "generated_by": "botpipe.sdk",
                    "task_id": task_dir.name,
                    "created_at": created_at,
                    "retention_mode": "delete_task_scratch",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        run_dir = task_dir / "wf_test" / "runs" / "run-1"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.json").write_text(json.dumps({"status": status, "terminal": terminal}) + "\n", encoding="utf-8")

    seed_task(
        old_completed,
        status="completed",
        terminal=FINISH,
        created_at=(now - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    seed_task(
        new_completed,
        status="completed",
        terminal=FINISH,
        created_at=(now - timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    seed_task(
        old_failed,
        status="failed",
        terminal=FAIL,
        created_at=(now - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    dry_run = client.tasks.cleanup(older_than=timedelta(days=2), dry_run=True)

    assert old_completed in dry_run.deleted
    assert new_completed in dry_run.skipped
    assert old_failed in dry_run.skipped
    assert old_completed.exists()
    assert new_completed.exists()
    assert old_failed.exists()

    result = client.tasks.cleanup(older_than=timedelta(days=2), include_failed=True)

    assert old_completed in result.deleted
    assert old_failed in result.deleted
    assert new_completed in result.skipped
    assert old_completed.exists() is False
    assert old_failed.exists() is False
    assert new_completed.exists()


def test_sdk_task_sentinel_identity_stays_canonical(tmp_path: Path) -> None:
    task_dir = tmp_path / ".botpipe" / "tasks" / "sdk-demo"
    default_policy = RetentionPolicy.sdk_default()

    sdk_module._write_sdk_task_sentinel(
        task_dir=task_dir,
        task_id="sdk-demo",
        policy=default_policy,
    )

    sentinel = sdk_module._sdk_task_sentinel_path(task_dir)
    payload = json.loads(sentinel.read_text(encoding="utf-8"))

    assert sdk_module.SDK_TASK_SENTINEL_FILENAME == ".botpipe-sdk-task.json"
    assert sentinel == task_dir / ".botpipe-sdk-task.json"
    assert sentinel.parent == tmp_path / ".botpipe" / "tasks" / "sdk-demo"
    assert payload["schema"] == "botpipe.sdk_task/v1"
    assert payload["generated_by"] == "botpipe.sdk"
    assert payload["task_id"] == "sdk-demo"
    assert RetentionPolicy().mode == "delete_task_scratch"
    assert default_policy.mode == "delete_task_scratch"
    assert payload["retention_mode"] == "delete_task_scratch"


def test_safe_delete_sdk_task_dir_refuses_unsafe_candidates(tmp_path: Path) -> None:
    tasks_root = tmp_path / ".botpipe" / "tasks"
    tasks_root.mkdir(parents=True, exist_ok=True)

    non_sdk = tasks_root / "manual-task"
    non_sdk.mkdir()
    (non_sdk / ".botpipe-sdk-task.json").write_text(
        json.dumps(
            {
                "schema": "botpipe.sdk_task/v1",
                "generated_by": "botpipe.sdk",
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
    (mismatched / ".botpipe-sdk-task.json").write_text(
        json.dumps(
            {
                "schema": "botpipe.sdk_task/v1",
                "generated_by": "botpipe.sdk",
                "task_id": "sdk-other",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(SDKExecutionError, match="refusing to delete"):
        sdk_module._safe_delete_sdk_task_dir(task_dir=mismatched, task_id="sdk-mismatched", tasks_root=tasks_root)

    wrong_schema = tasks_root / "sdk-wrong-schema"
    wrong_schema.mkdir()
    (wrong_schema / ".botpipe-sdk-task.json").write_text(
        json.dumps(
            {
                "schema": "botpipe.sdk_task/v0",
                "generated_by": "botpipe.sdk",
                "task_id": "sdk-wrong-schema",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(SDKExecutionError, match="refusing to delete"):
        sdk_module._safe_delete_sdk_task_dir(task_dir=wrong_schema, task_id="sdk-wrong-schema", tasks_root=tasks_root)

    wrong_owner = tasks_root / "sdk-wrong-owner"
    wrong_owner.mkdir()
    (wrong_owner / ".botpipe-sdk-task.json").write_text(
        json.dumps(
            {
                "schema": "botpipe.sdk_task/v1",
                "generated_by": "someone-else",
                "task_id": "sdk-wrong-owner",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(SDKExecutionError, match="refusing to delete"):
        sdk_module._safe_delete_sdk_task_dir(task_dir=wrong_owner, task_id="sdk-wrong-owner", tasks_root=tasks_root)

    outside = tmp_path / "sdk-outside"
    outside.mkdir()
    (outside / ".botpipe-sdk-task.json").write_text(
        json.dumps(
            {
                "schema": "botpipe.sdk_task/v1",
                "generated_by": "botpipe.sdk",
                "task_id": "sdk-outside",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(SDKExecutionError, match="refusing to delete"):
        sdk_module._safe_delete_sdk_task_dir(task_dir=outside, task_id="sdk-outside", tasks_root=tasks_root)


def test_sdk_runtime_prompt_rendering_supports_input_and_message(tmp_path: Path) -> None:
    seen: list[str] = []

    def record_prompt(request):
        seen.append(request.prompt.text)
        return Outcome(raw_output="ok", tag="done")

    provider = ScriptedLLMProvider(llm_turns=[record_prompt, record_prompt, record_prompt])
    client = _sdk_client(tmp_path, provider)

    client.step(simple.step("Echo {{ message }}", name="echo_message"), "hello")
    client.step(simple.step("Echo {{ request.text }}", name="echo_request"), "hello")
    client.prompt_step("Echo {{ input.topic }} / {{ message }}", "hello", input=_SDKTypedInput(topic="Acme"))

    assert seen == ["Echo hello", "Echo hello", "Echo Acme / hello"]


def test_sdk_prompt_step_missing_input_field_fails_clearly(tmp_path: Path) -> None:
    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    with pytest.raises(SDKExecutionError, match=r"undefined Jinja value: .*input"):
        client.prompt_step("Echo {{ input.customer }}", "hello")


def test_sdk_prompt_step_preserves_explicit_self_routes(tmp_path: Path) -> None:
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="retry", tag="again"),
            Outcome(raw_output="ok", tag="done"),
        ]
    )
    client = _sdk_client(tmp_path, provider)

    result = client.prompt_step(
        "Retry until complete.",
        "hello",
        routes={"again": SELF, "done": FINISH},
    )

    assert result.ok is True
    assert result.route == "done"
    assert [call.kind for call in provider.calls] == ["step", "step"]


def test_sdk_produce_verify_step_defaults_to_rework_self_loop(tmp_path: Path) -> None:
    provider = ScriptedLLMProvider(
        producer_turns=["draft-1", "draft-2"],
        verifier_turns=[
            Outcome(raw_output="rework", tag="needs_rework"),
            Outcome(raw_output="accepted", tag="accepted"),
        ],
    )
    client = _sdk_client(tmp_path, provider)

    result = client.produce_verify_step(
        producer="Draft {{ message }}",
        verifier="Review draft.",
        message="hello",
    )

    assert result.ok is True
    assert result.route == "accepted"
    assert [call.kind for call in provider.calls] == ["producer", "verifier", "producer", "verifier"]


def test_sdk_python_step_helper_executes_and_honors_retention_override(tmp_path: Path) -> None:
    client = _sdk_client_at_root(tmp_path, ScriptedLLMProvider())
    report = simple.Text("report", path="{{ task.folder }}/report.txt")
    retention = RetentionPolicy.keep_all()

    result = client.python_step(
        lambda ctx: (ctx.artifacts.report.write_text(ctx.message or ""), Event("done"))[1],
        "keep scratch",
        name="python_helper",
        writes=(report,),
        retention=retention,
    )

    assert result.ok is True
    assert result.artifacts.report.read_text() == "keep scratch"
    assert result.workflow_result.retention is not None
    assert result.workflow_result.retention.policy == retention
    assert result.workflow_result.retention.task_scratch_retained is True
    assert result.workflow_result.debug.task_dir.exists()


def test_sdk_workflow_step_renders_child_message_with_input_placeholders(tmp_path: Path) -> None:
    observed = tmp_path / "child-message.txt"

    class ChildWorkflow(simple.Workflow):
        class Input(BaseModel):
            topic: str

        captured = simple.Text("captured", path=observed)

        @simple.python_step(writes=[captured], routes={"done": FINISH})
        def capture(ctx):
            ctx.artifacts.captured.write_text(ctx.message or "")
            return Event("done")

    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    result = client.workflow_step(
        ChildWorkflow,
        "outer-message",
        input=_SDKTypedInput(topic="Acme"),
        child_message="Child {{ input.topic }} / {{ message }}",
    )

    assert result.ok is True
    assert observed.read_text(encoding="utf-8") == "Child Acme / outer-message"


def test_sdk_workflow_step_defaults_child_message_to_outer_message(tmp_path: Path) -> None:
    observed = tmp_path / "child-default-message.txt"

    class ChildWorkflow(simple.Workflow):
        captured = simple.Text("captured", path=observed)

        @simple.python_step(writes=[captured], routes={"done": FINISH})
        def capture(ctx):
            ctx.artifacts.captured.write_text(ctx.message or "")
            return Event("done")

    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    result = client.workflow_step(
        ChildWorkflow,
        "outer-message",
    )

    assert result.ok is True
    assert observed.read_text(encoding="utf-8") == "outer-message"
