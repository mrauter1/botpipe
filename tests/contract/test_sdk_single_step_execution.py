from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

import botlane.simple as simple
from botlane import AWAIT_INPUT, FINISH, SELF, Botlane, StaticInput
from botlane.core.primitives import Event, Outcome
from botlane.core.providers.fake import ScriptedLLMProvider
from botlane.runtime.config import GitTrackingRuntimeConfig, RuntimeConfig


class _SingleStepTypedInput(BaseModel):
    topic: str


class _SingleStepParams(BaseModel):
    mode: str


def _sdk_client(tmp_path: Path, provider: object) -> Botlane:
    return Botlane(
        workspace=tmp_path,
        provider=provider,
        state_dir=tmp_path / ".botlane",
        runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False, commit_policy="off")),
    )


def test_sdk_step_executes_single_step_plan_with_typed_input_and_params(tmp_path: Path) -> None:
    snapshot = simple.Json("snapshot")

    @simple.python_step(writes=[snapshot], routes={"done": FINISH})
    def capture(ctx):
        ctx.artifacts.snapshot.write_json(
            {
                "message": ctx.message,
                "params": ctx.params.model_dump(mode="python"),
                "input": ctx.input.model_dump(mode="python"),
            }
        )
        return Event("done")

    client = _sdk_client(tmp_path, ScriptedLLMProvider())
    result = client.step(
        capture,
        message="Handle the release.",
        input=_SingleStepTypedInput(topic="release"),
        params=_SingleStepParams(mode="focused"),
    )

    assert result.status == "completed"
    assert result.route == "done"
    assert result.value is None
    assert result.artifacts.snapshot.read_json() == {
        "message": "Handle the release.",
        "params": {"mode": "focused"},
        "input": {"message": "Handle the release.", "topic": "release"},
    }


def test_sdk_step_provider_question_flow_uses_single_step_execution_path(tmp_path: Path) -> None:
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="Need approval", tag="question", question="Proceed?"),
            Outcome(raw_output="Approved", tag="done"),
        ]
    )
    client = _sdk_client(tmp_path, provider)
    declaration = simple.step(
        "Review the request.",
        name="review",
        routes={"done": FINISH, "question": AWAIT_INPUT},
    )

    result = client.step(
        declaration,
        "Review the rollout.",
        on_input=StaticInput("yes"),
    )

    assert result.status == "completed"
    assert result.route == "done"
    assert len(result.workflow_result.handled_inputs) == 1


def test_sdk_step_preserves_explicit_self_routes_on_public_execution_path(tmp_path: Path) -> None:
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="Retry once", tag="repair"),
            Outcome(raw_output="Approved", tag="done"),
        ]
    )
    client = _sdk_client(tmp_path, provider)
    declaration = simple.step(
        "Review the request.",
        name="review",
        routes={
            "done": FINISH,
            "repair": simple.Route(target=SELF, summary="retry once"),
        },
    )

    result = client.step(
        declaration,
        "Review the rollout.",
    )

    assert result.status == "completed"
    assert result.route == "done"
    assert [call.step_name for call in provider.calls] == ["review", "review"]
