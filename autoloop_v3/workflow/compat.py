"""Compatibility normalization boundary."""

from __future__ import annotations

from typing import Any

from .artifacts import ResolvedArtifacts
from .context import Context
from .primitives import Event, FAIL, GLOBAL, Outcome, PAUSE, SUCCESS, Verdict
from .steps import Step
from .validation import WorkflowMeta


class LegacyWorkflow:
    """Permissive workflow base for unchanged legacy imports via the root shim."""

    __workflow_abstract__ = True
    __legacy_workflow__ = True


_TERMINAL_DESTINATIONS = {SUCCESS, PAUSE, FAIL}


def legacy_annotation_globals() -> dict[str, Any]:
    """Globals injected before executing legacy workflow modules."""

    return {
        "Context": Context,
        "Event": Event,
        "Outcome": Outcome,
        "ResolvedArtifacts": ResolvedArtifacts,
        "Verdict": Verdict,
    }


def normalize_workflow(workflow_cls: type[Any]) -> type[Any]:
    """Normalize a legacy workflow class into the strict validated model."""

    if getattr(workflow_cls, "__strict_workflow__", False):
        return workflow_cls

    cached = getattr(workflow_cls, "__normalized_workflow__", None)
    if isinstance(cached, type) and getattr(cached, "__strict_workflow__", False):
        return cached

    namespace = {
        key: value
        for key, value in vars(workflow_cls).items()
        if key not in {"__dict__", "__weakref__", "__workflow_definition__", "__compiled_workflow__"}
    }
    namespace["__module__"] = workflow_cls.__module__
    namespace["__doc__"] = workflow_cls.__doc__
    namespace["__qualname__"] = workflow_cls.__qualname__
    namespace["__workflow_abstract__"] = False
    namespace["__strict_workflow__"] = True
    namespace["__legacy_workflow_origin__"] = workflow_cls

    steps = _declared_steps(namespace)
    if ("entry" not in namespace or namespace["entry"] is None) and steps:
        namespace["entry"] = steps[0]
    elif isinstance(namespace.get("entry"), str):
        step_by_name = {step.name: step for step in steps}
        namespace["entry"] = step_by_name.get(namespace["entry"], namespace["entry"])

    if isinstance(namespace.get("transitions"), dict):
        namespace["transitions"] = _normalize_transitions(namespace["transitions"], steps)

    normalized = WorkflowMeta(workflow_cls.__name__, (), namespace)
    workflow_cls.__normalized_workflow__ = normalized
    return normalized


def _declared_steps(namespace: dict[str, Any]) -> list[Step]:
    steps = [value for value in namespace.values() if isinstance(value, Step)]
    return sorted(steps, key=lambda step: step._order)


def _normalize_transitions(
    transitions: dict[Any, Any],
    steps: list[Step],
) -> dict[Any, Any]:
    step_by_name = {step.name: step for step in steps}
    normalized: dict[Any, Any] = {}
    for source, routes in transitions.items():
        normalized_source = _normalize_source(source, step_by_name)
        if not isinstance(routes, dict):
            normalized[normalized_source] = routes
            continue
        normalized[normalized_source] = {
            tag: _normalize_destination(destination, step_by_name)
            for tag, destination in routes.items()
        }
    return normalized


def _normalize_source(source: Any, step_by_name: dict[str, Step]) -> Any:
    if isinstance(source, str) and source != GLOBAL:
        return step_by_name.get(source, source)
    return source


def _normalize_destination(destination: Any, step_by_name: dict[str, Step]) -> Any:
    if isinstance(destination, str) and destination not in _TERMINAL_DESTINATIONS | {GLOBAL}:
        return step_by_name.get(destination, destination)
    return destination
