"""Runtime-owned step state models and simple-surface state sugar."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import inspect
import re
from typing import Any

from pydantic import BaseModel, Field, create_model

from .errors import WorkflowValidationError


_MISSING = object()
_MUTABLE_LITERAL_DEFAULT_TYPES = (list, dict, set)
_BASE_RESERVED_STEP_STATE_FIELDS = frozenset({"visits", "last_route", "last_reason"})
_PRODUCE_VERIFY_RESERVED_STEP_STATE_FIELDS = frozenset({"rework_count", "replan_count"})
_ITEM_RUNTIME_STATE_FIELDS = frozenset({"status", "last_step", "last_route"})
DEFAULT_REWORK_ROUTE_TAGS = frozenset({"needs_rework", "minor_rework"})
DEFAULT_REPLAN_ROUTE_TAGS = frozenset({"needs_replan", "major_replan"})


class StepRuntimeState(BaseModel):
    """Built-in runtime-owned state available on every step."""

    visits: int = 0
    last_route: str | None = None
    last_reason: str | None = None


class ProduceVerifyRuntimeState(StepRuntimeState):
    """Built-in runtime-owned state for producer/verifier steps."""

    rework_count: int = 0
    replan_count: int = 0


class WorkItemRuntimeState(BaseModel):
    """Built-in runtime-owned state available on active scoped items."""

    status: str | None = None
    last_step: str | None = None
    last_route: str | None = None


class _TypedStateVarFactory:
    __slots__ = ("_annotation",)

    def __init__(self, annotation: Any) -> None:
        self._annotation = annotation

    def __call__(self, default: Any = _MISSING, *, default_factory: Any | None = None) -> "StateVar":
        return StateVar(default, default_factory=default_factory, annotation=self._annotation)


class StateVar:
    """Inline simple-surface step-state declaration."""

    __slots__ = ("annotation", "default", "default_factory")

    def __init__(
        self,
        default: Any = _MISSING,
        *,
        default_factory: Any | None = None,
        annotation: Any = Any,
    ) -> None:
        if default is not _MISSING and default_factory is not None:
            raise ValueError("StateVar default and default_factory are mutually exclusive")
        if default is _MISSING and default_factory is None:
            raise ValueError("StateVar requires either a default or a default_factory")
        if default_factory is not None and not callable(default_factory):
            raise TypeError("StateVar default_factory must be callable")
        if default is None and annotation is Any:
            raise ValueError("StateVar(None) is ambiguous; provide an explicit type, for example StateVar[str | None](None)")
        if isinstance(default, _MUTABLE_LITERAL_DEFAULT_TYPES):
            raise ValueError(
                "StateVar mutable defaults must use default_factory, for example StateVar[list[str]](default_factory=list)"
            )
        self.annotation = annotation
        self.default = default
        self.default_factory = default_factory

    @classmethod
    def __class_getitem__(cls, annotation: Any) -> _TypedStateVarFactory:
        return _TypedStateVarFactory(annotation)

    def __repr__(self) -> str:
        parts: list[str] = []
        if self.annotation is not Any:
            parts.append(f"annotation={self.annotation!r}")
        if self.default is not _MISSING:
            parts.append(f"default={self.default!r}")
        if self.default_factory is not None:
            parts.append(f"default_factory={self.default_factory!r}")
        joined = ", ".join(parts)
        return f"StateVar({joined})"


def reserved_step_state_field_names(step_kind: str) -> frozenset[str]:
    reserved = set(_BASE_RESERVED_STEP_STATE_FIELDS)
    if _is_produce_verify_kind(step_kind):
        reserved.update(_PRODUCE_VERIFY_RESERVED_STEP_STATE_FIELDS)
    return frozenset(reserved)


def built_in_step_state_model(step_kind: str) -> type[BaseModel]:
    return ProduceVerifyRuntimeState if _is_produce_verify_kind(step_kind) else StepRuntimeState


def build_step_state_model(
    raw_state: object,
    *,
    step_name: str,
    step_kind: str,
    module_name: str,
) -> type[BaseModel]:
    return _build_model_backed_state(
        raw_state,
        step_name=step_name,
        step_kind=step_kind,
        module_name=module_name,
        state_label="state",
        model_name_suffix="StepState",
    )


def build_step_item_state_model(
    raw_state: object,
    *,
    step_name: str,
    step_kind: str,
    module_name: str,
) -> type[BaseModel]:
    return _build_model_backed_state(
        raw_state,
        step_name=step_name,
        step_kind=step_kind,
        module_name=module_name,
        state_label="item_state",
        model_name_suffix="StepItemState",
    )


def built_in_item_state_model() -> type[BaseModel]:
    return WorkItemRuntimeState


def reserved_item_state_field_names() -> frozenset[str]:
    return _ITEM_RUNTIME_STATE_FIELDS


def build_worklist_item_state_model(
    raw_state: type[BaseModel] | None,
    *,
    worklist_name: str,
    module_name: str,
) -> type[BaseModel]:
    built_in_model = built_in_item_state_model()
    if raw_state is None:
        return built_in_model
    if not inspect.isclass(raw_state) or not issubclass(raw_state, BaseModel):
        raise WorkflowValidationError(
            f"worklist {worklist_name!r} item_state must inherit from pydantic.BaseModel"
        )
    try:
        raw_state()
    except Exception as exc:
        raise WorkflowValidationError(
            f"worklist {worklist_name!r} item_state model {raw_state.__name__} must be instantiable with no arguments"
        ) from exc
    for field_name in raw_state.model_fields:
        if field_name in reserved_item_state_field_names():
            raise WorkflowValidationError(
                f"worklist {worklist_name!r} item_state field {field_name!r} conflicts with built-in scoped item runtime state"
            )
    model_name = _generated_step_state_model_name(worklist_name, suffix="WorkItemState")
    combined_model = type(model_name, (built_in_model, raw_state), {"__module__": module_name})
    combined_model.model_rebuild(force=True)
    return combined_model


def _build_model_backed_state(
    raw_state: object,
    *,
    step_name: str,
    step_kind: str,
    module_name: str,
    state_label: str,
    model_name_suffix: str,
) -> type[BaseModel]:
    built_in_model = built_in_step_state_model(step_kind)
    if raw_state is None:
        return built_in_model
    if inspect.isclass(raw_state) and issubclass(raw_state, BaseModel):
        _validate_custom_state_model(
            raw_state,
            step_name=step_name,
            step_kind=step_kind,
            state_label=state_label,
        )
        model_name = _generated_step_state_model_name(step_name, suffix=model_name_suffix)
        combined_model = type(model_name, (built_in_model, raw_state), {"__module__": module_name})
        combined_model.model_rebuild(force=True)
        return combined_model
    if isinstance(raw_state, Mapping):
        return _build_statevar_step_state_model(
            raw_state,
            step_name=step_name,
            step_kind=step_kind,
            module_name=module_name,
            built_in_model=built_in_model,
            state_label=state_label,
            model_name_suffix=model_name_suffix,
        )
    raise WorkflowValidationError(
        f"simple step {step_name!r} {state_label} must be declared with a pydantic.BaseModel subclass "
        "or a mapping of StateVar declarations"
    )


def _validate_custom_state_model(
    raw_state: type[BaseModel],
    *,
    step_name: str,
    step_kind: str,
    state_label: str,
) -> None:
    try:
        raw_state()
    except Exception as exc:
        raise WorkflowValidationError(
            f"simple step {step_name!r} {state_label} model {raw_state.__name__} must be instantiable with no arguments"
        ) from exc
    for field_name in raw_state.model_fields:
        _validate_reserved_step_state_field_name(step_name=step_name, step_kind=step_kind, field_name=field_name)


def _build_statevar_step_state_model(
    raw_state: Mapping[object, object],
    *,
    step_name: str,
    step_kind: str,
    module_name: str,
    built_in_model: type[BaseModel],
    state_label: str,
    model_name_suffix: str,
) -> type[BaseModel]:
    field_definitions: dict[str, tuple[Any, Any]] = {}
    for raw_name, raw_value in raw_state.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise WorkflowValidationError(
                f"simple step {step_name!r} {state_label} field names must be non-empty strings"
            )
        field_name = raw_name.strip()
        _validate_reserved_step_state_field_name(step_name=step_name, step_kind=step_kind, field_name=field_name)
        if not isinstance(raw_value, StateVar):
            raise WorkflowValidationError(
                f"simple step {step_name!r} {state_label} field {field_name!r} must be declared with StateVar(...)"
            )
        annotation = _statevar_annotation(
            raw_value,
            step_name=step_name,
            field_name=field_name,
            state_label=state_label,
        )
        if raw_value.default_factory is not None:
            field_definitions[field_name] = (annotation, Field(default_factory=raw_value.default_factory))
            continue
        field_definitions[field_name] = (annotation, deepcopy(raw_value.default))
    if not field_definitions:
        return built_in_model
    return create_model(
        _generated_step_state_model_name(step_name, suffix=model_name_suffix),
        __base__=built_in_model,
        __module__=module_name,
        **field_definitions,
    )


def _statevar_annotation(
    state_var: StateVar,
    *,
    step_name: str,
    field_name: str,
    state_label: str,
) -> Any:
    if state_var.annotation is not Any:
        return state_var.annotation
    if state_var.default_factory is not None:
        raise WorkflowValidationError(
            f"simple step {step_name!r} {state_label} field {field_name!r} must declare an explicit type when using default_factory"
        )
    default = state_var.default
    if isinstance(default, bool):
        return bool
    if default is None:
        raise WorkflowValidationError(
            f"simple step {step_name!r} {state_label} field {field_name!r} uses StateVar(None), which is ambiguous; "
            "provide an explicit type"
        )
    return type(default)


def _validate_reserved_step_state_field_name(
    *,
    step_name: str,
    step_kind: str,
    field_name: str,
) -> None:
    if field_name not in reserved_step_state_field_names(step_kind):
        return
    raise WorkflowValidationError(
        f"Step {step_name!r} custom state field {field_name!r} conflicts with built-in runtime state. "
        f"Use ctx.step_state.{field_name} directly, or choose a different custom field name."
    )


def _generated_step_state_model_name(step_name: str, *, suffix: str) -> str:
    parts = [part for part in re.split(r"[^0-9A-Za-z]+", step_name) if part]
    stem = "".join(part[:1].upper() + part[1:] for part in parts) or "Generated"
    return f"{stem}{suffix}"


def _is_produce_verify_kind(step_kind: str) -> bool:
    return step_kind in {"pair", "produce_verify", "review"}


__all__ = [
    "DEFAULT_REPLAN_ROUTE_TAGS",
    "DEFAULT_REWORK_ROUTE_TAGS",
    "ProduceVerifyRuntimeState",
    "StateVar",
    "StepRuntimeState",
    "WorkItemRuntimeState",
    "build_step_item_state_model",
    "build_step_state_model",
    "build_worklist_item_state_model",
    "built_in_step_state_model",
    "built_in_item_state_model",
    "reserved_item_state_field_names",
    "reserved_step_state_field_names",
]
