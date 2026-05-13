"""Importing workflow-capability inspection for richer portfolio analysis."""

from __future__ import annotations

import importlib
import inspect
import sys
import tempfile
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from copy import deepcopy
from hashlib import sha1
from types import ModuleType, UnionType
from typing import Annotated, Any, Union, get_args, get_origin

from pydantic import BaseModel

from .compiler import compile_workflow
from .descriptors import effective_parameters_model
from .discovery import get_workflow_definition
from .lowering import step_authored_route_tags
from .route_reporting import (
    payload_contract_for_route,
    provider_response_contract_for_routes,
    route_fields_contract_for_route,
)
from .route_contracts import (
    available_route_tags_for_table,
    compiled_route_tags_for_table,
    provider_visible_route_tags_for_table,
    required_write_names,
    route_target_value,
    runtime_control_route_tags_for_table,
    suppressed_route_tags_for_table,
)
from .validation import is_workflow_class
from .workflow_catalog import AuthoringShape, WorkflowCatalogEntry, discover_workflow_catalog, workflow_search_roots
from .workflow_plan import WorkflowPlan


class WorkflowCapabilityInspectionError(LookupError):
    """Raised when rich workflow capability inspection cannot load a workflow."""


@dataclass(frozen=True, slots=True)
class WorkflowLoadedPackage:
    """Loaded workflow contract for importing inspection and runtime resolution."""

    workflow_cls: type[Any]
    parameters_cls: type[Any] | None
    compiled: WorkflowPlan


@dataclass(frozen=True, slots=True)
class _CapabilityResolvedReference:
    original: str
    kind: str
    workflow_name: str
    title: str | None
    description: str | None
    aliases: tuple[str, ...]
    class_name: str | None
    module_name: str | None
    source_path: Path | None
    package_dir: Path
    manifest_path: Path | None
    authoring_shape: AuthoringShape
    source_root_kind: str
    source_root: Path | None = None
    package_name: str | None = None
    package_module: str | None = None
    workflow_module: str | None = None


@dataclass(frozen=True, slots=True)
class _CapabilityResolvedWorkflow:
    reference: _CapabilityResolvedReference
    workflow_cls: type[Any]
    parameters_cls: type[Any] | None


@dataclass(frozen=True, slots=True)
class WorkflowParameterField:
    """Display and validation metadata for one workflow parameter."""

    name: str
    annotation: Any
    required: bool
    default: Any
    supports_multiple: bool


@dataclass(frozen=True, slots=True)
class WorkflowArtifactCapability:
    """Normalized compiled-artifact capability summary."""

    name: str
    template: str
    workflow_level: bool
    producer_steps: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WorkflowRouteCapability:
    """Normalized compiled-route capability summary."""

    target: str | None
    summary: str | None
    required_writes: tuple[str, ...]
    handoff: str | None
    on_taken: str | None
    provider_visibility: str
    provider_visible: bool
    provider_visible_interactive: bool
    provider_visible_full_auto: bool
    payload_schema_mode: str
    payload_schema: dict[str, Any] | None
    payload_contract: dict[str, Any]
    route_fields_schema: dict[str, Any] | None
    route_fields_contract: dict[str, Any]
    preset_kind: str
    inheritance_source: str
    disabled: bool
    is_runtime_control: bool
    available: bool


@dataclass(frozen=True, slots=True)
class WorkflowStepCapability:
    """Normalized compiled-step capability summary."""

    name: str
    kind: str
    session_name: str | None
    reads: tuple[str, ...]
    requires: tuple[str, ...]
    writes: tuple[str, ...]
    log_artifacts: tuple[str, ...]
    available_routes: tuple[str, ...]
    authored_routes: tuple[str, ...]
    compiled_route_tags: tuple[str, ...]
    suppressed_route_tags: tuple[str, ...]
    runtime_control_routes: tuple[str, ...]
    provider_visible_routes_interactive: tuple[str, ...]
    provider_visible_routes_full_auto: tuple[str, ...]
    provider_response_contracts: dict[str, Any]
    expected_output_schema: dict[str, Any] | None
    routes: dict[str, WorkflowRouteCapability]
    compiled_routes: dict[str, WorkflowRouteCapability]
    producer_prompt: str | None
    verifier_prompt: str | None


@dataclass(frozen=True, slots=True)
class WorkflowCapabilityEntry:
    """Rich importing inspection for one discovered or explicitly resolved workflow."""

    package_name: str
    workflow_name: str
    workflow_class: str
    state_model: str
    parameters_model: str | None
    title: str | None
    description: str | None
    aliases: tuple[str, ...]
    package_dir: Path
    package_folder: Path
    manifest_path: Path | None
    workflow_path: Path
    source_path: Path
    params_path: Path | None
    doc_path: Path | None
    authoring_shape: AuthoringShape
    flow_path: Path | None
    workflow_py_path: Path | None
    package_init_path: Path | None
    package_module: str | None
    workflow_module: str | None
    spec_paths: tuple[Path, ...]
    prompt_paths: tuple[Path, ...]
    asset_paths: tuple[Path, ...]
    doc_paths: tuple[Path, ...]
    test_paths: tuple[Path, ...]
    entry_step_name: str
    parameters_supported: bool
    parameters: tuple[WorkflowParameterField, ...]
    sessions: tuple[str, ...]
    artifacts: tuple[WorkflowArtifactCapability, ...]
    routes: dict[str, dict[str, str]]
    global_routes: dict[str, str]
    compiled_global_routes: dict[str, WorkflowRouteCapability]
    steps: tuple[WorkflowStepCapability, ...]


def inspect_workflow_capabilities(root: str | Path) -> tuple[WorkflowCapabilityEntry, ...]:
    """Inspect all discovered workflows with importing capability detail."""

    root_path = Path(root).resolve()
    catalog = discover_workflow_catalog(root_path)
    return tuple(_inspect_catalog_entry(root_path, entry) for entry in catalog)


def inspect_workflow_reference(root: str | Path, reference: str | type[Any]) -> WorkflowCapabilityEntry:
    """Inspect one workflow reference through the unified runtime resolver."""

    root_path = Path(root).resolve()
    resolved = _resolve_reference(root_path, reference)
    catalog_entry = _catalog_entry_for_reference(root_path, resolved.reference)
    compiled = compile_workflow(resolved.workflow_cls)
    return _capability_entry_from_resolved(resolved, compiled, catalog_entry)


def load_workflow_package_contract(root: str | Path, entry: WorkflowCatalogEntry) -> WorkflowLoadedPackage:
    """Load the main workflow class, parameters model, and compiled workflow for one catalog entry."""

    root_path = Path(root).resolve()
    if entry.source_root_kind != "package" or entry.workflow_module is None or entry.package_module is None:
        resolved = _resolve_reference(root_path, str(entry.source_path))
        compiled = compile_workflow(resolved.workflow_cls)
        return WorkflowLoadedPackage(
            workflow_cls=resolved.workflow_cls,
            parameters_cls=resolved.parameters_cls,
            compiled=compiled,
        )

    workflow_module = _import_discovered_module(entry.workflow_module, root_path)
    workflow_cls = locate_workflow_class(workflow_module, class_name=entry.manifest_class)
    compiled = compile_workflow(workflow_cls)
    if compiled.workflow_name != entry.workflow_name:
        raise WorkflowCapabilityInspectionError(
            f"workflow {entry.workflow_name!r} from {entry.source_path} compiles to {compiled.workflow_name!r}"
        )
    package_module = _import_discovered_module(entry.package_module, root_path)
    parameters_cls = _validate_package_exports(entry, package_module, workflow_cls)
    return WorkflowLoadedPackage(
        workflow_cls=workflow_cls,
        parameters_cls=parameters_cls,
        compiled=compiled,
    )


