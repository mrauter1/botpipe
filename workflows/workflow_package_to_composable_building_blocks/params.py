"""Workflow-specific parameter model for the decomposition building block."""

from __future__ import annotations

try:
    from autoloop_v3.stdlib import deduped_string_list_fields, optional_text_fields, required_text_fields
except ImportError:  # pragma: no cover - direct repo execution fallback
    from stdlib import deduped_string_list_fields, optional_text_fields, required_text_fields

from pydantic import BaseModel, Field


class Parameters(BaseModel):
    """Invocation contract for ``workflow_package_to_composable_building_blocks``."""

    selected_workflow: str
    task_title: str
    evidence_paths: list[str] = Field(default_factory=list)
    sponsor_role: str | None = None
    desired_outcome: str | None = None
    constraints: list[str] = Field(default_factory=list)
    target_test_command: str = "pytest -q"
    max_candidate_building_blocks: int = Field(default=3, ge=1)

    _validate_required_text = required_text_fields(
        "selected_workflow",
        "task_title",
        "target_test_command",
        error_message="value must be non-empty",
    )
    _normalize_optional_text = optional_text_fields("sponsor_role", "desired_outcome")
    _normalize_repeatable_strings = deduped_string_list_fields("evidence_paths", "constraints")


__all__ = ["Parameters"]
