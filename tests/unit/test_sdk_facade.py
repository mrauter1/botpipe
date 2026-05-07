from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pydantic import BaseModel

import autoloop.simple as simple
from autoloop import (
    AWAIT_INPUT,
    FINISH,
    ArtifactMap,
    Autoloop,
    InputRequest,
    InputRequired,
    InputResponseValidationError,
    SDKExecutionError,
    StaticInput,
    WorkflowInputError,
)
from autoloop.core.primitives import Event, Outcome, RequestInput
from autoloop.core.providers.fake import ScriptedLLMProvider
from autoloop.core.steps import PythonStep
from autoloop.runtime.config import GitTrackingRuntimeConfig, RuntimeConfig


class _SDKApprovalInput(BaseModel):
    approved: bool


class _SDKTypedInput(BaseModel):
    topic: str


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


def _sdk_client(tmp_path: Path, provider: object) -> Autoloop:
    return Autoloop(
        root=Path.cwd(),
        provider=provider,
        state_dir=tmp_path / ".autoloop",
        runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False, commit_policy="off")),
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
    assert result.debug.events_file.exists()


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

    with pytest.raises(InputRequired, match="Proceed\\?"):
        client.run(
            _SDKProviderQuestionWorkflow,
            "Review the rollout.",
            provider_questions=True,
        )


def test_sdk_run_keeps_direct_request_input_when_provider_questions_disabled(tmp_path: Path) -> None:
    client = _sdk_client(tmp_path, ScriptedLLMProvider())

    with pytest.raises(InputRequired, match="Approve the release"):
        client.run(
            _SDKPauseWorkflow,
            "Ship the release safely.",
            _SDKPauseWorkflow.Input(topic="release"),
            provider_questions=False,
        )


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


def test_sdk_step_executes_synthetic_simple_operation_workflow(tmp_path: Path) -> None:
    provider = ScriptedLLMProvider(operation_turns=["summary"])
    client = _sdk_client(tmp_path, provider)

    result = client.step(
        simple.llm.step(prompt="Summarize the request.", name="summarize"),
        "Summarize the incident.",
    )

    assert result.ok is True
    assert result.route == "done"
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
