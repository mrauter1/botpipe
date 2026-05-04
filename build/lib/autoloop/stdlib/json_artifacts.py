"""Optional typed helpers for JSON-backed workflow-local artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeVar

from pydantic import BaseModel

from .validation import ValidationReport, read_model_file, validate_model_file, write_model_file

ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class JsonArtifactSpec(Generic[ModelT]):
    """Typed JSON artifact contract that stays outside the root shim."""

    relative_path: str
    model_cls: type[ModelT]

    def read(self, path: str | Path) -> ModelT:
        return read_model_file(path, self.model_cls)

    def validate(self, path: str | Path) -> ValidationReport:
        return validate_model_file(path, self.model_cls)

    def write(self, ctx, model: ModelT) -> Path:
        return write_model_file(ctx, self.relative_path, model)


__all__ = ["JsonArtifactSpec"]
