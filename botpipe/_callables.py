"""Structural descriptions of executable Python callables.

This module deliberately has no Botpipe or codec imports.  It describes the
callable itself, but never walks a bound receiver or a callable instance's
state. Source capture and fingerprinting share this structural description.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from functools import partial
from types import ModuleType
from typing import Any


@dataclass(frozen=True)
class CallableDescriptor:
    kind: str
    implementation: Any | None = None
    child: "CallableDescriptor | None" = None
    args: tuple[Any, ...] = ()
    kwargs: tuple[tuple[str, Any], ...] = ()
    source_targets: tuple[Any, ...] = ()
    boundary_targets: tuple[Any, ...] = ()
    reference: str | None = None


def _unique(values: tuple[Any, ...]) -> tuple[Any, ...]:
    result = []
    seen = set()
    for value in values:
        identity = id(value)
        if identity not in seen:
            seen.add(identity)
            result.append(value)
    return tuple(result)


def _class_targets(cls: type) -> tuple[type, ...]:
    return tuple(base for base in cls.__mro__ if base is not object)


def describe_callable(value: Any) -> CallableDescriptor:
    """Normalize supported callables without changing the object to execute."""

    active: set[int] = set()

    def describe(current: Any) -> CallableDescriptor:
        marker = id(current)
        if marker in active:
            raise TypeError("Callable wrappers contain a cycle")
        active.add(marker)
        try:
            if (
                type(current).__module__ == "botpipe.runtime"
                and type(current).__name__ == "Workflow"
            ):
                child = describe(current.fn)
                return CallableDescriptor(
                    "workflow",
                    implementation=current,
                    child=child,
                    source_targets=child.source_targets,
                    boundary_targets=child.boundary_targets,
                )
            if isinstance(current, partial):
                child = describe(current.func)
                dependencies = tuple(
                    describe(bound)
                    for bound in (
                        *current.args,
                        *(current.keywords or {}).values(),
                    )
                    if callable(bound)
                )
                return CallableDescriptor(
                    "partial",
                    child=child,
                    args=tuple(current.args),
                    kwargs=tuple((current.keywords or {}).items()),
                    source_targets=_unique(
                        (
                            *child.source_targets,
                            *(
                                target
                                for dependency in dependencies
                                for target in dependency.source_targets
                            ),
                        )
                    ),
                    boundary_targets=_unique(
                        (
                            *child.boundary_targets,
                            *(
                                target
                                for dependency in dependencies
                                for target in dependency.boundary_targets
                            ),
                        )
                    ),
                )
            if inspect.ismethod(current):
                child = describe(current.__func__)
                owner = (
                    current.__self__
                    if isinstance(current.__self__, type)
                    else type(current.__self__)
                )
                owner_targets = _class_targets(owner)
                return CallableDescriptor(
                    "method",
                    implementation=owner,
                    child=child,
                    source_targets=_unique((*child.source_targets, *owner_targets)),
                    boundary_targets=_unique((*child.boundary_targets, owner)),
                )
            if inspect.isfunction(current):
                wrapped = getattr(current, "__wrapped__", None)
                if wrapped is not None:
                    child = describe(wrapped)
                    return CallableDescriptor(
                        "decorated",
                        implementation=current,
                        child=child,
                        source_targets=_unique((current, *child.source_targets)),
                        boundary_targets=_unique((current, *child.boundary_targets)),
                    )
                return CallableDescriptor(
                    "function",
                    implementation=current,
                    source_targets=(current,),
                    boundary_targets=(current,),
                )
            if inspect.isbuiltin(current):
                receiver = getattr(current, "__self__", None)
                owner = None
                if receiver is not None and not isinstance(receiver, ModuleType):
                    owner = receiver if isinstance(receiver, type) else type(receiver)
                reference = (
                    f"{owner.__module__}:{owner.__qualname__}.{current.__name__}"
                    if owner is not None
                    else (
                        f"{getattr(current, '__module__', 'builtins')}:"
                        f"{current.__name__}"
                    )
                )
                return CallableDescriptor(
                    "builtin",
                    reference=reference,
                )
            if inspect.ismethoddescriptor(current):
                owner = current.__objclass__
                return CallableDescriptor(
                    "method_descriptor",
                    reference=(
                        f"{owner.__module__}:{owner.__qualname__}.{current.__name__}"
                    ),
                )
            if inspect.isclass(current):
                targets = _class_targets(current)
                return CallableDescriptor(
                    "class",
                    implementation=current,
                    source_targets=targets,
                    boundary_targets=(current,),
                )
            if callable(current):
                cls = type(current)
                targets = _class_targets(cls)
                return CallableDescriptor(
                    "instance",
                    implementation=cls,
                    source_targets=targets,
                    boundary_targets=(cls,),
                )
            raise TypeError(
                f"Unsupported callable type {type(current).__module__}."
                f"{type(current).__qualname__}"
            )
        finally:
            active.remove(marker)

    return describe(value)


__all__ = ["CallableDescriptor", "describe_callable"]
