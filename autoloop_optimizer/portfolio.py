"""Small authoring helpers for explicit workflow-portfolio snapshots."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from autoloop.runtime.inspection import (
    discover_workflow_catalog,
    inspect_workflow_capabilities,
    list_workflow_run_summaries,
    normalize_run_status,
    resolve_workflow_reference,
    workflow_capability_payload,
)
from autoloop.stdlib.lifecycle import write_workflow_json
from autoloop.stdlib.validation import require_non_empty_string


def write_workflow_portfolio_snapshot(
    ctx,
    relative_path: str | Path = "workflow_portfolio_snapshot.json",
) -> Path:
    """Write a workflow-local snapshot of the current repo workflow catalog."""

    repo_root = _repo_root_from_context(ctx)
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


def write_workflow_portfolio_health_snapshot(
    ctx,
    workflows: Iterable[str | type[Any]] | str | type[Any] | None = None,
    *,
    statuses: str | Iterable[str] | None = None,
    max_runs_per_workflow: int | None = None,
    relative_path: str | Path = "workflow_portfolio_health_snapshot.json",
) -> Path:
    """Write a workflow-local snapshot of grouped per-workflow run health."""

    repo_root = _repo_root_from_context(ctx)
    catalog = discover_workflow_catalog(repo_root)
    selected_workflow_names = _resolve_selected_workflow_names(repo_root, workflows)
    normalized_statuses = _normalized_filters(statuses)
    selected_catalog = tuple(
        entry for entry in catalog if selected_workflow_names is None or entry.workflow_name in selected_workflow_names
    )
    run_summaries = list_workflow_run_summaries(
        repo_root,
        workflow_names=selected_workflow_names,
        statuses=normalized_statuses,
        max_runs_per_workflow=max_runs_per_workflow,
    )
    summary_by_name = {entry["workflow_name"]: entry for entry in run_summaries}

    return write_workflow_json(
        ctx,
        relative_path,
        {
            "repo_root": str(repo_root),
            "run_id": ctx.run_id,
            "task_id": ctx.task_id,
            "workflow_name": ctx.workflow_name,
            "workflow_portfolio_health": {
                "max_runs_per_workflow": max_runs_per_workflow,
                "selected_workflow_names": None if selected_workflow_names is None else list(selected_workflow_names),
                "statuses": normalized_statuses,
                "workflow_count": len(selected_catalog),
                "workflows": [
                    _workflow_health_payload(
                        entry,
                        summary_by_name.get(entry.workflow_name),
                    )
                    for entry in selected_catalog
                ],
            },
        },
    )


def write_workflow_capability_snapshot(
    ctx,
    relative_path: str | Path = "workflow_capability_snapshot.json",
) -> Path:
    """Write a workflow-local snapshot of the current repo workflow capabilities."""

    repo_root = _repo_root_from_context(ctx)
    catalog = inspect_workflow_capabilities(repo_root)
    return write_workflow_json(
        ctx,
        relative_path,
        {
            "repo_root": str(repo_root),
            "run_id": ctx.run_id,
            "task_id": ctx.task_id,
            "workflow_count": len(catalog),
            "workflow_name": ctx.workflow_name,
            "workflows": [workflow_capability_payload(entry) for entry in catalog],
        },
    )


def _catalog_entry_payload(entry) -> dict[str, object]:
    return {
        "aliases": list(entry.aliases),
        "authoring_shape": entry.authoring_shape,
        "description": entry.description,
        "doc_path": None if entry.doc_path is None else str(entry.doc_path),
        "doc_paths": [str(path) for path in entry.doc_paths],
        "manifest_path": None if entry.manifest_path is None else str(entry.manifest_path),
        "package_dir": str(entry.package_dir),
        "package_name": entry.package_name,
        "params_path": None if entry.params_path is None else str(entry.params_path),
        "source_path": str(entry.source_path),
        "spec_paths": [str(path) for path in entry.spec_paths],
        "test_paths": [str(path) for path in entry.test_paths],
        "title": entry.title,
        "workflow_name": entry.workflow_name,
        "workflow_path": str(entry.workflow_path),
    }


def _workflow_health_payload(entry, summary: dict[str, Any] | None) -> dict[str, object]:
    payload = {
        "aliases": list(entry.aliases),
        "description": entry.description,
        "title": entry.title,
        "workflow_name": entry.workflow_name,
    }
    if summary is None:
        payload.update(
            {
                "latest_run_id": None,
                "latest_updated_at": None,
                "recent_runs": [],
                "run_count": 0,
                "status_counts": {},
            }
        )
        return payload
    payload.update(
        {
            "latest_run_id": summary.get("latest_run_id"),
            "latest_updated_at": summary.get("latest_updated_at"),
            "recent_runs": list(summary.get("recent_runs", [])),
            "run_count": summary.get("run_count", 0),
            "status_counts": dict(summary.get("status_counts", {})),
        }
    )
    return payload


def _resolve_selected_workflow_names(
    repo_root: Path,
    workflows: Iterable[str | type[Any]] | str | type[Any] | None,
) -> tuple[str, ...] | None:
    if workflows is None:
        return None
    raw_workflows: Iterable[str | type[Any]]
    if isinstance(workflows, str) or isinstance(workflows, type):
        raw_workflows = (workflows,)
    else:
        raw_workflows = workflows
    selected = {
        resolve_workflow_reference(repo_root, workflow).reference.workflow_name
        for workflow in raw_workflows
    }
    if not selected:
        raise ValueError("workflows must contain at least one workflow reference when provided")
    return tuple(sorted(selected))


def _normalized_filters(statuses: str | Iterable[str] | None) -> list[str] | None:
    if statuses is None:
        return None
    raw_values: Iterable[str]
    if isinstance(statuses, str):
        raw_values = (statuses,)
    else:
        raw_values = statuses
    normalized = sorted(
        {
            normalize_run_status(
                require_non_empty_string(
                    value,
                    error_message="statuses entries must be non-empty strings",
                    coerce=False,
                )
            )
            for value in raw_values
        }
    )
    if not normalized:
        raise ValueError("statuses must contain at least one non-empty string when provided")
    return normalized


def _repo_root_from_context(ctx) -> Path:
    return ctx.root.resolve()


__all__ = [
    "write_workflow_capability_snapshot",
    "write_workflow_portfolio_health_snapshot",
    "write_workflow_portfolio_snapshot",
]
