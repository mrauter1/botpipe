"""Small authoring helpers for selected-workflow decomposition surfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:  # pragma: no branch - supports both package and direct repo-root imports
    from ..core.workflow_capabilities import selected_workflow_decomposition_surface_payload
except ImportError:  # pragma: no cover - direct repo-root import fallback
    from core.workflow_capabilities import selected_workflow_decomposition_surface_payload

from ._selected_workflow import inspect_selected_workflow, write_selected_workflow_artifact


def write_selected_workflow_decomposition_surface(
    ctx,
    workflow: str | type[Any],
    relative_path: str | Path = "selected_workflow_decomposition_surface.json",
) -> Path:
    """Write one selected workflow's authoring and compiled decomposition surface."""

    inspection = inspect_selected_workflow(ctx, workflow)
    return write_selected_workflow_artifact(
        ctx,
        capture=inspection.capture,
        relative_path=relative_path,
        artifact_name="selected_workflow_decomposition_surface",
        artifact_payload=selected_workflow_decomposition_surface_payload(
            inspection.capability,
            repo_root=inspection.capture.repo_root,
        ),
    ).path


__all__ = ["write_selected_workflow_decomposition_surface"]
