"""State validation facade."""

from .validation import _validate_state, _validate_worklists, WorkflowDefinition


def validate_state(definition: WorkflowDefinition) -> None:
    _validate_state(definition)


def validate_worklists(definition: WorkflowDefinition) -> None:
    _validate_worklists(definition)


__all__ = [
    "validate_state",
    "validate_worklists",
]
