"""Reusable validation helpers for optional workflow-local support files."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

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


def require_non_empty_string(value: Any, *, field_name: str = "value") -> str:
    """Return one stripped non-empty string or raise ``ValueError``."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def require_string_list(
    value: Any,
    *,
    field_name: str = "value",
    unique: bool = False,
    min_length: int = 1,
) -> list[str]:
    """Return one normalized string list or raise ``ValueError``."""

    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list of non-empty strings")
    normalized = [require_non_empty_string(item, field_name=field_name) for item in value]
    if len(normalized) < min_length:
        raise ValueError(f"{field_name} must contain at least {min_length} item(s)")
    if unique:
        return require_unique_values(normalized, field_name=field_name)
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


def read_model_file(path: str | Path, model_cls: type[ModelT]) -> ModelT:
    """Read and validate one JSON model file."""

    payload = _read_json_object(path)
    return model_cls.model_validate(payload)


def write_model_file(ctx, relative_path: str | Path, model: BaseModel) -> Path:
    """Persist one Pydantic model under ``ctx.workflow_folder`` as JSON."""

    return write_workflow_json(ctx, relative_path, model.model_dump(mode="json"))


def validate_model_file(path: str | Path, model_cls: type[BaseModel]) -> ValidationReport:
    """Return a readable validation report for one JSON model file."""

    target = Path(path)
    try:
        payload = _read_json_object(target)
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


def _read_json_object(path: str | Path) -> dict[str, Any]:
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
    "read_model_file",
    "require_non_empty_string",
    "require_string_list",
    "require_unique_values",
    "validate_model_file",
    "write_model_file",
]
