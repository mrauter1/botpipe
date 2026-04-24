"""Reusable validation helpers for optional workflow-local support files."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, TypeVar

from pydantic import BaseModel, ValidationError

from .lifecycle import write_workflow_json

ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One readable validation problem."""

    location: tuple[str, ...]
    message: str


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Validation result for one JSON-backed model file."""

    path: Path
    model_name: str
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.issues


def require_non_empty_string(
    value: Any,
    *,
    field_name: str = "value",
    error_message: str | None = None,
    coerce: bool = False,
) -> str:
    """Return one stripped non-empty string or raise ``ValueError``."""

    if isinstance(value, str):
        normalized = value.strip()
    elif coerce and value is not None:
        normalized = str(value).strip()
    else:
        raise ValueError(error_message or f"{field_name} must be a non-empty string")
    if not normalized:
        raise ValueError(error_message or f"{field_name} must be a non-empty string")
    return normalized


def normalize_optional_string(
    value: Any,
    *,
    field_name: str = "value",
    error_message: str | None = None,
    coerce: bool = True,
) -> str | None:
    """Return one stripped optional string or ``None``."""

    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
    elif coerce:
        normalized = str(value).strip()
    else:
        raise ValueError(error_message or f"{field_name} must be a string or null")
    return normalized or None


def normalize_unique_strings(
    value: Any,
    *,
    field_name: str = "value",
    error_message: str | None = None,
    item_error_message: str | None = None,
    allow_scalar: bool = False,
    allow_none: bool = True,
    coerce: bool = True,
) -> list[str]:
    """Return one deduplicated normalized string list."""

    if value is None:
        if allow_none:
            return []
        raise ValueError(error_message or f"{field_name} must be a list of non-empty strings")
    if isinstance(value, list):
        candidates = value
    elif allow_scalar:
        candidates = [value]
    else:
        raise ValueError(error_message or f"{field_name} must be a list of non-empty strings")
    normalized: list[str] = []
    for raw_value in candidates:
        candidate = normalize_optional_string(
            raw_value,
            field_name=field_name,
            error_message=item_error_message or error_message,
            coerce=coerce,
        )
        if candidate and candidate not in normalized:
            normalized.append(candidate)
    return normalized


def require_string_list(
    value: Any,
    *,
    field_name: str = "value",
    unique: bool = False,
    min_length: int = 1,
    error_message: str | None = None,
    allow_scalar: bool = False,
    coerce: bool = False,
    dedupe: bool = False,
    sort_output: bool = False,
) -> list[str]:
    """Return one normalized string list or raise ``ValueError``."""

    if isinstance(value, list):
        candidates = value
    elif allow_scalar:
        candidates = [value]
    else:
        raise ValueError(error_message or f"{field_name} must be a list of non-empty strings")
    normalized = [
        require_non_empty_string(
            item,
            field_name=field_name,
            error_message=error_message,
            coerce=coerce,
        )
        for item in candidates
    ]
    if dedupe:
        deduped: list[str] = []
        for item in normalized:
            if item not in deduped:
                deduped.append(item)
        normalized = deduped
    elif unique:
        normalized = require_unique_values(normalized, field_name=field_name)
    if sort_output:
        normalized = sorted(normalized)
    if len(normalized) < min_length:
        raise ValueError(error_message or f"{field_name} must contain at least {min_length} item(s)")
    return normalized


def require_unique_values(values: list[str], *, field_name: str = "value") -> list[str]:
    """Return values unchanged when unique or raise ``ValueError``."""

    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    if duplicates:
        repeated = ", ".join(repr(value) for value in duplicates)
        raise ValueError(f"{field_name} must not repeat values: {repeated}")
    return values


def require_positive_int(
    value: Any,
    *,
    field_name: str = "value",
    error_message: str | None = None,
    allow_bool: bool = False,
) -> int:
    """Return one positive integer or raise ``ValueError``."""

    if isinstance(value, bool) and not allow_bool:
        raise ValueError(error_message or f"{field_name} must be a positive integer")
    if not isinstance(value, int) or value < 1:
        raise ValueError(error_message or f"{field_name} must be a positive integer")
    return value


def require_mapping(
    value: Any,
    *,
    field_name: str = "value",
    error_message: str | None = None,
) -> dict[str, Any]:
    """Return one string-keyed mapping or raise ``ValueError``."""

    if not isinstance(value, Mapping):
        raise ValueError(error_message or f"{field_name} must be a JSON object")
    return {str(key): item for key, item in value.items()}


def require_mapping_list(
    value: Any,
    *,
    field_name: str = "value",
    error_message: str | None = None,
    min_length: int = 1,
) -> list[dict[str, Any]]:
    """Return one mapping list or raise ``ValueError``."""

    if not isinstance(value, list):
        raise ValueError(error_message or f"{field_name} must be a JSON array of objects")
    normalized = [
        require_mapping(item, field_name=field_name, error_message=error_message)
        for item in value
    ]
    if len(normalized) < min_length:
        raise ValueError(error_message or f"{field_name} must contain at least {min_length} item(s)")
    return normalized


def read_model_file(path: str | Path, model_cls: type[ModelT]) -> ModelT:
    """Read and validate one JSON model file."""

    payload = read_json_object(path)
    return model_cls.model_validate(payload)


def write_model_file(ctx, relative_path: str | Path, model: BaseModel) -> Path:
    """Persist one Pydantic model under ``ctx.workflow_folder`` as JSON."""

    return write_workflow_json(ctx, relative_path, model.model_dump(mode="json"))


def validate_model_file(path: str | Path, model_cls: type[BaseModel]) -> ValidationReport:
    """Return a readable validation report for one JSON model file."""

    target = Path(path)
    try:
        payload = read_json_object(target)
        model_cls.model_validate(payload)
    except FileNotFoundError:
        issues = (ValidationIssue(location=("file",), message="file does not exist"),)
    except json.JSONDecodeError as exc:
        issues = (ValidationIssue(location=("json",), message=f"invalid JSON: {exc.msg}"),)
    except ValidationError as exc:
        issues = tuple(_validation_issue(error) for error in exc.errors())
    except ValueError as exc:
        issues = (ValidationIssue(location=("json",), message=str(exc)),)
    else:
        issues = ()
    return ValidationReport(path=target, model_name=model_cls.__name__, issues=issues)


def read_json_object(path: str | Path) -> dict[str, Any]:
    """Read one JSON object from disk or raise ``ValueError``."""

    target = Path(path)
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{target.name} must contain a JSON object")
    return payload


def _validation_issue(error: dict[str, Any]) -> ValidationIssue:
    raw_location = error.get("loc") or ()
    location = tuple(str(item) for item in raw_location)
    return ValidationIssue(location=location, message=str(error.get("msg") or "invalid value"))


__all__ = [
    "ValidationIssue",
    "ValidationReport",
    "normalize_optional_string",
    "normalize_unique_strings",
    "read_json_object",
    "read_model_file",
    "require_mapping",
    "require_mapping_list",
    "require_non_empty_string",
    "require_positive_int",
    "require_string_list",
    "require_unique_values",
    "validate_model_file",
    "write_model_file",
]
