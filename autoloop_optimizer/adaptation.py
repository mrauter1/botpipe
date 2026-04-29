"""Small authoring helpers for selected-workflow adaptation artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:  # pragma: no branch - supports both package and direct repo-root imports
    from ..core.workflow_capabilities import selected_workflow_capability_payload
    from ..runtime.loader import coerce_workflow_parameter_mapping
except ImportError:  # pragma: no cover - direct repo-root import fallback
    from core.workflow_capabilities import selected_workflow_capability_payload
    from runtime.loader import coerce_workflow_parameter_mapping

from ._selected_workflow import (
    capture_selected_workflow,
    inspect_selected_workflow,
    write_selected_workflow_artifact,
)


def write_selected_workflow_capability_snapshot(
    ctx,
    workflow: str | type[Any],
    relative_path: str | Path = "selected_workflow_capability.json",
) -> Path:
    """Write one selected workflow's compiled contract under ``ctx.workflow_folder``."""

    inspection = inspect_selected_workflow(ctx, workflow)
    return write_selected_workflow_artifact(
        ctx,
        capture=inspection.capture,
        relative_path=relative_path,
        artifact_name="selected_workflow_capability",
        artifact_payload=selected_workflow_capability_payload(inspection.capability),
    ).path


def write_validated_workflow_parameters(
    ctx,
    workflow: str | type[Any],
    payload: Mapping[str, Any] | None,
    relative_path: str | Path = "validated_workflow_parameters.json",
) -> Path:
    """Validate and persist workflow parameters through the shared loader coercion path."""

    capture = capture_selected_workflow(ctx, workflow)
    validated = coerce_workflow_parameter_mapping(capture.resolved.parameters_cls, payload)
    return write_selected_workflow_artifact(
        ctx,
        capture=capture,
        relative_path=relative_path,
        artifact_name="validated_parameters",
        artifact_payload=validated,
    ).path


__all__ = [
    "write_selected_workflow_capability_snapshot",
    "write_validated_workflow_parameters",
]