def locate_workflow_class(module: ModuleType, *, class_name: str | None = None) -> type[Any]:
    """Return the target workflow class from a loaded module."""

    if class_name is not None:
        candidate = getattr(module, class_name, None)
        if not is_workflow_class(candidate):
            raise WorkflowCapabilityInspectionError(
                f"workflow class {class_name!r} was not found in module {module.__name__!r}"
            )
        return candidate

    candidates = [
        value
        for value in module.__dict__.values()
        if isinstance(value, type) and value.__module__ == module.__name__ and is_workflow_class(value)
    ]
    if not candidates:
        raise WorkflowCapabilityInspectionError(f"no workflow class was found in module {module.__name__!r}")
    if len(candidates) > 1:
        names = ", ".join(sorted(candidate.__name__ for candidate in candidates))
        raise WorkflowCapabilityInspectionError(
            f"multiple workflow classes were found in module {module.__name__!r}: {names}; specify class_name"
        )
    return candidates[0]


def workflow_parameter_fields(parameters_cls: type[Any] | None) -> tuple[WorkflowParameterField, ...]:
    """Return normalized workflow parameter metadata for display and inspection."""

    if parameters_cls is None:
        return ()
    if isinstance(parameters_cls, type) and issubclass(parameters_cls, BaseModel):
        return tuple(
            WorkflowParameterField(
                name=name,
                annotation=field.annotation,
                required=field.is_required(),
                default=None if field.is_required() else json_safe_parameter_value(_parameter_field_default(field)),
                supports_multiple=_annotation_supports_multiple(field.annotation),
            )
            for name, field in parameters_cls.model_fields.items()
        )

    annotations = dict(getattr(parameters_cls, "__annotations__", {}))
    return tuple(
        WorkflowParameterField(
            name=name,
            annotation=annotation,
            required=not hasattr(parameters_cls, name),
            default=json_safe_parameter_value(getattr(parameters_cls, name, None)),
            supports_multiple=_annotation_supports_multiple(annotation),
        )
        for name, annotation in annotations.items()
    )


def annotation_display_name(annotation: Any) -> str:
    """Return a compact display string for a parameter annotation."""

    if annotation is None:
        return "Any"
    if isinstance(annotation, type):
        return annotation.__name__
    return str(annotation).replace("typing.", "")


def json_safe_parameter_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize workflow-parameter payloads to JSON-safe values."""

    return {str(key): json_safe_parameter_value(value) for key, value in payload.items()}


def json_safe_parameter_value(value: Any) -> Any:
    """Normalize one workflow-parameter value to a JSON-safe representation."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return json_safe_parameter_value(value.value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, BaseModel):
        return json_safe_parameter_mapping(value.model_dump(mode="python"))
    if is_dataclass(value) and not isinstance(value, type):
        return json_safe_parameter_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): json_safe_parameter_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe_parameter_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [json_safe_parameter_value(item) for item in sorted(value, key=lambda item: str(item))]
    return str(value)


def workflow_capability_payload(entry: WorkflowCapabilityEntry) -> dict[str, object]:
    """Convert one workflow-capability entry to a JSON-ready payload."""

    return {
        "aliases": list(entry.aliases),
        "artifacts": [
            {
                "name": artifact.name,
                "producer_steps": list(artifact.producer_steps),
                "template": artifact.template,
                "workflow_level": artifact.workflow_level,
            }
            for artifact in entry.artifacts
        ],
        "artifact_count": len(entry.artifacts),
        "asset_paths": [str(path) for path in entry.asset_paths],
        "authoring_shape": entry.authoring_shape,
        "description": entry.description,
        "doc_path": None if entry.doc_path is None else str(entry.doc_path),
        "doc_paths": [str(path) for path in entry.doc_paths],
        "entry_step_name": entry.entry_step_name,
        "flow_path": None if entry.flow_path is None else str(entry.flow_path),
        "global_routes": dict(entry.global_routes),
        "compiled_global_routes": {
            route_name: _route_capability_payload(route)
            for route_name, route in entry.compiled_global_routes.items()
        },
        "workflow_py_path": None if entry.workflow_py_path is None else str(entry.workflow_py_path),
        "manifest_path": None if entry.manifest_path is None else str(entry.manifest_path),
        "package_dir": str(entry.package_dir),
        "package_folder": str(entry.package_folder),
        "package_init_path": None if entry.package_init_path is None else str(entry.package_init_path),
        "package_module": entry.package_module,
        "package_name": entry.package_name,
        "parameters": [
            {
                "default": field.default,
                "name": field.name,
                "repeated": field.supports_multiple,
                "required": field.required,
                "type": annotation_display_name(field.annotation),
            }
            for field in entry.parameters
        ],
        "parameters_model": entry.parameters_model,
        "parameters_supported": entry.parameters_supported,
        "params_path": None if entry.params_path is None else str(entry.params_path),
        "prompt_paths": [str(path) for path in entry.prompt_paths],
        "session_count": len(entry.sessions),
        "sessions": list(entry.sessions),
        "source_path": str(entry.source_path),
        "spec_paths": [str(path) for path in entry.spec_paths],
        "state_model": entry.state_model,
        "step_count": len(entry.steps),
        "steps": [
            {
                "available_routes": list(step.available_routes),
                "authored_routes": list(step.authored_routes),
                "compiled_route_tags": list(step.compiled_route_tags),
                "suppressed_route_tags": list(step.suppressed_route_tags),
                "has_expected_output_schema": step.expected_output_schema is not None,
                "kind": step.kind,
                "log_artifacts": [_surface_ref_payload(value) for value in step.log_artifacts],
                "name": step.name,
                "provider_visible_routes_full_auto": list(step.provider_visible_routes_full_auto),
                "provider_visible_routes_interactive": list(step.provider_visible_routes_interactive),
                "provider_response_contracts": deepcopy(step.provider_response_contracts),
                "producer_prompt": step.producer_prompt,
                "writes": [_surface_ref_payload(value) for value in step.writes],
                "reads": [_surface_ref_payload(value) for value in step.reads],
                "requires": [_surface_ref_payload(value) for value in step.requires],
                "runtime_control_routes": list(step.runtime_control_routes),
                "routes": {route_name: _route_capability_payload(route) for route_name, route in step.routes.items()},
                "compiled_routes": {
                    route_name: _route_capability_payload(route)
                    for route_name, route in step.compiled_routes.items()
                },
                "session_name": step.session_name,
                "typed_output_schema": step.expected_output_schema,
                "verifier_prompt": step.verifier_prompt,
            }
            for step in entry.steps
        ],
        "test_paths": [str(path) for path in entry.test_paths],
        "title": entry.title,
        "routes": {
            "global": dict(entry.global_routes),
            "steps": {step_name: dict(routes) for step_name, routes in entry.routes.items()},
        },
        "workflow_class": entry.workflow_class,
        "workflow_module": entry.workflow_module,
        "workflow_name": entry.workflow_name,
        "workflow_path": str(entry.workflow_path),
    }


def selected_workflow_capability_payload(entry: WorkflowCapabilityEntry) -> dict[str, object]:
    """Return the authoritative compiled selected-workflow payload."""

    return workflow_capability_payload(entry)


