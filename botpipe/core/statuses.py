"""Central route, terminal, and run-status classification helpers."""

from __future__ import annotations

from .primitives import AWAIT_INPUT, FAIL, FINISH
from .step_state import DEFAULT_REPLAN_ROUTE_TAGS, DEFAULT_REWORK_ROUTE_TAGS


def is_terminal(value: str | None) -> bool:
    return value in {FINISH, AWAIT_INPUT, FAIL}


def terminal_to_run_status(terminal: str | None, *, final_route: str | None = None) -> str | None:
    if terminal == AWAIT_INPUT and final_route == "blocked":
        return "blocked"
    if terminal == FINISH:
        return "success"
    if terminal == AWAIT_INPUT:
        return "awaiting_input"
    if terminal == FAIL:
        return "failed"
    if terminal is None:
        return None
    return terminal.lower()


def runtime_control_to_terminal(runtime_control: str | None) -> str | None:
    if runtime_control == "request_input":
        return AWAIT_INPUT
    if runtime_control == "fail":
        return FAIL
    if runtime_control == "goto":
        return None
    return None


def route_is_rework(route: str | None) -> bool:
    return route in DEFAULT_REWORK_ROUTE_TAGS


def route_is_replan(route: str | None) -> bool:
    return route in DEFAULT_REPLAN_ROUTE_TAGS


def route_is_input_request(route: str | None) -> bool:
    return route == "question"


def normalize_run_status(value: str | None) -> str | None:
    if value == "paused":
        return "awaiting_input"
    return value


def route_to_step_status(route: str | None, *, completed: bool) -> str:
    if route is None:
        return "completed" if completed else "pending"
    if route in {"done", "accepted", "approved"}:
        return "completed"
    if route_is_input_request(route) or route == "blocked":
        return "awaiting_input"
    if route == "failed":
        return "failed"
    return route if completed else "running"


def finalization_to_step_status(
    *,
    final_route: str | None,
    runtime_control: str | None,
    terminal: str | None,
) -> str:
    resolved_terminal = terminal or runtime_control_to_terminal(runtime_control)
    if resolved_terminal == AWAIT_INPUT:
        return "awaiting_input"
    if resolved_terminal == FAIL:
        return "failed"
    if runtime_control == "goto":
        return "completed"
    return route_to_step_status(final_route, completed=True)


__all__ = [
    "finalization_to_step_status",
    "is_terminal",
    "normalize_run_status",
    "route_is_input_request",
    "route_is_replan",
    "route_is_rework",
    "route_to_step_status",
    "runtime_control_to_terminal",
    "terminal_to_run_status",
]
