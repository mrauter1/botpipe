"""Typed invocation parameters."""

from __future__ import annotations

import shlex

from pydantic import Field, field_validator, model_validator

from botpipe_optimizer import SelectedWorkflowTaskFramingParameters


class Params(SelectedWorkflowTaskFramingParameters):
    evidence_paths: list[str] = Field(default_factory=list)
    candidate_paths: list[str] = Field(default_factory=list)
    target_test_command: str | None = None
    target_test_argv: list[str] | None = None
    validation_timeout: float = Field(default=600.0, gt=0)
    max_candidate_building_blocks: int = Field(default=3, ge=1)

    @field_validator("target_test_command", mode="before")
    @classmethod
    def normalize_command(cls, value):
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("target_test_command must be a string")
        return value.strip() or None

    @model_validator(mode="after")
    def normalize_test_argv(self):
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
