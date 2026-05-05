"""Shared context helpers for branch-group execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from ..errors import WorkflowExecutionError

if TYPE_CHECKING:
    from ..context import Context
    from ..worklists import Selection
    from ..stores.protocols import SessionStore


@dataclass(slots=True)
class StateCell:
    """Shared mutable state cell used across related contexts."""

    value: BaseModel
    version: int = 0

    def set(self, value: BaseModel) -> BaseModel:
        self.value = value
        self.version += 1
        return self.value


@dataclass(frozen=True, slots=True)
class BranchMetadata:
    """Runtime-visible metadata for one branch execution."""

    name: str
    index: int
    group: str
    input: Any
    count: int


@dataclass(frozen=True, slots=True)
class FanInMetadata:
    """Runtime-visible metadata for authored fan-in execution."""

    results: Any
    results_path: Path
    context_path: Path
    context_text: str
    branch_count: int
    completed_count: int
    failed_count: int
    needs_input_count: int
    cancelled_count: int


def branch_bookkeeping_key(*, group_name: str, branch_name: str, step_name: str) -> str:
    """Return the branch-scoped bookkeeping key for one step store."""

    return f"{group_name}:{branch_name}:{step_name}"


def branch_execution_id(*, group_name: str, branch_name: str, step_name: str, visit: int) -> str:
    """Return the canonical branch execution identifier."""

    return f"{group_name}:{branch_name}:{step_name}:{visit}"


def create_branch_context(
    parent: "Context",
    *,
    step_name: str,
    branch: BranchMetadata,
    session_store: "SessionStore",
    route: Mapping[str, Any] | Any | None = None,
    outcome: Mapping[str, Any] | Any | None = None,
    meta: Mapping[str, Any] | Any | None = None,
    step_state_store: BaseModel | dict[str, Any] | None = None,
    item_state_store: BaseModel | dict[str, Any] | None = None,
    step_item_state_store: BaseModel | dict[str, Any] | None = None,
) -> "Context":
    """Clone a parent runtime context for one branch execution."""

    return _create_child_context(
        parent,
        step_name=step_name,
        session_store=session_store,
        route=route,
        outcome=outcome,
        meta=meta,
        step_state_store=step_state_store,
        item_state_store=item_state_store,
        step_item_state_store=step_item_state_store,
        branch=branch,
        fan_in=None,
        step_execution_id=branch_execution_id(
            group_name=branch.group,
            branch_name=branch.name,
            step_name=step_name,
            visit=0,
        ),
    )


def create_fan_in_context(
    parent: "Context",
    *,
    step_name: str,
    fan_in: FanInMetadata,
    session_store: "SessionStore",
    route: Mapping[str, Any] | Any | None = None,
    outcome: Mapping[str, Any] | Any | None = None,
    meta: Mapping[str, Any] | Any | None = None,
    step_state_store: BaseModel | dict[str, Any] | None = None,
    item_state_store: BaseModel | dict[str, Any] | None = None,
    step_item_state_store: BaseModel | dict[str, Any] | None = None,
) -> "Context":
    """Clone a parent runtime context for authored fan-in execution."""

    return _create_child_context(
        parent,
        step_name=step_name,
        session_store=session_store,
        route=route,
        outcome=outcome,
        meta=meta,
        step_state_store=step_state_store,
        item_state_store=item_state_store,
        step_item_state_store=step_item_state_store,
        branch=None,
        fan_in=fan_in,
        step_execution_id=f"{step_name}:0",
    )


def _create_child_context(
    parent: "Context",
    *,
    step_name: str,
    session_store: "SessionStore",
    route: Mapping[str, Any] | Any | None,
    outcome: Mapping[str, Any] | Any | None,
    meta: Mapping[str, Any] | Any | None,
    step_state_store: BaseModel | dict[str, Any] | None,
    item_state_store: BaseModel | dict[str, Any] | None,
    step_item_state_store: BaseModel | dict[str, Any] | None,
    branch: BranchMetadata | None,
    fan_in: FanInMetadata | None,
    step_execution_id: str | None,
) -> "Context":
    """Clone a parent runtime context for branch-group nested execution."""

    from ..context import Context

    child = Context(
        root=parent.root,
        task_id=parent.task_id,
        run_id=parent.run_id,
        workflow_name=parent.workflow_name,
        task_folder=parent.task_folder,
        workflow_folder=parent.workflow_folder,
        run_folder=parent.run_folder,
        package_folder=parent.package_folder,
        state=parent.state,
        state_cell=parent.state_cell,
        session_store=session_store,
        session_definitions=parent._session_definitions,
        worklists=parent._worklists,
        selections=dict(parent._selections),
        selection_snapshots=dict(parent._selection_snapshots),
        active_worklist=parent._active_worklist,
        params=parent.params,
        workflow_params=parent._workflow_params,
        workflow_input=parent.input,
        workflow_invoker=parent._workflow_invoker,
        answer=parent.answer,
        input_response=parent.input_response,
        step_name=step_name,
        default_session_name=parent._default_session_name,
        artifacts=parent.artifacts,
        values=parent._values,
        route=route,
        outcome=outcome,
        meta=meta,
        step_state_store=step_state_store,
        item_state_store=item_state_store,
        step_item_state_store=step_item_state_store,
        runtime_event_sink=parent._runtime_event_sink,
        branch=branch,
        fan_in=fan_in,
        step_execution_id=step_execution_id,
    )
    _inherit_child_runtime_bookkeeping(parent, child)
    return child


def _inherit_child_runtime_bookkeeping(parent: "Context", child: "Context") -> None:
    """Initialize branch-local runtime bookkeeping from a parent context."""

    from ..context import context_runtime

    runtime = context_runtime(child)
    runtime.set_selection_snapshots(dict(parent._selection_snapshots))
    runtime.set_worklist_selection_resolver(_child_worklist_selection_resolver(child))
    child._worklist_items_cache = dict(parent._worklist_items_cache)


def _child_worklist_selection_resolver(child: "Context"):
    """Build a child-local lazy worklist selection resolver."""

    from ..context import context_runtime

    def resolve(worklist_name: str) -> "Selection[Any]":
        existing = child._selections.get(worklist_name)
        if existing is not None:
            return existing
        worklist = child._worklists.get(worklist_name)
        if worklist is None:
            raise WorkflowExecutionError(f"unknown worklist {worklist_name!r}")
        snapshot = child._selection_snapshots.get(worklist_name)
        worklist.ensure_source(child)
        items = worklist._load_source_items(child, ensure=False)
        worklist._validate_loaded_items(child, items)
        cached_items = worklist._cache_loaded_items(child, items)
        selection = worklist._selection_from_loaded_items(child, cached_items, snapshot=snapshot)
        runtime = context_runtime(child)
        runtime.set_selection(worklist_name, selection)
        runtime.sync_scoped_state_after_worklist_selection_change(worklist_name)
        runtime.emit_worklist_selection_resolved(
            worklist_name=worklist_name,
            selection=selection,
            lazy=True,
            source=worklist.source_descriptor(child),
        )
        return selection

    return resolve


__all__ = [
    "BranchMetadata",
    "FanInMetadata",
    "StateCell",
    "branch_bookkeeping_key",
    "branch_execution_id",
    "create_branch_context",
    "create_fan_in_context",
]
