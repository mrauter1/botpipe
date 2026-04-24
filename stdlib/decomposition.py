"""Small authoring helpers for selected-workflow decomposition surfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:  # pragma: no branch - supports both package and direct repo-root imports
    from ..core.workflow_capabilities import (
        WorkflowArtifactCapability,
        WorkflowStepCapability,
        annotation_display_name,
        inspect_workflow_reference,
        workflow_parameter_fields,
    )
    from ..runtime.loader import resolve_workflow_reference
except ImportError:  # pragma: no cover - direct repo-root import fallback
    from core.workflow_capabilities import (
        WorkflowArtifactCapability,
        WorkflowStepCapability,
        annotation_display_name,
        inspect_workflow_reference,
        workflow_parameter_fields,
    )
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
    capability = inspect_workflow_reference(repo_root, resolved.workflow_cls)
    package_dir = capability.package_dir
    package_init_path = None if capability.package_init_path is None else str(capability.package_init_path)
    prompt_paths = [str(path) for path in capability.prompt_paths]
    asset_paths = [str(path) for path in capability.asset_paths]
    contracts_path = None if capability.contracts_path is None else str(capability.contracts_path)
    runtime_test_path = _runtime_test_path(capability.test_paths)
    manifest_path = None if capability.manifest_path is None else str(capability.manifest_path)
    params_path = None if capability.params_path is None else str(capability.params_path)
    doc_path = None if capability.doc_path is None else str(capability.doc_path)
    spec_paths = [str(path) for path in capability.spec_paths]
    test_paths = [str(path) for path in capability.test_paths]
    editable_paths = sorted(
        {
            *(
                path
                for path in (
                    str(capability.workflow_path),
                    package_init_path,
                    manifest_path,
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
            "selected_workflow_decomposition_surface": {
                "selected_workflow_authoring_surface": {
                    "asset_paths": asset_paths,
                    "asset_paths_repo_relative": [_repo_relative(repo_root, path) for path in asset_paths],
                    "contracts_path": contracts_path,
                    "contracts_path_repo_relative": _optional_repo_relative(repo_root, contracts_path),
                    "doc_path": doc_path,
                    "doc_path_repo_relative": _optional_repo_relative(repo_root, doc_path),
                    "editable_paths": editable_paths,
                    "editable_paths_repo_relative": [_repo_relative(repo_root, path) for path in editable_paths],
                    "manifest_path": manifest_path,
                    "manifest_path_repo_relative": _optional_repo_relative(repo_root, manifest_path),
                    "package_dir": str(package_dir),
                    "package_dir_repo_relative": _optional_repo_relative(repo_root, package_dir),
                    "package_init_path": package_init_path,
                    "package_init_path_repo_relative": _optional_repo_relative(repo_root, package_init_path),
                    "params_path": params_path,
                    "params_path_repo_relative": _optional_repo_relative(repo_root, params_path),
                    "prompt_paths": prompt_paths,
                    "prompt_paths_repo_relative": [_repo_relative(repo_root, path) for path in prompt_paths],
                    "runtime_test_path": runtime_test_path,
                    "runtime_test_path_repo_relative": _optional_repo_relative(repo_root, runtime_test_path),
                    "spec_paths": spec_paths,
                    "spec_paths_repo_relative": [_repo_relative(repo_root, path) for path in spec_paths],
                    "test_paths": test_paths,
                    "test_paths_repo_relative": [_repo_relative(repo_root, path) for path in test_paths],
                    "workflow_path": str(capability.workflow_path),
                    "workflow_path_repo_relative": _optional_repo_relative(repo_root, capability.workflow_path),
                },
                "selected_workflow_compiled_surface": {
                    "artifacts": [_artifact_payload(artifact) for artifact in capability.artifacts],
                    "entry_step_name": capability.entry_step_name,
                    "global_routes": dict(capability.global_transitions),
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
                    "sessions": list(capability.sessions),
                    "state_model": capability.state_model,
                    "step_count": len(capability.steps),
                    "steps": [
                        _compiled_step_payload(
                            repo_root,
                            package_dir,
                            step=step,
                            route_targets=capability.transitions.get(step.name, {}),
                        )
                        for step in capability.steps
                    ],
                },
                "selected_workflow_identity": {
                    "aliases": list(capability.aliases),
                    "description": capability.description,
                    "package_name": capability.package_name,
                    "title": capability.title,
                    "workflow_class": capability.workflow_class,
                    "workflow_name": resolved.package.workflow_name,
                },
            },
            "selected_workflow_name": resolved.package.workflow_name,
            "task_id": ctx.task_id,
            "workflow_name": ctx.workflow_name,
        },
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


def _artifact_payload(artifact: WorkflowArtifactCapability) -> dict[str, Any]:
    return {
        "name": artifact.name,
        "producer_steps": list(artifact.producer_steps),
        "template": artifact.template,
        "workflow_level": artifact.workflow_level,
    }


def _prompt_repo_relative(repo_root: Path, package_dir: Path, prompt_path: str | None) -> str | None:
    if prompt_path is None:
        return None
    return _optional_repo_relative(repo_root, package_dir / prompt_path)


def _runtime_test_path(test_paths: tuple[Path, ...]) -> str | None:
    for path in test_paths:
        if path.name.startswith("test_"):
            return str(path)
    return None


def _optional_repo_relative(repo_root: Path, path: str | Path | None) -> str | None:
    if path is None:
        return None
    return _repo_relative(repo_root, path)


def _repo_relative(repo_root: Path, path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(repo_root).as_posix()
    except ValueError:
        return str(resolved)


def _repo_root_from_context(ctx) -> Path:
    return ctx.root.resolve()


__all__ = ["write_selected_workflow_decomposition_surface"]
