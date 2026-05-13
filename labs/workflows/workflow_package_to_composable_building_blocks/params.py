"""Workflow-specific parameter model for the decomposition building block."""

from __future__ import annotations

from botpipe_optimizer import SelectedWorkflowTaskFramingParameters
from botpipe.stdlib import deduped_string_list_fields, required_text_fields

from pydantic import Field


class Params(SelectedWorkflowTaskFramingParameters):
    """Invocation contract for ``workflow_package_to_composable_building_blocks``."""

    evidence_paths: list[str] = Field(default_factory=list)
    target_test_command: str = "pytest -q"
    max_candidate_building_blocks: int = Field(default=3, ge=1)

    _validate_decomposition_required_text = required_text_fields(
        "target_test_command",
        error_message="value must be non-empty",
    )
    _normalize_evidence_paths = deduped_string_list_fields("evidence_paths")


__all__ = ["Params"]