def selected_workflow_authoring_surface_payload(entry: WorkflowCapabilityEntry) -> dict[str, object]:
    """Return the authoritative editable selected-workflow surface payload."""

    repo_root = _infer_repo_root_from_package_dir(entry.package_dir)
    runtime_test_path = _runtime_test_path(entry.test_paths)
    asset_paths = [str(path) for path in entry.asset_paths]
    prompt_paths = [str(path) for path in entry.prompt_paths]
    spec_paths = [str(path) for path in entry.spec_paths]
    test_paths = [str(path) for path in entry.test_paths]
    package_init_path = _optional_path_string(entry.package_init_path)
    doc_path = _optional_path_string(entry.doc_path)
    manifest_path = _optional_path_string(entry.manifest_path)
    params_path = _optional_path_string(entry.params_path)
    workflow_py_path = _optional_path_string(entry.workflow_py_path)
    editable_paths = sorted(
        {
            str(entry.source_path),
            *(
                path
                for path in (
                    manifest_path,
                    package_init_path,
                    params_path,
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
    return {
        "asset_paths": asset_paths,
        "asset_paths_repo_relative": _selected_workflow_repo_relative_list(repo_root, entry, entry.asset_paths),
        "doc_path": doc_path,
        "doc_path_repo_relative": _selected_workflow_repo_relative(repo_root, entry, entry.doc_path),
        "editable_paths": editable_paths,
        "editable_paths_repo_relative": _selected_workflow_repo_relative_list(repo_root, entry, editable_paths),
        "manifest_path": manifest_path,
        "manifest_path_repo_relative": _selected_workflow_repo_relative(repo_root, entry, entry.manifest_path),
        "package_dir": str(entry.package_dir),
        "package_dir_repo_relative": _selected_workflow_repo_relative(repo_root, entry, entry.package_dir),
        "package_init_path": package_init_path,
        "package_init_path_repo_relative": _selected_workflow_repo_relative(repo_root, entry, entry.package_init_path),
        "package_name": entry.package_name,
        "params_path": params_path,
        "params_path_repo_relative": _selected_workflow_repo_relative(repo_root, entry, entry.params_path),
        "prompt_paths": prompt_paths,
        "prompt_paths_repo_relative": _selected_workflow_repo_relative_list(repo_root, entry, entry.prompt_paths),
        "runtime_test_path": runtime_test_path,
        "runtime_test_path_repo_relative": _selected_workflow_repo_relative(repo_root, entry, runtime_test_path),
        "spec_paths": spec_paths,
        "spec_paths_repo_relative": _selected_workflow_repo_relative_list(repo_root, entry, entry.spec_paths),
        "test_paths": test_paths,
        "test_paths_repo_relative": _selected_workflow_repo_relative_list(repo_root, entry, entry.test_paths),
        "workflow_name": entry.workflow_name,
        "workflow_py_path": workflow_py_path,
        "workflow_py_path_repo_relative": _selected_workflow_repo_relative(repo_root, entry, entry.workflow_py_path),
        "workflow_path": str(entry.workflow_path),
        "workflow_path_repo_relative": _selected_workflow_repo_relative(repo_root, entry, entry.workflow_path),
    }


def selected_workflow_decomposition_surface_payload(
    entry: WorkflowCapabilityEntry,
    *,
    repo_root: str | Path,
) -> dict[str, object]:
    """Return the authoritative decomposition payload for one selected workflow."""

    repo_root_path = Path(repo_root).resolve()
    authoring_surface = selected_workflow_authoring_surface_payload(entry)
    decomposition_authoring_surface = {
        key: value
        for key, value in authoring_surface.items()
        if key not in {"package_name", "workflow_name"}
    }
    return {
        "selected_workflow_authoring_surface": decomposition_authoring_surface,
        "selected_workflow_compiled_surface": {
            "artifacts": [_artifact_capability_payload(artifact) for artifact in entry.artifacts],
            "entry_step_name": entry.entry_step_name,
            "global_routes": dict(entry.global_routes),
            "compiled_global_routes": {
                route_name: _route_capability_payload(route)
                for route_name, route in entry.compiled_global_routes.items()
            },
            "parameters": [_parameter_field_payload(field) for field in entry.parameters],
            "parameters_supported": entry.parameters_supported,
            "sessions": list(entry.sessions),
            "state_model": entry.state_model,
            "step_count": len(entry.steps),
            "steps": [
                _step_payload(
                    repo_root_path,
                    entry.package_dir,
                    step=step,
                    route_targets=entry.routes.get(step.name, {}),
                )
                for step in entry.steps
            ],
        },
        "selected_workflow_identity": {
            "aliases": list(entry.aliases),
            "description": entry.description,
            "package_name": entry.package_name,
            "title": entry.title,
            "workflow_class": entry.workflow_class,
            "workflow_name": entry.workflow_name,
        },
    }


def _inspect_catalog_entry(root_path: Path, entry: WorkflowCatalogEntry) -> WorkflowCapabilityEntry:
    if entry.source_root_kind == "package" and entry.workflow_module is not None and entry.package_module is not None:
        loaded = load_workflow_package_contract(root_path, entry)
        reference = _CapabilityResolvedReference(
            original=entry.workflow_name,
            kind="catalog_name",
            workflow_name=entry.workflow_name,
            title=entry.title,
            description=entry.description,
            aliases=entry.aliases,
            class_name=loaded.workflow_cls.__name__,
            module_name=loaded.workflow_cls.__module__,
            source_path=entry.source_path,
            package_dir=entry.package_dir,
            manifest_path=entry.manifest_path,
            authoring_shape=entry.authoring_shape,
            source_root_kind=entry.source_root_kind,
            source_root=entry.source_root,
            package_name=entry.package_name,
            package_module=entry.package_module,
            workflow_module=entry.workflow_module,
        )
        resolved = _CapabilityResolvedWorkflow(
            reference=reference,
            workflow_cls=loaded.workflow_cls,
            parameters_cls=loaded.parameters_cls,
        )
        compiled = loaded.compiled
    else:
        resolved = _resolve_reference(root_path, str(entry.source_path))
        compiled = compile_workflow(resolved.workflow_cls)
    return _capability_entry_from_resolved(resolved, compiled, entry)


def _capability_entry_from_resolved(resolved, compiled: WorkflowPlan, catalog_entry: WorkflowCatalogEntry | None):
    reference = resolved.reference
    source_path = reference.source_path.resolve() if reference.source_path is not None else None
    if source_path is None:
        raise WorkflowCapabilityInspectionError(f"workflow {reference.workflow_name!r} does not have a source path")

    package_name = reference.package_name or (catalog_entry.package_name if catalog_entry is not None else source_path.stem)
    package_dir = reference.package_dir.resolve()
    inferred_prompt_paths = tuple(dict.fromkeys(_resolved_prompt_paths(package_dir, compiled)))
    catalog_prompt_paths = catalog_entry.prompt_paths if catalog_entry is not None else ()
    spec_paths = catalog_entry.spec_paths if catalog_entry is not None else _support_spec_paths(source_path)
    prompt_paths = tuple(dict.fromkeys((*catalog_prompt_paths, *inferred_prompt_paths)))
    asset_paths = catalog_entry.asset_paths if catalog_entry is not None else _support_asset_paths(source_path)
    doc_paths = catalog_entry.doc_paths if catalog_entry is not None else _support_doc_paths(package_dir)
    test_paths = catalog_entry.test_paths if catalog_entry is not None else _support_test_paths(package_dir)
    params_path = catalog_entry.params_path if catalog_entry is not None else _support_params_path(source_path)
    doc_path = catalog_entry.doc_path if catalog_entry is not None else (doc_paths[0] if doc_paths else None)
    flow_path = catalog_entry.flow_path if catalog_entry is not None else (source_path if source_path.name == "flow.py" else None)
    workflow_py_path = (
        catalog_entry.workflow_py_path
        if catalog_entry is not None
        else (source_path if source_path.name == "workflow.py" else None)
    )
    package_init_path = catalog_entry.package_init_path if catalog_entry is not None else _optional_file(package_dir / "__init__.py")
    package_module = reference.package_module or (catalog_entry.package_module if catalog_entry is not None else None)
    workflow_module = reference.workflow_module or (catalog_entry.workflow_module if catalog_entry is not None else None)
    title = reference.title if reference.title is not None else (catalog_entry.title if catalog_entry is not None else None)
    description = (
        reference.description
        if reference.description is not None
        else (catalog_entry.description if catalog_entry is not None else None)
    )
    aliases = reference.aliases if reference.aliases else (catalog_entry.aliases if catalog_entry is not None else ())
    sessions = tuple(
        sorted(
            {
                step.session_name
                for step in compiled.steps.values()
                if step.session_name is not None and step.session_name != compiled.default_session_name
            }
        )
    )
    return WorkflowCapabilityEntry(
        package_name=package_name,
        workflow_name=compiled.workflow_name,
        workflow_class=resolved.workflow_cls.__name__,
        state_model=_qualified_name(compiled.state_cls),
        parameters_model=None if resolved.parameters_cls is None else _qualified_name(resolved.parameters_cls),
        title=title,
        description=description,
        aliases=aliases,
        package_dir=package_dir,
        package_folder=package_dir,
        manifest_path=None if reference.manifest_path is None else reference.manifest_path.resolve(),
        workflow_path=source_path,
        source_path=source_path,
        params_path=params_path,
        doc_path=doc_path,
        authoring_shape=reference.authoring_shape,
        flow_path=flow_path,
        workflow_py_path=workflow_py_path,
        package_init_path=package_init_path,
        package_module=package_module,
        workflow_module=workflow_module,
        spec_paths=spec_paths,
        prompt_paths=prompt_paths,
        asset_paths=asset_paths,
        doc_paths=doc_paths,
        test_paths=test_paths,
        entry_step_name=compiled.entry_step_name,
        parameters_supported=resolved.parameters_cls is not None,
        parameters=workflow_parameter_fields(resolved.parameters_cls),
        sessions=sessions,
        artifacts=tuple(
            WorkflowArtifactCapability(
                name=name,
                template=artifact.template,
                workflow_level=artifact.workflow_level,
                producer_steps=tuple(artifact.producer_steps),
            )
            for name, artifact in compiled.artifact_items(authoritative=True)
        ),
        routes={
            step_name: {tag: route_target_value(route.target) for tag, route in routes.items()}
            for step_name, step in compiled.steps.items()
            for routes in (compiled.routes.get(step_name, {}),)
        },
        global_routes={tag: route_target_value(route.target) for tag, route in compiled.global_routes.items()},
        compiled_global_routes=_compiled_routes(
            tuple(compiled.global_routes.keys()),
            step_routes=compiled.global_routes,
            global_routes={},
            expected_output_schema=None,
        ),
        steps=tuple(
            _step_capability(
                compiled,
                step,
                default_session_name=compiled.default_session_name,
                step_routes=compiled.routes.get(step.name, {}),
                global_routes=compiled.global_routes,
            )
            for step in compiled.steps.values()
        ),
    )


def _catalog_entry_for_reference(root_path: Path, reference) -> WorkflowCatalogEntry | None:
    source_path = reference.source_path.resolve() if reference.source_path is not None else None
    manifest_path = reference.manifest_path.resolve() if reference.manifest_path is not None else None
    for entry in discover_workflow_catalog(root_path, include_shadowed=True):
        if source_path is not None and entry.source_path.resolve() == source_path:
            return entry
        if manifest_path is not None and entry.manifest_path is not None and entry.manifest_path.resolve() == manifest_path:
            return entry
    return None


def _resolve_reference(root_path: Path, reference: str | type[Any]):
    if isinstance(reference, str):
        base_reference, requested_class_name = _split_reference_class(reference)
        if _is_path_reference(base_reference):
            return _resolve_path_reference(
                root_path,
                original_reference=reference,
                raw_path_reference=base_reference,
                requested_class_name=requested_class_name,
            )
        if "." in base_reference:
            return _resolve_module_reference(
                root_path,
                original_reference=reference,
                module_name=base_reference,
                requested_class_name=requested_class_name,
            )
        return _resolve_named_reference(
            root_path,
            original_reference=reference,
            workflow_reference=base_reference,
            requested_class_name=requested_class_name,
        )
    if not isinstance(reference, type):
        raise WorkflowCapabilityInspectionError(f"unsupported workflow reference {reference!r}")
    return _resolve_workflow_class_reference(root_path, reference)


def _resolve_named_reference(
    root_path: Path,
    *,
    original_reference: str,
    workflow_reference: str,
    requested_class_name: str | None,
) -> _CapabilityResolvedWorkflow:
    entry = _catalog_entry_for_named_reference(root_path, workflow_reference)
    if entry is None:
        searched_roots = ", ".join(str(search_root.path) for search_root in workflow_search_roots(root_path))
        raise WorkflowCapabilityInspectionError(
            f"unknown workflow {workflow_reference!r} for workspace root {root_path}; searched roots: {searched_roots}"
        )
    return _resolved_from_catalog_entry(
        root_path,
        entry,
        original=original_reference,
        kind="catalog_name",
        requested_class_name=requested_class_name,
    )


def _resolve_path_reference(
    root_path: Path,
    *,
    original_reference: str,
    raw_path_reference: str,
    requested_class_name: str | None,
) -> _CapabilityResolvedWorkflow:
    path = _resolve_reference_path(root_path, raw_path_reference)
    if not path.exists():
        raise WorkflowCapabilityInspectionError(f"workflow path {path} does not exist")
    entry = _catalog_entry_for_explicit_path(root_path, path)
    if entry is not None:
        kind = "workflow_directory" if path.is_dir() else "python_file"
        return _resolved_from_catalog_entry(
            root_path,
            entry,
            original=original_reference,
            kind=kind,
            requested_class_name=requested_class_name,
        )
    if path.is_dir():
        for candidate in (path / "flow.py", path / "workflow.py"):
            if candidate.is_file():
                return _resolved_from_source_path(
                    root_path,
                    source_path=candidate,
                    original=original_reference,
                    kind="workflow_directory",
                    requested_class_name=requested_class_name,
                )
        raise WorkflowCapabilityInspectionError(
            f"workflow directory {path} must contain flow.py or workflow.py"
        )
    if path.suffix == ".toml":
        for candidate in (path.parent / "flow.py", path.parent / "workflow.py"):
            if candidate.is_file():
                return _resolved_from_source_path(
                    root_path,
                    source_path=candidate,
                    original=original_reference,
                    kind="python_file",
                    requested_class_name=requested_class_name,
                )
        raise WorkflowCapabilityInspectionError(f"workflow manifest {path} does not point to a loadable source file")
    if path.suffix != ".py":
        raise WorkflowCapabilityInspectionError(
            f"workflow path {path} must be a Python file, workflow.toml, or directory"
        )
    return _resolved_from_source_path(
        root_path,
        source_path=path,
        original=original_reference,
        kind="python_file",
        requested_class_name=requested_class_name,
    )


def _resolve_module_reference(
    root_path: Path,
    *,
    original_reference: str,
    module_name: str,
    requested_class_name: str | None,
) -> _CapabilityResolvedWorkflow:
    module = _import_discovered_module(module_name, root_path)
    workflow_cls = locate_workflow_class(module, class_name=requested_class_name)
    source_path = _module_origin_path(module)
    if source_path is None:
        raise WorkflowCapabilityInspectionError(f"workflow module {module_name!r} does not have a filesystem source path")
    entry = _catalog_entry_for_explicit_path(root_path, source_path.resolve())
    return _resolved_from_workflow_class(
        root_path,
        workflow_cls,
        original=original_reference,
        kind="python_module",
        catalog_entry=entry,
        source_path=source_path.resolve(),
    )


def _resolve_workflow_class_reference(
    root_path: Path,
    workflow_cls: type[Any],
) -> _CapabilityResolvedWorkflow:
    source_path = Path(inspect.getfile(workflow_cls)).resolve()
    entry = _catalog_entry_for_explicit_path(root_path, source_path)
    if entry is not None and entry.source_root_kind == "package":
        return _resolved_from_catalog_entry(
            root_path,
            entry,
            original=f"{workflow_cls.__module__}.{workflow_cls.__name__}",
            kind="workflow_class",
            requested_class_name=workflow_cls.__name__,
        )
    return _resolved_from_workflow_class(
        root_path,
        workflow_cls,
        original=f"{workflow_cls.__module__}.{workflow_cls.__name__}",
        kind="workflow_class",
        catalog_entry=entry,
        source_path=source_path,
    )


def _resolved_from_catalog_entry(
    root_path: Path,
    entry: WorkflowCatalogEntry,
    *,
    original: str,
    kind: str,
    requested_class_name: str | None,
) -> _CapabilityResolvedWorkflow:
    if entry.source_root_kind == "package" and entry.workflow_module is not None and entry.package_module is not None:
        loaded = load_workflow_package_contract(root_path, entry)
        if requested_class_name is not None and loaded.workflow_cls.__name__ != requested_class_name:
            raise WorkflowCapabilityInspectionError(
                f"workflow reference {original!r} resolved to {loaded.workflow_cls.__name__!r}; "
                f"class {requested_class_name!r} was not found"
            )
        return _CapabilityResolvedWorkflow(
            reference=_CapabilityResolvedReference(
                original=original,
                kind=kind,
                workflow_name=entry.workflow_name,
                title=entry.title,
                description=entry.description,
                aliases=entry.aliases,
                class_name=loaded.workflow_cls.__name__,
                module_name=loaded.workflow_cls.__module__,
                source_path=entry.source_path,
                package_dir=entry.package_dir,
                manifest_path=entry.manifest_path,
                authoring_shape=entry.authoring_shape,
                source_root_kind=entry.source_root_kind,
                source_root=entry.source_root,
                package_name=entry.package_name,
                package_module=entry.package_module,
                workflow_module=entry.workflow_module,
            ),
            workflow_cls=loaded.workflow_cls,
            parameters_cls=loaded.parameters_cls,
        )
    target_class_name = requested_class_name or entry.manifest_class
    if entry.workflow_module is not None:
        module = _import_discovered_module(entry.workflow_module, root_path)
        workflow_cls = locate_workflow_class(module, class_name=target_class_name)
        if entry.manifest_path is not None:
            _apply_manifest_name_override(workflow_cls, entry.manifest_path)
        if (
            kind == "catalog_name"
            and entry.source_root_kind == "workspace"
            and entry.import_prefix == "workflows"
            and entry.package_module is not None
        ):
            parameters_cls = _resolve_repo_module_parameters_cls(
                root_path,
                workflow_cls,
                module,
                package_dir=entry.package_dir,
                package_module_name=entry.package_module,
            )
            return _CapabilityResolvedWorkflow(
                reference=_CapabilityResolvedReference(
                    original=original,
                    kind=kind,
                    workflow_name=entry.workflow_name,
                    title=entry.title,
                    description=entry.description,
                    aliases=entry.aliases,
                    class_name=workflow_cls.__name__,
                    module_name=workflow_cls.__module__,
                    source_path=entry.source_path,
                    package_dir=entry.package_dir,
                    manifest_path=entry.manifest_path,
                    authoring_shape=entry.authoring_shape,
                    source_root_kind=entry.source_root_kind,
                    source_root=entry.source_root,
                    package_name=entry.package_name,
                    package_module=entry.package_module,
                    workflow_module=entry.workflow_module,
                ),
                workflow_cls=workflow_cls,
                parameters_cls=parameters_cls,
            )
        return _resolved_from_workflow_class(
            root_path,
            workflow_cls,
            original=original,
            kind=kind,
            catalog_entry=entry,
            source_path=entry.source_path,
        )
    return _resolved_from_source_path(
        root_path,
        source_path=entry.source_path,
        original=original,
        kind=kind,
        requested_class_name=target_class_name,
        catalog_entry=entry,
    )


def _resolved_from_source_path(
    root_path: Path,
    *,
    source_path: Path,
    original: str,
    kind: str,
    requested_class_name: str | None,
    catalog_entry: WorkflowCatalogEntry | None = None,
) -> _CapabilityResolvedWorkflow:
    module = _load_isolated_workflow_module(source_path)
    workflow_cls = locate_workflow_class(module, class_name=requested_class_name)
    return _resolved_from_workflow_class(
        root_path,
        workflow_cls,
        original=original,
        kind=kind,
        catalog_entry=catalog_entry,
        source_path=source_path.resolve(),
    )


def _resolved_from_workflow_class(
    root_path: Path,
    workflow_cls: type[Any],
    *,
    original: str,
    kind: str,
    catalog_entry: WorkflowCatalogEntry | None,
    source_path: Path,
) -> _CapabilityResolvedWorkflow:
    if (
        catalog_entry is not None
        and catalog_entry.source_root_kind != "package"
        and catalog_entry.manifest_path is not None
    ):
        _apply_manifest_name_override(workflow_cls, catalog_entry.manifest_path)
    module = sys.modules.get(workflow_cls.__module__)
    compiled = compile_workflow(workflow_cls)
    package_dir = catalog_entry.package_dir if catalog_entry is not None else source_path.parent
    package_module_name = None if catalog_entry is None else catalog_entry.package_module
    parameters_cls = compiled.parameters_cls
    if isinstance(module, ModuleType):
        resolved_parameters = _resolve_repo_module_parameters_cls(
            root_path,
            workflow_cls,
            module,
            package_dir=package_dir,
            package_module_name=package_module_name,
        )
        if resolved_parameters is not None:
            parameters_cls = resolved_parameters
    if catalog_entry is not None:
        reference = _CapabilityResolvedReference(
            original=original,
            kind=kind,
            workflow_name=catalog_entry.workflow_name,
            title=catalog_entry.title,
            description=catalog_entry.description,
            aliases=catalog_entry.aliases,
            class_name=workflow_cls.__name__,
            module_name=workflow_cls.__module__,
            source_path=catalog_entry.source_path,
            package_dir=catalog_entry.package_dir,
            manifest_path=catalog_entry.manifest_path,
            authoring_shape=catalog_entry.authoring_shape,
            source_root_kind=catalog_entry.source_root_kind,
            source_root=catalog_entry.source_root,
            package_name=catalog_entry.package_name,
            package_module=catalog_entry.package_module,
            workflow_module=catalog_entry.workflow_module,
        )
    else:
        package_dir = source_path.parent
        reference = _CapabilityResolvedReference(
            original=original,
            kind=kind,
            workflow_name=compiled.workflow_name,
            title=None,
            description=None,
            aliases=(),
            class_name=workflow_cls.__name__,
            module_name=workflow_cls.__module__,
            source_path=source_path,
            package_dir=package_dir,
            manifest_path=None,
            authoring_shape=_authoring_shape_for_source_path(source_path),
            source_root_kind="workspace",
            source_root=root_path,
            package_name=package_dir.name,
            package_module=None,
            workflow_module=None,
        )
    return _CapabilityResolvedWorkflow(
        reference=reference,
        workflow_cls=workflow_cls,
        parameters_cls=parameters_cls,
    )


def _split_reference_class(reference: str) -> tuple[str, str | None]:
    base_reference, separator, requested_class_name = reference.partition(":")
    if not separator:
        return reference, None
    if not requested_class_name.strip():
        raise WorkflowCapabilityInspectionError(f"workflow reference {reference!r} must use a non-empty class name")
    return base_reference, requested_class_name.strip()


def _is_path_reference(reference: str) -> bool:
    return (
        reference.startswith(".")
        or reference.startswith("/")
        or "/" in reference
        or "\\" in reference
        or reference.endswith(".py")
        or reference.endswith(".toml")
    )


def _resolve_reference_path(root_path: Path, reference: str) -> Path:
    candidate = Path(reference)
    if candidate.is_absolute():
        return candidate.resolve()
    return (root_path / candidate).resolve()


def _catalog_entry_for_named_reference(root_path: Path, workflow_reference: str) -> WorkflowCatalogEntry | None:
    for entry in discover_workflow_catalog(root_path):
        if entry.workflow_name == workflow_reference or workflow_reference in entry.aliases:
            return entry
    return None


def _catalog_entry_for_explicit_path(root_path: Path, path: Path) -> WorkflowCatalogEntry | None:
    resolved_path = path.resolve()
    for entry in discover_workflow_catalog(root_path, include_shadowed=True):
        candidates = {
            entry.source_path.resolve(),
            entry.package_dir.resolve(),
        }
        if entry.manifest_path is not None:
            candidates.add(entry.manifest_path.resolve())
        if entry.flow_path is not None:
            candidates.add(entry.flow_path.resolve())
        if entry.workflow_py_path is not None:
            candidates.add(entry.workflow_py_path.resolve())
        if resolved_path in candidates:
            return entry
    return None


def _load_isolated_workflow_module(source_path: Path) -> ModuleType:
    source_path = source_path.resolve()
    module_name = f"_botpipe_capability_{sha1(str(source_path).encode('utf-8')).hexdigest()[:12]}"
    for cached_name in tuple(sys.modules):
        if cached_name == module_name or cached_name.startswith(f"{module_name}."):
            sys.modules.pop(cached_name, None)
    spec = importlib.util.spec_from_file_location(module_name, source_path)
    if spec is None or spec.loader is None:
        raise WorkflowCapabilityInspectionError(f"could not load workflow module from {source_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    with _no_bytecode_writes():
        spec.loader.exec_module(module)
    return module


def _authoring_shape_for_source_path(source_path: Path) -> AuthoringShape:
    if source_path.name == "flow.py":
        return "flow_package"
    if source_path.name == "workflow.py":
        return "workflow_package"
    if source_path.name == "__init__.py":
        return "manifest_package"
    return "single_file"


def _compiled_routes(
    available_routes: Sequence[str],
    *,
    step_routes: Mapping[str, Any],
    global_routes: Mapping[str, Any],
    expected_output_schema: Mapping[str, Any] | None,
) -> dict[str, WorkflowRouteCapability]:
    routes: dict[str, WorkflowRouteCapability] = {}
    for route_name in available_routes:
        route = step_routes.get(route_name) or global_routes.get(route_name)
        if route is None:
            continue
        payload_contract = payload_contract_for_route(
            route,
            expected_output_schema=expected_output_schema,
        )
        route_fields_contract = route_fields_contract_for_route(route)
        routes[route_name] = WorkflowRouteCapability(
            target=route_target_value(route.target),
            summary=route.summary,
            required_writes=required_write_names(route),
            handoff=route.handoff,
            on_taken=getattr(route.on_taken, "__name__", None),
            provider_visibility=route.provider_visibility,
            provider_visible=route.provider_visible,
            provider_visible_interactive=route.provider_visible_interactive,
            provider_visible_full_auto=route.provider_visible_full_auto,
            payload_schema_mode=route.payload_schema_mode,
            payload_schema=payload_contract["schema"],
            payload_contract=payload_contract,
            route_fields_schema=route.route_fields_schema,
            route_fields_contract=route_fields_contract,
            preset_kind=route.preset_kind,
            inheritance_source=route.inheritance_source,
            disabled=route.disabled,
            is_runtime_control=route.is_runtime_control,
            available=not route.disabled,
        )
    return routes


def _composite_route_tags(step: Any) -> tuple[str, ...]:
    branch_group = getattr(step, "branch_group", None)
    if branch_group is None:
        return ()
    return branch_group.composite_route_tags


def _step_authored_routes(compiled: WorkflowPlan, step: Any) -> tuple[str, ...]:
    definition = get_workflow_definition(compiled.workflow_cls)
    authored_step = next((candidate for candidate in definition.steps if candidate.name == step.name), None)
    if authored_step is None:
        return ()
    return step_authored_route_tags(definition, authored_step)


def _provider_route_map(
    *,
    visible_tags: tuple[str, ...],
    step_routes: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        route_tag: step_routes[route_tag]
        for route_tag in visible_tags
        if route_tag in step_routes and not step_routes[route_tag].disabled
    }


def _step_capability(
    compiled: WorkflowPlan,
    step,
    *,
    default_session_name: str,
    step_routes: Mapping[str, Any],
    global_routes: Mapping[str, Any],
) -> WorkflowStepCapability:
    composite_route_tags = _composite_route_tags(step)
    available_routes = available_route_tags_for_table(step_routes, composite_route_tags=composite_route_tags)
    authored_routes = _step_authored_routes(compiled, step)
    compiled_tags = compiled_route_tags_for_table(step_routes)
    suppressed_tags = suppressed_route_tags_for_table(step_routes)
    interactive_visible_routes = provider_visible_route_tags_for_table(step_routes, mode="interactive")
    full_auto_visible_routes = provider_visible_route_tags_for_table(step_routes, mode="full_auto")
    runtime_control_routes = runtime_control_route_tags_for_table(step_routes)
    routes = _compiled_routes(
        available_routes,
        step_routes=step_routes,
        global_routes=global_routes,
        expected_output_schema=step.expected_output_schema,
    )
    compiled_routes = _compiled_routes(
        compiled_tags,
        step_routes=step_routes,
        global_routes=global_routes,
        expected_output_schema=step.expected_output_schema,
    )
    return WorkflowStepCapability(
        name=step.name,
        kind=step.kind,
        session_name=None if step.session_name == default_session_name else step.session_name,
        reads=step.reads,
        requires=step.requires,
        writes=step.writes,
        log_artifacts=step.log_artifacts,
        available_routes=available_routes,
        authored_routes=authored_routes,
        compiled_route_tags=compiled_tags,
        suppressed_route_tags=suppressed_tags,
        runtime_control_routes=runtime_control_routes,
        provider_visible_routes_interactive=interactive_visible_routes,
        provider_visible_routes_full_auto=full_auto_visible_routes,
        provider_response_contracts={
            "interactive": provider_response_contract_for_routes(
                routes=_provider_route_map(visible_tags=interactive_visible_routes, step_routes=step_routes),
                expected_output_schema=step.expected_output_schema,
            ),
            "full_auto": provider_response_contract_for_routes(
                routes=_provider_route_map(visible_tags=full_auto_visible_routes, step_routes=step_routes),
                expected_output_schema=step.expected_output_schema,
            ),
        },
        expected_output_schema=step.expected_output_schema,
        routes=routes,
        compiled_routes=compiled_routes,
        producer_prompt=_prompt_path(step.producer_prompt),
        verifier_prompt=_prompt_path(step.verifier_prompt),
    )


def _parameter_field_payload(field: WorkflowParameterField) -> dict[str, object]:
    return {
        "default": field.default,
        "name": field.name,
        "repeated": field.supports_multiple,
        "required": field.required,
        "type": annotation_display_name(field.annotation),
    }


def _artifact_capability_payload(artifact: WorkflowArtifactCapability) -> dict[str, object]:
    return {
        "name": artifact.name,
        "producer_steps": list(artifact.producer_steps),
        "template": artifact.template,
        "workflow_level": artifact.workflow_level,
    }


def _route_capability_payload(route: WorkflowRouteCapability) -> dict[str, object]:
    return {
        "target": route.target,
        "summary": route.summary,
        "required_writes": list(route.required_writes or ()),
        "handoff": route.handoff,
        "on_taken": route.on_taken,
        "provider_visibility": route.provider_visibility,
        "provider_visible": route.provider_visible,
        "provider_visible_interactive": route.provider_visible_interactive,
        "provider_visible_full_auto": route.provider_visible_full_auto,
        "payload_schema_mode": route.payload_schema_mode,
        "payload_schema": deepcopy(route.payload_schema),
        "payload_contract": deepcopy(route.payload_contract),
        "route_fields_schema": deepcopy(route.route_fields_schema),
        "route_fields_contract": deepcopy(route.route_fields_contract),
        "preset_kind": route.preset_kind,
        "inheritance_source": route.inheritance_source,
        "disabled": route.disabled,
        "available": route.available,
        "suppressed": route.disabled,
        "is_runtime_control": route.is_runtime_control,
    }


def _step_payload(
    repo_root: Path,
    package_dir: Path,
    *,
    step: WorkflowStepCapability,
    route_targets: Mapping[str, str],
) -> dict[str, object]:
    return {
        "available_routes": list(step.available_routes),
        "authored_routes": list(step.authored_routes),
        "compiled_route_tags": list(step.compiled_route_tags),
        "suppressed_route_tags": list(step.suppressed_route_tags),
        "expected_output_schema": step.expected_output_schema,
        "kind": step.kind,
        "log_artifacts": [_surface_ref_payload(value) for value in step.log_artifacts],
        "name": step.name,
        "provider_visible_routes_full_auto": list(step.provider_visible_routes_full_auto),
        "provider_visible_routes_interactive": list(step.provider_visible_routes_interactive),
        "provider_response_contracts": deepcopy(step.provider_response_contracts),
        "producer_prompt": step.producer_prompt,
        "producer_prompt_repo_relative": _prompt_repo_relative(repo_root, package_dir, step.producer_prompt),
        "writes": [_surface_ref_payload(value) for value in step.writes],
        "reads": [_surface_ref_payload(value) for value in step.reads],
        "requires": [_surface_ref_payload(value) for value in step.requires],
        "runtime_control_routes": list(step.runtime_control_routes),
        "routes": {route_name: _route_capability_payload(route) for route_name, route in step.routes.items()},
        "compiled_routes": {
            route_name: _route_capability_payload(route)
            for route_name, route in step.compiled_routes.items()
        },
        "route_targets": dict(route_targets),
        "session_name": step.session_name,
        "verifier_prompt": step.verifier_prompt,
        "verifier_prompt_repo_relative": _prompt_repo_relative(repo_root, package_dir, step.verifier_prompt),
    }


def _resolved_prompt_paths(package_dir: Path, compiled: WorkflowPlan) -> tuple[Path, ...]:
    paths: list[Path] = []
    for step in compiled.steps.values():
        for prompt in (step.producer_prompt, step.verifier_prompt):
            prompt_path = _prompt_path(prompt)
            if prompt_path is None:
                continue
            candidate = (package_dir / prompt_path).resolve()
            if candidate.is_file():
                paths.append(candidate)
    return tuple(paths)


def _runtime_test_path(test_paths: tuple[Path, ...]) -> str | None:
    for path in test_paths:
        if path.name.startswith("test_"):
            return str(path)
    return None


def _optional_path_string(path: Path | None) -> str | None:
    return None if path is None else str(path)


def _selected_workflow_repo_relative_list(
    repo_root: Path,
    entry: WorkflowCapabilityEntry,
    paths: Sequence[str | Path],
) -> list[str]:
    return [
        repo_relative
        for path in paths
        if (repo_relative := _selected_workflow_repo_relative(repo_root, entry, path)) is not None
    ]


def _selected_workflow_repo_relative(
    repo_root: Path,
    entry: WorkflowCapabilityEntry,
    path: str | Path | None,
) -> str | None:
    if path is None:
        return None
    resolved = Path(path).resolve()
    canonical_package_root = _canonical_first_party_repo_relative_root(repo_root, entry)
    if canonical_package_root is not None:
        try:
            return str(canonical_package_root / resolved.relative_to(entry.package_dir.resolve()))
        except ValueError:
            pass
    return _repo_relative(repo_root, resolved)


def _canonical_first_party_repo_relative_root(
    repo_root: Path,
    entry: WorkflowCapabilityEntry,
) -> Path | None:
    package_dir_repo_relative = _optional_repo_relative(repo_root, entry.package_dir)
    if package_dir_repo_relative != str(Path("workflows") / entry.workflow_name):
        return None
    doc_path_repo_relative = _optional_repo_relative(repo_root, entry.doc_path)
    expected_doc_repo_relative = str(Path("workflows") / entry.workflow_name / "README.md")
    if doc_path_repo_relative != expected_doc_repo_relative:
        return None
    return Path("botpipe") / "workflows" / entry.workflow_name


def _infer_repo_root_from_package_dir(package_dir: Path) -> Path:
    resolved_package_dir = package_dir.resolve()
    parts = resolved_package_dir.parts
    for marker in (
        ("botpipe", "workflows"),
        (".botpipe", "workflows"),
        ("labs", "workflows"),
        ("workflows",),
    ):
        marker_length = len(marker)
        for index in range(len(parts) - marker_length, -1, -1):
            if parts[index : index + marker_length] == marker:
                if marker == ("workflows",) and index > 0 and parts[index - 1].startswith("."):
                    continue
                return Path(*parts[:index]).resolve()
    return resolved_package_dir.parent.resolve()


def _prompt_repo_relative(repo_root: Path, package_dir: Path, prompt_path: str | None) -> str | None:
    if prompt_path is None:
        return None
    return _optional_repo_relative(repo_root, package_dir / prompt_path)


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


def _support_params_path(source_path: Path) -> Path | None:
    if source_path.name not in {"flow.py", "workflow.py", "__init__.py"}:
        return None
    return _optional_file(source_path.parent / "params.py")


def _support_spec_paths(source_path: Path) -> tuple[Path, ...]:
    if source_path.name not in {"flow.py", "workflow.py", "__init__.py"}:
        return ()
    return tuple(
        path
        for filename in ("specs.py", "contracts.py")
        if (path := _optional_file(source_path.parent / filename)) is not None
    )


def _support_asset_paths(source_path: Path) -> tuple[Path, ...]:
    if source_path.name not in {"flow.py", "workflow.py", "__init__.py"}:
        return ()
    assets_root = source_path.parent / "assets"
    return tuple(sorted(path.resolve() for path in assets_root.rglob("*") if path.is_file())) if assets_root.is_dir() else ()


def _support_doc_paths(package_dir: Path) -> tuple[Path, ...]:
    return tuple(
        path
        for filename in ("README.md", "docs.md")
        if (path := _optional_file(package_dir / filename)) is not None
    )


def _support_test_paths(package_dir: Path) -> tuple[Path, ...]:
    tests_root = package_dir / "tests"
    return tuple(sorted(path.resolve() for path in tests_root.rglob("*") if path.is_file())) if tests_root.is_dir() else ()


def _validate_package_exports(
    entry: WorkflowCatalogEntry,
    package_module: ModuleType,
    workflow_cls: type[Any],
) -> type[Any] | None:
    exported = getattr(package_module, workflow_cls.__name__, None)
    if exported is not workflow_cls:
        raise WorkflowCapabilityInspectionError(
            f"workflow package {entry.package_name!r} must re-export {workflow_cls.__name__} from __init__.py"
        )

    package_all = getattr(package_module, "__all__", None)
    if not isinstance(package_all, list):
        raise WorkflowCapabilityInspectionError(
            f"workflow package {entry.package_name!r} must define __all__ as a list"
        )
    if workflow_cls.__name__ not in package_all:
        raise WorkflowCapabilityInspectionError(
            f"workflow package {entry.package_name!r} must include {workflow_cls.__name__!r} in __all__"
        )

    parameters_cls = getattr(package_module, "Params", None)
    if parameters_cls is None:
        if getattr(package_module, "Parameters", None) is not None:
            raise WorkflowCapabilityInspectionError("Use Params, not Parameters.")
        return None
    if not isinstance(parameters_cls, type):
        raise WorkflowCapabilityInspectionError(
            f"workflow package {entry.package_name!r} exports a non-type Params symbol"
        )
    if "Params" not in package_all:
        raise WorkflowCapabilityInspectionError(
            f"workflow package {entry.package_name!r} must include 'Params' in __all__ when it is exported"
        )
    return parameters_cls


def _resolve_repo_module_parameters_cls(
    root_path: Path,
    workflow_cls: type[Any],
    module: ModuleType,
    *,
    package_dir: Path,
    package_module_name: str | None,
) -> type[Any] | None:
    class_parameters = effective_parameters_model(workflow_cls)
    if class_parameters is not None:
        return _require_parameter_type(class_parameters, f"{workflow_cls.__name__}.Params")

    module_params = getattr(module, "Params", None)
    if module_params is not None:
        return _require_parameter_type(module_params, f"{module.__name__}.Params")
    if getattr(module, "Parameters", None) is not None:
        raise WorkflowCapabilityInspectionError("Use Params, not Parameters.")

    if package_module_name is not None:
        exported = _load_repo_package_exported_parameters(root_path, package_module_name)
        if exported is not None:
            return exported

    return _load_repo_parameters_from_params_py(
        root_path,
        package_dir,
        package_module_name=package_module_name,
    )


def _load_repo_package_exported_parameters(root_path: Path, package_module_name: str) -> type[Any] | None:
    package_module = _import_discovered_module(package_module_name, root_path)
    exported = getattr(package_module, "Params", None)
    if exported is None:
        if getattr(package_module, "Parameters", None) is not None:
            raise WorkflowCapabilityInspectionError("Use Params, not Parameters.")
        return None
    parameters_cls = _require_parameter_type(exported, f"{package_module_name}.Params")
    package_all = getattr(package_module, "__all__", None)
    if not isinstance(package_all, list):
        raise WorkflowCapabilityInspectionError(f"workflow package {package_module_name!r} must define __all__ as a list")
    if "Params" not in package_all:
        raise WorkflowCapabilityInspectionError(
            f"workflow package {package_module_name!r} must include 'Params' in __all__ when it is exported"
        )
    return parameters_cls


def _load_repo_parameters_from_params_py(
    root_path: Path,
    package_dir: Path,
    *,
    package_module_name: str | None,
) -> type[Any] | None:
    params_path = package_dir / "params.py"
    if not params_path.is_file():
        return None
    if package_module_name is not None:
        params_module = _import_discovered_module(f"{package_module_name}.params", root_path)
    else:
        params_module = _load_isolated_workflow_module(params_path)
    parameters_cls = getattr(params_module, "Params", None)
    if parameters_cls is None:
        if getattr(params_module, "Parameters", None) is not None:
            raise WorkflowCapabilityInspectionError("Use Params, not Parameters.")
        return None
    return _require_parameter_type(parameters_cls, f"{params_module.__name__}.Params")


def _require_parameter_type(candidate: Any, label: str) -> type[Any]:
    if not isinstance(candidate, type):
        raise WorkflowCapabilityInspectionError(f"workflow parameter symbol {label!r} must be a type")
    return candidate


def _apply_manifest_name_override(workflow_cls: type[Any], manifest_path: Path) -> None:
    declared_name = getattr(workflow_cls, "name", None)
    if isinstance(declared_name, str) and declared_name.strip():
        return
    try:
        manifest = read_workflow_manifest(manifest_path, require_title_description=False)
    except Exception:
        return
    manifest_name = manifest.get("name")
    if isinstance(manifest_name, str) and manifest_name.strip():
        setattr(workflow_cls, "name", manifest_name.strip())


def _import_discovered_module(module_name: str, root_path: Path) -> ModuleType:
    importlib.invalidate_caches()
    _evict_stale_workflow_modules(module_name, root_path)
    with _repo_root_on_syspath(root_path):
        with _no_bytecode_writes():
            return importlib.import_module(module_name)


def _evict_stale_workflow_modules(module_name: str, root_path: Path) -> None:
    if module_name == "workflows" or module_name.startswith("workflows."):
        expected_root = (root_path / "workflows").resolve()
        module = sys.modules.get("workflows")
        if module is not None:
            origin = _module_origin_path(module)
            if origin is not None and origin.is_relative_to(expected_root):
                return
        for cached_name in tuple(sys.modules):
            if cached_name == "workflows" or cached_name.startswith("workflows."):
                sys.modules.pop(cached_name, None)
        return
    if not module_name.startswith("botpipe.workflows."):
        return
    for name, module in tuple(sys.modules.items()):
        if name != "botpipe.workflows" and not name.startswith("botpipe.workflows."):
            continue
        if _module_within_package_namespace(module):
            continue
        for cached_name in tuple(sys.modules):
            if cached_name == "botpipe.workflows" or cached_name.startswith("botpipe.workflows."):
                sys.modules.pop(cached_name, None)
        return


def _module_within_package_namespace(module: ModuleType) -> bool:
    origin = _module_origin_path(module)
    if origin is None:
        return True
    return "botpipe/workflows" in origin.as_posix()


def _module_origin_path(module: ModuleType) -> Path | None:
    module_file = getattr(module, "__file__", None)
    if isinstance(module_file, str) and module_file:
        return Path(module_file).resolve()

    module_spec = getattr(module, "__spec__", None)
    origin = getattr(module_spec, "origin", None)
    if isinstance(origin, str) and origin:
        return Path(origin).resolve()
    return None


@contextmanager
def _no_bytecode_writes():
    original = sys.dont_write_bytecode
    original_prefix = getattr(sys, "pycache_prefix", None)
    sys.dont_write_bytecode = True
    with tempfile.TemporaryDirectory(prefix="botpipe-capability-pyc-") as pycache_root:
        sys.pycache_prefix = pycache_root
        try:
            yield
        finally:
            sys.dont_write_bytecode = original
            sys.pycache_prefix = original_prefix


def _parameter_field_default(field: Any) -> Any:
    if getattr(field, "default_factory", None) is not None:
        return "<factory>"
    if callable(field.default):
        return "<factory>"
    return field.default


def _annotation_supports_multiple(annotation: Any) -> bool:
    origin = get_origin(annotation)
    if origin is None:
        return False
    if origin in {Annotated}:
        return _annotation_supports_multiple(get_args(annotation)[0])
    if origin in {Union, UnionType}:
        return any(_annotation_supports_multiple(arg) for arg in get_args(annotation) if arg is not type(None))
    if origin in {list, tuple, set, frozenset, Sequence}:
        return True
    origin_name = getattr(origin, "__name__", "")
    if origin_name in {"Sequence", "MutableSequence"}:
        return True
    return False


def _qualified_name(candidate: type[Any]) -> str:
    return f"{candidate.__module__}.{candidate.__qualname__}"


def _surface_ref_payload(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Path):
        return str(value)
    qualified_name = getattr(value, "qualified_name", None)
    if isinstance(qualified_name, str) and qualified_name:
        return qualified_name
    raw_value = getattr(value, "value", None)
    if isinstance(raw_value, Path):
        return str(raw_value)
    if isinstance(raw_value, str):
        return raw_value
    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name
    return str(value)


def _prompt_path(prompt: Any) -> str | None:
    if prompt is None:
        return None
    return getattr(prompt, "path", prompt)


def _optional_file(path: Path) -> Path | None:
    return path.resolve() if path.is_file() else None


@contextmanager
def _repo_root_on_syspath(root_path: Path):
    entry = str(root_path)
    inserted = False
    if entry not in sys.path:
        sys.path.insert(0, entry)
        inserted = True
    try:
        yield
    finally:
        if inserted:
            try:
                sys.path.remove(entry)
            except ValueError:  # pragma: no cover - defensive against external sys.path mutation
                pass


__all__ = [
    "WorkflowArtifactCapability",
    "WorkflowCapabilityEntry",
    "WorkflowCapabilityInspectionError",
    "WorkflowLoadedPackage",
    "WorkflowParameterField",
    "WorkflowStepCapability",
    "annotation_display_name",
    "inspect_workflow_capabilities",
    "inspect_workflow_reference",
    "json_safe_parameter_mapping",
    "json_safe_parameter_value",
    "load_workflow_package_contract",
    "locate_workflow_class",
    "selected_workflow_authoring_surface_payload",
    "selected_workflow_capability_payload",
    "selected_workflow_decomposition_surface_payload",
    "workflow_capability_payload",
    "workflow_parameter_fields",
]
