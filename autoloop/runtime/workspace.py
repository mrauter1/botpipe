"""Generic filesystem workspace management."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from uuid import uuid4

from autoloop.core.mappings import normalize_mapping
from autoloop.core.schema_registry import (
    CHILD_RUN_SUMMARY_SCHEMA,
    RUN_METADATA_SCHEMA,
    migrate_schemaless_payload,
    validate_persisted_schema,
)
from autoloop.core.statuses import normalize_run_status


STATE_DIRNAME = ".autoloop"
DEFAULT_REQUEST_TEXT = "No explicit initial message was provided for this run. Use repository artifacts and explicit clarifications only."
_RAW_SEQUENCE_PATTERN = re.compile(r"^(?P<sequence>\d+)_")
_UNSET = object()


@dataclass(frozen=True, slots=True)
class TaskWorkspace:
    root: Path
    state_root: Path
    tasks_dir: Path
    task_dir: Path
    task_id: str
    task_root_rel: Path
    task_meta_file: Path
    task_request_file: Path
    task_messages_file: Path


@dataclass(frozen=True, slots=True)
class WorkflowWorkspace:
    task_workspace: TaskWorkspace
    workflow_name: str
    workflow_dir: Path
    workflow_root_rel: Path
    workflow_meta_file: Path
    runs_dir: Path
    package_dir: Path
    reference: str
    source_path: Path | None
    manifest_path: Path | None
    module_name: str | None
    class_name: str | None
    authoring_shape: str | None
    source_root_kind: str
    source_root: Path | None
    package_name: str | None
    package_module: str | None
    workflow_module: str | None


@dataclass(frozen=True, slots=True)
class RunWorkspace:
    workflow_workspace: WorkflowWorkspace
    run_id: str
    run_dir: Path
    events_file: Path
    request_file: Path
    sessions_dir: Path
    checkpoint_file: Path
    run_meta_file: Path
    trace_file: Path
    raw_dir: Path
    children_file: Path
    parent_file: Path


@dataclass(frozen=True, slots=True)
class ParentRunRecord:
    task_id: str
    workflow_name: str
    run_id: str
    task_folder: str
    workflow_folder: str
    run_folder: str


@dataclass(frozen=True, slots=True)
class RunRecord:
    root: Path
    task_id: str
    workflow_name: str
    run_id: str
    status: str | None
    created_at: str | None
    updated_at: str | None
    metadata: dict[str, Any]
    task_dir: Path
    workflow_dir: Path
    run_dir: Path
    run_meta_file: Path
    checkpoint_file: Path
    request_file: Path
    events_file: Path
    children_file: Path
    parent_file: Path
    trace_file: Path
    raw_dir: Path

    @property
    def workflow_params(self) -> dict[str, Any]:
        payload = self.metadata.get("workflow_params")
        if isinstance(payload, dict):
            return normalize_mapping(payload)
        return {}

    @property
    def pending_input(self) -> dict[str, Any] | None:
        payload = self.metadata.get("pending_input")
        if isinstance(payload, dict):
            return normalize_mapping(payload)
        question = self.metadata.get("pending_question")
        if isinstance(question, str) and question:
            return {"question": question}
        return None

    @property
    def pending_question(self) -> str | None:
        pending_input = self.pending_input
        if pending_input is not None:
            question = pending_input.get("question")
            if isinstance(question, str) and question:
                return question
        value = self.metadata.get("pending_question")
        if isinstance(value, str) and value:
            return value
        return None

    @property
    def normalized_status(self) -> str | None:
        return normalize_run_status(self.status)

    @property
    def awaiting_input(self) -> bool:
        return self.normalized_status == "awaiting_input"

    @property
    def paused(self) -> bool:
        return self.awaiting_input

    @property
    def resumable(self) -> bool:
        return self.checkpoint_file.is_file()

    @property
    def checkpoint_exists(self) -> bool:
        return self.checkpoint_file.is_file()

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return (
            self.updated_at or "",
            self.created_at or "",
            self.run_id,
        )


@dataclass(frozen=True, slots=True)
class TaskRecord:
    root: Path
    task_id: str
    created_at: str | None
    updated_at: str | None
    request_updated_at: str | None
    metadata: dict[str, Any]
    task_dir: Path
    task_meta_file: Path
    task_request_file: Path
    task_messages_file: Path

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return (
            self.updated_at or self.request_updated_at or "",
            self.created_at or "",
            self.task_id,
        )


def primary_state_root(root: Path) -> Path:
    return root / STATE_DIRNAME


def resolve_resume_state_root(root: Path) -> Path:
    return primary_state_root(root.resolve())


def latest_run_id(runs_dir: Path) -> str | None:
    if not runs_dir.exists():
        return None
    run_dirs = [path for path in runs_dir.iterdir() if path.is_dir()]
    if not run_dirs:
        return None
    return max(run_dirs, key=lambda path: path.stat().st_mtime).name


def create_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"run-{timestamp}-{uuid4().hex[:8]}"


def repo_relative_path(root: Path, path: Path) -> Path:
    return Path(os.path.relpath(path, root))


def task_request_text(task_request_file: Path) -> str | None:
    if not task_request_file.exists():
        return None
    return _normalize_request_text(task_request_file.read_text(encoding="utf-8"))


def write_request_snapshot(request_file: Path, request_text: str | None) -> None:
    if request_file.exists():
        return
    body = _normalize_request_text(request_text) or DEFAULT_REQUEST_TEXT
    request_file.parent.mkdir(parents=True, exist_ok=True)
    request_file.write_text(body.rstrip() + "\n", encoding="utf-8")


def ensure_workspace(
    root: Path,
    task_id: str,
    message: str | None = None,
    record_message: bool = True,
    *,
    state_dir: Path | None = None,
) -> TaskWorkspace:
    workspace = resolve_task_workspace(root, task_id, state_dir=state_dir)
    resolved_root = workspace.root
    resolved_state_root = workspace.state_root
    tasks_dir = workspace.tasks_dir
    tasks_dir.mkdir(parents=True, exist_ok=True)

    task_dir = workspace.task_dir
    task_dir.mkdir(parents=True, exist_ok=True)
    task_root_rel = workspace.task_root_rel
    task_meta_file = workspace.task_meta_file
    task_request_file = workspace.task_request_file
    task_messages_file = workspace.task_messages_file

    current_request = task_request_text(task_request_file)
    normalized_message = _normalize_request_text(message)
    request_updated = False
    if normalized_message is not None and record_message:
        _append_message(task_messages_file, normalized_message)
        next_request = normalized_message
        if next_request != current_request:
            current_request = next_request
            request_updated = True

    had_request = current_request is not None
    body = current_request or DEFAULT_REQUEST_TEXT
    task_request_file.parent.mkdir(parents=True, exist_ok=True)
    if request_updated or not had_request or not task_request_file.exists():
        task_request_file.write_text(body.rstrip() + "\n", encoding="utf-8")

    now = _utcnow()
    task_meta = _load_json(task_meta_file, default={"task_id": task_id, "created_at": now})
    task_meta["task_id"] = task_id
    task_meta["request_file"] = str(task_root_rel / "request.md")
    task_meta["messages_file"] = str(task_root_rel / "messages.jsonl")
    if request_updated or "request_updated_at" not in task_meta:
        task_meta["request_updated_at"] = now
    task_meta["updated_at"] = now
    _write_json(task_meta_file, task_meta)

    return workspace


def resolve_task_workspace(
    root: Path,
    task_id: str,
    *,
    state_dir: Path | None = None,
) -> TaskWorkspace:
    resolved_root = root.resolve()
    resolved_state_root = (state_dir or primary_state_root(resolved_root)).resolve()
    tasks_dir = resolved_state_root / "tasks"
    task_dir = tasks_dir / task_id
    task_root_rel = repo_relative_path(resolved_root, task_dir)
    return TaskWorkspace(
        root=resolved_root,
        state_root=resolved_state_root,
        tasks_dir=tasks_dir,
        task_dir=task_dir,
        task_id=task_id,
        task_root_rel=task_root_rel,
        task_meta_file=task_dir / "task.json",
        task_request_file=task_dir / "request.md",
        task_messages_file=task_dir / "messages.jsonl",
    )


def ensure_workflow_workspace(
    task_workspace: TaskWorkspace,
    workflow_name: str,
    *,
    package_dir: Path,
    reference: str,
    source_path: Path | None = None,
    manifest_path: Path | None = None,
    module_name: str | None = None,
    class_name: str | None = None,
    authoring_shape: str | None = None,
    source_root_kind: str = "workspace",
    source_root: Path | None = None,
    package_name: str | None = None,
    package_module: str | None = None,
    workflow_module: str | None = None,
) -> WorkflowWorkspace:
    workspace = resolve_workflow_workspace(
        task_workspace,
        workflow_name,
        package_dir=package_dir,
        reference=reference,
        source_path=source_path,
        manifest_path=manifest_path,
        module_name=module_name,
        class_name=class_name,
        authoring_shape=authoring_shape,
        source_root_kind=source_root_kind,
        source_root=source_root,
        package_name=package_name,
        package_module=package_module,
        workflow_module=workflow_module,
    )
    workflow_dir = workspace.workflow_dir
    workflow_dir.mkdir(parents=True, exist_ok=True)
    runs_dir = workspace.runs_dir
    runs_dir.mkdir(parents=True, exist_ok=True)

    workflow_meta_file = workspace.workflow_meta_file
    workflow_root_rel = workspace.workflow_root_rel
    now = _utcnow()
    payload = _load_json(
        workflow_meta_file,
        default={
            "task_id": task_workspace.task_id,
            "workflow_name": workflow_name,
            "created_at": now,
        },
    )
    payload["task_id"] = task_workspace.task_id
    payload["workflow_name"] = workflow_name
    payload["workflow_folder"] = str(workflow_root_rel)
    payload["package_folder"] = _serialize_path(task_workspace.root, workspace.package_dir)
    payload["workflow"] = _workflow_origin_payload(
        task_workspace.root,
        workflow_name=workflow_name,
        reference=reference,
        source_path=workspace.source_path,
        manifest_path=workspace.manifest_path,
        module_name=workspace.module_name,
        class_name=workspace.class_name,
        authoring_shape=workspace.authoring_shape,
        source_root_kind=workspace.source_root_kind,
        source_root=workspace.source_root,
        package_name=workspace.package_name,
        package_module=workspace.package_module,
        workflow_module=workspace.workflow_module,
        package_folder=workspace.package_dir,
    )
    payload["updated_at"] = now
    _write_json(workflow_meta_file, payload)

    return workspace


def resolve_workflow_workspace(
    task_workspace: TaskWorkspace,
    workflow_name: str,
    *,
    package_dir: Path,
    reference: str,
    source_path: Path | None = None,
    manifest_path: Path | None = None,
    module_name: str | None = None,
    class_name: str | None = None,
    authoring_shape: str | None = None,
    source_root_kind: str = "workspace",
    source_root: Path | None = None,
    package_name: str | None = None,
    package_module: str | None = None,
    workflow_module: str | None = None,
) -> WorkflowWorkspace:
    workflow_dir = task_workspace.task_dir / f"wf_{workflow_name}"
    workflow_root_rel = repo_relative_path(task_workspace.root, workflow_dir)
    return WorkflowWorkspace(
        task_workspace=task_workspace,
        workflow_name=workflow_name,
        workflow_dir=workflow_dir,
        workflow_root_rel=workflow_root_rel,
        workflow_meta_file=workflow_dir / "workflow.json",
        runs_dir=workflow_dir / "runs",
        package_dir=package_dir.resolve(),
        reference=reference,
        source_path=None if source_path is None else source_path.resolve(),
        manifest_path=None if manifest_path is None else manifest_path.resolve(),
        module_name=module_name,
        class_name=class_name,
        authoring_shape=authoring_shape,
        source_root_kind=source_root_kind,
        source_root=None if source_root is None else source_root.resolve(),
        package_name=package_name,
        package_module=package_module,
        workflow_module=workflow_module,
    )


def create_run(
    workflow_workspace: WorkflowWorkspace,
    *,
    run_id: str | None = None,
    message: str | None = None,
    workflow_params: dict[str, Any] | None = None,
    workflow_input: dict[str, Any] | None = None,
) -> RunWorkspace:
    resolved_run_id = run_id or create_run_id()
    run_workspace = resolve_run_workspace(workflow_workspace, resolved_run_id)
    run_dir = run_workspace.run_dir
    if run_dir.exists():
        raise FileExistsError(f"run {resolved_run_id!r} already exists under {workflow_workspace.runs_dir}")
    run_dir.mkdir(parents=True, exist_ok=False)

    run_workspace.events_file.write_text("", encoding="utf-8")
    if message is None:
        message = task_request_text(workflow_workspace.task_workspace.task_request_file)
    write_request_snapshot(run_workspace.request_file, message)
    run_workspace.sessions_dir.mkdir(parents=True, exist_ok=True)
    update_run_metadata(
        run_workspace,
        workflow_params=resolve_run_workflow_params(run_workspace, workflow_params),
        workflow_input=resolve_run_workflow_input(run_workspace, workflow_input),
        status="created",
    )
    update_workflow_metadata(workflow_workspace, last_run_id=resolved_run_id)
    return run_workspace


def open_existing_run(workflow_workspace: WorkflowWorkspace, run_id: str) -> RunWorkspace:
    run_workspace = resolve_run_workspace(workflow_workspace, run_id)
    run_dir = run_workspace.run_dir
    if not run_dir.is_dir():
        raise FileNotFoundError(f"run {run_id!r} does not exist under {workflow_workspace.runs_dir}")

    run_workspace.events_file.touch(exist_ok=True)
    if not run_workspace.request_file.exists():
        write_request_snapshot(
            run_workspace.request_file,
            task_request_text(workflow_workspace.task_workspace.task_request_file),
        )
    run_workspace.sessions_dir.mkdir(parents=True, exist_ok=True)
    return run_workspace


def resolve_run_workspace(workflow_workspace: WorkflowWorkspace, run_id: str) -> RunWorkspace:
    run_dir = workflow_workspace.runs_dir / run_id
    return RunWorkspace(
        workflow_workspace=workflow_workspace,
        run_id=run_id,
        run_dir=run_dir,
        events_file=run_dir / "events.jsonl",
        request_file=run_dir / "request.md",
        sessions_dir=run_dir / "sessions",
        checkpoint_file=run_dir / "checkpoint.json",
        run_meta_file=run_dir / "run.json",
        trace_file=run_dir / "trace.jsonl",
        raw_dir=run_dir / "raw",
        children_file=run_dir / "children.jsonl",
        parent_file=run_dir / "parent.json",
    )


def list_task_records(
    root: Path,
    *,
    task_ids: str | Iterable[str] | None = None,
) -> tuple[TaskRecord, ...]:
    tasks_dir = primary_state_root(root.resolve()) / "tasks"
    if not tasks_dir.is_dir():
        return ()

    normalized_task_ids = _normalize_summary_names(task_ids, field_name="task_ids")
    allowed_task_ids = None if normalized_task_ids is None else set(normalized_task_ids)

    records: list[TaskRecord] = []
    for task_dir in sorted(path for path in tasks_dir.iterdir() if path.is_dir()):
        if allowed_task_ids is not None and task_dir.name not in allowed_task_ids:
            continue
        task_meta_file = task_dir / "task.json"
        metadata = _load_json(task_meta_file, default={"task_id": task_dir.name})
        task_id = metadata.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            task_id = task_dir.name
        if allowed_task_ids is not None and task_id not in allowed_task_ids:
            continue
        records.append(
            TaskRecord(
                root=root.resolve(),
                task_id=task_id,
                created_at=_optional_text_value(metadata.get("created_at")),
                updated_at=_optional_text_value(metadata.get("updated_at")),
                request_updated_at=_optional_text_value(metadata.get("request_updated_at")),
                metadata=metadata,
                task_dir=task_dir,
                task_meta_file=task_meta_file,
                task_request_file=task_dir / "request.md",
                task_messages_file=task_dir / "messages.jsonl",
            )
        )
    return tuple(sorted(records, key=lambda record: record.sort_key, reverse=True))


def list_run_records(
    root: Path,
    *,
    workflow_name: str | None = None,
    task_id: str | None = None,
    status: str | None = None,
) -> tuple[RunRecord, ...]:
    tasks_dir = primary_state_root(root.resolve()) / "tasks"
    if not tasks_dir.is_dir():
        return ()

    normalized_status = normalize_run_status(status)
    records: list[RunRecord] = []
    for task_dir in sorted(path for path in tasks_dir.iterdir() if path.is_dir()):
        if task_id is not None and task_dir.name != task_id:
            continue
        for workflow_dir in sorted(path for path in task_dir.glob("wf_*") if path.is_dir()):
            fallback_workflow_name = workflow_dir.name[3:]
            if workflow_name is not None and fallback_workflow_name != workflow_name:
                continue
            runs_dir = workflow_dir / "runs"
            if not runs_dir.is_dir():
                continue
            for run_dir in sorted(path for path in runs_dir.iterdir() if path.is_dir()):
                metadata = _load_json(run_dir / "run.json", default={})
                resolved_workflow_name = metadata.get("workflow_name")
                if not isinstance(resolved_workflow_name, str) or not resolved_workflow_name:
                    resolved_workflow_name = fallback_workflow_name
                if workflow_name is not None and resolved_workflow_name != workflow_name:
                    continue
                resolved_task_id = metadata.get("task_id")
                if not isinstance(resolved_task_id, str) or not resolved_task_id:
                    resolved_task_id = task_dir.name
                record = RunRecord(
                    root=root.resolve(),
                    task_id=resolved_task_id,
                    workflow_name=resolved_workflow_name,
                    run_id=run_dir.name,
                    status=metadata.get("status") if isinstance(metadata.get("status"), str) else None,
                    created_at=metadata.get("created_at") if isinstance(metadata.get("created_at"), str) else None,
                    updated_at=metadata.get("updated_at") if isinstance(metadata.get("updated_at"), str) else None,
                    metadata=metadata,
                    task_dir=task_dir,
                    workflow_dir=workflow_dir,
                    run_dir=run_dir,
                    run_meta_file=run_dir / "run.json",
                    checkpoint_file=run_dir / "checkpoint.json",
                    request_file=run_dir / "request.md",
                    events_file=run_dir / "events.jsonl",
                    children_file=run_dir / "children.jsonl",
                    parent_file=run_dir / "parent.json",
                    trace_file=run_dir / "trace.jsonl",
                    raw_dir=run_dir / "raw",
                )
                if normalized_status is not None and record.normalized_status != normalized_status:
                    continue
                records.append(record)
    return tuple(sorted(records, key=lambda record: record.sort_key, reverse=True))


def list_workflow_run_summaries(
    root: Path,
    *,
    workflow_names: Iterable[str] | None = None,
    statuses: str | Iterable[str] | None = None,
    max_runs_per_workflow: int | None = None,
) -> tuple[dict[str, Any], ...]:
    normalized_workflow_names = _normalize_summary_names(workflow_names, field_name="workflow_names")
    normalized_statuses = _normalize_summary_statuses(statuses)
    normalized_max_runs = _normalize_summary_limit(max_runs_per_workflow, field_name="max_runs_per_workflow")

    records = list_run_records(root.resolve())
    allowed_workflows = None if normalized_workflow_names is None else set(normalized_workflow_names)
    allowed_statuses = None if normalized_statuses is None else set(normalized_statuses)

    grouped: dict[str, list[RunRecord]] = {}
    for record in records:
        if allowed_workflows is not None and record.workflow_name not in allowed_workflows:
            continue
        if allowed_statuses is not None and record.normalized_status not in allowed_statuses:
            continue
        grouped.setdefault(record.workflow_name, []).append(record)

    summary_names = tuple(sorted(grouped)) if normalized_workflow_names is None else normalized_workflow_names
    return tuple(
        _workflow_run_summary_payload(
            workflow_name=name,
            records=grouped.get(name, ()),
            max_runs_per_workflow=normalized_max_runs,
        )
        for name in summary_names
    )


def list_task_operation_summaries(
    root: Path,
    *,
    task_ids: str | Iterable[str] | None = None,
    workflow_names: str | Iterable[str] | None = None,
    statuses: str | Iterable[str] | None = None,
    max_tasks: int | None = None,
    max_runs_per_workflow: int | None = None,
    max_messages_per_task: int | None = None,
) -> tuple[dict[str, Any], ...]:
    normalized_task_ids = _normalize_summary_names(task_ids, field_name="task_ids")
    normalized_workflow_names = _normalize_summary_names(workflow_names, field_name="workflow_names")
    normalized_statuses = _normalize_summary_statuses(statuses)
    normalized_max_tasks = _normalize_summary_limit(max_tasks, field_name="max_tasks")
    normalized_max_runs = _normalize_summary_limit(max_runs_per_workflow, field_name="max_runs_per_workflow")
    normalized_max_messages = _normalize_summary_limit(max_messages_per_task, field_name="max_messages_per_task")

    task_records = list_task_records(root.resolve(), task_ids=normalized_task_ids)
    records = list_run_records(root.resolve())
    allowed_workflows = None if normalized_workflow_names is None else set(normalized_workflow_names)
    allowed_statuses = None if normalized_statuses is None else set(normalized_statuses)

    grouped_by_task: dict[str, list[RunRecord]] = {}
    for record in records:
        if allowed_workflows is not None and record.workflow_name not in allowed_workflows:
            continue
        if allowed_statuses is not None and record.normalized_status not in allowed_statuses:
            continue
        grouped_by_task.setdefault(record.task_id, []).append(record)

    if normalized_task_ids is None and (allowed_workflows is not None or allowed_statuses is not None):
        task_records = tuple(record for record in task_records if record.task_id in grouped_by_task)

    summaries = [
        _task_operation_summary_payload(
            record,
            grouped_by_task.get(record.task_id, ()),
            workflow_names=normalized_workflow_names,
            max_runs_per_workflow=normalized_max_runs,
            max_messages_per_task=normalized_max_messages,
        )
        for record in task_records
    ]
    ordered = tuple(sorted(summaries, key=_task_operation_summary_sort_key, reverse=True))
    if normalized_max_tasks is not None:
        return ordered[:normalized_max_tasks]
    return ordered


def resolve_run_record(
    root: Path,
    *,
    workflow_name: str,
    task_id: str,
    run_id: str | None = None,
    selector: str = "latest",
) -> RunRecord:
    records = list_run_records(root, workflow_name=workflow_name, task_id=task_id)
    if run_id is not None:
        for record in records:
            if record.run_id == run_id:
                return record
        raise FileNotFoundError(f"run {run_id!r} does not exist for workflow {workflow_name!r} on task {task_id!r}")

    if selector == "latest":
        label = "run"
        candidates = records
    elif selector == "latest_resumable":
        label = "resumable run"
        candidates = tuple(record for record in records if record.resumable)
    elif selector == "latest_paused":
        label = "awaiting-input run"
        candidates = tuple(record for record in records if record.paused)
    else:  # pragma: no cover - defensive branch
        raise ValueError(f"unsupported run selector {selector!r}")

    if not candidates:
        raise FileNotFoundError(f"no {label} exists for workflow {workflow_name!r} on task {task_id!r}")
    return max(candidates, key=lambda record: record.sort_key)


def update_run_metadata(
    run_workspace: RunWorkspace,
    *,
    workflow_params: dict[str, Any] | None = None,
    workflow_input: dict[str, Any] | None = None,
    status: str | None = None,
    terminal: str | None = None,
    pending_input: Mapping[str, Any] | None = None,
    error: str | None = None,
    topology: Mapping[str, Any] | None = None,
    finalization: Mapping[str, Any] | None | object = _UNSET,
) -> None:
    workflow_workspace = run_workspace.workflow_workspace
    task_workspace = workflow_workspace.task_workspace
    now = _utcnow()
    payload = _load_json(
        run_workspace.run_meta_file,
        default={
            "task_id": task_workspace.task_id,
            "workflow_name": workflow_workspace.workflow_name,
            "run_id": run_workspace.run_id,
            "created_at": now,
        },
    )
    payload["schema"] = RUN_METADATA_SCHEMA
    payload["task_id"] = task_workspace.task_id
    payload["workflow_name"] = workflow_workspace.workflow_name
    payload["run_id"] = run_workspace.run_id
    payload["task_folder"] = str(task_workspace.task_root_rel)
    payload["workflow_folder"] = str(workflow_workspace.workflow_root_rel)
    payload["run_folder"] = _serialize_path(task_workspace.root, run_workspace.run_dir)
    payload["package_folder"] = _serialize_path(task_workspace.root, workflow_workspace.package_dir)
    payload["request_file"] = _serialize_path(task_workspace.root, run_workspace.request_file)
    payload["workflow"] = _workflow_origin_payload(
        task_workspace.root,
        workflow_name=workflow_workspace.workflow_name,
        reference=workflow_workspace.reference,
        source_path=workflow_workspace.source_path,
        manifest_path=workflow_workspace.manifest_path,
        module_name=workflow_workspace.module_name,
        class_name=workflow_workspace.class_name,
        authoring_shape=workflow_workspace.authoring_shape,
        source_root_kind=workflow_workspace.source_root_kind,
        source_root=workflow_workspace.source_root,
        package_name=workflow_workspace.package_name,
        package_module=workflow_workspace.package_module,
        workflow_module=workflow_workspace.workflow_module,
        package_folder=workflow_workspace.package_dir,
    )
    if workflow_params is not None:
        payload["workflow_params"] = normalize_mapping(workflow_params)
    else:
        payload.setdefault("workflow_params", {})
    if workflow_input is not None:
        payload["workflow_input"] = normalize_mapping(workflow_input)
    if status is not None:
        payload["status"] = status
    if terminal is not None:
        payload["terminal"] = terminal
    elif status == "running":
        payload.pop("terminal", None)
    if pending_input is not None:
        payload["pending_input"] = normalize_mapping(pending_input)
    elif "pending_input" in payload and pending_input is None:
        payload["pending_input"] = None
    payload.pop("pending_question", None)
    if error is not None:
        payload["error"] = error
    elif error is None and "error" in payload and status not in {"fatal_error"}:
        payload.pop("error", None)
    if topology is not None:
        payload["topology"] = normalize_mapping(topology)
    if finalization is not _UNSET:
        if isinstance(finalization, Mapping):
            payload["finalization"] = normalize_mapping(finalization)
        else:
            payload.pop("finalization", None)
    payload["updated_at"] = now
    _write_json(run_workspace.run_meta_file, payload)
    update_workflow_metadata(workflow_workspace, last_run_id=run_workspace.run_id, last_status=payload.get("status"))


def update_run_git_tracking(run_dir: Path, payload: Mapping[str, Any]) -> None:
    def mutate(run_meta: dict[str, Any]) -> None:
        section = run_meta.get("git_tracking")
        if not isinstance(section, dict):
            section = {}
            run_meta["git_tracking"] = section
        section.update(normalize_mapping(payload))

    _update_run_metadata_file(run_dir, mutate)


def append_run_git_step(run_dir: Path, payload: Mapping[str, Any]) -> None:
    def mutate(run_meta: dict[str, Any]) -> None:
        section = run_meta.get("git_tracking")
        if not isinstance(section, dict):
            section = {}
            run_meta["git_tracking"] = section
        summary = normalize_mapping(payload)
        section["latest_step"] = summary
        sequence = summary.get("sequence")
        if isinstance(sequence, int):
            section["latest_sequence"] = sequence

    _update_run_metadata_file(run_dir, mutate)


def update_run_tracing(run_dir: Path, payload: Mapping[str, Any]) -> None:
    def mutate(run_meta: dict[str, Any]) -> None:
        section = run_meta.get("tracing")
        if not isinstance(section, dict):
            section = {}
            run_meta["tracing"] = section
        section.update(normalize_mapping(payload))

    _update_run_metadata_file(run_dir, mutate)


def append_run_warning(run_dir: Path, payload: Mapping[str, Any]) -> None:
    def mutate(run_meta: dict[str, Any]) -> None:
        warnings = run_meta.get("warnings")
        if not isinstance(warnings, list):
            warnings = []
            run_meta["warnings"] = warnings
        warnings.append(normalize_mapping(payload))

    _update_run_metadata_file(run_dir, mutate)


def next_observability_sequence(run_dir: Path) -> int:
    max_sequence = 0
    for filename in ("trace.jsonl", "git_tracking.jsonl"):
        candidate = run_dir / filename
        if not candidate.is_file():
            continue
        for raw_line in candidate.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip():
                continue
            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            sequence = payload.get("sequence")
            if isinstance(sequence, int):
                max_sequence = max(max_sequence, sequence)
    raw_dir = run_dir / "raw"
    if raw_dir.is_dir():
        for path in raw_dir.iterdir():
            if not path.is_file():
                continue
            match = _RAW_SEQUENCE_PATTERN.match(path.name)
            if match is None:
                continue
            max_sequence = max(max_sequence, int(match.group("sequence")))
    return max_sequence + 1


def resolve_run_workflow_params(
    run_workspace: RunWorkspace,
    workflow_params: dict[str, Any] | None,
) -> dict[str, Any]:
    if run_workspace.run_meta_file.exists():
        payload = _load_json(run_workspace.run_meta_file, default={})
        stored_params = payload.get("workflow_params")
        if isinstance(stored_params, dict):
            return normalize_mapping(stored_params)
        return {}

    if workflow_params is not None:
        return normalize_mapping(workflow_params)
    return {}


def resolve_run_workflow_input(
    run_workspace: RunWorkspace,
    workflow_input: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if run_workspace.run_meta_file.exists():
        payload = _load_json(run_workspace.run_meta_file, default={})
        stored_input = payload.get("workflow_input")
        if isinstance(stored_input, dict):
            return normalize_mapping(stored_input)
        if workflow_input is not None:
            return normalize_mapping(workflow_input)
        return None

    if workflow_input is not None:
        return normalize_mapping(workflow_input)
    return None


def update_workflow_metadata(
    workflow_workspace: WorkflowWorkspace,
    *,
    last_run_id: str | None = None,
    last_status: object | None = None,
) -> None:
    now = _utcnow()
    payload = _load_json(
        workflow_workspace.workflow_meta_file,
        default={
            "task_id": workflow_workspace.task_workspace.task_id,
            "workflow_name": workflow_workspace.workflow_name,
            "created_at": now,
        },
    )
    payload["task_id"] = workflow_workspace.task_workspace.task_id
    payload["workflow_name"] = workflow_workspace.workflow_name
    payload["workflow_folder"] = str(workflow_workspace.workflow_root_rel)
    payload["package_folder"] = _serialize_path(workflow_workspace.task_workspace.root, workflow_workspace.package_dir)
    payload["workflow"] = _workflow_origin_payload(
        workflow_workspace.task_workspace.root,
        workflow_name=workflow_workspace.workflow_name,
        reference=workflow_workspace.reference,
        source_path=workflow_workspace.source_path,
        manifest_path=workflow_workspace.manifest_path,
        module_name=workflow_workspace.module_name,
        class_name=workflow_workspace.class_name,
        authoring_shape=workflow_workspace.authoring_shape,
        source_root_kind=workflow_workspace.source_root_kind,
        source_root=workflow_workspace.source_root,
        package_name=workflow_workspace.package_name,
        package_module=workflow_workspace.package_module,
        workflow_module=workflow_workspace.workflow_module,
        package_folder=workflow_workspace.package_dir,
    )
    if last_run_id is not None:
        payload["last_run_id"] = last_run_id
    if isinstance(last_status, str):
        payload["last_status"] = last_status
    payload["updated_at"] = now
    _write_json(workflow_workspace.workflow_meta_file, payload)


def write_parent_run_metadata(child_run: RunWorkspace, parent_run: RunWorkspace) -> ParentRunRecord:
    child_task_workspace = child_run.workflow_workspace.task_workspace
    parent_workflow = parent_run.workflow_workspace
    parent_task_workspace = parent_workflow.task_workspace
    payload = ParentRunRecord(
        task_id=parent_task_workspace.task_id,
        workflow_name=parent_workflow.workflow_name,
        run_id=parent_run.run_id,
        task_folder=str(parent_task_workspace.task_root_rel),
        workflow_folder=str(parent_workflow.workflow_root_rel),
        run_folder=_serialize_path(child_task_workspace.root, parent_run.run_dir),
    )
    serialized = {
        "task_id": payload.task_id,
        "workflow_name": payload.workflow_name,
        "run_id": payload.run_id,
        "task_folder": payload.task_folder,
        "workflow_folder": payload.workflow_folder,
        "run_folder": payload.run_folder,
    }
    _write_json(child_run.parent_file, serialized)

    run_payload = _load_json(child_run.run_meta_file, default={})
    run_payload["schema"] = RUN_METADATA_SCHEMA
    run_payload["parent"] = serialized
    run_payload["updated_at"] = _utcnow()
    _write_json(child_run.run_meta_file, run_payload)
    return payload


def append_child_run_record(parent_run: RunWorkspace, payload: dict[str, Any]) -> None:
    record = normalize_mapping(payload)
    record.setdefault("schema", CHILD_RUN_SUMMARY_SCHEMA)
    record.setdefault("ts", _utcnow())
    parent_run.children_file.parent.mkdir(parents=True, exist_ok=True)
    with parent_run.children_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _workflow_run_summary_payload(
    *,
    workflow_name: str,
    records: Iterable[RunRecord],
    max_runs_per_workflow: int | None,
) -> dict[str, Any]:
    materialized = tuple(records)
    status_counts: dict[str, int] = {}
    for record in materialized:
        status_key = record.normalized_status or "unknown"
        status_counts[status_key] = status_counts.get(status_key, 0) + 1

    recent_records = materialized if max_runs_per_workflow is None else materialized[:max_runs_per_workflow]
    latest_record = materialized[0] if materialized else None
    return {
        "latest_run_id": None if latest_record is None else latest_record.run_id,
        "latest_updated_at": None if latest_record is None else latest_record.updated_at,
        "recent_runs": [_workflow_run_excerpt_payload(record) for record in recent_records],
        "run_count": len(materialized),
        "status_counts": dict(sorted(status_counts.items())),
        "workflow_name": workflow_name,
    }


def _workflow_run_excerpt_payload(record: RunRecord) -> dict[str, Any]:
    return {
        "created_at": record.created_at,
        "error": _optional_text_value(record.metadata.get("error")),
        "finalization": dict(record.metadata.get("finalization"))
        if isinstance(record.metadata.get("finalization"), dict)
        else None,
        "pending_input": record.pending_input,
        "request_excerpt": _request_excerpt(record.request_file),
        "request_file": str(record.request_file),
        "run_folder": str(record.run_dir),
        "run_id": record.run_id,
        "status": record.normalized_status,
        "task_id": record.task_id,
        "terminal": _optional_text_value(record.metadata.get("terminal")),
        "updated_at": record.updated_at,
    }


def _task_operation_summary_payload(
    task_record: TaskRecord,
    records: Iterable[RunRecord],
    *,
    workflow_names: tuple[str, ...] | None,
    max_runs_per_workflow: int | None,
    max_messages_per_task: int | None,
) -> dict[str, Any]:
    materialized = tuple(records)
    grouped: dict[str, list[RunRecord]] = {}
    for record in materialized:
        grouped.setdefault(record.workflow_name, []).append(record)

    recent_messages, message_count, latest_message_at = _recent_message_excerpt_payloads(
        task_record.task_messages_file,
        max_messages_per_task=max_messages_per_task,
    )
    summary_names = tuple(sorted(grouped)) if workflow_names is None else workflow_names
    workflow_run_summaries = [
        _workflow_run_summary_payload(
            workflow_name=name,
            records=grouped.get(name, ()),
            max_runs_per_workflow=max_runs_per_workflow,
        )
        for name in summary_names
    ]

    latest_run_activity = next(
        (
            record.updated_at or record.created_at
            for record in materialized
            if (record.updated_at or record.created_at) is not None
        ),
        None,
    )
    latest_activity_at = max(
        [
            value
            for value in (
                task_record.updated_at,
                task_record.request_updated_at,
                latest_message_at,
                latest_run_activity,
            )
            if value is not None
        ],
        default=None,
    )
    return {
        "created_at": task_record.created_at,
        "latest_activity_at": latest_activity_at,
        "message_count": message_count,
        "recent_messages": recent_messages,
        "request_excerpt": _request_excerpt(task_record.task_request_file),
        "request_updated_at": task_record.request_updated_at,
        "source_paths": {
            "messages_file": str(task_record.task_messages_file),
            "request_file": str(task_record.task_request_file),
            "task_dir": str(task_record.task_dir),
            "task_meta_file": str(task_record.task_meta_file),
        },
        "task_id": task_record.task_id,
        "updated_at": task_record.updated_at,
        "workflow_run_summaries": workflow_run_summaries,
    }


def _task_operation_summary_sort_key(summary: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _optional_text_value(summary.get("latest_activity_at")) or "",
        _optional_text_value(summary.get("updated_at")) or "",
        _optional_text_value(summary.get("task_id")) or "",
    )


def _workflow_origin_payload(
    root: Path,
    *,
    workflow_name: str,
    reference: str,
    source_path: Path | None,
    manifest_path: Path | None,
    module_name: str | None,
    class_name: str | None,
    authoring_shape: str | None,
    source_root_kind: str,
    source_root: Path | None,
    package_name: str | None,
    package_module: str | None,
    workflow_module: str | None,
    package_folder: Path,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": workflow_name,
        "reference": reference,
        "authoring_shape": authoring_shape,
        "module_name": module_name,
        "class_name": class_name,
        "source_path": None if source_path is None else _serialize_origin_path(root, source_path),
        "manifest_path": None if manifest_path is None else _serialize_origin_path(root, manifest_path),
        "package_folder": _serialize_origin_path(root, package_folder),
        "source_root_kind": source_root_kind,
        "source_root": None if source_root is None else _serialize_origin_path(root, source_root),
        "package_name": package_name,
        "package_module": package_module,
        "workflow_module": workflow_module,
    }
    return payload


def _update_run_metadata_file(run_dir: Path, mutator: Callable[[dict[str, Any]], None]) -> None:
    run_meta_file = run_dir / "run.json"
    payload = _load_json(run_meta_file, default={})
    mutator(payload)
    payload["schema"] = RUN_METADATA_SCHEMA
    payload["updated_at"] = _utcnow()
    _write_json(run_meta_file, payload)


def _append_message(task_messages_file: Path, message: str) -> None:
    task_messages_file.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": _utcnow(),
        "message": message,
    }
    with task_messages_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _normalize_request_text(text: str | None) -> str | None:
    if text is None:
        return None
    normalized = text.strip()
    return normalized or None


def _text_excerpt(text: str | None, *, max_chars: int = 160) -> str | None:
    excerpt = _normalize_request_text(text)
    if excerpt is None:
        return None
    single_line = " ".join(excerpt.split())
    if len(single_line) <= max_chars:
        return single_line
    return single_line[: max_chars - 3].rstrip() + "..."


def _request_excerpt(request_file: Path, *, max_chars: int = 160) -> str | None:
    if not request_file.is_file():
        return None
    return _text_excerpt(request_file.read_text(encoding="utf-8"), max_chars=max_chars)


def _recent_message_excerpt_payloads(
    task_messages_file: Path,
    *,
    max_messages_per_task: int | None,
) -> tuple[list[dict[str, Any]], int, str | None]:
    if not task_messages_file.is_file():
        return [], 0, None

    entries: list[dict[str, Any]] = []
    for index, raw_line in enumerate(task_messages_file.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive branch
            raise ValueError(f"{task_messages_file} line {index} is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"{task_messages_file} line {index} must decode to a JSON object")
        message = _require_message_text(payload.get("message"), task_messages_file=task_messages_file, line_no=index)
        entries.append(
            {
                "message_excerpt": _text_excerpt(message),
                "ts": _optional_text_value(payload.get("ts")),
            }
        )

    recent = entries if max_messages_per_task is None else entries[-max_messages_per_task:]
    latest_message_at = next(
        (entry["ts"] for entry in reversed(entries) if isinstance(entry.get("ts"), str) and entry["ts"]),
        None,
    )
    return list(reversed(recent)), len(entries), latest_message_at


def _normalize_summary_names(values: str | Iterable[str] | None, *, field_name: str) -> tuple[str, ...] | None:
    if values is None:
        return None
    raw_values: Iterable[str]
    if isinstance(values, str):
        raw_values = (values,)
    else:
        raw_values = values
    normalized = sorted({_require_summary_text(value, field_name=field_name) for value in raw_values})
    if not normalized:
        raise ValueError(f"{field_name} must contain at least one non-empty string when provided")
    return tuple(normalized)


def _normalize_summary_statuses(values: str | Iterable[str] | None) -> tuple[str, ...] | None:
    normalized = _normalize_summary_names(values, field_name="statuses")
    if normalized is None:
        return None
    return tuple(
        sorted(
            {
                status
                for status in (normalize_run_status(value) for value in normalized)
                if status is not None
            }
        )
    )


def _normalize_summary_limit(value: int | None, *, field_name: str) -> int | None:
    if value is None:
        return None
    if value <= 0:
        raise ValueError(f"{field_name} must be a positive integer when provided")
    return value


def _require_summary_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} entries must be non-empty strings")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} entries must be non-empty strings")
    return normalized


def _require_message_text(value: object, *, task_messages_file: Path, line_no: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{task_messages_file} line {line_no} must define a non-empty string message")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{task_messages_file} line {line_no} must define a non-empty string message")
    return normalized


def _optional_text_value(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _load_json(path: Path, *, default: dict[str, Any]) -> dict[str, Any]:
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                if path.name == "run.json":
                    validate_persisted_schema(
                        payload,
                        expected=RUN_METADATA_SCHEMA,
                        artifact_name=str(path),
                        legacy_migrator=lambda value: migrate_schemaless_payload(value, expected=RUN_METADATA_SCHEMA),
                    )
                return payload
        except (json.JSONDecodeError, OSError):
            pass
    return dict(default)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _serialize_path(root: Path, path: Path) -> str:
    return str(repo_relative_path(root, path))


def _serialize_origin_path(root: Path, path: Path) -> str:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        return str(resolved_path.relative_to(resolved_root))
    except ValueError:
        return str(resolved_path)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()
