"""Workflow-specific parameter model for the task-to-candidate-workflow-set package."""

from __future__ import annotations

try:
    from autoloop_v3.stdlib import TaskFramingWithEvidenceParameters
except ImportError:  # pragma: no cover - direct repo execution fallback
    from stdlib import TaskFramingWithEvidenceParameters

class Parameters(TaskFramingWithEvidenceParameters):
    """Invocation contract for ``task_to_candidate_workflow_set``."""


__all__ = ["Parameters"]
