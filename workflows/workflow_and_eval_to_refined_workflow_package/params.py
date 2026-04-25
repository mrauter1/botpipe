"""Workflow-specific parameter model for the refinement building block."""

from __future__ import annotations

try:
    from autoloop_v3.stdlib import (
        SelectedWorkflowTaskFramingParameters,
        optional_text_fields,
        required_text_fields,
    )
except ImportError:  # pragma: no cover - direct repo execution fallback
    from stdlib import (
        SelectedWorkflowTaskFramingParameters,
        optional_text_fields,
        required_text_fields,
    )


class Parameters(SelectedWorkflowTaskFramingParameters):
    """Invocation contract for ``workflow_and_eval_to_refined_workflow_package``."""

    evaluation_summary_path: str
    evaluation_findings_path: str
    failure_modes_path: str | None = None
    target_test_command: str = "pytest -q"

    _validate_refinement_required_text = required_text_fields(
        "evaluation_summary_path",
        "evaluation_findings_path",
        "target_test_command",
        error_message="value must be non-empty",
    )
    _normalize_failure_modes_path = optional_text_fields("failure_modes_path")


__all__ = ["Parameters"]
