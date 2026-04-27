"""Importing workflow-capability inspection for richer portfolio analysis."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from types import ModuleType, UnionType
from typing import Annotated, Any, Union, get_args, get_origin

from pydantic import BaseModel

from .compiler import CompiledWorkflow, compile_workflow
from .routes import RouteInfo
from .workflow_catalog import AuthoringShape, WorkflowCatalogEntry, discover_workflow_catalog


class WorkflowCapabilityInspectionError(LookupError):
    """Raised when rich workflow capability inspection cannot load a workflow."""


@dataclass(frozen=True, slots=True)
class WorkflowLoadedPackage:
    """Loaded workflow contract for importing inspection and runtime resolution."""

    workflow_cls: type[Any]
    parameters_cls: type[Any] | None
    compiled: CompiledWorkflow


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
class WorkflowStepCapability:
    """Normalized compiled-step capability summary."""

    name: str
    kind: str
    session_name: str | None
    reads: tuple[str, ...]
    requires: tuple[str, ...]
    produces: tuple[str, ...]
    log_artifacts: tuple[str, ...]
    available_routes: tuple[str, ...]
    expected_output_schema: dict[str, Any] | None
    route_infos: dict[str, RouteInfo]
    route_required_outputs: dict[str, tuple[str, ...]]
    route_contracts: dict[str, dict[str, Any]]
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
    contracts_path: Path | None
    doc_path: Path | None
    authoring_shape: AuthoringShape
    flow_path: Path | None
    legacy_workflow_path: Path | None
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
    transitions: dict[str, dict[str, str]]
    global_transitions: dict[str, str]
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
    if entry.workflow_module is None or entry.package_module is None:
        resolved = _resolve_reference(root_path, str(entry.source_path))
        compiled = compile_workflow(resolved.workflow_cls)
        return WorkflowLoadedPackage(
            workflow_cls=resolved.workflow_cls,
            parameters_cls=resolved.parameters_cls,
            compiled=compiled,
        )

    workflow_module = _import_discovered_module(entry.workflow_module, root_path)
    workflow_cls = locate_workflow_class(workflow_module)
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
        if not isinstance(candidate, type):
            raise WorkflowCapabilityInspectionError(
                f"workflow class {class_name!r} was not found in module {module.__name__!r}"
            )
        return candidate

    from .steps import Step

    candidates = [
        value
        for value in module.__dict__.values()
        if isinstance(value, type)
        and value.__module__ == module.__name__
        and value.__name__ != "Workflow"
        and getattr(value, "State", None) is not None
        and any(isinstance(member, Step) for member in value.__dict__.values())
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
        "contracts_path": None if entry.contracts_path is None else str(entry.contracts_path),
        "description": entry.description,
        "doc_path": None if entry.doc_path is None else str(entry.doc_path),
        "doc_paths": [str(path) for path in entry.doc_paths],
        "entry_step_name": entry.entry_step_name,
        "flow_path": None if entry.flow_path is None else str(entry.flow_path),
        "global_transitions": dict(entry.global_transitions),
        "legacy_workflow_path": None if entry.legacy_workflow_path is None else str(entry.legacy_workflow_path),
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
                "has_expected_output_schema": step.expected_output_schema is not None,
                "kind": step.kind,
                "log_artifacts": list(step.log_artifacts),
                "name": step.name,
                "producer_prompt": step.producer_prompt,
                "produces": list(step.produces),
                "reads": list(step.reads),
                "requires": list(step.requires),
                "route_infos": {
                    route_name: {
                        "summary": info.summary,
                        "required_outputs": list(info.required_outputs),
                        "handoff": info.handoff,
                    }
                    for route_name, info in step.route_infos.items()
                },
                "route_required_outputs": {
                    route_name: list(required_outputs)
                    for route_name, required_outputs in step.route_required_outputs.items()
                },
                "route_contracts": {
                    route_name: dict(contract)
                    for route_name, contract in step.route_contracts.items()
                },
                "session_name": step.session_name,
                "typed_output_schema": step.expected_output_schema,
                "verifier_prompt": step.verifier_prompt,
            }
            for step in entry.steps
        ],
        "test_paths": [str(path) for path in entry.test_paths],
        "title": entry.title,
        "transitions": {
            "global": dict(entry.global_transitions),
            "steps": {step_name: dict(routes) for step_name, routes in entry.transitions.items()},
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

    runtime_test_path = _runtime_test_path(entry.test_paths)
    asset_paths = [str(path) for path in entry.asset_paths]
    prompt_paths = [str(path) for path in entry.prompt_paths]
    spec_paths = [str(path) for path in entry.spec_paths]
    test_paths = [str(path) for path in entry.test_paths]
    package_init_path = _optional_path_string(entry.package_init_path)
    contracts_path = _optional_path_string(entry.contracts_path)
    doc_path = _optional_path_string(entry.doc_path)
    manifest_path = _optional_path_string(entry.manifest_path)
    params_path = _optional_path_string(entry.params_path)
    editable_paths = sorted(
        {
            str(entry.source_path),
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
    return {
        "asset_paths": asset_paths,
        "contracts_path": contracts_path,
        "doc_path": doc_path,
        "editable_paths": editable_paths,
        "manifest_path": manifest_path,
        "package_dir": str(entry.package_dir),
        "package_init_path": package_init_path,
        "package_name": entry.package_name,
        "params_path": params_path,
        "prompt_paths": prompt_paths,
        "runtime_test_path": runtime_test_path,
        "spec_paths": spec_paths,
        "test_paths": test_paths,
        "workflow_name": entry.workflow_name,
        "workflow_path": str(entry.workflow_path),
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
        "selected_workflow_authoring_surface": {
            **decomposition_authoring_surface,
            "asset_paths_repo_relative": _repo_relative_list(
                repo_root_path,
                decomposition_authoring_surface["asset_paths"],
            ),
            "contracts_path_repo_relative": _optional_repo_relative(
                repo_root_path,
                decomposition_authoring_surface["contracts_path"],
            ),
            "doc_path_repo_relative": _optional_repo_relative(repo_root_path, decomposition_authoring_surface["doc_path"]),
            "editable_paths_repo_relative": _repo_relative_list(
                repo_root_path,
                decomposition_authoring_surface["editable_paths"],
            ),
            "manifest_path_repo_relative": _optional_repo_relative(
                repo_root_path,
                decomposition_authoring_surface["manifest_path"],
            ),
            "package_dir_repo_relative": _optional_repo_relative(
                repo_root_path,
                decomposition_authoring_surface["package_dir"],
            ),
            "package_init_path_repo_relative": _optional_repo_relative(
                repo_root_path,
                decomposition_authoring_surface["package_init_path"],
            ),
            "params_path_repo_relative": _optional_repo_relative(
                repo_root_path,
                decomposition_authoring_surface["params_path"],
            ),
            "prompt_paths_repo_relative": _repo_relative_list(
                repo_root_path,
                decomposition_authoring_surface["prompt_paths"],
            ),
            "runtime_test_path_repo_relative": _optional_repo_relative(
                repo_root_path,
                decomposition_authoring_surface["runtime_test_path"],
            ),
            "spec_paths_repo_relative": _repo_relative_list(
                repo_root_path,
                decomposition_authoring_surface["spec_paths"],
            ),
            "test_paths_repo_relative": _repo_relative_list(
                repo_root_path,
                decomposition_authoring_surface["test_paths"],
            ),
            "workflow_path_repo_relative": _optional_repo_relative(
                repo_root_path,
                decomposition_authoring_surface["workflow_path"],
            ),
        },
        "selected_workflow_compiled_surface": {
            "artifacts": [_artifact_capability_payload(artifact) for artifact in entry.artifacts],
            "entry_step_name": entry.entry_step_name,
            "global_routes": dict(entry.global_transitions),
            "parameters": [_parameter_field_payload(field) for field in entry.parameters],
            "parameters_supported": entry.parameters_supported,
            "sessions": list(entry.sessions),
            "state_model": entry.state_model,
            "step_count": len(entry.steps),
            "steps": [
                _compiled_step_payload(
                    repo_root_path,
                    entry.package_dir,
                    step=step,
                    route_targets=entry.transitions.get(step.name, {}),
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
    if entry.manifest_path is not None and entry.workflow_module is not None and entry.package_module is not None:
        from ..runtime.loader import ResolvedWorkflow, WorkflowReference

        loaded = load_workflow_package_contract(root_path, entry)
        reference = WorkflowReference(
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
            package_name=entry.package_name,
            package_module=entry.package_module,
            workflow_module=entry.workflow_module,
        )
        resolved = ResolvedWorkflow(reference=reference, workflow_cls=loaded.workflow_cls, parameters_cls=loaded.parameters_cls)
        compiled = loaded.compiled
    else:
        resolved = _resolve_reference(root_path, str(entry.source_path))
        compiled = compile_workflow(resolved.workflow_cls)
    return _capability_entry_from_resolved(resolved, compiled, entry)


def _capability_entry_from_resolved(resolved, compiled: CompiledWorkflow, catalog_entry: WorkflowCatalogEntry | None):
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
    contracts_path = catalog_entry.contracts_path if catalog_entry is not None else _support_contracts_path(source_path)
    doc_path = catalog_entry.doc_path if catalog_entry is not None else (doc_paths[0] if doc_paths else None)
    flow_path = catalog_entry.flow_path if catalog_entry is not None else (source_path if source_path.name == "flow.py" else None)
    legacy_workflow_path = (
        catalog_entry.legacy_workflow_path
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
        contracts_path=contracts_path,
        doc_path=doc_path,
        authoring_shape=reference.authoring_shape,
        flow_path=flow_path,
        legacy_workflow_path=legacy_workflow_path,
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
            _compiled_artifact_capability(name, artifact)
            for name, artifact in compiled.artifact_items(authoritative=True)
        ),
        transitions={
            step_name: {tag: route.target for tag, route in routes.items()}
            for step_name, routes in compiled.routes.items()
        },
        global_transitions={tag: route.target for tag, route in compiled.global_routes.items()},
        steps=tuple(
            _compiled_step_capability(step, default_session_name=compiled.default_session_name)
            for step in compiled.steps.values()
        ),
    )


def _catalog_entry_for_reference(root_path: Path, reference) -> WorkflowCatalogEntry | None:
    source_path = reference.source_path.resolve() if reference.source_path is not None else None
    manifest_path = reference.manifest_path.resolve() if reference.manifest_path is not None else None
    for entry in discover_workflow_catalog(root_path):
        if source_path is not None and entry.source_path.resolve() == source_path:
            return entry
        if manifest_path is not None and entry.manifest_path is not None and entry.manifest_path.resolve() == manifest_path:
            return entry
    return None


def _resolve_reference(root_path: Path, reference: str | type[Any]):
    from ..runtime.loader import WorkflowDiscoveryError, WorkflowManifestError, resolve_workflow_reference

    try:
        return resolve_workflow_reference(root_path, reference)
    except (WorkflowDiscoveryError, WorkflowManifestError) as exc:
        raise WorkflowCapabilityInspectionError(str(exc)) from exc


def _compiled_artifact_capability(name: str, artifact) -> WorkflowArtifactCapability:
    return WorkflowArtifactCapability(
        name=name,
        template=artifact.template,
        workflow_level=artifact.workflow_level,
        producer_steps=tuple(artifact.producer_steps),
    )


def _compiled_step_capability(step, *, default_session_name: str) -> WorkflowStepCapability:
    return WorkflowStepCapability(
        name=step.name,
        kind=step.kind,
        session_name=None if step.session_name == default_session_name else step.session_name,
        reads=step.reads,
        requires=step.requires,
        produces=step.produces,
        log_artifacts=step.log_artifacts,
        available_routes=step.available_routes,
        expected_output_schema=step.expected_output_schema,
        route_infos=dict(step.route_infos),
        route_required_outputs=dict(step.route_required_outputs),
        route_contracts={route_name: dict(contract) for route_name, contract in step.route_contracts.items()},
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


def _compiled_step_payload(
    repo_root: Path,
    package_dir: Path,
    *,
    step: WorkflowStepCapability,
    route_targets: Mapping[str, str],
) -> dict[str, object]:
    return {
        "available_routes": list(step.available_routes),
        "expected_output_schema": step.expected_output_schema,
        "kind": step.kind,
        "log_artifacts": list(step.log_artifacts),
        "name": step.name,
        "producer_prompt": step.producer_prompt,
        "producer_prompt_repo_relative": _prompt_repo_relative(repo_root, package_dir, step.producer_prompt),
        "produces": list(step.produces),
        "reads": list(step.reads),
        "requires": list(step.requires),
        "route_infos": {
            route_name: {
                "summary": info.summary,
                "required_outputs": list(info.required_outputs),
                "handoff": info.handoff,
            }
            for route_name, info in step.route_infos.items()
        },
        "route_required_outputs": {
            route_name: list(required_outputs)
            for route_name, required_outputs in step.route_required_outputs.items()
        },
        "route_contracts": {route_name: dict(contract) for route_name, contract in step.route_contracts.items()},
        "route_targets": dict(route_targets),
        "session_name": step.session_name,
        "verifier_prompt": step.verifier_prompt,
        "verifier_prompt_repo_relative": _prompt_repo_relative(repo_root, package_dir, step.verifier_prompt),
    }


def _resolved_prompt_paths(package_dir: Path, compiled: CompiledWorkflow) -> tuple[Path, ...]:
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


def _repo_relative_list(repo_root: Path, paths: Sequence[str]) -> list[str]:
    return [_repo_relative(repo_root, path) for path in paths]


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


def _support_contracts_path(source_path: Path) -> Path | None:
    if source_path.name not in {"flow.py", "workflow.py", "__init__.py"}:
        return None
    return _optional_file(source_path.parent / "contracts.py")


def _support_spec_paths(source_path: Path) -> tuple[Path, ...]:
    if source_path.name not in {"flow.py", "workflow.py", "__init__.py"}:
        return ()
    specs_path = _optional_file(source_path.parent / "specs.py")
    return () if specs_path is None else (specs_path,)


def _support_asset_paths(source_path: Path) -> tuple[Path, ...]:
    if source_path.name not in {"flow.py", "workflow.py", "__init__.py"}:
        return ()
    assets_root = source_path.parent / "assets"
    return tuple(sorted(path.resolve() for path in assets_root.rglob("*") if path.is_file())) if assets_root.is_dir() else ()


def _support_doc_paths(package_dir: Path) -> tuple[Path, ...]:
    docs_path = _optional_file(package_dir / "docs.md")
    return () if docs_path is None else (docs_path,)


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

    parameters_cls = getattr(package_module, "Parameters", None)
    if parameters_cls is None:
        return None
    if not isinstance(parameters_cls, type):
        raise WorkflowCapabilityInspectionError(
            f"workflow package {entry.package_name!r} exports a non-type Parameters symbol"
        )
    if "Parameters" not in package_all:
        raise WorkflowCapabilityInspectionError(
            f"workflow package {entry.package_name!r} must include 'Parameters' in __all__ when it is exported"
        )
    return parameters_cls


def _import_discovered_module(module_name: str, root_path: Path) -> ModuleType:
    importlib.invalidate_caches()
    _evict_stale_workflow_modules(root_path / "workflows")
    with _repo_root_on_syspath(root_path):
        return importlib.import_module(module_name)


def _evict_stale_workflow_modules(workflows_root: Path) -> None:
    resolved_root = workflows_root.resolve()
    for name, module in tuple(sys.modules.items()):
        if name != "workflows" and not name.startswith("workflows."):
            continue
        if _module_within_workflows_root(module, resolved_root):
            continue
        for cached_name in tuple(sys.modules):
            if cached_name == "workflows" or cached_name.startswith("workflows."):
                sys.modules.pop(cached_name, None)
        return


def _module_within_workflows_root(module: ModuleType, workflows_root: Path) -> bool:
    origin = _module_origin_path(module)
    if origin is None:
        return True
    try:
        origin.relative_to(workflows_root)
    except ValueError:
        return False
    return True


def _module_origin_path(module: ModuleType) -> Path | None:
    module_file = getattr(module, "__file__", None)
    if isinstance(module_file, str) and module_file:
        return Path(module_file).resolve()

    module_spec = getattr(module, "__spec__", None)
    origin = getattr(module_spec, "origin", None)
    if isinstance(origin, str) and origin:
        return Path(origin).resolve()
    return None


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
