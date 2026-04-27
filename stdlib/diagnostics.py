"""Small authoring helpers for workflow-local diagnostic snapshots."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

try:  # pragma: no branch - supports both package and direct repo-root imports
    from ..runtime.workspace import list_run_records
except ImportError:  # pragma: no cover - direct repo-root import fallback
    from runtime.workspace import list_run_records

from ._selected_workflow import capture_selected_workflow, write_selected_workflow_artifact
from .validation import require_non_empty_string


def write_selected_workflow_run_history_snapshot(
    ctx,
    workflow: str | type[Any],
    *,
    statuses: str | Iterable[str] | None = None,
    max_runs: int | None = None,
    relative_path: str | Path = "selected_workflow_run_history.json",
) -> Path:
    """Write one selected workflow's filtered run history under ``ctx.workflow_folder``."""

    capture = capture_selected_workflow(ctx, workflow)
    normalized_statuses = _normalize_statuses(statuses)
    normalized_max_runs = _normalize_max_runs(max_runs)

    records = list_run_records(capture.repo_root, workflow_name=capture.selected_workflow_name)
    if normalized_statuses is not None:
        allowed_statuses = set(normalized_statuses)
        records = tuple(record for record in records if record.status in allowed_statuses)
    if normalized_max_runs is not None:
        records = records[:normalized_max_runs]

    return write_selected_workflow_artifact(
        ctx,
        capture=capture,
        relative_path=relative_path,
        artifact_name="selected_workflow_run_history",
        artifact_payload={
            "max_runs": normalized_max_runs,
            "run_count": len(records),
            "runs": [_run_history_payload(record) for record in records],
            "statuses": normalized_statuses,
        },
    ).path


def _run_history_payload(record) -> dict[str, Any]:
    return {
        "children": _jsonl_object_entries(record.children_file),
        "events": _jsonl_object_entries(record.events_file),
        "parent_record": _optional_json_object(record.parent_file),
        "request_text": _optional_text(record.request_file),
        "run_metadata": _normalized_run_metadata(record),
        "source_paths": {
            "checkpoint_file": str(record.checkpoint_file),
            "children_file": str(record.children_file),
            "events_file": str(record.events_file),
            "parent_file": str(record.parent_file),
            "raw_dir": str(record.raw_dir),
            "request_file": str(record.request_file),
            "run_dir": str(record.run_dir),
            "run_meta_file": str(record.run_meta_file),
            "task_dir": str(record.task_dir),
            "trace_file": str(record.trace_file),
            "workflow_dir": str(record.workflow_dir),
        },
    }


def _normalized_run_metadata(record) -> dict[str, Any]:
    metadata = record.metadata
    normalized = {
        "created_at": record.created_at,
        "error": _optional_text_value(metadata.get("error")),
        "pending_question": record.pending_question,
        "run_id": record.run_id,
        "status": record.status,
        "task_id": record.task_id,
        "terminal": _optional_text_value(metadata.get("terminal")),
        "updated_at": record.updated_at,
        "workflow_name": record.workflow_name,
        "workflow_params": record.workflow_params,
    }
    package_folder = _optional_text_value(metadata.get("package_folder"))
    if package_folder is not None:
        normalized["package_folder"] = package_folder
    return normalized


def _normalize_statuses(statuses: str | Iterable[str] | None) -> list[str] | None:
    if statuses is None:
        return None
    raw_statuses: Iterable[str]
    if isinstance(statuses, str):
        raw_statuses = (statuses,)
    else:
        raw_statuses = statuses
    normalized = sorted(
        {
            require_non_empty_string(
                status,
                error_message="statuses entries must be non-empty strings",
                coerce=False,
            )
            for status in raw_statuses
        }
    )
    if not normalized:
        raise ValueError("statuses must contain at least one non-empty string when provided")
    return normalized


def _normalize_max_runs(max_runs: int | None) -> int | None:
    if max_runs is None:
        return None
    if max_runs <= 0:
        raise ValueError("max_runs must be a positive integer when provided")
    return max_runs


def _jsonl_object_entries(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    entries: list[dict[str, Any]] = []
    for index, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive branch
            raise ValueError(f"{path} line {index} is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"{path} line {index} must decode to a JSON object")
        entries.append(payload)
    return entries


def _optional_json_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive branch
        raise ValueError(f"{path} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must decode to a JSON object")
    return payload


def _optional_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _optional_text_value(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


__all__ = ["write_selected_workflow_run_history_snapshot"]
