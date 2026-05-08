"""Small authoring helpers for deterministic workflow bootstrap/publication code."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def open_workflow_sessions(ctx, *session_refs: Any, scope: str | None = None) -> tuple[Any, ...]:
    """Open one or more declared workflow sessions explicitly from workflow code."""

    return tuple(ctx.open_session(ref, scope=scope) for ref in session_refs)


def write_workflow_json(ctx, relative_path: str | Path, payload: Mapping[str, Any]) -> Path:
    """Write one JSON artifact under ``ctx.workflow_folder`` and return its path."""

    target_path = _workflow_json_path(ctx, relative_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target_path


def write_invocation_contract(
    ctx,
    payload: Mapping[str, Any],
    *,
    relative_path: str | Path = "invocation_contract.json",
) -> Path:
    """Write the canonical workflow-local invocation contract with the run request snapshot."""

    request_path = ctx.run_folder / "request.md"
    return write_workflow_json(
        ctx,
        relative_path,
        {
            **dict(payload),
            "workflow_name": ctx.workflow_name,
            "task_id": ctx.task_id,
            "run_id": ctx.run_id,
            "request_file": str(request_path),
            "message": request_path.read_text(encoding="utf-8"),
        },
    )


def write_publication_receipt(
    ctx,
    relative_path: str | Path,
    payload: Mapping[str, Any],
) -> Path:
    """Write a workflow-local publication receipt without widening runtime behavior."""

    return write_workflow_json(ctx, relative_path, payload)


def _workflow_json_path(ctx, relative_path: str | Path) -> Path:
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("workflow-local JSON paths must stay under ctx.workflow_folder")
    if path.suffix != ".json":
        raise ValueError("workflow-local JSON helper paths must end in .json")
    return ctx.workflow_folder / path


__all__ = [
    "open_workflow_sessions",
    "write_invocation_contract",
    "write_publication_receipt",
    "write_workflow_json",
]
