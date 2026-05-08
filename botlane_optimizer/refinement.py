"""Small authoring helpers for selected-workflow refinement surfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from botlane.runtime.inspection import selected_workflow_authoring_surface_payload

from ._selected_workflow import inspect_selected_workflow, write_selected_workflow_artifact


def write_selected_workflow_authoring_surface(
    ctx,
    workflow: str | type[Any],
    relative_path: str | Path = "selected_workflow_authoring_surface.json",
) -> Path:
    """Write one selected workflow's editable authoring surface under ``ctx.workflow_folder``."""

    inspection = inspect_selected_workflow(ctx, workflow)
    return write_selected_workflow_artifact(
        ctx,
        capture=inspection.capture,
        relative_path=relative_path,
        artifact_name="selected_workflow_authoring_surface",
        artifact_payload=selected_workflow_authoring_surface_payload(inspection.capability),
    ).path


__all__ = ["write_selected_workflow_authoring_surface"]
