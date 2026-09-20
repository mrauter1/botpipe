"""Workflow-specific parameter model for the decomposition building block."""

from __future__ import annotations

from botpipe_optimizer import SelectedWorkflowTaskFramingParameters
from botpipe.stdlib import deduped_string_list_fields

from pydantic import Field, model_validator


class Params(SelectedWorkflowTaskFramingParameters):
    """Invocation contract for ``workflow_package_to_composable_building_blocks``."""

    evidence_paths: list[str] = Field(default_factory=list)
    target_test_command: str | None = None
    target_test_argv: list[str] | None = None
    max_candidate_building_blocks: int = Field(default=3, ge=1)

    _normalize_evidence_paths = deduped_string_list_fields("evidence_paths")

    @model_validator(mode="after")
    def _normalize_test_command(self) -> "Params":
        command_set = self.target_test_command is not None
        argv_set = self.target_test_argv is not None
        if command_set and argv_set:
            raise ValueError(
                "target_test_argv and target_test_command are mutually exclusive"
            )
        if command_set:
            if self.target_test_command is None or not self.target_test_command.strip():
                raise ValueError("target_test_command must be non-empty")
            self.target_test_argv = None
        elif argv_set:
            if not self.target_test_argv or any(
                not isinstance(item, str) or not item.strip()
                for item in self.target_test_argv
            ):
                raise ValueError("target_test_argv must be a non-empty list of strings")
            self.target_test_command = None
        else:
            self.target_test_argv = ["pytest", "-q"]
        return self


__all__ = ["Params"]
