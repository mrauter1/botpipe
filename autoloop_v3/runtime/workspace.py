"""Generic filesystem workspace management."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


STATE_DIRNAME = ".autoloop"
LEGACY_STATE_DIRNAME = ".superloop"
DEFAULT_REQUEST_TEXT = "No explicit initial request was provided for this run. Use repository artifacts and explicit clarifications only."


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
    legacy_context_file: Path
    runs_dir: Path


@dataclass(frozen=True, slots=True)
class RunWorkspace:
    run_id: str
    run_dir: Path
    events_file: Path
    request_file: Path
    sessions_dir: Path
    checkpoint_file: Path


def primary_state_root(root: Path) -> Path:
    return root / STATE_DIRNAME


def legacy_state_root(root: Path) -> Path:
    return root / LEGACY_STATE_DIRNAME


def resolve_resume_state_root(root: Path, *, task_id: str | None = None, run_id: str | None = None) -> Path:
    primary_tasks = primary_state_root(root) / "tasks"
    legacy_tasks = legacy_state_root(root) / "tasks"
    if run_id is not None:
        primary_run_task = task_id_for_run(primary_tasks, run_id)
        if primary_run_task is not None and (task_id is None or primary_run_task == task_id):
            return primary_state_root(root)
        legacy_run_task = task_id_for_run(legacy_tasks, run_id)
        if legacy_run_task is not None and (task_id is None or legacy_run_task == task_id):
            return legacy_state_root(root)
    if task_id is not None and (primary_tasks / task_id).is_dir():
        return primary_state_root(root)
    if task_id is not None and (legacy_tasks / task_id).is_dir():
        return legacy_state_root(root)
    if latest_task_id(primary_tasks) is not None:
        return primary_state_root(root)
    if latest_task_id(legacy_tasks) is not None:
        return legacy_state_root(root)
    return primary_state_root(root)


def latest_task_id(tasks_dir: Path) -> str | None:
    if not tasks_dir.exists():
        return None
    task_dirs = [path for path in tasks_dir.iterdir() if path.is_dir()]
    if not task_dirs:
        return None
    return max(task_dirs, key=lambda path: path.stat().st_mtime).name


def task_id_for_run(tasks_dir: Path, run_id: str) -> str | None:
    if not tasks_dir.exists():
        return None
    for task_dir in tasks_dir.iterdir():
        if not task_dir.is_dir():
            continue
        if (task_dir / "runs" / run_id).is_dir():
            return task_dir.name
    return None


def create_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"run-{timestamp}-{uuid4().hex[:8]}"


def repo_relative_path(root: Path, path: Path) -> Path:
    return Path(os.path.relpath(path, root))


def write_request_snapshot(request_file: Path, request_text: str | None) -> None:
    if request_file.exists():
        return
    body = _normalize_request_text(request_text) or DEFAULT_REQUEST_TEXT
    request_file.parent.mkdir(parents=True, exist_ok=True)
    request_file.write_text(body.rstrip() + "\n", encoding="utf-8")


def task_request_text(task_meta_file: Path, legacy_context_file: Path | None = None) -> str | None:
    payload = _load_task_meta(task_meta_file, task_meta_file.parent.name)
    request_text = _normalize_request_text(
        payload.get("request_text") if isinstance(payload.get("request_text"), str) else None
    )
    if request_text:
        return request_text
    if legacy_context_file is not None:
        return _extract_request_from_legacy_context(legacy_context_file)
    return None


def ensure_workspace(
    root: Path,
    task_id: str,
    product_intent: str | None = None,
    intent_mode: str = "replace",
    *,
    state_dir: Path | None = None,
) -> TaskWorkspace:
    resolved_root = root.resolve()
    resolved_state_root = (state_dir or primary_state_root(resolved_root)).resolve()
    tasks_dir = resolved_state_root / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    task_dir = tasks_dir / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    task_root_rel = repo_relative_path(resolved_root, task_dir)
    runs_dir = task_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    task_meta_file = task_dir / "task.json"
    legacy_context_file = task_dir / "context.md"
    task_request_file = task_dir / "request.md"

    task_meta = _load_task_meta(task_meta_file, task_id)
    existing_request = _normalize_request_text(
        task_meta.get("request_text") if isinstance(task_meta.get("request_text"), str) else None
    )
    if existing_request is None:
        existing_request = _extract_request_from_legacy_context(legacy_context_file)

    normalized_intent = _normalize_request_text(product_intent)
    if normalized_intent is not None:
        if intent_mode == "replace" or existing_request is None:
            existing_request = normalized_intent
        elif intent_mode == "append":
            stamp = datetime.now(timezone.utc).isoformat()
            existing_request = f"{existing_request}\n\n## Run Intent ({stamp})\n{normalized_intent}"
        elif intent_mode == "preserve" and existing_request is None:
            existing_request = normalized_intent

    task_meta["request_text"] = existing_request
    task_meta["request_updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_task_meta(task_meta_file, task_meta)

    task_body = _normalize_request_text(existing_request) or DEFAULT_REQUEST_TEXT
    task_request_file.write_text(task_body.rstrip() + "\n", encoding="utf-8")

    return TaskWorkspace(
        root=resolved_root,
        state_root=resolved_state_root,
        tasks_dir=tasks_dir,
        task_dir=task_dir,
        task_id=task_id,
        task_root_rel=task_root_rel,
        task_meta_file=task_meta_file,
        task_request_file=task_request_file,
        legacy_context_file=legacy_context_file,
        runs_dir=runs_dir,
    )


def create_run(
    workspace: TaskWorkspace,
    *,
    run_id: str | None = None,
    request_text: str | None = None,
) -> RunWorkspace:
    resolved_run_id = run_id or create_run_id()
    run_dir = workspace.runs_dir / resolved_run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    events_file = run_dir / "events.jsonl"
    events_file.write_text("", encoding="utf-8")

    request_file = run_dir / "request.md"
    write_request_snapshot(request_file, request_text)

    sessions_dir = run_dir / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    return RunWorkspace(
        run_id=resolved_run_id,
        run_dir=run_dir,
        events_file=events_file,
        request_file=request_file,
        sessions_dir=sessions_dir,
        checkpoint_file=run_dir / "checkpoint.json",
    )


def open_existing_run(workspace: TaskWorkspace, run_id: str) -> RunWorkspace:
    run_dir = workspace.runs_dir / run_id
    if not run_dir.is_dir():
        raise FileNotFoundError(f"run {run_id!r} does not exist under {workspace.runs_dir}")

    events_file = run_dir / "events.jsonl"
    events_file.touch(exist_ok=True)
    request_file = run_dir / "request.md"
    if not request_file.exists():
        write_request_snapshot(request_file, task_request_text(workspace.task_meta_file, workspace.legacy_context_file))

    sessions_dir = run_dir / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    return RunWorkspace(
        run_id=run_id,
        run_dir=run_dir,
        events_file=events_file,
        request_file=request_file,
        sessions_dir=sessions_dir,
        checkpoint_file=run_dir / "checkpoint.json",
    )


def _normalize_request_text(text: str | None) -> str | None:
    if text is None:
        return None
    normalized = text.strip()
    return normalized or None


def _extract_request_from_legacy_context(context_file: Path) -> str | None:
    if not context_file.exists():
        return None
    text = context_file.read_text(encoding="utf-8").strip()
    if not text:
        return None
    text = re.split(r"\n### Clarification\b", text, maxsplit=1)[0].strip()
    if text.startswith("# Product Context"):
        text = text[len("# Product Context") :].strip()
    return text or None


def _load_task_meta(task_meta_file: Path, task_id: str) -> dict[str, object]:
    if task_meta_file.exists():
        try:
            payload = json.loads(task_meta_file.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except (json.JSONDecodeError, OSError):
            pass
    return {"task_id": task_id, "created_at": datetime.now(timezone.utc).isoformat()}


def _write_task_meta(task_meta_file: Path, payload: dict[str, object]) -> None:
    task_meta_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
