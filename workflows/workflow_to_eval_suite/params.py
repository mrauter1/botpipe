"""Workflow-specific parameter model for the eval-suite building block."""

from __future__ import annotations

try:
    from autoloop_v3.stdlib import SelectedWorkflowTaskFramingWithEvidenceParameters
except ImportError:  # pragma: no cover - direct repo execution fallback
    from stdlib import SelectedWorkflowTaskFramingWithEvidenceParameters

class Parameters(SelectedWorkflowTaskFramingWithEvidenceParameters):
    """Invocation contract for ``workflow_to_eval_suite``."""


__all__ = ["Parameters"]
