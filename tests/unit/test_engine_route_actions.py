from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from botlane.core import AWAIT_INPUT, FAIL, FINISH, Workflow
from botlane.core.engine import Engine, StepFinalizationRecord
from botlane.core.engine_collaborators import StepExecutionResult
from botlane.core.errors import WorkflowExecutionError
from botlane.core.prompts import Prompt
from botlane.core.providers.fake import ScriptedLLMProvider
from botlane.core.route_contracts import AwaitInput, Continue, FailAction, Finish
from botlane.core.steps import PromptStep, PythonStep
from botlane.core.stores import InMemoryCheckpointStore, InMemorySessionStore, PendingInput


class _RouteActionWorkflow(Workflow):
    class State(BaseModel):
        status: str = "new"

    first = PromptStep(name="first", producer=Prompt.inline("Route to the next step."))
    second = PythonStep(name="second", handler=lambda ctx: None)
    entry = first
    transitions = {
        first: {"done": second},
        second: {"done": FINISH},
    }


def _prepare_loop(engine: Engine, tmp_path: Path):
    task_folder = tmp_path / "task"
    run_folder = tmp_path / "run"
    package_folder = tmp_path / "package"
    task_folder.mkdir()
    run_folder.mkdir()
    package_folder.mkdir()

    env = engine._prepare_run_environment(
        task_id="task-engine-route-actions",
        run_id="run-engine-route-actions",
        task_folder=task_folder,
        workflow_folder=None,
        run_folder=run_folder,
        package_folder=package_folder,
        root=tmp_path,
        request_file=None,
        task_request_file=None,
        params=None,
        workflow_params=None,
        message=None,
        workflow_input=None,
        workflow_invoker=None,
    )
    loop = engine._new_run_loop_state()
    loop = engine._initialize_run_loop(env, loop=loop, initial_state=None)
    frame = engine._prepare_step_frame(env, loop)
    return env, loop, frame


def _build_engine() -> Engine:
    return Engine(
        _RouteActionWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )


def test_handle_step_result_uses_continue_action_target_over_legacy_destination(tmp_path: Path) -> None:
    engine = _build_engine()
    env, loop, frame = _prepare_loop(engine, tmp_path)

    step_result = StepExecutionResult(
        state=loop.state,
        destination=FINISH,
        event=None,
        outcome=None,
        pending_handoffs=(),
        action=Continue(target_step="second"),
        transition=StepFinalizationRecord(final_route="done", target_step="second"),
    )

    terminal = engine._handle_step_result(env, loop, frame, step_result)

    assert terminal is None
    assert loop.current_step_name == "second"


def test_handle_step_result_rejects_missing_canonical_route_action(tmp_path: Path) -> None:
    engine = _build_engine()
    env, loop, frame = _prepare_loop(engine, tmp_path)

    step_result = StepExecutionResult(
        state=loop.state,
        destination="second",
        event=None,
        outcome=None,
        pending_handoffs=(),
        action=None,
        transition=StepFinalizationRecord(final_route="done", target_step="second"),
    )

    with pytest.raises(WorkflowExecutionError, match="canonical route action"):
        engine._handle_step_result(env, loop, frame, step_result)


def test_handle_step_result_uses_finish_action_over_legacy_destination(tmp_path: Path) -> None:
    engine = _build_engine()
    env, loop, frame = _prepare_loop(engine, tmp_path)

    step_result = StepExecutionResult(
        state=loop.state,
        destination="second",
        event=None,
        outcome=None,
        pending_handoffs=(),
        action=Finish(),
        transition=StepFinalizationRecord(final_route="done", terminal=FINISH),
    )

    terminal = engine._handle_step_result(env, loop, frame, step_result)

    assert terminal is not None
    assert terminal.terminal == FINISH


def test_handle_step_result_uses_await_input_action_over_legacy_destination(tmp_path: Path) -> None:
    engine = _build_engine()
    env, loop, frame = _prepare_loop(engine, tmp_path)
    pending_input = PendingInput(
        pending_input_id="pending-1",
        source_step="first",
        question="Need approval?",
    )

    step_result = StepExecutionResult(
        state=loop.state,
        destination="second",
        event=None,
        outcome=None,
        pending_handoffs=(),
        action=AwaitInput(pending_input=pending_input),
        pending_input=pending_input,
        transition=StepFinalizationRecord(runtime_control="request_input", terminal=AWAIT_INPUT),
    )

    terminal = engine._handle_step_result(env, loop, frame, step_result)

    assert terminal is not None
    assert terminal.terminal == AWAIT_INPUT
    assert terminal.checkpoint is not None
    assert terminal.checkpoint.pending_input == pending_input


def test_handle_step_result_uses_fail_action_over_legacy_destination(tmp_path: Path) -> None:
    engine = _build_engine()
    env, loop, frame = _prepare_loop(engine, tmp_path)

    step_result = StepExecutionResult(
        state=loop.state,
        destination="second",
        event=None,
        outcome=None,
        pending_handoffs=(),
        action=FailAction(reason="route failed"),
        transition=StepFinalizationRecord(runtime_control="fail", terminal=FAIL),
    )

    terminal = engine._handle_step_result(env, loop, frame, step_result)

    assert terminal is not None
    assert terminal.terminal == FAIL
    assert terminal.checkpoint is not None
