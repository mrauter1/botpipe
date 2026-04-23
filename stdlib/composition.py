"""Small authoring helpers for explicit child-workflow composition."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def run_child_workflow(
    ctx,
    workflow: str | type[Any],
    *,
    message: str,
    parameters: Mapping[str, Any] | None = None,
):
    """Invoke a child workflow through the existing runtime-backed context surface."""

    return ctx.invoke_workflow(workflow, message=message, parameters=dict(parameters or {}))


def adopt_child_artifacts(
    ctx,
    child_result,
    *,
    mapping: Mapping[str, str | Path],
) -> dict[str, Path]:
    """Copy selected child artifacts into ``ctx.workflow_folder`` explicitly."""

    adopted: dict[str, Path] = {}
    for artifact_name, relative_path in mapping.items():
        try:
            source_path = child_result.output_artifacts[artifact_name]
        except KeyError as exc:
            raise KeyError(
                f"child workflow {child_result.workflow_name!r} did not produce artifact {artifact_name!r}"
            ) from exc
        if not source_path.is_file():
            raise FileNotFoundError(
                f"child artifact {artifact_name!r} for workflow {child_result.workflow_name!r} is missing at "
                f"{source_path}"
            )
        target_path = _workflow_local_path(ctx, relative_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target_path)
        adopted[artifact_name] = target_path
    return adopted


def _workflow_local_path(ctx, relative_path: str | Path) -> Path:
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("composition helper adoption paths must stay under ctx.workflow_folder")
    return ctx.workflow_folder / path


__all__ = ["adopt_child_artifacts", "run_child_workflow"]
