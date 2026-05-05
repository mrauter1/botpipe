"""Shared context helpers for branch-group execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from ..context import Context
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

    from ..context import Context

    return Context(
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
        selections=parent._selections,
        selection_snapshots=parent._selection_snapshots,
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

    from ..context import Context

    return Context(
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
        selections=parent._selections,
        selection_snapshots=parent._selection_snapshots,
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
        fan_in=fan_in,
    )


__all__ = [
    "BranchMetadata",
    "FanInMetadata",
    "StateCell",
    "branch_bookkeeping_key",
    "branch_execution_id",
    "create_branch_context",
    "create_fan_in_context",
]
