from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from botlane.core import FINISH, Workflow
from botlane.core.discovery import describe_workflow_class
from botlane.core.engine import Engine
from botlane.core.errors import WorkflowExecutionError
from botlane.core.extensions import RunBinding, TerminalFinish
from botlane.core.primitives import Event
from botlane.core.providers.fake import ScriptedLLMProvider
from botlane.core.steps import PythonStep, Session
from botlane.core.stores import InMemoryCheckpointStore, InMemorySessionStore


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
