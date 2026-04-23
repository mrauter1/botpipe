"""Workflow-specific parameter model for the workflow-builder package."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Parameters(BaseModel):
    """Invocation contract for ``workflow_idea_to_workflow_package``."""

    package_name: str
    package_title: str | None = None
    workflow_kind: Literal["end_to_end", "building_block"]
    aliases: list[str] = Field(default_factory=list)
    target_test_command: str = "pytest"

    @field_validator("package_name")
    @classmethod
    def _validate_package_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("package_name must be non-empty")
        if not normalized.replace("_", "").isalnum() or normalized[0].isdigit():
            raise ValueError(
                "package_name must be a valid Python package identifier using letters, digits, or underscores"
            )
        return normalized

    @field_validator("package_title")
    @classmethod
    def _normalize_package_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("aliases")
    @classmethod
    def _normalize_aliases(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            alias = value.strip()
            if alias and alias not in normalized:
                normalized.append(alias)
        return normalized

    @field_validator("target_test_command")
    @classmethod
    def _validate_target_test_command(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("target_test_command must be non-empty")
        return normalized


__all__ = ["Parameters"]
