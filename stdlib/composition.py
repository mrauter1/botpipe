"""Small authoring helpers for explicit child-workflow composition."""

from __future__ import annotations

import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def run_child_workflow(
    ctx,
    workflow: str | type[Any],
    *,
    message: str,
    parameters: Mapping[str, Any] | None = None,
    input: Any | None = None,
):
    """Invoke a child workflow through the existing runtime-backed context surface."""

    return ctx.invoke_workflow(workflow, message=message, parameters=dict(parameters or {}), input=input)


def require_child_workflow_result(
    child_result,
    *,
    status: str = "success",
    last_event: str | None = None,
    required_artifacts: Sequence[str] = (),
):
    """Validate an explicit child-workflow success contract before parent-local adoption."""

    if child_result.status != status:
        raise ValueError(
            f"child workflow {child_result.workflow_name!r} returned status {child_result.status!r}, "
            f"expected {status!r}"
        )
    child_last_event = None if child_result.last_event is None else child_result.last_event.tag
    if last_event is not None and child_last_event != last_event:
        raise ValueError(
            f"child workflow {child_result.workflow_name!r} ended with route {child_last_event!r}, "
            f"expected {last_event!r}"
        )
    for artifact_name in required_artifacts:
        try:
            source_path = child_result.output_artifacts[artifact_name]
        except KeyError as exc:
            raise KeyError(
                f"child workflow {child_result.workflow_name!r} did not produce required artifact "
                f"{artifact_name!r}"
            ) from exc
        if not source_path.is_file():
            raise FileNotFoundError(
                f"child workflow {child_result.workflow_name!r} reported required artifact "
                f"{artifact_name!r} at {source_path}, but the file is missing"
            )
    return child_result


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


__all__ = ["adopt_child_artifacts", "require_child_workflow_result", "run_child_workflow"]
