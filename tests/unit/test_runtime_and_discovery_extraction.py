from __future__ import annotations

from pathlib import Path
import sys
import types

import pytest
from pydantic import BaseModel

_sdk = types.ModuleType("botlane.sdk")
for _name in (
    "ArtifactMap",
    "Botlane",
    "BotlaneSDKError",
    "BestSuppositionInput",
    "CleanupResult",
    "ConsoleInput",
    "HandledInput",
    "InputRequest",
    "InputRequired",
    "InputResponseValidationError",
    "MappingInput",
    "RetentionInfo",
    "RetentionPolicy",
    "ResultArtifact",
    "SDKDebugInfo",
    "SDKExecutionError",
    "StaticInput",
    "StepResult",
    "TooManyPauses",
    "WorkflowInputError",
    "WorkflowParameterError",
    "WorkflowResult",
):
    setattr(_sdk, _name, type(_name, (), {}))
sys.modules.setdefault("botlane.sdk", _sdk)

from botlane import simple
from botlane.core import FAIL, FINISH, Workflow
from botlane.core.discovery import describe_workflow_class
from botlane.core.engine import Engine
from botlane.core.errors import WorkflowExecutionError, WorkflowValidationError
from botlane.core.extensions import RunBinding, TerminalFinish
from botlane.core.primitives import Event, RequestInput
from botlane.core.providers.fake import ScriptedLLMProvider
from botlane.core.steps import PythonStep, Session
from botlane.core.stores import InMemoryCheckpointStore, InMemorySessionStore


class ApprovalInput(BaseModel):
    approval: str


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    task_folder = tmp_path / "task"
    run_folder = tmp_path / "run"
    task_folder.mkdir()
    run_folder.mkdir()
    return task_folder, run_folder


def test_engine_max_steps_exhaustion_emits_fatal_terminal_without_checkpoint(tmp_path: Path) -> None:
    seen: list[tuple[str, str | None, int | None]] = []

    class TerminalExtension:
        def bind(self, binding: RunBinding):
            class Bound:
                def before_step(self, event) -> None:
                    return None

                def after_step(self, event) -> None:
                    return None

                def on_terminal(self, event: TerminalFinish) -> None:
                    passes = None if event.state is None else event.state.passes
                    seen.append((event.terminal, event.step_name, passes))

            return Bound()

    def _loopworkflow_on_spin(ctx):
        ctx.state = ctx.state.model_copy(update={"passes": ctx.state.passes + 1})
        return Event("again")

    class LoopWorkflow(Workflow):
        class State(BaseModel):
            passes: int = 0

        extensions = (TerminalExtension(),)
        spin = PythonStep(name="spin", handler=_loopworkflow_on_spin)
        entry = spin
        transitions = {spin: {"again": spin}}

    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        LoopWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(WorkflowExecutionError, match="workflow exceeded max_steps=2"):
        engine.run(
            task_id="task-max-steps",
            run_id="run-max-steps",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
            max_steps=2,
        )

    assert checkpoint_store.load() is None
    assert seen == [("fatal", "spin", 2)]


