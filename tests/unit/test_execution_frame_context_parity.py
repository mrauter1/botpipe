from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

import botlane.core.context as context_module
from botlane.core.branch_groups.context import (
    BranchMetadata,
    FanInMetadata,
    create_branch_context,
    create_fan_in_context,
)
from botlane.core.context import Context, _DEFAULT_MESSAGE
from botlane.core.execution_frame import _DEFAULT_FRAME_MESSAGE
from botlane.core.stores import InMemorySessionStore
from botlane.core.worklists import SelectionSnapshot, WorkItemSnapshot, Worklist


class _State(BaseModel):
    counter: int = 0


class _Input(BaseModel):
    topic: str = "release"


def _make_context(
    tmp_path: Path,
    *,
    message: str | None | object = _DEFAULT_MESSAGE,
    values: dict[str, object] | None = None,
    worklists: dict[str, object] | None = None,
    selection_snapshots: dict[str, SelectionSnapshot] | None = None,
) -> Context:
    task_folder = tmp_path / ".botlane" / "tasks" / "task-1"
    workflow_folder = task_folder / "wf_example"
    run_folder = workflow_folder / "runs" / "run-1"
    package_folder = tmp_path / "workflows" / "example"
    run_folder.mkdir(parents=True, exist_ok=True)
    package_folder.mkdir(parents=True, exist_ok=True)
    (task_folder / "request.md").write_text("task request\n", encoding="utf-8")
    (run_folder / "request.md").write_text("run request\n", encoding="utf-8")
    return Context(
        root=tmp_path,
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        state=_State(),
        workflow_input=_Input(),
        session_store=InMemorySessionStore(),
        message=message,
        values=values,
        worklists=worklists,
        selection_snapshots=selection_snapshots,
    )


def test_context_synthesizes_execution_frame_and_preserves_default_message_sentinel(tmp_path: Path) -> None:
    default_ctx = _make_context(tmp_path)
    none_ctx = _make_context(tmp_path / "explicit-none", message=None)

    assert default_ctx._execution_frame.identity is default_ctx._run_identity
    assert default_ctx._execution_frame.message is _DEFAULT_FRAME_MESSAGE
    assert default_ctx._message is _DEFAULT_MESSAGE
    assert default_ctx.message == "run request"
    assert default_ctx.input.message == "run request"
    assert default_ctx.input.topic == "release"

    assert none_ctx._execution_frame.message is None
    assert none_ctx._message is None
    assert none_ctx.message is None
    assert none_ctx.input.message is None
    assert none_ctx.input.topic == "release"


def test_context_module_has_no_weakref_runtime_sidecar() -> None:
    assert not hasattr(context_module, "_CONTEXT_RUNTIMES")
    assert not hasattr(context_module, "_ContextRuntime")
    assert not hasattr(context_module, "context_runtime")


def test_context_frame_mutators_update_execution_frame_and_legacy_fields(tmp_path: Path) -> None:
    ctx = _make_context(tmp_path, values={"shared": "root"})

    ctx._execution_frame.set_values({"shared": "updated", "count": 2})
    ctx._execution_frame.set_route({"tag": "done"})
    ctx._execution_frame.set_event({"tag": "progress"})
    ctx._execution_frame.set_outcome({"status": "ok"})
    ctx._execution_frame.set_meta({"source": "test"})
    ctx._execution_frame.answer = "42"
    ctx._execution_frame.input_response = {"approved": True}
    ctx._execution_frame.set_step_state({"visits": 1, "last_route": None, "last_reason": None})
    ctx._execution_frame.set_item_state({"status": "queued"})
    ctx._execution_frame.set_step_item_state({"visits": 2, "last_route": "done", "last_reason": None})
    ctx._execution_frame.set_state(ctx.state.model_copy(update={"counter": 3}))

    assert ctx._execution_frame.values == {"shared": "updated", "count": 2}
    assert ctx._values == {"shared": "updated", "count": 2}
    assert ctx.values.shared == "updated"
    assert ctx.route is not None and ctx.route.tag == "done"
    assert ctx.event is not None and ctx.event.tag == "progress"
    assert ctx.outcome.status == "ok"
    assert ctx.meta.source == "test"
    assert ctx.answer == "42"
    assert ctx.input_response == {"approved": True}
    assert ctx.step_state.visits == 1
    assert ctx.item_state.status == "queued"
    assert ctx.step_item_state.visits == 2
    assert ctx.state.counter == 3
    assert ctx._execution_frame.state_cell is ctx.state_cell


