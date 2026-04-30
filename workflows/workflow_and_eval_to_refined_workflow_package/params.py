"""Workflow-specific parameter model for the refinement building block."""

from __future__ import annotations

from autoloop_v3.autoloop_optimizer import SelectedWorkflowTaskFramingParameters
from stdlib import optional_text_fields, required_text_fields


class Params(SelectedWorkflowTaskFramingParameters):
    """Invocation contract for ``workflow_and_eval_to_refined_workflow_package``."""

    evaluation_summary_path: str
    evaluation_findings_path: str
    failure_modes_path: str | None = None
    refinement_evidence_path: str | None = None
    target_test_command: str = "pytest -q"

    _validate_refinement_required_text = required_text_fields(
        "evaluation_summary_path",
        "evaluation_findings_path",
        "target_test_command",
        error_message="value must be non-empty",
    )
    _normalize_optional_paths = optional_text_fields("failure_modes_path", "refinement_evidence_path")


__all__ = ["Params"]
