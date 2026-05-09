"""Internal mutable execution-frame state.

Not part of the public botlane authoring API.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping

from .run_paths import RunIdentity
from .workflow_plan import WorkflowPlan


_DEFAULT_FRAME_MESSAGE = object()


@dataclass(slots=True)
class ExecutionFrame:
    identity: RunIdentity | None = None
    workflow: WorkflowPlan | None = None

    state_cell: Any | None = None
    params: Any | None = None
    workflow_params: dict[str, Any] | None = None
    message: object = _DEFAULT_FRAME_MESSAGE
    input_fields: Any | None = None
    answer: str | None = None
    input_response: Any | None = None

    session_store: Any | None = None
    session_definitions: dict[str, Any] | None = None
    worklists: dict[str, Any] | None = None
    selections: dict[str, Any] | None = None
    selection_snapshots: dict[str, Any] | None = None
    active_worklist: str | None = None

    artifacts: Any | None = None
    values: dict[str, Any] | None = None
    route: Any | None = None
    event: Any | None = None
    outcome: Any | None = None
    meta: Any | None = None

    step_name: str | None = None
    step_execution_id: str | None = None
    step_state: Any | None = None
    item_state: Any | None = None
    step_item_state: Any | None = None

    branch: Any | None = None
    fan_in: Any | None = None

    runtime_event_sink: Callable[[str, Mapping[str, Any]], None] | None = None
    workflow_invoker: Callable[..., Any] | None = None

    def child_for_step(
        self,
        *,
        step_name: str | None,
        session_store: Any | None,
        route: Any | None = None,
        outcome: Any | None = None,
        meta: Any | None = None,
        step_state: Any | None = None,
        item_state: Any | None = None,
        step_item_state: Any | None = None,
        branch: Any | None = None,
        fan_in: Any | None = None,
        step_execution_id: str | None = None,
    ) -> ExecutionFrame:
        return replace(
            self,
            session_store=self.session_store if session_store is None else session_store,
            selections=dict(self.selections or {}),
            selection_snapshots=dict(self.selection_snapshots or {}),
            route=route,
            event=None,
            outcome=outcome,
            meta=meta,
            step_name=step_name,
            step_execution_id=step_execution_id,
            step_state=step_state,
            item_state=item_state,
            step_item_state=step_item_state,
            branch=branch,
            fan_in=fan_in,
        )

    def child_for_branch(
        self,
        *,
        step_name: str,
        branch: Any,
        session_store: Any | None,
        route: Any | None = None,
        outcome: Any | None = None,
        meta: Any | None = None,
        step_state: Any | None = None,
        item_state: Any | None = None,
        step_item_state: Any | None = None,
        step_execution_id: str | None = None,
    ) -> ExecutionFrame:
        return self.child_for_step(
            step_name=step_name,
            session_store=session_store,
            route=route,
            outcome=outcome,
            meta=meta,
            step_state=step_state,
            item_state=item_state,
            step_item_state=step_item_state,
            branch=branch,
            fan_in=None,
            step_execution_id=step_execution_id,
        )

    def child_for_fan_in(
        self,
        *,
        step_name: str,
        fan_in: Any,
        session_store: Any | None,
        route: Any | None = None,
        outcome: Any | None = None,
        meta: Any | None = None,
        step_state: Any | None = None,
        item_state: Any | None = None,
        step_item_state: Any | None = None,
        step_execution_id: str | None = None,
    ) -> ExecutionFrame:
        return self.child_for_step(
            step_name=step_name,
            session_store=session_store,
            route=route,
            outcome=outcome,
            meta=meta,
            step_state=step_state,
            item_state=item_state,
            step_item_state=step_item_state,
            branch=None,
            fan_in=fan_in,
            step_execution_id=step_execution_id,
        )

    def set_state(self, state: Any) -> Any:
        if self.state_cell is None:
            raise ValueError("ExecutionFrame.state_cell is required to set state")
        setter = getattr(self.state_cell, "set", None)
        if callable(setter):
            return setter(state)
        self.state_cell.value = state
        return state

    def set_artifacts(self, artifacts: Any | None) -> None:
        self.artifacts = artifacts

    def set_values(self, values: dict[str, Any] | None) -> None:
        self.values = values

    def set_route(self, route: Any | None) -> None:
        self.route = route

    def set_event(self, event: Any | None) -> None:
        self.event = event

    def set_outcome(self, outcome: Any | None) -> None:
        self.outcome = outcome

    def set_meta(self, meta: Any | None) -> None:
        self.meta = meta

    def set_step_state(self, step_state: Any | None) -> None:
        self.step_state = step_state

    def set_item_state(self, item_state: Any | None) -> None:
        self.item_state = item_state

    def set_step_item_state(self, step_item_state: Any | None) -> None:
        self.step_item_state = step_item_state
