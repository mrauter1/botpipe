"""Small authoring helpers for selected-workflow refinement surfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:  # pragma: no branch - supports both package and direct repo-root imports
    from ..runtime.loader import resolve_workflow_reference
    from ..core.workflow_catalog import discover_workflow_catalog
except ImportError:  # pragma: no cover - direct repo-root import fallback
    from runtime.loader import resolve_workflow_reference
    from core.workflow_catalog import discover_workflow_catalog

from .lifecycle import write_workflow_json


def write_selected_workflow_authoring_surface(
    ctx,
    workflow: str | type[Any],
    relative_path: str | Path = "selected_workflow_authoring_surface.json",
) -> Path:
    """Write one selected workflow's editable authoring surface under ``ctx.workflow_folder``."""

    repo_root = _repo_root_from_context(ctx)
    resolved = resolve_workflow_reference(repo_root, workflow)
    catalog_entry = _selected_workflow_catalog_entry(repo_root, resolved.package.package_name)
    package_dir = catalog_entry.package_dir
    prompt_paths = _descendant_file_paths(package_dir / "prompts")
    asset_paths = _descendant_file_paths(package_dir / "assets")
    runtime_test_path = _optional_file(repo_root / "tests" / "runtime" / f"test_{resolved.package.workflow_name}.py")
    package_init_path = package_dir / "__init__.py"
    contracts_path = _optional_file(package_dir / "contracts.py")

    surface_paths = sorted(
        {
            str(package_init_path),
            str(catalog_entry.manifest_path),
            str(catalog_entry.workflow_path),
            *prompt_paths,
            *asset_paths,
            *(
                path
                for path in (
                    None if catalog_entry.params_path is None else str(catalog_entry.params_path),
                    contracts_path,
                    None if catalog_entry.doc_path is None else str(catalog_entry.doc_path),
                    runtime_test_path,
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
                "doc_path": None if catalog_entry.doc_path is None else str(catalog_entry.doc_path),
                "editable_paths": surface_paths,
                "manifest_path": str(catalog_entry.manifest_path),
                "package_dir": str(package_dir),
                "package_init_path": str(package_init_path),
                "package_name": catalog_entry.package_name,
                "params_path": None if catalog_entry.params_path is None else str(catalog_entry.params_path),
                "prompt_paths": prompt_paths,
                "runtime_test_path": runtime_test_path,
                "workflow_name": resolved.package.workflow_name,
                "workflow_path": str(catalog_entry.workflow_path),
            },
            "selected_workflow_name": resolved.package.workflow_name,
            "task_id": ctx.task_id,
            "workflow_name": ctx.workflow_name,
        },
    )


def _selected_workflow_catalog_entry(repo_root: Path, package_name: str):
    catalog_entry = next(
        (
            entry
            for entry in discover_workflow_catalog(repo_root)
            if entry.package_name == package_name
        ),
        None,
    )
    if catalog_entry is None:
        raise LookupError(f"workflow package {package_name!r} was not found in the workflow catalog")
    return catalog_entry


def _descendant_file_paths(root: Path) -> list[str]:
    if not root.is_dir():
        return []
    return [str(path) for path in sorted(path for path in root.rglob("*") if path.is_file())]


def _optional_file(path: Path) -> str | None:
    return str(path) if path.is_file() else None


def _repo_root_from_context(ctx) -> Path:
    return ctx.root.resolve()


__all__ = ["write_selected_workflow_authoring_surface"]