def test_context_private_mutator_facade_updates_execution_frame_and_legacy_fields(tmp_path: Path) -> None:
    ctx = _make_context(tmp_path, values={"shared": "root"})
    updated_values = {"shared": "updated", "count": 2}

    ctx._set_values(updated_values)
    ctx._set_route({"tag": "done"})
    ctx._set_event({"tag": "progress"})
    ctx._set_outcome({"status": "ok"})
    ctx._set_meta({"source": "test"})
    ctx._execution_frame.answer = "42"
    ctx._execution_frame.input_response = {"approved": True}
    ctx._set_step_state({"visits": 1, "last_route": None, "last_reason": None})
    ctx._set_item_state({"status": "queued"})
    ctx._set_step_item_state({"visits": 2, "last_route": "done", "last_reason": None})
    ctx._set_state(ctx.state.model_copy(update={"counter": 3}))

    assert ctx._execution_frame.values is updated_values
    assert ctx._values is updated_values
    assert ctx.values.shared == "updated"
    assert ctx.route is not None and ctx.route.tag == "done"
    assert ctx.event is not None and ctx.event.tag == "progress"
    assert ctx.outcome.status == "ok"
    assert ctx.meta.source == "test"
    assert ctx.answer == "42"
    assert ctx.input_response == {"approved": True}
    assert ctx.step_state.visits == 1
    assert ctx.item_state.status == "queued"
    assert ctx.step_item_state.visits == 2
    assert ctx.state.counter == 3
    assert ctx._execution_frame.state_cell is ctx.state_cell


def test_worklist_runtime_mutators_keep_frame_and_public_selection_in_sync(tmp_path: Path) -> None:
    gates = Worklist.from_items(name="gate", items=({"id": "alpha", "title": "Alpha"},))
    ctx = _make_context(
        tmp_path,
        worklists={"gate": gates},
        selection_snapshots={
            "gate": SelectionSnapshot(
                worklist_name="gate",
                mode="single",
                items=(WorkItemSnapshot(id="alpha", title="Alpha"),),
                explicit=True,
            )
        },
    )
    selection = gates.initial_selection(ctx)

    ctx._execution_frame.set_selection("gate", selection)
    ctx._execution_frame.set_active_worklist("gate")

    assert ctx._execution_frame.selections == {"gate": selection}
    assert ctx._execution_frame.selection_snapshots == {}
    assert ctx._execution_frame.active_worklist == "gate"
    assert ctx._selection_snapshots == {}
    assert ctx.selection("gate") is selection
    assert ctx.current_worklist.current_id == "alpha"


def test_context_selection_mutator_clears_only_touched_snapshot_and_runs_sync(tmp_path: Path) -> None:
    gates = Worklist.from_items(name="gate", items=({"id": "alpha", "title": "Alpha"},))
    later = Worklist.from_items(name="later", items=({"id": "beta", "title": "Beta"},))
    snapshots = {
        "gate": SelectionSnapshot(
            worklist_name="gate",
            mode="single",
            items=(WorkItemSnapshot(id="alpha", title="Alpha"),),
            explicit=True,
        ),
        "later": SelectionSnapshot(
            worklist_name="later",
            mode="single",
            items=(WorkItemSnapshot(id="beta", title="Beta"),),
            explicit=True,
        ),
    }
    ctx = _make_context(
        tmp_path,
        worklists={"gate": gates, "later": later},
        selection_snapshots=snapshots,
    )
    sync_calls: list[str] = []
    selection = gates.initial_selection(ctx)

    ctx._set_worklist_selection_sync(sync_calls.append)
    ctx._set_worklist_selection("gate", selection)

    assert ctx.selection("gate") is selection
    assert ctx._selection_snapshots == {"later": snapshots["later"]}
    assert ctx._execution_frame.selection_snapshots == {"later": snapshots["later"]}
    assert sync_calls == ["gate"]


