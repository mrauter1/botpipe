"""Workflow state and declaration-shape validation."""

from __future__ import annotations

import inspect
from typing import Any

from pydantic import BaseModel

from .errors import WorkflowValidationError
from .steps import ProduceVerifyStep, PythonStep


def validate_state(definition: Any) -> None:
    if not inspect.isclass(definition.state_cls) or not issubclass(definition.state_cls, BaseModel):
        raise WorkflowValidationError("workflow must define nested State inheriting from pydantic.BaseModel")


def validate_entry(definition: Any) -> None:
    if definition.entry is None or not hasattr(definition.entry, "name"):
        raise WorkflowValidationError("workflow entry must exist and be a step")
    if definition.entry.name not in definition.steps_by_name:
        raise WorkflowValidationError("workflow entry step must be declared on the workflow class")


def validate_transitions_shape(definition: Any) -> None:
    if not isinstance(definition.transitions, dict):
        raise WorkflowValidationError("workflow transitions must be a dict")
    for source, routes in definition.transitions.items():
        if source != definition.global_route_sentinel and not hasattr(source, "name"):
            raise WorkflowValidationError(f"transition source {source!r} must be a step or GLOBAL")
        if not isinstance(routes, dict):
            raise WorkflowValidationError("each transition table must be a dict")
        for tag in routes:
            if not isinstance(tag, str) or not tag.strip():
                raise WorkflowValidationError("transition route tags must be non-empty strings")


def validate_sessions(definition: Any) -> None:
    declared_sessions = {id(session) for session in definition.sessions_by_name.values()}
    for step in definition.steps:
        if step.session is not None and id(step.session) not in declared_sessions:
            raise WorkflowValidationError(f"step {step.name!r} references an undeclared session slot")
        if isinstance(step, ProduceVerifyStep) and step.verifier_session is not None and id(step.verifier_session) not in declared_sessions:
            raise WorkflowValidationError(
                f"step {step.name!r} references an undeclared verifier session slot"
            )


def validate_worklists(definition: Any) -> None:
    declared_worklists = definition.worklists_by_name
    for step in definition.steps:
        if getattr(step, "item_state", None) is not None and step.scope is None:
            raise WorkflowValidationError(f"step {step.name!r} item_state requires scope on the same step")
        if step.scope is None:
            continue
        if isinstance(step, PythonStep):
            raise WorkflowValidationError(f"python_step {step.name!r} cannot declare scope")
        scope_name = _resolve_worklist_name(step.scope)
        if scope_name not in declared_worklists:
            raise WorkflowValidationError(
                f"step {step.name!r} references unknown worklist {scope_name!r}"
            )


def validate_extensions(definition: Any) -> None:
    if not isinstance(definition.extensions, tuple):
        raise WorkflowValidationError("workflow extensions must be declared as a tuple")
    for extension in definition.extensions:
        if not callable(getattr(extension, "bind", None)):
            raise WorkflowValidationError(
                f"workflow extension {extension!r} must define a callable bind(binding) method"
            )


def _resolve_worklist_name(worklist: object | str) -> str:
    return worklist if isinstance(worklist, str) else getattr(worklist, "name", None)


__all__ = [
    "validate_entry",
    "validate_extensions",
    "validate_sessions",
    "validate_state",
    "validate_transitions_shape",
    "validate_worklists",
]
