"""Small authoring helpers for selected-workflow decomposition surfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:  # pragma: no branch - supports both package and direct repo-root imports
    from ..core.workflow_capabilities import (
        inspect_workflow_reference,
        selected_workflow_decomposition_surface_payload,
    )
    from ..runtime.loader import resolve_workflow_reference
except ImportError:  # pragma: no cover - direct repo-root import fallback
    from core.workflow_capabilities import (
        inspect_workflow_reference,
        selected_workflow_decomposition_surface_payload,
    )
    from runtime.loader import resolve_workflow_reference

from .lifecycle import write_workflow_json


def write_selected_workflow_decomposition_surface(
    ctx,
    workflow: str | type[Any],
    relative_path: str | Path = "selected_workflow_decomposition_surface.json",
) -> Path:
    """Write one selected workflow's authoring and compiled decomposition surface."""

    repo_root = _repo_root_from_context(ctx)
    resolved = resolve_workflow_reference(repo_root, workflow)
    capability = inspect_workflow_reference(repo_root, resolved.workflow_cls)

    return write_workflow_json(
        ctx,
        relative_path,
        {
            "repo_root": str(repo_root),
            "run_id": ctx.run_id,
            "selected_workflow_decomposition_surface": selected_workflow_decomposition_surface_payload(
                capability,
                repo_root=repo_root,
            ),
            "selected_workflow_name": capability.workflow_name,
            "task_id": ctx.task_id,
            "workflow_name": ctx.workflow_name,
        },
    )


def _repo_root_from_context(ctx) -> Path:
    return ctx.root.resolve()


__all__ = ["write_selected_workflow_decomposition_surface"]
