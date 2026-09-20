"""Typed invocation parameters."""

from __future__ import annotations

import shlex

from pydantic import Field, field_validator, model_validator

from botpipe_optimizer import SelectedWorkflowTaskFramingParameters


class Params(SelectedWorkflowTaskFramingParameters):
    evaluation_summary_path: str | None = None
    evaluation_findings_path: str | None = None
    optimization_receipt_path: str | None = None
    candidate_id: str | None = None
    evaluation_spec_path: str | None = None
    failure_modes_path: str | None = None
    refinement_evidence_path: str | None = None
    candidate_paths: list[str] = Field(default_factory=list)
    target_test_command: str | None = None
    target_test_argv: list[str] | None = None
    validation_timeout: float = Field(default=600.0, gt=0)

    @field_validator(
        "evaluation_summary_path",
        "evaluation_findings_path",
        "optimization_receipt_path",
        "candidate_id",
        "evaluation_spec_path",
        "failure_modes_path",
        "refinement_evidence_path",
        "target_test_command",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value):
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("optional path and command fields must be strings")
        return value.strip() or None

    @model_validator(mode="after")
    def validate_input_form(self):
        legacy = bool(self.evaluation_summary_path or self.evaluation_findings_path)
        optimizer = bool(self.optimization_receipt_path or self.candidate_id)
        if legacy and optimizer:
            raise ValueError(
                "legacy evaluation input and optimizer candidate input are mutually exclusive"
            )
        if legacy and not (
            self.evaluation_summary_path and self.evaluation_findings_path
        ):
            raise ValueError(
                "legacy input requires evaluation_summary_path and evaluation_findings_path"
            )
        if optimizer and not (self.optimization_receipt_path and self.candidate_id):
            raise ValueError(
                "optimizer input requires optimization_receipt_path and candidate_id"
            )
        if not legacy and not optimizer:
            raise ValueError("supply one complete legacy or optimizer refinement input")
        if self.target_test_command and self.target_test_argv:
            raise ValueError(
                "target_test_argv and target_test_command are mutually exclusive"
            )
        if self.target_test_command:
            self.target_test_argv = shlex.split(self.target_test_command)
        elif self.target_test_argv is None:
            self.target_test_argv = ["pytest", "-q"]
        if not self.target_test_argv or any(
            not isinstance(item, str) or not item.strip()
            for item in self.target_test_argv
        ):
            raise ValueError("target_test_argv must be a non-empty list of strings")
        return self


__all__ = ["Params"]
