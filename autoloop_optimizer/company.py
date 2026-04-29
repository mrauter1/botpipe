"""Small authoring helpers for workflow-local company-operation snapshots."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

try:  # pragma: no branch - supports both package and direct repo-root imports
    from ..runtime.loader import resolve_workflow_reference
    from ..runtime.workspace import list_task_operation_summaries
except ImportError:  # pragma: no cover - direct repo-root import fallback
    from autoloop_v3.runtime.loader import resolve_workflow_reference
    from autoloop_v3.runtime.workspace import list_task_operation_summaries

try:  # pragma: no branch - supports both package and direct repo-root imports
    from ..stdlib.lifecycle import write_workflow_json
    from ..stdlib.validation import require_non_empty_string
except ImportError:  # pragma: no cover - direct repo-root import fallback
    from autoloop_v3.stdlib.lifecycle import write_workflow_json
    from autoloop_v3.stdlib.validation import require_non_empty_string


def write_company_operation_snapshot(
    ctx,
    task_ids: str | Iterable[str] | None = None,
    workflows: Iterable[str | type[Any]] | str | type[Any] | None = None,
    *,
    statuses: str | Iterable[str] | None = None,
    max_tasks: int | None = None,
    max_runs_per_workflow: int | None = None,
    max_messages_per_task: int | None = None,
    relative_path: str | Path = "company_operation_snapshot.json",
) -> Path:
    """Write a workflow-local snapshot of bounded company-operation history."""

    repo_root = _repo_root_from_context(ctx)
    selected_task_ids = _normalized_text_filters(task_ids, field_name="task_ids")
    selected_workflow_names = _resolve_selected_workflow_names(repo_root, workflows)
    normalized_statuses = _normalized_text_filters(statuses, field_name="statuses")
    task_summaries = list_task_operation_summaries(
        repo_root,
        task_ids=selected_task_ids,
        workflow_names=selected_workflow_names,
        statuses=normalized_statuses,
        max_tasks=max_tasks,
        max_runs_per_workflow=max_runs_per_workflow,
        max_messages_per_task=max_messages_per_task,
    )
    return write_workflow_json(
        ctx,
        relative_path,
        {
            "company_operation": {
                "max_messages_per_task": max_messages_per_task,
                "max_runs_per_workflow": max_runs_per_workflow,
                "max_tasks": max_tasks,
                "selected_task_ids": None if selected_task_ids is None else list(selected_task_ids),
                "selected_workflow_names": None if selected_workflow_names is None else list(selected_workflow_names),
                "statuses": normalized_statuses,
                "task_count": len(task_summaries),
                "tasks": list(task_summaries),
            },
            "repo_root": str(repo_root),
            "run_id": ctx.run_id,
            "task_id": ctx.task_id,
            "workflow_name": ctx.workflow_name,
        },
    )


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


def _normalized_text_filters(values: str | Iterable[str] | None, *, field_name: str) -> list[str] | None:
    if values is None:
        return None
    raw_values: Iterable[str]
    if isinstance(values, str):
        raw_values = (values,)
    else:
        raw_values = values
    normalized = sorted(
        {
            require_non_empty_string(
                value,
                error_message=f"{field_name} entries must be non-empty strings",
                coerce=False,
            )
            for value in raw_values
        }
    )
    if not normalized:
        raise ValueError(f"{field_name} must contain at least one non-empty string when provided")
    return normalized


def _repo_root_from_context(ctx) -> Path:
    return ctx.root.resolve()


__all__ = ["write_company_operation_snapshot"]
