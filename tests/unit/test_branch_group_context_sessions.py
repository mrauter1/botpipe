from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

import autoloop.simple as simple
from autoloop.core.branch_groups.context import (
    BranchMetadata,
    FanInMetadata,
    create_branch_context,
    create_fan_in_context,
)
from autoloop.core.branch_groups.sessions import BranchSessionStoreView
from autoloop.core.context import Context, context_runtime
from autoloop.core.engine import Engine
from autoloop.core.errors import WorkflowExecutionError
from autoloop.core.providers.fake import ScriptedLLMProvider
from autoloop.core.sessions import Continuity
from autoloop.core.stores import InMemoryCheckpointStore, InMemorySessionStore, SessionBinding
from autoloop.core.worklists import Worklist


class _State(BaseModel):
    counter: int = 0
    note: str = ""


def _make_context(
    tmp_path: Path,
    *,
    session_store: InMemorySessionStore | BranchSessionStoreView | None = None,
    session_definitions: dict[str, simple.Session] | None = None,
    values: dict[str, object] | None = None,
) -> Context:
    return Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=session_store or InMemorySessionStore(),
        session_definitions=session_definitions,
        values=values,
    )


def test_branch_context_shares_state_cell_values_and_branch_metadata(tmp_path: Path) -> None:
    shared_values = {"shared": "root"}
    parent = _make_context(tmp_path, values=shared_values)
    branch = create_branch_context(
        parent,
        step_name="assess",
        branch=BranchMetadata(name="security", index=0, group="reviews", input={"area": "security"}, count=2),
        session_store=BranchSessionStoreView(parent._session_store, namespace="reviews.security"),
    )

    assert parent.state_cell is branch.state_cell
    assert branch.branch.name == "security"
    assert branch.branch.group == "reviews"
    assert branch.branch.input.area == "security"

    branch.values.shared = "branch-updated"
    assert parent.values.shared == "branch-updated"

    branch.state = branch.state.model_copy(update={"counter": 1})
    assert parent.state.counter == 1
    assert parent.state_cell.version == 1

    context_runtime(branch).set_state(branch.state.model_copy(update={"counter": 2}))
    assert parent.state.counter == 2
    assert parent.state_cell.version == 2

    with pytest.raises(WorkflowExecutionError, match="branch metadata"):
        _ = parent.branch


def test_fan_in_context_exposes_metadata_and_branch_execution_ids(tmp_path: Path) -> None:
    emitted: list[tuple[str, dict[str, object]]] = []
    parent = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
        runtime_event_sink=lambda event_type, payload: emitted.append((event_type, dict(payload))),
    )
    branch = create_branch_context(
        parent,
        step_name="assess",
        branch=BranchMetadata(name="security", index=0, group="reviews", input={}, count=2),
        session_store=BranchSessionStoreView(parent._session_store, namespace="reviews.security"),
    )
    runtime = context_runtime(branch)
    runtime.set_step_state_store({"visits": 3})
    runtime.emit_runtime_event("branch_started")

    assert emitted[-1][1]["step_execution_id"] == "reviews:security:assess:3"

    fan_in = create_fan_in_context(
        parent,
        step_name="combine",
        fan_in=FanInMetadata(
            results={"branches": []},
            results_path=parent.workflow_folder / "_branch_groups" / "reviews" / "results.json",
            context_path=parent.workflow_folder / "_branch_groups" / "reviews" / "context.md",
            context_text="# Reviews",
            branch_count=2,
            completed_count=2,
            failed_count=0,
            needs_input_count=0,
            cancelled_count=0,
        ),
        session_store=parent._session_store,
    )

    assert fan_in.fan_in.branch_count == 2
    assert fan_in.fan_in.context_text == "# Reviews"
    with pytest.raises(WorkflowExecutionError, match="fan_in metadata"):
        _ = parent.fan_in


def test_branch_session_store_view_keeps_activation_local_to_branch(tmp_path: Path) -> None:
    parent = _make_context(tmp_path)
    parent_binding = parent.open_session("main")
    branch_store = BranchSessionStoreView(parent._session_store, namespace="reviews.security")
    branch = create_branch_context(
        parent,
        step_name="assess",
        branch=BranchMetadata(name="security", index=0, group="reviews", input={}, count=2),
        session_store=branch_store,
    )

    assert branch.get_session("main", continuity=Continuity.fresh()) is None
    fresh_binding = branch.open_session("main", continuity=Continuity.fresh())
    assert branch.get_session("main") == fresh_binding
    assert branch.get_session("main", continuity=Continuity.fresh()) == fresh_binding
    assert fresh_binding.key != parent_binding.key
    assert fresh_binding.key.domain == "fresh"
    assert fresh_binding.key.value.startswith("reviews.security:")
    assert fresh_binding.session_id is None
    assert parent.get_session("main") == parent_binding

    updated = SessionBinding(key=fresh_binding.key, session_id="branch-session-updated")
    branch_store.upsert(updated)

    assert branch.get_session("main").session_id == "branch-session-updated"
    assert parent.get_session("main").session_id == parent_binding.session_id


