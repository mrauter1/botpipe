"""Workflow-specific parameter model for the task-to-workflow-strategy package."""

from __future__ import annotations

try:
    from autoloop_v3.stdlib import deduped_string_list_fields, optional_text_fields, required_text_fields
except ImportError:  # pragma: no cover - direct repo execution fallback
    from stdlib import deduped_string_list_fields, optional_text_fields, required_text_fields

from pydantic import BaseModel, Field


class Parameters(BaseModel):
    """Invocation contract for ``task_to_workflow_strategy``."""

    task_title: str
    sponsor_role: str | None = None
    desired_outcome: str | None = None
    constraints: list[str] = Field(default_factory=list)
    evidence_expectations: list[str] = Field(default_factory=list)

    _validate_task_title = required_text_fields("task_title")
    _normalize_optional_text = optional_text_fields("sponsor_role", "desired_outcome")
    _normalize_repeatable_strings = deduped_string_list_fields("constraints", "evidence_expectations")


__all__ = ["Parameters"]
