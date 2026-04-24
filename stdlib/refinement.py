"""Small authoring helpers for selected-workflow refinement surfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:  # pragma: no branch - supports both package and direct repo-root imports
    from ..core.workflow_capabilities import inspect_workflow_reference
    from ..runtime.loader import resolve_workflow_reference
except ImportError:  # pragma: no cover - direct repo-root import fallback
    from core.workflow_capabilities import inspect_workflow_reference
    from runtime.loader import resolve_workflow_reference

from .lifecycle import write_workflow_json


def write_selected_workflow_authoring_surface(
    ctx,
    workflow: str | type[Any],
    relative_path: str | Path = "selected_workflow_authoring_surface.json",
) -> Path:
    """Write one selected workflow's editable authoring surface under ``ctx.workflow_folder``."""

    repo_root = _repo_root_from_context(ctx)
    resolved = resolve_workflow_reference(repo_root, workflow)
    capability = inspect_workflow_reference(repo_root, resolved.workflow_cls)
    package_dir = capability.package_dir
    prompt_paths = [str(path) for path in capability.prompt_paths]
    asset_paths = [str(path) for path in capability.asset_paths]
    runtime_test_path = _runtime_test_path(capability.test_paths)
    package_init_path = None if capability.package_init_path is None else str(capability.package_init_path)
    contracts_path = None if capability.contracts_path is None else str(capability.contracts_path)
    doc_path = None if capability.doc_path is None else str(capability.doc_path)
    manifest_path = None if capability.manifest_path is None else str(capability.manifest_path)
    params_path = None if capability.params_path is None else str(capability.params_path)
    spec_paths = [str(path) for path in capability.spec_paths]
    test_paths = [str(path) for path in capability.test_paths]
    editable_paths = sorted(
        {
            str(capability.source_path),
            *(
                path
                for path in (
                    manifest_path,
                    package_init_path,
                    params_path,
                    contracts_path,
                    doc_path,
                    runtime_test_path,
                    *spec_paths,
                    *prompt_paths,
                    *asset_paths,
                    *test_paths,
                )
                if path is not None
            ),
        }
    )

    return write_workflow_json(
        ctx,
        relative_path,
        {
            "repo_root": str(repo_root),
            "run_id": ctx.run_id,
            "selected_workflow_authoring_surface": {
                "asset_paths": asset_paths,
                "contracts_path": contracts_path,
                "doc_path": doc_path,
                "editable_paths": editable_paths,
                "manifest_path": manifest_path,
                "package_dir": str(package_dir),
                "package_init_path": package_init_path,
                "package_name": capability.package_name,
                "params_path": params_path,
                "prompt_paths": prompt_paths,
                "runtime_test_path": runtime_test_path,
                "spec_paths": spec_paths,
                "test_paths": test_paths,
                "workflow_name": resolved.package.workflow_name,
                "workflow_path": str(capability.workflow_path),
            },
            "selected_workflow_name": resolved.package.workflow_name,
            "task_id": ctx.task_id,
            "workflow_name": ctx.workflow_name,
        },
    )


def _runtime_test_path(test_paths: tuple[Path, ...]) -> str | None:
    for path in test_paths:
        if path.name.startswith("test_"):
            return str(path)
    return None


def _repo_root_from_context(ctx) -> Path:
    return ctx.root.resolve()


__all__ = ["write_selected_workflow_authoring_surface"]
