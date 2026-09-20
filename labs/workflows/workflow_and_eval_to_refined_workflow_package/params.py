"""Workflow-specific parameter model for the refinement building block."""

from __future__ import annotations

from botpipe_optimizer import SelectedWorkflowTaskFramingParameters
from botpipe.stdlib import optional_text_fields
from pydantic import model_validator


class Params(SelectedWorkflowTaskFramingParameters):
    """Invocation contract for ``workflow_and_eval_to_refined_workflow_package``."""

    evaluation_summary_path: str | None = None
    evaluation_findings_path: str | None = None
    optimization_receipt_path: str | None = None
    candidate_id: str | None = None
    evaluation_spec_path: str | None = None
    failure_modes_path: str | None = None
    refinement_evidence_path: str | None = None
    target_test_command: str | None = "pytest -q"
    target_test_argv: list[str] | None = None

    _normalize_optional_paths = optional_text_fields(
        "evaluation_summary_path", "evaluation_findings_path", "optimization_receipt_path",
        "candidate_id", "evaluation_spec_path", "failure_modes_path", "refinement_evidence_path",
    )

    @model_validator(mode="after")
    def _one_primary_input(self) -> "Params":
        legacy = self.evaluation_summary_path is not None or self.evaluation_findings_path is not None
        optimizer = self.optimization_receipt_path is not None or self.candidate_id is not None
        if legacy and optimizer:
            raise ValueError("legacy evaluation input and optimizer candidate input are mutually exclusive")
        if legacy and (self.evaluation_summary_path is None or self.evaluation_findings_path is None):
            raise ValueError("legacy input requires evaluation_summary_path and evaluation_findings_path")
        if optimizer and (self.optimization_receipt_path is None or self.candidate_id is None):
            raise ValueError("optimizer input requires optimization_receipt_path and candidate_id")
        if not legacy and not optimizer:
            raise ValueError("supply one complete legacy or optimizer refinement input")
        if self.target_test_argv is not None:
            if "target_test_command" in self.model_fields_set:
                raise ValueError("target_test_argv and target_test_command are mutually exclusive")
            if not self.target_test_argv or any(not isinstance(item, str) or not item.strip() for item in self.target_test_argv):
                raise ValueError("target_test_argv must be a non-empty list of strings")
            self.target_test_command = None
        elif self.target_test_command is None or not self.target_test_command.strip():
            raise ValueError("target_test_command must be non-empty when target_test_argv is omitted")
        return self


__all__ = ["Params"]
