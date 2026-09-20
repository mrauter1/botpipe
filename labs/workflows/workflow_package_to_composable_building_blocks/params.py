"""Workflow-specific parameter model for the decomposition building block."""

from __future__ import annotations

from botpipe_optimizer import SelectedWorkflowTaskFramingParameters
from botpipe.stdlib import deduped_string_list_fields

from pydantic import Field, model_validator


class Params(SelectedWorkflowTaskFramingParameters):
    """Invocation contract for ``workflow_package_to_composable_building_blocks``."""

    evidence_paths: list[str] = Field(default_factory=list)
    target_test_command: str | None = "pytest -q"
    target_test_argv: list[str] | None = None
    max_candidate_building_blocks: int = Field(default=3, ge=1)

    _normalize_evidence_paths = deduped_string_list_fields("evidence_paths")

    @model_validator(mode="after")
    def _normalize_test_command(self) -> "Params":
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