def test_engine_resume_input_failure_preserves_fatal_terminal_step_context(tmp_path: Path) -> None:
    seen: list[tuple[str, str | None, bool]] = []

    class TerminalExtension:
        def bind(self, binding: RunBinding):
            class Bound:
                def before_step(self, event) -> None:
                    return None

                def after_step(self, event) -> None:
                    return None

                def on_terminal(self, event: TerminalFinish) -> None:
                    seen.append((event.terminal, event.step_name, event.state is not None))

            return Bound()

    def _requestinputworkflow_on_ask(ctx):
        if ctx.input_response is None:
            return RequestInput("Approve the review?", input_schema=ApprovalInput)
        return Event("done")

    class RequestInputWorkflow(Workflow):
        class State(BaseModel):
            pass

        extensions = (TerminalExtension(),)
        ask = PythonStep(name="ask", handler=_requestinputworkflow_on_ask)
        entry = ask
        transitions = {ask: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        RequestInputWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    first = engine.run(
        task_id="task-resume-fatal",
        run_id="run-resume-fatal",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert first.terminal == "AWAIT_INPUT"
    assert first.checkpoint is not None
    assert seen[0] == ("AWAIT_INPUT", "ask", True)

    with pytest.raises(WorkflowExecutionError, match="resumed input did not satisfy"):
        engine.resume(
            task_id="task-resume-fatal",
            run_id="run-resume-fatal",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
            answer='{"approval": 7}',
        )

    assert seen[-1] == ("fatal", "ask", True)


def test_engine_fail_terminal_saves_checkpoint_and_emits_terminal_state(tmp_path: Path) -> None:
    seen: list[tuple[str, str | None, str | None]] = []

    class TerminalExtension:
        def bind(self, binding: RunBinding):
            class Bound:
                def before_step(self, event) -> None:
                    return None

                def after_step(self, event) -> None:
                    return None

                def on_terminal(self, event: TerminalFinish) -> None:
                    status = None if event.state is None else event.state.status
                    seen.append((event.terminal, event.step_name, status))

            return Bound()

    def _failworkflow_on_review(ctx):
        ctx.state = ctx.state.model_copy(update={"status": "failed-in-review"})
        return Event("failed")

    class FailWorkflow(Workflow):
        class State(BaseModel):
            status: str = "new"

        extensions = (TerminalExtension(),)
        review = PythonStep(name="review", handler=_failworkflow_on_review)
        entry = review
        transitions = {review: {"failed": FAIL}}

    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    result = Engine(
        FailWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    ).run(
        task_id="task-fail-terminal",
        run_id="run-fail-terminal",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    checkpoint = checkpoint_store.load()
    assert result.terminal == FAIL
    assert checkpoint is not None
    assert checkpoint.stage == "review"
    assert checkpoint.state.status == "failed-in-review"
    assert seen == [(FAIL, "review", "failed-in-review")]


def test_engine_finish_terminal_skips_checkpoint_and_emits_terminal_state(tmp_path: Path) -> None:
    seen: list[tuple[str, str | None, int | None]] = []

    class TerminalExtension:
        def bind(self, binding: RunBinding):
            class Bound:
                def before_step(self, event) -> None:
                    return None

                def after_step(self, event) -> None:
                    return None

                def on_terminal(self, event: TerminalFinish) -> None:
                    completed = None if event.state is None else event.state.completed
                    seen.append((event.terminal, event.step_name, completed))

            return Bound()

    def _finishworkflow_on_publish(ctx):
        ctx.state = ctx.state.model_copy(update={"completed": ctx.state.completed + 1})
        return Event("done")

    class FinishWorkflow(Workflow):
        class State(BaseModel):
            completed: int = 0

        extensions = (TerminalExtension(),)
        publish = PythonStep(name="publish", handler=_finishworkflow_on_publish)
        entry = publish
        transitions = {publish: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    result = Engine(
        FinishWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    ).run(
        task_id="task-finish-terminal",
        run_id="run-finish-terminal",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.checkpoint is None
    assert checkpoint_store.load() is None
    assert seen == [(FINISH, "publish", 1)]


def test_describe_workflow_class_preserves_default_entry_order_and_global_session() -> None:
    def _discoveryworkflow_on_draft(ctx):
        return Event("done")

    def _discoveryworkflow_on_publish(ctx):
        return Event("done")

    class DiscoveryWorkflow(Workflow):
        class State(BaseModel):
            pass

        global_session = Session.run(open=True)
        draft = PythonStep(name="draft", handler=_discoveryworkflow_on_draft)
        publish = PythonStep(name="publish", handler=_discoveryworkflow_on_publish)
        transitions = {draft: {"done": publish}, publish: {"done": FINISH}}

    definition = describe_workflow_class(DiscoveryWorkflow)

    assert definition.workflow_name == "discovery_workflow"
    assert definition.entry.name == "draft"
    assert tuple(step.name for step in definition.steps) == ("draft", "publish")
    assert definition.default_session_name == "global"
    assert definition.sessions_by_name["global"] is DiscoveryWorkflow.global_session


def test_describe_workflow_class_lowers_simple_step_declarations_in_order() -> None:
    class SimpleDiscoveryWorkflow(simple.Workflow):
        draft = simple.python_step(lambda ctx: simple.Event("done"), name="draft")
        publish = simple.python_step(
            lambda ctx: simple.Event("done"),
            name="publish",
            routes={"done": simple.FINISH},
        )

    definition = describe_workflow_class(SimpleDiscoveryWorkflow)
    publish = definition.steps_by_name["publish"]

    assert definition.workflow_name == "simple_discovery_workflow"
    assert definition.entry.name == "draft"
    assert tuple(step.name for step in definition.steps) == ("draft", "publish")
    assert definition.transitions[definition.entry]["done"] is publish
    assert definition.transitions[publish]["done"] == FINISH


def test_describe_workflow_class_rejects_duplicate_step_names() -> None:
    def _duplicateworkflow_on_first(ctx):
        return Event("done")

    def _duplicateworkflow_on_second(ctx):
        return Event("done")

    with pytest.raises(WorkflowValidationError, match="duplicate step name 'review'"):
        class DuplicateWorkflow(Workflow):
            class State(BaseModel):
                pass

            first = PythonStep(name="review", handler=_duplicateworkflow_on_first)
            second = PythonStep(name="review", handler=_duplicateworkflow_on_second)
            entry = first
            transitions = {first: {"done": FINISH}, second: {"done": FINISH}}

        describe_workflow_class(DuplicateWorkflow)