def test_branch_child_context_uses_child_frame_and_preserves_shared_state(tmp_path: Path) -> None:
    gates = Worklist.from_items(name="gate", items=({"id": "alpha", "title": "Alpha"},))
    snapshots = {
        "gate": SelectionSnapshot(
            worklist_name="gate",
            mode="single",
            items=(WorkItemSnapshot(id="alpha", title="Alpha"),),
            explicit=True,
        )
    }
    parent = _make_context(
        tmp_path,
        values={"shared": "root"},
        worklists={"gate": gates},
        selection_snapshots=snapshots,
    )

    branch = create_branch_context(
        parent,
        step_name="assess",
        branch=BranchMetadata(name="security", index=0, group="reviews", input={"area": "security"}, count=1),
        session_store=parent._session_store,
        step_state_store={"visits": 1, "last_route": None, "last_reason": None},
    )

    assert branch.state_cell is parent.state_cell
    assert branch._execution_frame.state_cell is parent._execution_frame.state_cell
    assert branch._execution_frame.branch == BranchMetadata(
        name="security",
        index=0,
        group="reviews",
        input={"area": "security"},
        count=1,
    )
    assert branch._execution_frame.fan_in is None
    assert branch._execution_frame.selection_snapshots == snapshots
    assert branch._execution_frame.selection_snapshots is not parent._execution_frame.selection_snapshots
    assert branch._execution_frame.worklist_selection_resolver is not None
    assert branch._execution_frame.worklist_selection_resolver is not parent._execution_frame.worklist_selection_resolver
    assert branch._execution_frame.worklist_items_cache == {}
    assert branch._execution_frame.worklist_items_cache is not parent._execution_frame.worklist_items_cache

    branch.values.shared = "branch"
    branch.state = branch.state.model_copy(update={"counter": 5})
    branch._execution_frame.set_selection_snapshots({})

    assert parent.values.shared == "branch"
    assert parent.state.counter == 5
    assert parent._selection_snapshots == snapshots
    assert branch._selection_snapshots == {}


def test_branch_child_lazy_selection_uses_context_selection_mutator_path(tmp_path: Path) -> None:
    gates = Worklist.from_items(name="gate", items=({"id": "alpha", "title": "Alpha"},))
    snapshots = {
        "gate": SelectionSnapshot(
            worklist_name="gate",
            mode="single",
            items=(WorkItemSnapshot(id="alpha", title="Alpha"),),
            explicit=True,
        )
    }
    parent = _make_context(
        tmp_path,
        values={"shared": "root"},
        worklists={"gate": gates},
        selection_snapshots=snapshots,
    )
    branch = create_branch_context(
        parent,
        step_name="assess",
        branch=BranchMetadata(name="security", index=0, group="reviews", input={"area": "security"}, count=1),
        session_store=parent._session_store,
        step_state_store={"visits": 1, "last_route": None, "last_reason": None},
    )
    sync_calls: list[str] = []

    branch._set_worklist_selection_sync(sync_calls.append)
    selection = branch.ensure_selection("gate")

    assert branch.selection("gate") is selection
    assert branch._selection_snapshots == {}
    assert parent._selection_snapshots == snapshots
    assert parent._selections == {}
    assert sync_calls == ["gate"]


def test_fan_in_child_context_exposes_fan_in_frame_metadata(tmp_path: Path) -> None:
    parent = _make_context(tmp_path)
    fan_in = create_fan_in_context(
        parent,
        step_name="combine",
        fan_in=FanInMetadata(
            results={"branches": []},
            results_path=parent.workflow_folder / "_branch_groups" / "reviews" / "results.json",
            context_path=parent.workflow_folder / "_branch_groups" / "reviews" / "context.md",
            context_text="# Reviews",
            branch_count=2,
            completed_count=1,
            failed_count=0,
            needs_input_count=1,
            cancelled_count=0,
        ),
        session_store=parent._session_store,
    )

    assert fan_in._execution_frame.branch is None
    assert fan_in._execution_frame.fan_in is not None
    assert fan_in.fan_in.context_text == "# Reviews"
    assert fan_in.fan_in.needs_input_count == 1
