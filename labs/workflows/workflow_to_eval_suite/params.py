"""Typed invocation parameters."""

from __future__ import annotations

from pydantic import field_validator, model_validator

from botpipe_optimizer import SelectedWorkflowTaskFramingWithEvidenceParameters


class Params(SelectedWorkflowTaskFramingWithEvidenceParameters):
    optimization_receipt_path: str | None = None
    candidate_id: str | None = None

    @field_validator("optimization_receipt_path", "candidate_id", mode="before")
    @classmethod
    def normalize_optional_text(cls, value):
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("optimizer selection fields must be strings")
        return value.strip() or None

    @model_validator(mode="after")
    def complete_optimizer_selection(self):
        if bool(self.optimization_receipt_path) != bool(self.candidate_id):
            raise ValueError(
                "optimization_receipt_path and candidate_id must be supplied together"
            )
        return self


__all__ = ["Params"]