def test_branch_context_resolves_worklists_locally_without_mutating_parent(tmp_path: Path) -> None:
    worklist = Worklist.from_items(
        "items",
        (
            {"id": "one", "title": "One"},
            {"id": "two", "title": "Two"},
        ),
        item_id="id",
        title="title",
    )
    parent = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
        worklists={"items": worklist},
    )
    branch = create_branch_context(
        parent,
        step_name="assess",
        branch=BranchMetadata(name="security", index=0, group="reviews", input={}, count=1),
        session_store=BranchSessionStoreView(parent._session_store, namespace="reviews.security"),
    )

    selection = branch.selection("items")
    assert selection.current is not None
    assert selection.current.id == "one"
    assert "items" not in parent._selections
    assert "items" in branch._selections

    branch.worklist("items").advance()

    assert parent._selections == {}
    assert branch._selections["items"].current is not None
    assert branch._selections["items"].current.id == "two"
    assert parent._worklist_items_cache == {}
    assert "items" in branch._worklist_items_cache


def test_engine_session_selection_and_persistence_follow_context_store(tmp_path: Path) -> None:
    class SessionWorkflow(simple.Workflow):
        class State(BaseModel):
            done: bool = False

        main = simple.Session.fresh()
        ask = simple.step("Draft a response.", session=main)

    parent_store = InMemorySessionStore()
    engine = Engine(
        SessionWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=parent_store,
        checkpoint_store=InMemoryCheckpointStore(),
    )
    parent = _make_context(
        tmp_path,
        session_store=parent_store,
        session_definitions=engine.compiled.sessions,
    )
    parent_binding = parent.open_session("main")
    branch = create_branch_context(
        parent,
        step_name="ask",
        branch=BranchMetadata(name="security", index=0, group="reviews", input={}, count=1),
        session_store=BranchSessionStoreView(parent_store, namespace="reviews.security"),
    )

    step = engine.compiled.steps["ask"]
    binding = engine._select_session(step, branch)
    rebound = engine._select_session(step, branch)

    assert binding is not None
    assert binding == rebound
    assert binding.session_id is None
    assert binding.key.domain == "fresh"
    assert binding.key.value.startswith("reviews.security:")
    assert parent.get_session("main") == parent_binding
    assert parent_store.snapshot().active_keys_by_slot["main"] == parent_binding.key

    updated = SessionBinding(key=binding.key, session_id="provider-session")
    engine._persist_session(updated, context=branch)

    assert branch.get_session("main").session_id == "provider-session"
    assert parent_store.get(binding.key) is None
    assert parent.get_session("main") == parent_binding


def test_engine_hook_snapshot_and_restore_follow_branch_context_store(tmp_path: Path) -> None:
    class SessionWorkflow(simple.Workflow):
        class State(BaseModel):
            done: bool = False

        main = simple.Session.fresh()
        ask = simple.step("Draft a response.", session=main)

    parent_store = InMemorySessionStore()
    engine = Engine(
        SessionWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=parent_store,
        checkpoint_store=InMemoryCheckpointStore(),
    )
    parent = _make_context(
        tmp_path,
        session_store=parent_store,
        session_definitions=engine.compiled.sessions,
    )
    parent_binding = parent.open_session("main")
    branch = create_branch_context(
        parent,
        step_name="ask",
        branch=BranchMetadata(name="security", index=0, group="reviews", input={}, count=1),
        session_store=BranchSessionStoreView(parent_store, namespace="reviews.security"),
    )
    original_branch_binding = branch.open_session("main", continuity=Continuity.fresh())

    snapshot = engine._snapshot_hook_context(branch, branch.state)

    replacement_binding = branch.open_session("main", continuity=Continuity.fresh())
    assert replacement_binding.key != original_branch_binding.key
    assert branch.get_session("main") == replacement_binding
    assert parent.get_session("main") == parent_binding

    engine._restore_hook_context(branch, snapshot)

    assert branch.get_session("main") == original_branch_binding
    assert parent.get_session("main") == parent_binding
    assert parent_store.snapshot().active_keys_by_slot["main"] == parent_binding.key
