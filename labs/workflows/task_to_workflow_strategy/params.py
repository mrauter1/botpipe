"""Workflow-specific parameter model for the task-to-workflow-strategy package."""

from __future__ import annotations

from botpipe_optimizer import TaskFramingWithEvidenceParameters

class Params(TaskFramingWithEvidenceParameters):
    """Invocation contract for ``task_to_workflow_strategy``."""


__all__ = ["Params"]
