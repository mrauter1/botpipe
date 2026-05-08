"""Workflow-specific parameter model for the adaptation-planning building block."""

from __future__ import annotations

from botlane_optimizer import SelectedWorkflowTaskFramingWithEvidenceParameters

class Params(SelectedWorkflowTaskFramingWithEvidenceParameters):
    """Invocation contract for ``candidate_workflow_to_adapted_execution_plan``."""


__all__ = ["Params"]
