"""Descriptor-backed workflow state and parameter helpers."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, create_model


_MISSING = object()


class _TypedDescriptorFactory:
    __slots__ = ("_descriptor_cls", "_annotation")

    def __init__(self, descriptor_cls: type["_BaseDescriptor"], annotation: Any) -> None:
        self._descriptor_cls = descriptor_cls
        self._annotation = annotation

    def __call__(self, default: Any = _MISSING, *, default_factory: Any | None = None) -> "_BaseDescriptor":
        return self._descriptor_cls(default=default, default_factory=default_factory, annotation=self._annotation)


class _BaseDescriptor:
    __slots__ = ("annotation", "default", "default_factory", "name")

    def __init__(
        self,
        default: Any = _MISSING,
        *,
        default_factory: Any | None = None,
        annotation: Any = Any,
    ) -> None:
        if default is not _MISSING and default_factory is not None:
            raise ValueError("default and default_factory are mutually exclusive")
        self.annotation = annotation
        self.default = default
        self.default_factory = default_factory
        self.name: str | None = None

    def __set_name__(self, owner: type[object], name: str) -> None:
        self.name = name

    @classmethod
    def __class_getitem__(cls, annotation: Any) -> _TypedDescriptorFactory:
        return _TypedDescriptorFactory(cls, annotation)


class StateField(_BaseDescriptor):
    """Explicit workflow or step state declaration."""


class ParameterField(_BaseDescriptor):
    """Explicit workflow parameter declaration."""


@dataclass(frozen=True, slots=True)
class DescriptorField:
    name: str
    annotation: Any
    default: Any = _MISSING
    default_factory: Any | None = None

    def materialize_default(self) -> Any:
        if self.default_factory is not None:
            return self.default_factory()
        if self.default is _MISSING:
            return None
        return deepcopy(self.default)


def collect_descriptor_fields(
    workflow_cls: type[Any],
    *,
    descriptor_type: type[_BaseDescriptor],
) -> tuple[DescriptorField, ...]:
    fields: dict[str, DescriptorField] = {}
    hierarchy = [cls for cls in reversed(workflow_cls.__mro__) if cls is not object]
    for cls in hierarchy:
        for name, value in cls.__dict__.items():
            if not isinstance(value, descriptor_type):
                continue
            field_name = value.name or name
            fields[field_name] = DescriptorField(
                name=field_name,
                annotation=value.annotation,
                default=value.default,
                default_factory=value.default_factory,
            )
    return tuple(fields.values())


def build_descriptor_model(
    name: str,
    *,
    descriptor_fields: tuple[DescriptorField, ...],
    base_model: type[BaseModel] | None,
    module_name: str,
) -> type[BaseModel] | None:
    if not descriptor_fields:
        return base_model
    base = base_model or BaseModel
    field_definitions: dict[str, tuple[Any, Any]] = {}
    for field in descriptor_fields:
        if field.default_factory is not None:
            field_value = Field(default_factory=field.default_factory)
        elif field.default is _MISSING:
            field_value = ...
        else:
            field_value = deepcopy(field.default)
        field_definitions[field.name] = (field.annotation, field_value)
    return create_model(
        name,
        __base__=base,
        __module__=module_name,
        **field_definitions,
    )


def materialize_descriptor_defaults(fields: Mapping[str, DescriptorField] | tuple[DescriptorField, ...]) -> dict[str, Any]:
    if isinstance(fields, Mapping):
        iterable = fields.values()
    else:
        iterable = fields
    return {field.name: field.materialize_default() for field in iterable}


def _uses_simple_authoring_model(workflow_cls: type[Any]) -> bool:
    return any((base.__module__, base.__name__) == ("autoloop.simple", "Workflow") for base in workflow_cls.__mro__)


def effective_state_model(workflow_cls: type[Any], *, fallback_model: type[BaseModel]) -> type[BaseModel]:
    if _uses_simple_authoring_model(workflow_cls):
        base_model = getattr(workflow_cls, "State", None)
        if not isinstance(base_model, type) or not issubclass(base_model, BaseModel):
            return fallback_model
        return base_model
    base_model = getattr(workflow_cls, "State", None)
    if not isinstance(base_model, type) or not issubclass(base_model, BaseModel):
        base_model = fallback_model
    descriptor_fields = collect_descriptor_fields(workflow_cls, descriptor_type=StateField)
    model = build_descriptor_model(
        f"{workflow_cls.__name__}State",
        descriptor_fields=descriptor_fields,
        base_model=base_model,
        module_name=workflow_cls.__module__,
    )
    return base_model if model is None else model


def effective_parameters_model(workflow_cls: type[Any]) -> type[BaseModel] | None:
    if _uses_simple_authoring_model(workflow_cls):
        base_model = getattr(workflow_cls, "Params", None)
        if base_model is None:
            return None
        # autoloop.simple.Workflow provides EmptyParams as a sentinel default.
        # Treat that default as "no explicit class-level params" so package-
        # level exports such as params.py can still define the effective model.
        if (getattr(base_model, "__module__", None), getattr(base_model, "__name__", None)) == (
            "autoloop.simple",
            "EmptyParams",
        ):
            return None
        if not isinstance(base_model, type) or not issubclass(base_model, BaseModel):
            return None
        return base_model
    base_model = getattr(workflow_cls, "Params", None)
    if base_model is not None and (not isinstance(base_model, type) or not issubclass(base_model, BaseModel)):
        return None
    descriptor_fields = collect_descriptor_fields(workflow_cls, descriptor_type=ParameterField)
    if base_model is None and not descriptor_fields:
        return None
    model = build_descriptor_model(
        f"{workflow_cls.__name__}Params",
        descriptor_fields=descriptor_fields,
        base_model=base_model,
        module_name=workflow_cls.__module__,
    )
    return base_model if model is None else model


__all__ = [
    "DescriptorField",
    "ParameterField",
    "StateField",
    "build_descriptor_model",
    "collect_descriptor_fields",
    "effective_parameters_model",
    "effective_state_model",
    "materialize_descriptor_defaults",
]
