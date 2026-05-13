"""Workflow-specific parameter model for the task-to-candidate-workflow-set package."""

from __future__ import annotations

from botpipe_optimizer import TaskFramingWithEvidenceParameters

class Params(TaskFramingWithEvidenceParameters):
    """Invocation contract for ``task_to_candidate_workflow_set``."""


__all__ = ["Params"]
