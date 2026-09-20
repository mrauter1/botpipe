"""Workflow-specific parameter model for the eval-suite building block."""

from __future__ import annotations

from botpipe_optimizer import SelectedWorkflowTaskFramingWithEvidenceParameters
from botpipe.stdlib.validation import optional_text_fields
from pydantic import model_validator

class Params(SelectedWorkflowTaskFramingWithEvidenceParameters):
    """Invocation contract for ``workflow_to_eval_suite``."""

    optimization_receipt_path: str | None = None
    candidate_id: str | None = None

    _normalize_selection = optional_text_fields("optimization_receipt_path", "candidate_id")

    @model_validator(mode="after")
    def complete_optimizer_selection(self):
        if bool(self.optimization_receipt_path) != bool(self.candidate_id):
            raise ValueError("optimization_receipt_path and candidate_id must be supplied together")
        return self


__all__ = ["Params"]
