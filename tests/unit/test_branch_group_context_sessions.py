from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import BaseModel

import botlane.simple as simple
from botlane.core.branch_groups.context import (
    BranchMetadata,
    FanInMetadata,
    create_branch_context,
    create_fan_in_context,
)
from botlane.core.branch_groups.sessions import BranchSessionStoreView
from botlane.core.context import Context
from botlane.core.engine import Engine, StepFinalizationRecord
from botlane.core.engine_collaborators import StepExecutionResult
from botlane.core.errors import WorkflowExecutionError
from botlane.core.providers.fake import ScriptedLLMProvider
from botlane.core.sessions import Continuity
from botlane.core.stores import InMemoryCheckpointStore, InMemorySessionStore, SessionBinding
from botlane.core.worklists import Worklist


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

    branch._execution_frame.set_state(branch.state.model_copy(update={"counter": 2}))
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
    branch._execution_frame.set_step_state({"visits": 3})
    branch._emit_runtime_event("branch_started")

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


def test_branch_and_fan_in_contexts_preserve_parent_request_snapshot(tmp_path: Path) -> None:
    class Input(BaseModel):
        topic: str

    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_example"
    run_folder = workflow_folder / "runs" / "run-1"
    package_folder = tmp_path / "package"
    run_folder.mkdir(parents=True)
    package_folder.mkdir(parents=True)
    (task_folder / "request.md").write_text("Task request\n", encoding="utf-8")
    (run_folder / "request.md").write_text("Branch-safe request\n", encoding="utf-8")

    parent = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        state=_State(),
        workflow_input=Input(topic="release"),
        session_store=InMemorySessionStore(),
    )
    branch = create_branch_context(
        parent,
        step_name="assess",
        branch=BranchMetadata(name="security", index=0, group="reviews", input={}, count=1),
        session_store=BranchSessionStoreView(parent._session_store, namespace="reviews.security"),
    )
    fan_in = create_fan_in_context(
        parent,
        step_name="combine",
        fan_in=FanInMetadata(
            results={"branches": []},
            results_path=workflow_folder / "_branch_groups" / "reviews" / "results.json",
            context_path=workflow_folder / "_branch_groups" / "reviews" / "context.md",
            context_text="# Reviews",
            branch_count=1,
            completed_count=1,
            failed_count=0,
            needs_input_count=0,
            cancelled_count=0,
        ),
        session_store=parent._session_store,
    )

    for child in (branch, fan_in):
        assert child.request_file == parent.request_file
        assert child.request.task_file == parent.request.task_file
        assert child.message == "Branch-safe request"
        assert child.input_fields is parent.input_fields
        assert child.input.message == "Branch-safe request"
        assert child.input.topic == "release"


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

    assert branch_store.get("main") is None
    assert branch.get_session("main") is None
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


def test_branch_session_store_view_uses_distinct_fresh_keys_per_branch_namespace(tmp_path: Path) -> None:
    parent = _make_context(tmp_path)
    parent_binding = parent.open_session("main")

    security_branch = create_branch_context(
        parent,
        step_name="assess",
        branch=BranchMetadata(name="security", index=0, group="reviews", input={}, count=2),
        session_store=BranchSessionStoreView(parent._session_store, namespace="reviews:security:0"),
    )
    performance_branch = create_branch_context(
        parent,
        step_name="assess",
        branch=BranchMetadata(name="performance", index=1, group="reviews", input={}, count=2),
        session_store=BranchSessionStoreView(parent._session_store, namespace="reviews:performance:1"),
    )

    security_binding = security_branch.open_session("main", continuity=Continuity.fresh())
    performance_binding = performance_branch.open_session("main", continuity=Continuity.fresh())

    assert security_binding.session_id is None
    assert performance_binding.session_id is None
    assert security_binding.key.domain == "fresh"
    assert performance_binding.key.domain == "fresh"
    assert security_binding.key.value.startswith("reviews:security:0:")
    assert performance_binding.key.value.startswith("reviews:performance:1:")
    assert security_binding.key != performance_binding.key
    assert security_branch.get_session("main") == security_binding
    assert performance_branch.get_session("main") == performance_binding
    assert parent.get_session("main") == parent_binding


def test_branch_session_store_view_snapshot_is_branch_local_only(tmp_path: Path) -> None:
    parent = _make_context(tmp_path)
    parent_binding = parent.open_session("main")
    branch_store = BranchSessionStoreView(parent._session_store, namespace="reviews.security")

    snapshot = branch_store.snapshot()

    assert snapshot.bindings == ()
    assert snapshot.active_keys_by_slot == {}
    assert parent.get_session("main") == parent_binding

    branch_binding = branch_store.open("main")
    branch_snapshot = branch_store.snapshot()

    assert branch_snapshot.bindings == (branch_binding,)
    assert branch_snapshot.active_keys_by_slot == {"main": branch_binding.key}
    assert all(binding.key != parent_binding.key for binding in branch_snapshot.bindings)


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


