"""Small authoring helpers for selected-workflow adaptation artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:  # pragma: no branch - supports both package and direct repo-root imports
    from ..core.compiler import compile_workflow
    from ..core.workflow_capabilities import (
        WorkflowCapabilityEntry,
        WorkflowStepCapability,
        workflow_capability_payload,
        workflow_parameter_fields,
    )
    from ..core.workflow_catalog import discover_workflow_catalog
    from ..runtime.loader import coerce_workflow_parameter_mapping, resolve_workflow_reference
except ImportError:  # pragma: no cover - direct repo-root import fallback
    from core.compiler import compile_workflow
    from core.workflow_capabilities import (
        WorkflowCapabilityEntry,
        WorkflowStepCapability,
        workflow_capability_payload,
        workflow_parameter_fields,
    )
    from core.workflow_catalog import discover_workflow_catalog
    from runtime.loader import coerce_workflow_parameter_mapping, resolve_workflow_reference

from .lifecycle import write_workflow_json


def write_selected_workflow_capability_snapshot(
    ctx,
    workflow: str | type[Any],
    relative_path: str | Path = "selected_workflow_capability.json",
) -> Path:
    """Write one selected workflow's compiled contract under ``ctx.workflow_folder``."""

    repo_root = _repo_root_from_context(ctx)
    resolved = resolve_workflow_reference(repo_root, workflow)
    capability = workflow_capability_payload(_selected_workflow_capability_entry(repo_root, resolved))
    return write_workflow_json(
        ctx,
        relative_path,
        {
            "repo_root": str(repo_root),
            "run_id": ctx.run_id,
            "selected_workflow_capability": capability,
            "selected_workflow_name": resolved.package.workflow_name,
            "task_id": ctx.task_id,
            "workflow_name": ctx.workflow_name,
        },
    )


def write_validated_workflow_parameters(
    ctx,
    workflow: str | type[Any],
    payload: Mapping[str, Any] | None,
    relative_path: str | Path = "validated_workflow_parameters.json",
) -> Path:
    """Validate and persist workflow parameters through the shared loader coercion path."""

    repo_root = _repo_root_from_context(ctx)
    resolved = resolve_workflow_reference(repo_root, workflow)
    validated = coerce_workflow_parameter_mapping(resolved.parameters_cls, payload)
    return write_workflow_json(
        ctx,
        relative_path,
        {
            "repo_root": str(repo_root),
            "run_id": ctx.run_id,
            "selected_workflow_name": resolved.package.workflow_name,
            "task_id": ctx.task_id,
            "validated_parameters": validated,
            "workflow_name": ctx.workflow_name,
        },
    )


def _selected_workflow_capability_entry(repo_root: Path, resolved) -> WorkflowCapabilityEntry:
    catalog_entry = next(
        (
            entry
            for entry in discover_workflow_catalog(repo_root)
            if entry.package_name == resolved.package.package_name
        ),
        None,
    )
    if catalog_entry is None:
        raise LookupError(f"workflow package {resolved.package.package_name!r} was not found in the workflow catalog")

    compiled = compile_workflow(resolved.workflow_cls)
    return WorkflowCapabilityEntry(
        package_name=catalog_entry.package_name,
        workflow_name=catalog_entry.workflow_name,
        workflow_class=resolved.workflow_cls.__name__,
        title=catalog_entry.title,
        description=catalog_entry.description,
        aliases=catalog_entry.aliases,
        package_dir=catalog_entry.package_dir,
        manifest_path=catalog_entry.manifest_path,
        workflow_path=catalog_entry.workflow_path,
        params_path=catalog_entry.params_path,
        doc_path=catalog_entry.doc_path,
        entry_step_name=compiled.entry_step_name,
        parameters_supported=resolved.parameters_cls is not None,
        parameters=workflow_parameter_fields(resolved.parameters_cls),
        steps=tuple(_compiled_step_capability(step) for step in compiled.steps.values()),
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


def _prompt_path(prompt: Any) -> str | None:
    if prompt is None:
        return None
    return getattr(prompt, "path", prompt)


def _repo_root_from_context(ctx) -> Path:
    return ctx.root.resolve()


__all__ = [
    "write_selected_workflow_capability_snapshot",
    "write_validated_workflow_parameters",
]
