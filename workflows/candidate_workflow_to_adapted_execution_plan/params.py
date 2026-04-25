"""Workflow-specific parameter model for the adaptation-planning building block."""

from __future__ import annotations

try:
    from autoloop_v3.stdlib import SelectedWorkflowTaskFramingWithEvidenceParameters
except ImportError:  # pragma: no cover - direct repo execution fallback
    from stdlib import SelectedWorkflowTaskFramingWithEvidenceParameters

class Parameters(SelectedWorkflowTaskFramingWithEvidenceParameters):
    """Invocation contract for ``candidate_workflow_to_adapted_execution_plan``."""


__all__ = ["Parameters"]
