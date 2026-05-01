"""Workflow-specific parameter model for the workflow-builder package."""

from __future__ import annotations

from typing import Literal

from autoloop.stdlib import deduped_string_list_fields, optional_text_fields, required_text_fields

from pydantic import BaseModel, Field, field_validator


class Params(BaseModel):
    """Invocation contract for ``workflow_idea_to_workflow_package``."""

    package_name: str
    package_title: str | None = None
    workflow_kind: Literal["end_to_end", "building_block"]
    authoring_shape: Literal["single", "flow_specs", "package"] = "flow_specs"
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

    _normalize_package_title = optional_text_fields("package_title")
    _normalize_aliases = deduped_string_list_fields("aliases")

    @field_validator("authoring_shape", mode="before")
    @classmethod
    def _normalize_authoring_shape(cls, value: str) -> str:
        normalized = str(value or "").strip().replace("-", "_")
        if normalized not in {"single", "flow_specs", "package"}:
            raise ValueError("authoring_shape must be one of: single, flow_specs, package")
        return normalized

    _validate_target_test_command = required_text_fields(
        "target_test_command",
        error_message="target_test_command must be non-empty",
    )


__all__ = ["Params"]
