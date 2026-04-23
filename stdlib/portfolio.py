"""Small authoring helpers for explicit workflow-portfolio snapshots."""

from __future__ import annotations

from pathlib import Path

try:  # pragma: no branch - supports both package and direct repo-root imports
    from autoloop_v3.core.workflow_catalog import discover_workflow_catalog
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from core.workflow_catalog import discover_workflow_catalog

from .lifecycle import write_workflow_json


def write_workflow_portfolio_snapshot(
    ctx,
    relative_path: str | Path = "workflow_portfolio_snapshot.json",
) -> Path:
    """Write a workflow-local snapshot of the current repo workflow catalog."""

    repo_root = ctx.package_folder.resolve().parent.parent
    catalog = discover_workflow_catalog(repo_root)
    return write_workflow_json(
        ctx,
        relative_path,
        {
            "repo_root": str(repo_root),
            "run_id": ctx.run_id,
            "task_id": ctx.task_id,
            "workflow_count": len(catalog),
            "workflow_name": ctx.workflow_name,
            "workflows": [_catalog_entry_payload(entry) for entry in catalog],
        },
    )


def _catalog_entry_payload(entry) -> dict[str, object]:
    return {
        "aliases": list(entry.aliases),
        "description": entry.description,
        "doc_path": None if entry.doc_path is None else str(entry.doc_path),
        "manifest_path": str(entry.manifest_path),
        "package_dir": str(entry.package_dir),
        "package_name": entry.package_name,
        "params_path": None if entry.params_path is None else str(entry.params_path),
        "title": entry.title,
        "workflow_name": entry.workflow_name,
        "workflow_path": str(entry.workflow_path),
    }


__all__ = ["write_workflow_portfolio_snapshot"]
