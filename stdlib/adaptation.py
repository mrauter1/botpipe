"""Small authoring helpers for selected-workflow adaptation artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:  # pragma: no branch - supports both package and direct repo-root imports
    from ..core.workflow_capabilities import (
        WorkflowCapabilityEntry,
        inspect_workflow_reference,
        workflow_capability_payload,
    )
    from ..runtime.loader import coerce_workflow_parameter_mapping, resolve_workflow_reference
except ImportError:  # pragma: no cover - direct repo-root import fallback
    from core.workflow_capabilities import (
        WorkflowCapabilityEntry,
        inspect_workflow_reference,
        workflow_capability_payload,
    )
    from runtime.loader import coerce_workflow_parameter_mapping, resolve_workflow_reference

from .lifecycle import write_workflow_json


def write_selected_workflow_capability_snapshot(
    ctx,
    workflow: str | type[Any],
    relative_path: str | Path = "selected_workflow_capability.json",
) -> Path:
    """Write one selected workflow's compiled contract under ``ctx.workflow_folder``."""

    repo_root = _repo_root_from_context(ctx)
    resolved = resolve_workflow_reference(repo_root, workflow)
    capability = workflow_capability_payload(_selected_workflow_capability_entry(repo_root, resolved))
    return write_workflow_json(
        ctx,
        relative_path,
        {
            "repo_root": str(repo_root),
            "run_id": ctx.run_id,
            "selected_workflow_capability": capability,
            "selected_workflow_name": resolved.package.workflow_name,
            "task_id": ctx.task_id,
            "workflow_name": ctx.workflow_name,
        },
    )


def write_validated_workflow_parameters(
    ctx,
    workflow: str | type[Any],
    payload: Mapping[str, Any] | None,
    relative_path: str | Path = "validated_workflow_parameters.json",
) -> Path:
    """Validate and persist workflow parameters through the shared loader coercion path."""

    repo_root = _repo_root_from_context(ctx)
    resolved = resolve_workflow_reference(repo_root, workflow)
    validated = coerce_workflow_parameter_mapping(resolved.parameters_cls, payload)
    return write_workflow_json(
        ctx,
        relative_path,
        {
            "repo_root": str(repo_root),
            "run_id": ctx.run_id,
            "selected_workflow_name": resolved.package.workflow_name,
            "task_id": ctx.task_id,
            "validated_parameters": validated,
            "workflow_name": ctx.workflow_name,
        },
    )


def _selected_workflow_capability_entry(repo_root: Path, resolved) -> WorkflowCapabilityEntry:
    return inspect_workflow_reference(repo_root, resolved.workflow_cls)


def _repo_root_from_context(ctx) -> Path:
    return ctx.root.resolve()


__all__ = [
    "write_selected_workflow_capability_snapshot",
    "write_validated_workflow_parameters",
]
