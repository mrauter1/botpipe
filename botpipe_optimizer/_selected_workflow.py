"""Shared authoring-only seam for selected-workflow capture and envelope writing."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from botpipe.runtime.inspection import WorkflowCapabilityEntry, ResolvedWorkflow, inspect_workflow_reference, resolve_workflow_reference
from botpipe.stdlib.lifecycle import write_workflow_json


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


def resolve_selected_workflow_names(
    repo_root: Path,
    workflows: Iterable[str | type[Any]] | str | type[Any] | None,
    *,
    resolve_reference: Callable[[Path, str | type[Any]], ResolvedWorkflow] = resolve_workflow_reference,
) -> tuple[str, ...] | None:
    """Resolve optional workflow filters to stable workflow names."""

    if workflows is None:
        return None
    raw_workflows: Iterable[str | type[Any]]
    if isinstance(workflows, str) or isinstance(workflows, type):
        raw_workflows = (workflows,)
    else:
        raw_workflows = workflows
    selected = {
        resolve_reference(repo_root, workflow).reference.workflow_name
        for workflow in raw_workflows
    }
    if not selected:
        raise ValueError("workflows must contain at least one workflow reference when provided")
    return tuple(sorted(selected))


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
