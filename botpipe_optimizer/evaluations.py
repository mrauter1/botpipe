"""Callable-aware workflow parameter and evaluation-manifest validation."""

from __future__ import annotations

import inspect
from collections.abc import Mapping, Sequence
from typing import Any, Literal, get_type_hints

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

CaseKind = Literal["benchmark", "edge", "adversarial"]
_KIND_ORDER = {"benchmark": 0, "edge": 1, "adversarial": 2}


class ValidatedEvalCase(BaseModel):
    case_id: str = Field(min_length=1)
    case_kind: CaseKind
    prompt: str = Field(min_length=1)
    workflow_parameters: dict[str, Any]
    expected_artifacts: list[str] = Field(min_length=1)


class ValidatedEvalManifest(BaseModel):
    workflow_name: str = Field(min_length=1)
    callable_signature: str = Field(min_length=1)
    case_count: int = Field(gt=0)
    case_ids: list[str]
    case_kinds: list[CaseKind]
    covered_expected_artifacts: list[str]
    artifact_surface_checked: bool
    cases: list[ValidatedEvalCase] = Field(min_length=1)


def validate_workflow_parameters(
    workflow: Any,
    payload: Mapping[str, Any] | None,
    *,
    parameter_name: str | None = None,
) -> dict[str, Any]:
    """Validate one parameter object against an ordinary workflow callable signature."""
    target = inspect.unwrap(getattr(workflow, "fn", workflow))
    signature = inspect.signature(target)
    parameters = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        not in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
    ]
    if not parameters:
        if payload:
            raise ValueError("workflow accepts no parameter object")
        return {}
    selected = (
        signature.parameters.get(parameter_name) if parameter_name else parameters[0]
    )
    if selected is None:
        raise ValueError(f"workflow has no parameter named {parameter_name!r}")
    try:
        hints = get_type_hints(target)
    except (NameError, TypeError):
        hints = {}
    values = dict(payload or {})
    annotation = hints.get(selected.name, selected.annotation)
    model_parameter = isinstance(annotation, type) and issubclass(annotation, BaseModel)
    if model_parameter and selected.name not in values:
        remaining_required = [
            parameter.name
            for parameter in parameters
            if parameter is not selected
            and parameter.default is inspect.Parameter.empty
        ]
        if remaining_required:
            names = ", ".join(remaining_required)
            raise ValueError(
                f"workflow requires additional invocation arguments: {names}"
            )
        return _validate_parameter_value(selected.name, annotation, values)

    # Non-model callables use the manifest mapping as ordinary keyword arguments.
    try:
        bound = signature.bind(**values)
    except TypeError as error:
        raise ValueError(f"invalid workflow invocation arguments: {error}") from error
    bound.apply_defaults()
    result: dict[str, Any] = {}
    for name, value in bound.arguments.items():
        parameter = signature.parameters[name]
        current_annotation = hints.get(name, parameter.annotation)
        result[name] = _validate_parameter_value(name, current_annotation, value)
    return result


def validate_eval_case_manifest(
    workflow: Any,
    manifest: Mapping[str, Any],
    *,
    known_artifacts: Sequence[str] | None = None,
    require_all_kinds: bool = True,
) -> ValidatedEvalManifest:
    """Validate cases against the selected callable's input schema and artifact surface."""
    if not isinstance(manifest, Mapping):
        raise TypeError("eval case manifest must be an object")
    raw_cases = manifest.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("eval case manifest must define a non-empty cases array")
    allowed_artifacts = (
        None
        if known_artifacts is None
        else set(_strings(known_artifacts, "known_artifacts"))
    )
    cases: list[ValidatedEvalCase] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_cases):
        if not isinstance(raw, Mapping):
            raise TypeError(f"eval case at index {index} must be an object")
        case_id = _text(raw.get("case_id"), f"eval case at index {index} case_id")
        if case_id in seen:
            raise ValueError(f"eval case manifest repeats case_id {case_id!r}")
        seen.add(case_id)
        kind = _text(raw.get("case_kind"), f"eval case {case_id!r} case_kind")
        if kind not in _KIND_ORDER:
            raise ValueError(
                f"eval case {case_id!r} has unsupported case_kind {kind!r}"
            )
        expected = _strings(
            raw.get("expected_artifacts"), f"eval case {case_id!r} expected_artifacts"
        )
        if not expected:
            raise ValueError(f"eval case {case_id!r} must expect at least one artifact")
        if allowed_artifacts is not None:
            unknown = sorted(set(expected) - allowed_artifacts)
            if unknown:
                raise ValueError(
                    f"eval case {case_id!r} expects unknown artifacts: {', '.join(unknown)}"
                )
        cases.append(
            ValidatedEvalCase(
                case_id=case_id,
                case_kind=kind,
                prompt=_text(raw.get("prompt"), f"eval case {case_id!r} prompt"),
                workflow_parameters=validate_workflow_parameters(
                    workflow, raw.get("workflow_parameters")
                ),
                expected_artifacts=expected,
            )
        )
    present = {case.case_kind for case in cases}
    if require_all_kinds and present != set(_KIND_ORDER):
        missing = [kind for kind in _KIND_ORDER if kind not in present]
        raise ValueError(
            f"eval case manifest is missing required case kinds: {', '.join(missing)}"
        )
    cases.sort(key=lambda case: (_KIND_ORDER[case.case_kind], case.case_id))
    target = inspect.unwrap(getattr(workflow, "fn", workflow))
    name = str(getattr(workflow, "name", None) or target.__name__)
    return ValidatedEvalManifest(
        workflow_name=name,
        callable_signature=str(inspect.signature(target)),
        case_count=len(cases),
        case_ids=[case.case_id for case in cases],
        case_kinds=[kind for kind in _KIND_ORDER if kind in present],
        covered_expected_artifacts=sorted(
            {artifact for case in cases for artifact in case.expected_artifacts}
        ),
        artifact_surface_checked=allowed_artifacts is not None,
        cases=cases,
    )


def _validate_parameter_value(name: str, annotation: Any, value: Any) -> Any:
    if annotation is inspect.Parameter.empty or annotation is Any:
        return value
    if isinstance(annotation, str):
        raise TypeError(f"workflow parameter {name!r} has an unresolved annotation")
    try:
        validated = TypeAdapter(annotation).validate_python(value)
    except (TypeError, ValidationError) as error:
        raise ValueError(
            f"invalid workflow parameters for {name!r}: {error}"
        ) from error
    if isinstance(validated, BaseModel):
        return validated.model_dump(mode="json")
    return validated


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError(f"{label} must be a string array")
    result: list[str] = []
    for item in value:
        text = _text(item, f"{label} entry")
        if text in result:
            raise ValueError(f"{label} must not contain duplicates")
        result.append(text)
    return sorted(result)


__all__ = [
    "CaseKind",
    "ValidatedEvalCase",
    "ValidatedEvalManifest",
    "validate_eval_case_manifest",
    "validate_workflow_parameters",
]
