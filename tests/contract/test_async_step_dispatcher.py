from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel

import autoloop.simple as simple
from autoloop.core.context import Context, context_runtime
from autoloop.core.engine import Engine
from autoloop.core.primitives import Event, Outcome
from autoloop.core.providers.fake import ScriptedLLMProvider
from autoloop.core.stores import InMemoryCheckpointStore, InMemorySessionStore


def _build_step_context(engine: Engine, tmp_path: Path, *, step_name: str) -> tuple[object, Context]:
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / f"wf_{engine.compiled.workflow_name}"
    run_folder = tmp_path / "run"
    package_folder = tmp_path / "package"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    run_folder.mkdir(parents=True, exist_ok=True)
    package_folder.mkdir(parents=True, exist_ok=True)

    step = engine.compiled.steps[step_name]
    context = Context(
        root=tmp_path,
        task_id="task-async-dispatch",
        run_id="run-async-dispatch",
        workflow_name=engine.compiled.workflow_name,
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        state=engine.compiled.new_state(),
        session_store=engine.session_store,
        session_definitions=engine.compiled.sessions,
        worklists=engine.compiled.worklists,
        selections={},
        selection_snapshots={},
        step_name=step.name,
        default_session_name=engine.compiled.default_session_name,
        values={},
    )
    runtime = context_runtime(context)
    runtime.set_worklist_selection_resolver(lambda worklist_name: (_ for _ in ()).throw(AssertionError(worklist_name)))
    step_state_store = engine._ensure_step_state_store({}, step)
    engine._increment_step_runtime_state(step_state_store)
    runtime.set_step_state_store(step_state_store)
    runtime.set_values(context._values)
    runtime.set_meta({"step": {"name": step.name, "kind": step.kind, "visits": 1, "last_route": None}})
    return step, context


def test_step_dispatcher_execute_async_capture_runs_hooks_and_skips_route_on_taken(tmp_path: Path) -> None:
    on_taken_calls: list[str] = []

    def before_hook(ctx: Context) -> None:
        ctx.values.before_seen = True

    def after_hook(ctx: Context) -> None:
        ctx.write("report", "captured")
        ctx.values.after_seen = True

    def on_done_taken(ctx: Context) -> None:
        on_taken_calls.append("done")

    class CaptureWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        review = simple.step(
            "Review the artifact.",
            name="review",
            writes=[simple.Md("report", path="report.md")],
            before=before_hook,
            after=after_hook,
            routes={"done": simple.Route.to("publish", on_taken=on_done_taken, required_writes=("report",))},
        )
        publish = simple.python_step(lambda ctx: Event("done"), name="publish", routes={"done": simple.FINISH})

    engine = Engine(
        CaptureWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )
    step, context = _build_step_context(engine, tmp_path, step_name="review")

    result = asyncio.run(engine.step_dispatcher.execute_async(step, context, context.state, (), route_mode="capture"))

    report_path = engine._resolve_artifacts(context)["report"].path
    assert result.event is not None
    assert result.event.tag == "done"
    assert result.destination == "publish"
    assert result.pending_handoffs == ()
    assert report_path.read_text(encoding="utf-8") == "captured"
    assert context.values.before_seen is True
    assert context.values.after_seen is True
    assert on_taken_calls == []
