"""Hook and handler signature validation."""

from __future__ import annotations

import inspect
from typing import Any

from .discovery import has_start_hook
from .errors import WorkflowValidationError
from .lowering import outcome_middleware_name
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

    for step in definition.steps:
        handler_name = f"on_{step.name}"
        raw_handler = getattr(definition.workflow_cls, handler_name, None)
        if isinstance(step, PythonStep):
            active_handler = step.handler if step.handler is not None else raw_handler
            if active_handler is None:
                raise WorkflowValidationError(f"system step {step.name!r} is missing handler {handler_name!r}")
            validate_callable_arity(handler_name, active_handler, {1, 2})
            continue
        if raw_handler is not None:
            validate_callable_arity(handler_name, raw_handler, {3})

    active_middleware = outcome_middleware_name(definition)
    raw_middleware = getattr(definition.workflow_cls, active_middleware, None) if active_middleware else None
    if raw_middleware is not None:
        validate_callable_arity(active_middleware, raw_middleware, {2})

    if has_start_hook(definition):
        raw_start = getattr(definition.workflow_cls, "on_start", None)
        if raw_start is not None:
            validate_callable_arity("on_start", raw_start, {2})

    reserved_handler_names: set[str] = set()
    if has_start_hook(definition):
        reserved_handler_names.add("on_start")
    if active_middleware is not None:
        reserved_handler_names.add(active_middleware)

    for handler_name in handler_names:
        if handler_name in reserved_handler_names:
            continue
        step_name = handler_name[3:]
        if step_name not in definition.steps_by_name:
            raise WorkflowValidationError(f"orphan handler {handler_name!r} does not match any step")


def validate_step_hooks(definition: Any) -> None:
    for step in definition.steps:
        if step.before is not None:
            validate_callable_arity(f"{step.name!r} before hook", step.before, {1, 2})
        if step.after is not None:
            validate_callable_arity(f"{step.name!r} after hook", step.after, {1, 2, 3, 4})
        for route_name, destination in definition.transitions.get(step, {}).items():
            route = normalize_route_spec(destination)
            if route.on_taken is not None:
                validate_callable_arity(f"{step.name!r} route {route_name!r} on_taken hook", route.on_taken, {1})
        if isinstance(step, ProduceVerifyStep):
            if getattr(step, "before_do", None) is not None:
                validate_callable_arity(f"{step.name!r} before_do hook", step.before_do, {1, 2})
            if getattr(step, "after_do", None) is not None:
                validate_callable_arity(f"{step.name!r} after_do hook", step.after_do, {1, 2, 3, 4})
            if getattr(step, "before_review", None) is not None:
                validate_callable_arity(f"{step.name!r} before_review hook", step.before_review, {1, 2})
            if getattr(step, "after_review", None) is not None:
                validate_callable_arity(f"{step.name!r} after_review hook", step.after_review, {1, 2, 3, 4})


__all__ = [
    "validate_callable_arity",
    "validate_handlers",
    "validate_step_hooks",
]
