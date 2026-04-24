"""Workflow-specific parameter model for the refinement building block."""

from __future__ import annotations

try:
    from autoloop_v3.stdlib import deduped_string_list_fields, optional_text_fields, required_text_fields
except ImportError:  # pragma: no cover - direct repo execution fallback
    from stdlib import deduped_string_list_fields, optional_text_fields, required_text_fields

from pydantic import BaseModel, Field


class Parameters(BaseModel):
    """Invocation contract for ``workflow_and_eval_to_refined_workflow_package``."""

    selected_workflow: str
    task_title: str
    evaluation_summary_path: str
    evaluation_findings_path: str
    failure_modes_path: str | None = None
    sponsor_role: str | None = None
    desired_outcome: str | None = None
    constraints: list[str] = Field(default_factory=list)
    target_test_command: str = "pytest -q"

    _validate_required_text = required_text_fields(
        "selected_workflow",
        "task_title",
        "evaluation_summary_path",
        "evaluation_findings_path",
        "target_test_command",
        error_message="value must be non-empty",
    )
    _normalize_optional_text = optional_text_fields("failure_modes_path", "sponsor_role", "desired_outcome")
    _normalize_repeatable_strings = deduped_string_list_fields("constraints")


__all__ = ["Parameters"]
