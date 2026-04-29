"""Shared authoring-only seam for selected-workflow capture and envelope writing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:  # pragma: no branch - supports both package and direct repo-root imports
    from ..core.workflow_capabilities import WorkflowCapabilityEntry, inspect_workflow_reference
    from ..runtime.loader import ResolvedWorkflow, resolve_workflow_reference
except ImportError:  # pragma: no cover - direct repo-root import fallback
    from autoloop_v3.core.workflow_capabilities import WorkflowCapabilityEntry, inspect_workflow_reference
    from autoloop_v3.runtime.loader import ResolvedWorkflow, resolve_workflow_reference

try:  # pragma: no branch - supports both package and direct repo-root imports
    from ..stdlib.lifecycle import write_workflow_json
except ImportError:  # pragma: no cover - direct repo-root import fallback
    from autoloop_v3.stdlib.lifecycle import write_workflow_json


@dataclass(frozen=True, slots=True)
class SelectedWorkflowCapture:
    """Resolved selected-workflow context shared across artifact writers."""

    repo_root: Path
    resolved: ResolvedWorkflow

    @property
    def selected_workflow_name(self) -> str:
        return self.resolved.reference.workflow_name


@dataclass(frozen=True, slots=True)
class SelectedWorkflowInspection:
    """Selected-workflow context plus rich capability inspection."""

    capture: SelectedWorkflowCapture
    capability: WorkflowCapabilityEntry


@dataclass(frozen=True, slots=True)
class SelectedWorkflowArtifactWrite:
    """Written artifact path plus the selected-workflow capture that produced it."""

    path: Path
    capture: SelectedWorkflowCapture


def capture_selected_workflow(ctx, workflow: str | type[Any]) -> SelectedWorkflowCapture:
    """Resolve one selected workflow against the workflow author's repo root."""

    repo_root = ctx.root.resolve()
    resolved = resolve_workflow_reference(repo_root, workflow)
    return SelectedWorkflowCapture(repo_root=repo_root, resolved=resolved)


def inspect_selected_workflow(ctx, workflow: str | type[Any]) -> SelectedWorkflowInspection:
    """Resolve and inspect one selected workflow through the shared capture seam."""

    capture = capture_selected_workflow(ctx, workflow)
    capability = inspect_workflow_reference(capture.repo_root, capture.resolved.workflow_cls)
    return SelectedWorkflowInspection(capture=capture, capability=capability)


def write_selected_workflow_artifact(
    ctx,
    *,
    capture: SelectedWorkflowCapture,
    relative_path: str | Path,
    artifact_name: str,
    artifact_payload: Any,
) -> SelectedWorkflowArtifactWrite:
    """Write a selected-workflow envelope with the shared top-level fields."""

    path = write_workflow_json(
        ctx,
        relative_path,
        {
            "repo_root": str(capture.repo_root),
            "run_id": ctx.run_id,
            artifact_name: artifact_payload,
            "selected_workflow_name": capture.selected_workflow_name,
            "task_id": ctx.task_id,
            "workflow_name": ctx.workflow_name,
        },
    )
    return SelectedWorkflowArtifactWrite(path=path, capture=capture)


__all__ = [
    "SelectedWorkflowArtifactWrite",
    "SelectedWorkflowCapture",
    "SelectedWorkflowInspection",
    "capture_selected_workflow",
    "inspect_selected_workflow",
    "write_selected_workflow_artifact",
]