def test_branch_result_payload_builder_does_not_double_increment_rework_count(tmp_path: Path) -> None:
    class BranchWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        producer = simple.Session.fresh()
        verifier = simple.Session.fresh()
        reviews = simple.parallel(
            branches={
                "security": simple.produce_verify_step(
                    producer_prompt="Draft branch.",
                    verifier_prompt="Verify branch.",
                    name="review_branch",
                    session=producer,
                    verifier_session=verifier,
                ),
            }
        )

    engine = Engine(
        BranchWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )
    parent = _make_context(
        tmp_path,
        session_store=InMemorySessionStore(),
        session_definitions=engine.compiled.sessions,
    )
    group_step = engine.compiled.steps["reviews"]
    spec = group_step.branch_group
    assert spec is not None
    branch = spec.branches[0]
    step_state_store = branch.step.step_state_model()
    step_state_store.rework_count = 1
    branch_context = create_branch_context(
        parent,
        step_name=branch.step.name,
        branch=BranchMetadata(name=branch.name, index=branch.index, group=spec.name, input=branch.input, count=1),
        session_store=BranchSessionStoreView(parent._session_store, namespace="reviews.security"),
        step_state_store=step_state_store,
    )

    payload = engine.branch_group_runtime._branch_result_from_step_result(
        spec=spec,
        branch=branch,
        compiled_step=branch.step,
        branch_context=branch_context,
        step_result=StepExecutionResult(
            state=branch_context.state,
            destination=branch.step.name,
            event=simple.Event("needs_rework", reason="Retry the branch."),
            outcome=None,
            pending_handoffs=(),
            finalization=StepFinalizationRecord(final_route="needs_rework"),
        ),
        branch_dir=parent.workflow_folder / "_branch_groups" / spec.name / "branches" / branch.name,
        started_at=datetime.now(timezone.utc),
    )

    assert payload["route"] == "needs_rework"
    assert step_state_store.rework_count == 1


def test_failed_branch_result_reads_provider_session_snapshot_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class BranchWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        main = simple.Session.fresh()
        reviews = simple.parallel(
            branches={"security": simple.step("Review security.", name="review_branch", session=main)}
        )

    engine = Engine(
        BranchWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )
    parent = _make_context(
        tmp_path,
        session_store=InMemorySessionStore(),
        session_definitions=engine.compiled.sessions,
    )
    group_step = engine.compiled.steps["reviews"]
    spec = group_step.branch_group
    assert spec is not None
    branch = spec.branches[0]
    branch_context = create_branch_context(
        parent,
        step_name=branch.step.name,
        branch=BranchMetadata(name=branch.name, index=branch.index, group=spec.name, input=branch.input, count=1),
        session_store=BranchSessionStoreView(parent._session_store, namespace="reviews.security"),
        step_state_store=branch.step.step_state_model(),
    )
    calls = 0

    def fake_snapshot(*args: object, **kwargs: object) -> tuple[str | None, dict[str, str]]:
        nonlocal calls
        calls += 1
        return "branch-session", {"producer": "branch-session"}

    monkeypatch.setattr(engine.branch_group_runtime, "_provider_session_snapshot", fake_snapshot)

    payload = engine.branch_group_runtime._failed_branch_result(
        spec=spec,
        branch=branch,
        compiled_step=branch.step,
        branch_context=branch_context,
        branch_dir=parent.workflow_folder / "_branch_groups" / spec.name / "branches" / branch.name,
        started_at=datetime.now(timezone.utc),
        exc=RuntimeError("boom"),
    )

    assert calls == 1
    assert payload["provider_session"] == "branch-session"
    assert payload["provider_sessions"] == {"producer": "branch-session"}


def test_branch_runtime_rejects_scoped_compiled_branches_defensively(tmp_path: Path) -> None:
    class BranchWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        reviews = simple.parallel(
            branches={"security": simple.python_step(lambda ctx: simple.Event("done"), name="review_branch")}
        )

    engine = Engine(
        BranchWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )
    parent = _make_context(
        tmp_path,
        session_store=InMemorySessionStore(),
        session_definitions=engine.compiled.sessions,
    )
    group_step = engine.compiled.steps["reviews"]
    spec = group_step.branch_group
    assert spec is not None
    scoped_branch = replace(
        spec.branches[0],
        step=replace(spec.branches[0].step, scope_name="queue"),
    )

    with pytest.raises(AssertionError, match="does not support scoped branch step"):
        asyncio.run(engine.branch_group_runtime._execute_branch(spec, scoped_branch, parent))
