"""Stable read-only workflow inspection and run-observability APIs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from autoloop.core.history import HistoryReader
from autoloop.core.schema_registry import (
    RUN_METADATA_SCHEMA,
    WORKFLOW_TOPOLOGY_SCHEMA,
    migrate_schemaless_payload,
    validate_persisted_schema,
)
from autoloop.core.workflow_capabilities import (
    WorkflowCapabilityEntry,
    inspect_workflow_capabilities,
    inspect_workflow_reference,
    selected_workflow_authoring_surface_payload,
    selected_workflow_capability_payload,
    selected_workflow_decomposition_surface_payload,
    workflow_capability_payload,
)
from autoloop.core.workflow_catalog import WorkflowCatalogEntry, discover_workflow_catalog

from .loader import ResolvedWorkflow, resolve_workflow_package, resolve_workflow_reference
from .static_graph import TOPOLOGY_FILENAME
from .workspace import (
    RunRecord,
    list_run_records,
    list_task_operation_summaries,
    list_workflow_run_summaries,
    normalize_run_status,
)


def list_runs(
    root: str | Path,
    *,
    workflow_name: str | None = None,
    task_id: str | None = None,
    status: str | None = None,
) -> tuple[RunRecord, ...]:
    return list_run_records(Path(root), workflow_name=workflow_name, task_id=task_id, status=status)


def load_run_record(
    root: str | Path,
    *,
    run_id: str,
    workflow_name: str | None = None,
    task_id: str | None = None,
) -> RunRecord:
    matches = [record for record in list_runs(root, workflow_name=workflow_name, task_id=task_id) if record.run_id == run_id]
    if not matches:
        raise FileNotFoundError(f"run {run_id!r} was not found")
    if len(matches) > 1:
        raise ValueError(f"run id {run_id!r} is ambiguous without narrower workflow/task filters")
    return matches[0]


def load_run_topology(run: RunRecord | str | Path) -> dict[str, Any]:
    run_dir = _run_dir(run)
    payload = json.loads((run_dir / TOPOLOGY_FILENAME).read_text(encoding="utf-8"))
    validate_persisted_schema(
        payload,
        expected=WORKFLOW_TOPOLOGY_SCHEMA,
        artifact_name=TOPOLOGY_FILENAME,
        legacy_migrator=lambda value: migrate_schemaless_payload(value, expected=WORKFLOW_TOPOLOGY_SCHEMA),
    )
    return payload


def load_run_metadata(run: RunRecord | str | Path) -> dict[str, Any]:
    run_dir = _run_dir(run)
    payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    validate_persisted_schema(
        payload,
        expected=RUN_METADATA_SCHEMA,
        artifact_name="run.json",
        legacy_migrator=lambda value: migrate_schemaless_payload(value, expected=RUN_METADATA_SCHEMA),
    )
    return payload


def load_run_history(run: RunRecord | str | Path) -> HistoryReader:
    return HistoryReader(_run_dir(run))


def _run_dir(run: RunRecord | str | Path) -> Path:
    if isinstance(run, RunRecord):
        return run.run_dir
    return Path(run).resolve()


__all__ = [
    "HistoryReader",
    "ResolvedWorkflow",
    "RunRecord",
    "WorkflowCapabilityEntry",
    "WorkflowCatalogEntry",
    "discover_workflow_catalog",
    "inspect_workflow_capabilities",
    "inspect_workflow_reference",
    "list_run_records",
    "list_runs",
    "list_task_operation_summaries",
    "list_workflow_run_summaries",
    "load_run_history",
    "load_run_metadata",
    "load_run_record",
    "load_run_topology",
    "normalize_run_status",
    "resolve_workflow_package",
    "resolve_workflow_reference",
    "selected_workflow_authoring_surface_payload",
    "selected_workflow_capability_payload",
    "selected_workflow_decomposition_surface_payload",
    "workflow_capability_payload",
]
