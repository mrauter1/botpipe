"""Hook and handler signature validation."""

from __future__ import annotations

import inspect
from typing import Any

from .discovery import _uses_simple_authoring_model
from .errors import WorkflowValidationError
from .routes import normalize_route_spec
from .steps import ProduceVerifyStep, PythonStep


def validate_callable_arity(name: str, func: Any, expected: set[int]) -> None:
    signature = inspect.signature(func)
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if len(positional) not in expected:
        expected_text = " or ".join(str(value) for value in sorted(expected))
        raise WorkflowValidationError(f"{name!r} must accept {expected_text} positional arguments")


def validate_handlers(definition: Any) -> None:
    handler_names = {name for name in definition.workflow_cls.__dict__ if name.startswith("on_")}
    if _uses_simple_authoring_model(definition.workflow_cls) and handler_names:
        ordered_handler_names = ", ".join(sorted(handler_names))
        raise WorkflowValidationError(
            "simple workflows must declare lifecycle and step behavior on explicit step declarations; "
            f"remove legacy class-level handlers: {ordered_handler_names}"
        )
    for handler_name in handler_names:
        if handler_name == "on_start":
            raise WorkflowValidationError(
                "legacy workflow-level on_start handlers are no longer supported; use explicit step hooks instead"
            )
        if handler_name == "on_outcome":
            raise WorkflowValidationError(
                "legacy workflow-level on_outcome handlers are no longer supported; use explicit step hooks instead"
            )
        step_name = handler_name[3:]
        if step_name in definition.steps_by_name:
            raise WorkflowValidationError(
                f"legacy class-level step handler {handler_name!r} is no longer supported; "
                "declare behavior on the step itself"
            )
        raise WorkflowValidationError(f"orphan handler {handler_name!r} does not match any step")

    for step in definition.steps:
        if isinstance(step, PythonStep):
            if step.handler is None:
                raise WorkflowValidationError(f"python_step {step.name!r} is missing handler")
            validate_callable_arity(f"python_step {step.name!r} handler", step.handler, {1, 2})


def validate_step_hooks(definition: Any) -> None:
    for step in definition.steps:
        if step.before is not None:
            validate_callable_arity(f"{step.name!r} before hook", step.before, {1})
        if step.after is not None:
            validate_callable_arity(f"{step.name!r} after hook", step.after, {1})
        for route_name, destination in definition.transitions.get(step, {}).items():
            route = normalize_route_spec(destination)
            if route.on_taken is not None:
                validate_callable_arity(f"{step.name!r} route {route_name!r} on_taken hook", route.on_taken, {1})
        if isinstance(step, ProduceVerifyStep):
            if getattr(step, "before_producer", None) is not None:
                validate_callable_arity(f"{step.name!r} before_producer hook", step.before_producer, {1})
            if getattr(step, "after_producer", None) is not None:
                validate_callable_arity(f"{step.name!r} after_producer hook", step.after_producer, {1})
            if getattr(step, "before_verifier", None) is not None:
                validate_callable_arity(f"{step.name!r} before_verifier hook", step.before_verifier, {1})
            if getattr(step, "after_verifier", None) is not None:
                validate_callable_arity(f"{step.name!r} after_verifier hook", step.after_verifier, {1})


__all__ = [
    "validate_callable_arity",
    "validate_handlers",
    "validate_step_hooks",
]
