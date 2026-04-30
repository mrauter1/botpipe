"""Workflow-specific parameter model for the eval-suite building block."""

from __future__ import annotations

from autoloop_v3.autoloop_optimizer import SelectedWorkflowTaskFramingWithEvidenceParameters

class Params(SelectedWorkflowTaskFramingWithEvidenceParameters):
    """Invocation contract for ``workflow_to_eval_suite``."""


__all__ = ["Params"]
