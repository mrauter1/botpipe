"""Shared helpers for explicit labs durable functions."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from botpipe import ArtifactHandle, activity, current_run
from botpipe.workflows._authoring import (
    PhaseControl,
    PhaseEvidence,
    PhaseOutcome,
    PhaseRejected,
    PhaseReview,
    PhaseRun,
    ReplanRequired,
    WorkflowResult,
    artifact,
    finish,
    observe_catalog,
    run_phase,
)

LabPhaseControl = PhaseControl
LabPhaseOutcome = PhaseOutcome
LabPhaseRejected = PhaseRejected
LabPhaseReview = PhaseReview
LabWorkflowResult = WorkflowResult


@activity(retry_safe=True, name="read publication JSON")
def read_publication_json(
    handles: Sequence[ArtifactHandle], names: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """Read immutable captured JSON handles for a deterministic publication gate."""

    by_name = {str(handle.name): handle for handle in handles}
    result: dict[str, dict[str, Any]] = {}
    for name in names:
        handle = by_name.get(name)
        if handle is None:
            raise FileNotFoundError(f"missing required publication artifact {name}")
        try:
            value = json.loads(handle.read_bytes())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"{name} must contain a JSON object") from exc
        if not isinstance(value, dict):
            raise TypeError(f"{name} must contain a JSON object")
        result[name] = value
    return result


def observe_workflow(reference: str) -> dict[str, Any]:
    """Journal the callable/source contract used by a selected-workflow lab."""
    from botpipe.inspection import inspect_workflow

    context = current_run()
    return context.operation(
        "labs.inspect_workflow",
        {"reference": reference},
        lambda: inspect_workflow(reference, context.workspace),
        retry_safe=True,
        name="inspect selected workflow",
    )


@activity(retry_safe=True, name="prepare candidate surface")
def prepare_selected_candidate_surface(
    source_path: str,
    destination: str,
    preferred_root: str,
    candidate_paths: Sequence[str] = (),
):
    """Create an immutable baseline and editable allowlisted copy for one source file."""
    from botpipe_optimizer import prepare_candidate_workspace, repository_root_for

    repo_root = repository_root_for(source_path, preferred_root)
    source = Path(source_path).resolve()
    if candidate_paths:
        paths = list(candidate_paths)
    elif (source.parent / "__init__.py").is_file():
        paths = [source.parent.relative_to(repo_root).as_posix()]
    else:
        paths = [source.relative_to(repo_root).as_posix()]
    return prepare_candidate_workspace(repo_root, paths, destination)


@activity(retry_safe=True, name="validate workflow parameters")
def validate_selected_workflow_parameters(
    reference: str,
    workspace: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a proposed invocation against the selected callable signature."""
    from botpipe.discovery import resolve_workflow
    from botpipe_optimizer import validate_workflow_parameters

    return validate_workflow_parameters(resolve_workflow(reference, workspace), payload)


@activity(retry_safe=True, name="validate evaluation cases")
def validate_selected_eval_manifest(
    reference: str,
    workspace: str,
    manifest: Mapping[str, Any],
):
    """Validate eval cases and their flat Params payloads against a selected callable."""
    from botpipe.discovery import resolve_workflow
    from botpipe_optimizer import validate_eval_case_manifest

    # The lab chooses meaningful case categories during design, without a quota.
    return validate_eval_case_manifest(
        resolve_workflow(reference, workspace), manifest, require_all_kinds=False
    )


def observe_run_history(
    workflow_name: str | None = None,
    *,
    statuses: Sequence[str] = (),
    limit: int = 25,
    task_ids: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """Journal bounded run inspection data; absent runs remain an explicit empty list."""
    context = current_run()

    def collect():
        selected = []
        allowed_statuses = set(statuses)
        allowed_tasks = set(task_ids)
        for summary in context.client.runs():
            record = summary if isinstance(summary, dict) else vars(summary)
            if (
                workflow_name
                and (record.get("workflow_name") or record.get("workflow"))
                != workflow_name
            ):
                continue
            if allowed_statuses and record.get("status") not in allowed_statuses:
                continue
            if allowed_tasks and record.get("task_id") not in allowed_tasks:
                continue
            selected.append(context.client.inspect(str(record["run_id"])))
            if len(selected) >= limit:
                break
        return selected

    return context.operation(
        "labs.observe_run_history",
        {
            "workflow_name": workflow_name,
            "statuses": list(statuses),
            "limit": limit,
            "task_ids": list(task_ids),
        },
        collect,
        retry_safe=True,
        name="inspect durable run history",
    )


__all__ = [
    "LabPhaseControl",
    "LabPhaseOutcome",
    "LabPhaseRejected",
    "LabPhaseReview",
    "LabWorkflowResult",
    "PhaseEvidence",
    "PhaseRun",
    "ReplanRequired",
    "artifact",
    "finish",
    "observe_catalog",
    "observe_run_history",
    "observe_workflow",
    "prepare_selected_candidate_surface",
    "read_publication_json",
    "run_phase",
    "validate_selected_eval_manifest",
    "validate_selected_workflow_parameters",
]
