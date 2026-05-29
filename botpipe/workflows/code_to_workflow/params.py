"""Workflow parameters for code_to_workflow."""

from __future__ import annotations

from pydantic import BaseModel, field_validator


class Params(BaseModel):
    """Invocation contract for ``code_to_workflow``."""

    generated_workflow_name: str | None = None

    @field_validator("generated_workflow_name")
    @classmethod
    def _validate_generated_workflow_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if not normalized.replace("_", "").isalnum() or normalized[0].isdigit():
            raise ValueError(
                "generated_workflow_name must be a valid workflow identifier using letters, digits, or underscores"
            )
        return normalized


__all__ = ["Params"]
