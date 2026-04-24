"""Small authoring helpers for selected-workflow decomposition surfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:  # pragma: no branch - supports both package and direct repo-root imports
    from ..core.compiler import compile_workflow
    from ..core.workflow_capabilities import (
        WorkflowStepCapability,
        annotation_display_name,
        workflow_parameter_fields,
    )
    from ..core.workflow_catalog import discover_workflow_catalog
    from ..runtime.loader import resolve_workflow_reference
except ImportError:  # pragma: no cover - direct repo-root import fallback
    from core.compiler import compile_workflow
    from core.workflow_capabilities import WorkflowStepCapability, annotation_display_name, workflow_parameter_fields
    from core.workflow_catalog import discover_workflow_catalog
    from runtime.loader import resolve_workflow_reference

from .lifecycle import write_workflow_json


def write_selected_workflow_decomposition_surface(
    ctx,
    workflow: str | type[Any],
    relative_path: str | Path = "selected_workflow_decomposition_surface.json",
) -> Path:
    """Write one selected workflow's authoring and compiled decomposition surface."""

    repo_root = _repo_root_from_context(ctx)
    resolved = resolve_workflow_reference(repo_root, workflow)
    catalog_entry = _selected_workflow_catalog_entry(repo_root, resolved.package.package_name)
    package_dir = catalog_entry.package_dir
    package_init_path = package_dir / "__init__.py"
    prompt_paths = _descendant_file_paths(package_dir / "prompts")
    asset_paths = _descendant_file_paths(package_dir / "assets")
    contracts_path = _optional_file(package_dir / "contracts.py")
    runtime_test_path = _optional_file(repo_root / "tests" / "runtime" / f"test_{resolved.package.workflow_name}.py")
    editable_paths = sorted(
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
    compiled = compile_workflow(resolved.workflow_cls)

    return write_workflow_json(
        ctx,
        relative_path,
        {
            "repo_root": str(repo_root),
            "run_id": ctx.run_id,
            "selected_workflow_decomposition_surface": {
                "selected_workflow_authoring_surface": {
                    "asset_paths": asset_paths,
                    "asset_paths_repo_relative": [_repo_relative(repo_root, path) for path in asset_paths],
                    "contracts_path": contracts_path,
                    "contracts_path_repo_relative": _optional_repo_relative(repo_root, contracts_path),
                    "doc_path": None if catalog_entry.doc_path is None else str(catalog_entry.doc_path),
                    "doc_path_repo_relative": _optional_repo_relative(
                        repo_root,
                        None if catalog_entry.doc_path is None else str(catalog_entry.doc_path),
                    ),
                    "editable_paths": editable_paths,
                    "editable_paths_repo_relative": [_repo_relative(repo_root, path) for path in editable_paths],
                    "manifest_path": str(catalog_entry.manifest_path),
                    "manifest_path_repo_relative": _repo_relative(repo_root, catalog_entry.manifest_path),
                    "package_dir": str(package_dir),
                    "package_dir_repo_relative": _repo_relative(repo_root, package_dir),
                    "package_init_path": str(package_init_path),
                    "package_init_path_repo_relative": _repo_relative(repo_root, package_init_path),
                    "params_path": None if catalog_entry.params_path is None else str(catalog_entry.params_path),
                    "params_path_repo_relative": _optional_repo_relative(
                        repo_root,
                        None if catalog_entry.params_path is None else str(catalog_entry.params_path),
                    ),
                    "prompt_paths": prompt_paths,
                    "prompt_paths_repo_relative": [_repo_relative(repo_root, path) for path in prompt_paths],
                    "runtime_test_path": runtime_test_path,
                    "runtime_test_path_repo_relative": _optional_repo_relative(repo_root, runtime_test_path),
                    "workflow_path": str(catalog_entry.workflow_path),
                    "workflow_path_repo_relative": _repo_relative(repo_root, catalog_entry.workflow_path),
                },
                "selected_workflow_compiled_surface": {
                    "entry_step_name": compiled.entry_step_name,
                    "global_routes": dict(compiled.global_routes),
                    "parameters": [
                        {
                            "default": field.default,
                            "name": field.name,
                            "repeated": field.supports_multiple,
                            "required": field.required,
                            "type": annotation_display_name(field.annotation),
                        }
                        for field in workflow_parameter_fields(resolved.parameters_cls)
                    ],
                    "parameters_supported": resolved.parameters_cls is not None,
                    "step_count": len(compiled.steps),
                    "steps": [
                        _compiled_step_payload(
                            repo_root,
                            package_dir,
                            step=_compiled_step_capability(compiled.steps[step_name]),
                            route_targets=compiled.routes.get(step_name, {}),
                        )
                        for step_name in compiled.steps
                    ],
                },
                "selected_workflow_identity": {
                    "aliases": list(catalog_entry.aliases),
                    "description": catalog_entry.description,
                    "package_name": catalog_entry.package_name,
                    "title": catalog_entry.title,
                    "workflow_class": resolved.workflow_cls.__name__,
                    "workflow_name": resolved.package.workflow_name,
                },
            },
            "selected_workflow_name": resolved.package.workflow_name,
            "task_id": ctx.task_id,
            "workflow_name": ctx.workflow_name,
        },
    )


def _compiled_step_capability(step) -> WorkflowStepCapability:
    return WorkflowStepCapability(
        name=step.name,
        kind=step.kind,
        session_name=step.session_name,
        requires=step.requires,
        produces=step.produces,
        log_artifacts=step.log_artifacts,
        available_routes=step.available_routes,
        expected_output_schema=step.expected_output_schema,
        route_contracts={route_name: dict(contract) for route_name, contract in step.route_contracts.items()},
        producer_prompt=_prompt_path(step.producer_prompt),
        verifier_prompt=_prompt_path(step.verifier_prompt),
    )


def _compiled_step_payload(
    repo_root: Path,
    package_dir: Path,
    *,
    step: WorkflowStepCapability,
    route_targets: dict[str, str],
) -> dict[str, Any]:
    return {
        "available_routes": list(step.available_routes),
        "expected_output_schema": step.expected_output_schema,
        "kind": step.kind,
        "log_artifacts": list(step.log_artifacts),
        "name": step.name,
        "producer_prompt": step.producer_prompt,
        "producer_prompt_repo_relative": _prompt_repo_relative(repo_root, package_dir, step.producer_prompt),
        "produces": list(step.produces),
        "requires": list(step.requires),
        "route_contracts": {route_name: dict(contract) for route_name, contract in step.route_contracts.items()},
        "route_targets": dict(route_targets),
        "session_name": step.session_name,
        "verifier_prompt": step.verifier_prompt,
        "verifier_prompt_repo_relative": _prompt_repo_relative(repo_root, package_dir, step.verifier_prompt),
    }


def _prompt_repo_relative(repo_root: Path, package_dir: Path, prompt_path: str | None) -> str | None:
    if prompt_path is None:
        return None
    return _repo_relative(repo_root, package_dir / prompt_path)


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


def _optional_repo_relative(repo_root: Path, path: str | Path | None) -> str | None:
    if path is None:
        return None
    return _repo_relative(repo_root, path)


def _repo_relative(repo_root: Path, path: str | Path) -> str:
    return Path(path).resolve().relative_to(repo_root).as_posix()

def _prompt_path(prompt: Any) -> str | None:
    if prompt is None:
        return None
    return getattr(prompt, "path", prompt)


def _repo_root_from_context(ctx) -> Path:
    return ctx.root.resolve()


__all__ = ["write_selected_workflow_decomposition_surface"]
