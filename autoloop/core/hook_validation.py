"""Hook validation facade."""

from __future__ import annotations

from typing import Any

from .validation import _validate_callable_arity, _validate_step_hooks, WorkflowDefinition


def validate_hook_arity(name: str, func: Any, expected: set[int]) -> None:
    _validate_callable_arity(name, func, expected)


def validate_step_hooks(definition: WorkflowDefinition) -> None:
    _validate_step_hooks(definition)


__all__ = [
    "validate_hook_arity",
    "validate_step_hooks",
]
