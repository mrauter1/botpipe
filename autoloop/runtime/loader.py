"""Workflow loading helpers."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
import tempfile
import tomllib
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
from types import ModuleType
from typing import Any, Literal

from pydantic import BaseModel, ValidationError, create_model

from autoloop.core.compiler import CompiledWorkflow, compile_workflow
from autoloop.core.context import EmptyParameters
from autoloop.core.descriptors import effective_parameters_model
from autoloop.core.mappings import normalize_mapping
from autoloop.core.validation import is_workflow_class
from autoloop.core.workflow_capabilities import (
    WorkflowCapabilityEntry,
    WorkflowCapabilityInspectionError,
    WorkflowParameterField,
    annotation_display_name,
    inspect_workflow_reference as _inspect_workflow_reference,
    inspect_workflow_capabilities as _inspect_workflow_capabilities,
    json_safe_parameter_mapping,
    load_workflow_package_contract,
    workflow_parameter_fields,
)
from autoloop.core.workflow_catalog import (
    WorkflowCatalogDiscoveryError,
    WorkflowCatalogEntry,
    WorkflowCatalogManifestError,
    WorkflowSourceKind,
    discover_workflow_catalog as _discover_workflow_catalog,
    read_workflow_manifest,
    workflow_search_roots,
)


class WorkflowManifestError(ValueError):
    """Raised when a workflow manifest is invalid."""


class WorkflowDiscoveryError(LookupError):
    """Raised when workflow discovery or resolution fails."""


class WorkflowParameterError(ValueError):
    """Raised when workflow-specific parameter input is invalid."""


@dataclass(frozen=True, slots=True)
class WorkflowPackage:
    """Discovered manifest-backed workflow package metadata."""

    package_name: str
    workflow_name: str
    title: str | None
    description: str | None
    aliases: tuple[str, ...]
    package_dir: Path
    manifest_path: Path
    source_path: Path
    source_root_kind: WorkflowSourceKind
    source_root: Path
    authoring_shape: Literal["single_file", "flow_package", "workflow_package", "manifest_package", "unknown"]
    package_module: str | None
    workflow_module: str | None
    manifest_class: str | None = None


@dataclass(frozen=True, slots=True)
class WorkflowReference:
    """Resolved workflow origin metadata used by runtime execution."""

    original: str
    kind: Literal["catalog_name", "python_file", "python_module", "workflow_class", "workflow_directory"]
    workflow_name: str
    title: str | None
    description: str | None
    aliases: tuple[str, ...]
    class_name: str | None
    module_name: str | None
    source_path: Path | None
    package_dir: Path
    manifest_path: Path | None
    authoring_shape: Literal["single_file", "flow_package", "workflow_package", "manifest_package", "unknown"]
    source_root_kind: WorkflowSourceKind = "workspace"
    source_root: Path | None = None
    package_name: str | None = None
    package_module: str | None = None
    workflow_module: str | None = None


@dataclass(frozen=True, slots=True)
class ResolvedWorkflow:
    """Resolved workflow contract."""

    reference: WorkflowReference
    workflow_cls: type[Any]
    parameters_cls: type[Any] | None


def discover_workflow_catalog(
    root: str | Path,
    *,
    include_shadowed: bool = False,
) -> tuple[WorkflowCatalogEntry, ...]:
    """Discover pure workflow catalog metadata while preserving runtime error types."""

    try:
        return _discover_workflow_catalog(root, include_shadowed=include_shadowed)
    except WorkflowCatalogManifestError as exc:
        raise WorkflowManifestError(str(exc)) from exc
    except WorkflowCatalogDiscoveryError as exc:
        raise WorkflowDiscoveryError(str(exc)) from exc


def discover_workflow_packages(root: str | Path) -> tuple[WorkflowPackage, ...]:
    """Discover manifest-backed workflows from the effective catalog."""

    return tuple(
        WorkflowPackage(
            package_name=entry.package_name,
            workflow_name=entry.workflow_name,
            title=entry.title,
            description=entry.description,
            aliases=entry.aliases,
            package_dir=entry.package_dir,
            manifest_path=entry.manifest_path,
            source_path=entry.source_path,
            source_root_kind=entry.source_root_kind,
            source_root=entry.source_root,
            authoring_shape=entry.authoring_shape,
            package_module=entry.package_module,
            workflow_module=entry.workflow_module,
            manifest_class=entry.manifest_class,
        )
        for entry in discover_workflow_catalog(root)
        if entry.manifest_path is not None
    )


def resolve_workflow_package(root: str | Path, reference: str) -> WorkflowPackage:
    """Resolve a manifest-backed workflow by the catalog's precedence rules."""

    root_path = Path(root).resolve()
    entry = _resolve_catalog_entry_by_reference(root_path, reference, require_manifest=True)
    if entry is None:
        raise WorkflowDiscoveryError(f"unknown workflow {reference!r}")
    return _workflow_package_from_entry(entry)


def resolve_workflow_reference(root: str | Path, reference: str | type[Any]) -> ResolvedWorkflow:
    """Resolve a workflow name, path, module, or imported class through one runtime path."""

    root_path = Path(root).resolve()
    try:
        if isinstance(reference, str):
            base_reference, requested_class_name = _split_reference_class(reference)
            if _is_path_reference(base_reference):
                return _resolve_path_reference(root_path, reference, base_reference, requested_class_name)
            if "." in base_reference:
                return _resolve_module_reference(root_path, reference, base_reference, requested_class_name)
            return _resolve_named_reference(root_path, reference, base_reference, requested_class_name)
        if not isinstance(reference, type):
            raise TypeError(f"unsupported workflow reference {reference!r}")
        return _resolve_imported_class_reference(root_path, reference)
    finally:
        _cleanup_workflow_pycache(root_path)


def load_workflow_package_class(root: str | Path, reference: str | type[Any]) -> type[Any]:
    """Resolve and load the main workflow class from a workflow reference."""

    return resolve_workflow_reference(root, reference).workflow_cls


def load_compiled_workflow_package(root: str | Path, reference: str | type[Any]) -> CompiledWorkflow:
    """Resolve and compile the main workflow class from a workflow reference."""

    return compile_workflow(load_workflow_package_class(root, reference))


def inspect_workflow_capabilities(root: str | Path) -> tuple[WorkflowCapabilityEntry, ...]:
    """Inspect discovered workflows with importing capability detail and runtime error types."""

    try:
        return _inspect_workflow_capabilities(root)
    except WorkflowCatalogManifestError as exc:
        raise WorkflowManifestError(str(exc)) from exc
    except (WorkflowCatalogDiscoveryError, WorkflowCapabilityInspectionError) as exc:
        raise WorkflowDiscoveryError(str(exc)) from exc


def inspect_workflow_reference(root: str | Path, reference: str | type[Any]) -> WorkflowCapabilityEntry:
    """Inspect one workflow reference with importing capability detail and runtime error types."""

    try:
        return _inspect_workflow_reference(root, reference)
    except WorkflowCatalogManifestError as exc:
        raise WorkflowManifestError(str(exc)) from exc
    except (WorkflowCatalogDiscoveryError, WorkflowCapabilityInspectionError) as exc:
        raise WorkflowDiscoveryError(str(exc)) from exc


def validate_workflow_parameters(
    parameters_cls: type[Any] | None,
    raw_pairs: Sequence[tuple[str, str]] | None,
) -> dict[str, Any]:
    """Validate and coerce ordered ``-wf`` pairs through the workflow Params model."""

    ordered_pairs = tuple(raw_pairs or ())
    if parameters_cls is None:
        if ordered_pairs:
            raise WorkflowParameterError("workflow does not declare Params and does not accept -wf arguments")
        return {}

    fields = workflow_parameter_fields(parameters_cls)
    known_fields = {field.name: field for field in fields}
    payload: dict[str, Any] = {}
    for name, raw_value in ordered_pairs:
        field = known_fields.get(name)
        if field is None:
            raise WorkflowParameterError(f"unknown workflow parameter {name!r}")
        if field.supports_multiple:
            payload.setdefault(name, []).append(raw_value)
            continue
        if name in payload:
            raise WorkflowParameterError(
                f"workflow parameter {name!r} was provided multiple times but does not accept repeated values"
            )
        payload[name] = raw_value

    return coerce_workflow_parameter_mapping(parameters_cls, payload)


def coerce_workflow_parameter_mapping(
    parameters_cls: type[Any] | None,
    raw_values: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Validate and coerce workflow parameters supplied as a mapping."""

    payload = normalize_mapping(raw_values)
    if parameters_cls is None:
        if payload:
            raise WorkflowParameterError("workflow does not declare Params and does not accept workflow parameters")
        return {}
    for name in payload:
        if not isinstance(name, str) or not name:
            raise WorkflowParameterError("workflow parameter names must be non-empty strings")
    known_fields = {field.name for field in workflow_parameter_fields(parameters_cls)}
    unknown = sorted(set(payload) - known_fields)
    if unknown:
        if len(unknown) == 1:
            raise WorkflowParameterError(f"unknown workflow parameter {unknown[0]!r}")
        names = ", ".join(repr(name) for name in unknown)
        raise WorkflowParameterError(f"unknown workflow parameters: {names}")

    instance = _instantiate_workflow_parameters(parameters_cls, payload)
    return json_safe_parameter_mapping(_workflow_parameter_payload(parameters_cls, instance))


def materialize_workflow_params(
    parameters_cls: type[Any] | None,
    raw_values: Mapping[str, Any] | None,
) -> BaseModel:
    """Return a typed params object for runtime context access."""

    payload = normalize_mapping(raw_values)
    if parameters_cls is None:
        return EmptyParameters()

    instance = _instantiate_workflow_parameters(parameters_cls, payload)
    if isinstance(instance, BaseModel):
        return instance

    resolved_payload = _workflow_parameter_payload(parameters_cls, instance)
    if not resolved_payload:
        return EmptyParameters()
    snapshot_model = _workflow_parameter_snapshot_model(parameters_cls, resolved_payload)
    return snapshot_model.model_validate(resolved_payload)


def _resolve_named_reference(
    root_path: Path,
    original_reference: str,
    workflow_reference: str,
    requested_class_name: str | None,
) -> ResolvedWorkflow:
    entry = _resolve_catalog_entry_by_reference(root_path, workflow_reference)
    if entry is None:
        searched_roots = ", ".join(str(search_root.path) for search_root in workflow_search_roots(root_path))
        raise WorkflowDiscoveryError(
            f"unknown workflow {workflow_reference!r} for workspace root {root_path}; searched roots: {searched_roots}"
        )
    return _resolve_catalog_entry_reference(
        root_path,
        entry,
        original=original_reference,
        requested_class_name=requested_class_name,
        kind="catalog_name",
    )


def _resolve_path_reference(
    root_path: Path,
    original_reference: str,
    raw_path_reference: str,
    requested_class_name: str | None,
) -> ResolvedWorkflow:
    path = _resolve_reference_path(root_path, raw_path_reference)
    if not path.exists():
        raise FileNotFoundError(f"workflow path {path} does not exist")
    catalog_entry = _catalog_entry_for_explicit_path(root_path, path)
    if catalog_entry is not None:
        kind: Literal["python_file", "workflow_directory"] = "workflow_directory" if path.is_dir() else "python_file"
        return _resolve_catalog_entry_reference(
            root_path,
            catalog_entry,
            original=original_reference,
            requested_class_name=requested_class_name,
            kind=kind,
        )
    if path.is_dir():
        return _resolve_directory_reference(root_path, original_reference, path, requested_class_name)
    if path.suffix == ".toml":
        return _resolve_manifest_path_reference(root_path, original_reference, path, requested_class_name)
    if path.suffix != ".py":
        raise WorkflowDiscoveryError(f"workflow path {path} must be a Python file, workflow.toml, or directory")
    return _resolve_python_path(
        root_path,
        original=original_reference,
        source=path,
        requested_class_name=requested_class_name,
        kind="python_file",
        source_root_kind="workspace",
    )


def _resolve_directory_reference(
    root_path: Path,
    original_reference: str,
    directory: Path,
    requested_class_name: str | None,
) -> ResolvedWorkflow:
    manifest_path = directory / "workflow.toml"
    if manifest_path.is_file():
        return _resolve_manifest_path_reference(root_path, original_reference, manifest_path, requested_class_name)
    preferred = directory / "flow.py"
    workflow_py_path = directory / "workflow.py"
    if preferred.is_file():
        return _resolve_python_path(
            root_path,
            original=original_reference,
            source=preferred,
            requested_class_name=requested_class_name,
            kind="workflow_directory",
            source_root_kind="workspace",
        )
    if workflow_py_path.is_file():
        return _resolve_python_path(
            root_path,
            original=original_reference,
            source=workflow_py_path,
            requested_class_name=requested_class_name,
            kind="workflow_directory",
            source_root_kind="workspace",
        )
    raise WorkflowDiscoveryError(f"workflow directory {directory} must contain flow.py or workflow.py")


def _resolve_module_reference(
    root_path: Path,
    original_reference: str,
    module_name: str,
    requested_class_name: str | None,
) -> ResolvedWorkflow:
    module = _import_repo_module(module_name, root_path)
    workflow_cls = _locate_workflow_class(module, class_name=requested_class_name)
    source_path = _module_file(module)
    if source_path is None:
        raise WorkflowDiscoveryError(f"workflow module {module_name!r} does not have a filesystem source path")
    source_path = source_path.resolve()
    _apply_manifest_name_override(workflow_cls, _adjacent_manifest_path(source_path))
    parameters_cls = _resolve_parameters_cls(
        root_path,
        workflow_cls,
        module,
        package_dir=_package_dir_for_source(source_path),
        package_module_name=_package_module_name(module_name),
    )
    reference = _build_reference(
        original=original_reference,
        kind="python_module",
        workflow_cls=workflow_cls,
        module=module,
        source_path=source_path,
        package_dir=_package_dir_for_source(source_path),
        manifest_path=_adjacent_manifest_path(source_path),
        authoring_shape=_authoring_shape_for_source(source_path),
        aliases=(),
        title=None,
        description=None,
        source_root_kind=_source_root_kind_for_module(module_name),
        source_root=_classify_source_root(root_path, source_path),
        package_name=_package_name_from_module_name(module_name),
        package_module=_package_module_name(module_name),
        workflow_module=module_name,
    )
    return ResolvedWorkflow(reference=reference, workflow_cls=workflow_cls, parameters_cls=parameters_cls)


def _resolve_imported_class_reference(root_path: Path, workflow_cls: type[Any]) -> ResolvedWorkflow:
    module = sys.modules.get(workflow_cls.__module__)
    source_path = Path(inspect.getfile(workflow_cls)).resolve()
    manifest_path = _adjacent_manifest_path(source_path)
    module_name = workflow_cls.__module__
    if (
        manifest_path is not None
        and source_path.name in {"flow.py", "workflow.py"}
        and _source_root_kind_for_module(module_name) == "package"
    ):
        entry = _catalog_entry_for_explicit_path(root_path, source_path)
        if entry is not None and entry.manifest_path is not None and entry.source_root_kind == "package":
            resolved = _resolve_catalog_entry_reference(
                root_path,
                entry,
                original=f"{module_name}.{workflow_cls.__name__}",
                requested_class_name=workflow_cls.__name__,
                kind="catalog_name",
            )
            if resolved.workflow_cls is not workflow_cls:
                raise WorkflowDiscoveryError(
                    f"workflow class {module_name}.{workflow_cls.__name__} is not the main workflow export "
                    f"for package {entry.package_name!r}"
                )
            return resolved

    if module is None:
        module = _load_isolated_python_module(source_path)
        workflow_cls = _locate_workflow_class(module, class_name=workflow_cls.__name__)

    _apply_manifest_name_override(workflow_cls, manifest_path)
    parameters_cls = _resolve_parameters_cls(
        root_path,
        workflow_cls,
        module,
        package_dir=_package_dir_for_source(source_path),
        package_module_name=_package_module_name(workflow_cls.__module__),
    )
    reference = _build_reference(
        original=f"{workflow_cls.__module__}.{workflow_cls.__name__}",
        kind="workflow_class",
        workflow_cls=workflow_cls,
        module=module,
        source_path=source_path,
        package_dir=_package_dir_for_source(source_path),
        manifest_path=manifest_path,
        authoring_shape=_authoring_shape_for_source(source_path),
        aliases=(),
        title=None,
        description=None,
        source_root_kind=_classify_source_root_kind(root_path, source_path, module_name=workflow_cls.__module__),
        source_root=_classify_source_root(root_path, source_path),
        package_name=_package_name_from_source(root_path, source_path),
        package_module=_package_module_name(workflow_cls.__module__),
        workflow_module=workflow_cls.__module__,
    )
    return ResolvedWorkflow(reference=reference, workflow_cls=workflow_cls, parameters_cls=parameters_cls)


def _resolve_python_path(
    root_path: Path,
    *,
    original: str,
    source: Path,
    requested_class_name: str | None,
    kind: Literal["catalog_name", "python_file", "workflow_directory"],
    source_root_kind: WorkflowSourceKind,
    source_root: Path | None = None,
    package_module_name: str | None = None,
    workflow_module_name: str | None = None,
    title: str | None = None,
    description: str | None = None,
    aliases: tuple[str, ...] = (),
) -> ResolvedWorkflow:
    module = _load_isolated_python_module(source)
    workflow_cls = _locate_workflow_class(module, class_name=requested_class_name)
    manifest_path = _adjacent_manifest_path(source)
    _apply_manifest_name_override(workflow_cls, manifest_path)
    parameters_cls = _resolve_parameters_cls(
        root_path,
        workflow_cls,
        module,
        package_dir=_package_dir_for_source(source),
        package_module_name=package_module_name,
    )
    reference = _build_reference(
        original=original,
        kind=kind,
        workflow_cls=workflow_cls,
        module=module,
        source_path=source,
        package_dir=_package_dir_for_source(source),
        manifest_path=manifest_path,
        authoring_shape=_authoring_shape_for_source(source),
        aliases=aliases,
        title=title,
        description=description,
        source_root_kind=source_root_kind,
        source_root=source_root,
        package_name=_package_name_from_source(root_path, source),
        package_module=package_module_name,
        workflow_module=workflow_module_name,
    )
    return ResolvedWorkflow(reference=reference, workflow_cls=workflow_cls, parameters_cls=parameters_cls)


def _load_manifest_package_reference(
    root_path: Path,
    package: WorkflowPackage,
    *,
    original: str,
    requested_class_name: str | None,
) -> ResolvedWorkflow:
    entry = _catalog_entry_for_manifest_package(root_path, package)
    return _resolve_catalog_entry_reference(
        root_path,
        entry,
        original=original,
        requested_class_name=requested_class_name,
        kind="catalog_name",
    )


def _resolve_parameters_cls(
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
        raise WorkflowDiscoveryError("Use Params, not Parameters.")

    if package_module_name is not None:
        exported = _load_package_exported_parameters(root_path, package_module_name)
        if exported is not None:
            return exported

    parameters_from_params_py = _load_parameters_from_params_py(
        root_path,
        package_dir,
        package_module_name=package_module_name,
    )
    if parameters_from_params_py is not None:
        return parameters_from_params_py
    return None


def _load_package_exported_parameters(root_path: Path, package_module_name: str) -> type[Any] | None:
    package_module = _import_repo_module(package_module_name, root_path)
    exported = getattr(package_module, "Params", None)
    if exported is None:
        if getattr(package_module, "Parameters", None) is not None:
            raise WorkflowDiscoveryError("Use Params, not Parameters.")
        return None
    parameters_cls = _require_parameter_type(exported, f"{package_module_name}.Params")
    package_all = getattr(package_module, "__all__", None)
    if not isinstance(package_all, list):
        raise WorkflowDiscoveryError(f"workflow package {package_module_name!r} must define __all__ as a list")
    if "Params" not in package_all:
        raise WorkflowDiscoveryError(
            f"workflow package {package_module_name!r} must include 'Params' in __all__ when it is exported"
        )
    return parameters_cls


def _load_parameters_from_params_py(
    root_path: Path,
    package_dir: Path,
    *,
    package_module_name: str | None,
) -> type[Any] | None:
    params_path = package_dir / "params.py"
    if not params_path.is_file():
        return None
    if package_module_name is not None:
        params_module = _import_repo_module(f"{package_module_name}.params", root_path)
    else:
        params_module = _load_isolated_python_module(params_path)
    parameters_cls = getattr(params_module, "Params", None)
    if parameters_cls is None:
        if getattr(params_module, "Parameters", None) is not None:
            raise WorkflowDiscoveryError("Use Params, not Parameters.")
        return None
    return _require_parameter_type(parameters_cls, f"{params_module.__name__}.Params")


def _build_reference(
    *,
    original: str,
    kind: Literal["catalog_name", "python_file", "python_module", "workflow_class", "workflow_directory"],
    workflow_cls: type[Any],
    module: ModuleType,
    source_path: Path,
    package_dir: Path,
    manifest_path: Path | None,
    authoring_shape: Literal["single_file", "flow_package", "workflow_package", "manifest_package", "unknown"],
    aliases: tuple[str, ...],
    title: str | None,
    description: str | None,
    source_root_kind: WorkflowSourceKind,
    source_root: Path | None,
    package_name: str | None,
    package_module: str | None,
    workflow_module: str | None,
) -> WorkflowReference:
    compiled = compile_workflow(workflow_cls)
    return WorkflowReference(
        original=original,
        kind=kind,
        workflow_name=compiled.workflow_name,
        title=title,
        description=description,
        aliases=aliases,
        class_name=workflow_cls.__name__,
        module_name=module.__name__,
        source_path=source_path.resolve(),
        package_dir=package_dir.resolve(),
        manifest_path=None if manifest_path is None else manifest_path.resolve(),
        authoring_shape=authoring_shape,
        source_root_kind=source_root_kind,
        source_root=None if source_root is None else source_root.resolve(),
        package_name=package_name,
        package_module=package_module,
        workflow_module=workflow_module,
    )


def _locate_workflow_class(module: ModuleType, *, class_name: str | None = None) -> type[Any]:
    if class_name is not None:
        candidate = getattr(module, class_name, None)
        if not is_workflow_class(candidate):
            raise WorkflowDiscoveryError(f"workflow class {class_name!r} was not found in module {module.__name__!r}")
        return candidate

    candidates = [
        value
        for value in module.__dict__.values()
        if isinstance(value, type) and value.__module__ == module.__name__ and is_workflow_class(value)
    ]
    if not candidates:
        raise WorkflowDiscoveryError(f"no workflow class was found in module {module.__name__!r}")
    if len(candidates) > 1:
        names = ", ".join(sorted(candidate.__name__ for candidate in candidates))
        raise WorkflowDiscoveryError(
            f"multiple workflow classes were found in module {module.__name__!r}: {names}; specify :ClassName"
        )
    return candidates[0]


def _instantiate_workflow_parameters(parameters_cls: type[Any], payload: Mapping[str, Any]) -> Any:
    try:
        if isinstance(parameters_cls, type) and issubclass(parameters_cls, BaseModel):
            return parameters_cls.model_validate(payload)
        return parameters_cls(**payload)
    except ValidationError as exc:
        raise WorkflowParameterError(str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise WorkflowParameterError(str(exc)) from exc


def _workflow_parameter_payload(parameters_cls: type[Any], instance: Any) -> dict[str, Any]:
    if isinstance(instance, BaseModel):
        return instance.model_dump(mode="python")
    if isinstance(instance, dict):
        return dict(instance)
    if hasattr(instance, "__dict__"):
        return dict(vars(instance))
    raise WorkflowParameterError(
        f"workflow Params model {parameters_cls.__module__}.{parameters_cls.__name__} did not produce a mapping"
    )


def _workflow_parameter_snapshot_model(parameters_cls: type[Any], payload: Mapping[str, Any]) -> type[BaseModel]:
    field_definitions = {
        name: ((type(value) if value is not None else Any), value)
        for name, value in payload.items()
    }
    return create_model(
        f"{parameters_cls.__name__}Snapshot",
        __base__=EmptyParameters,
        __module__=parameters_cls.__module__,
        **field_definitions,
    )


def _load_isolated_python_module(source_path: Path) -> ModuleType:
    source_path = source_path.resolve()
    module_name = _isolated_module_name(source_path)
    for cached_name in tuple(sys.modules):
        if cached_name == module_name or cached_name.startswith(f"{module_name}."):
            sys.modules.pop(cached_name, None)
    if _should_treat_as_package_module(source_path):
        spec = importlib.util.spec_from_file_location(
            module_name,
            source_path,
            submodule_search_locations=[str(source_path.parent)],
        )
    else:
        spec = importlib.util.spec_from_file_location(module_name, source_path)
    if spec is None or spec.loader is None:
        raise WorkflowDiscoveryError(f"could not load workflow module from {source_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    with _no_bytecode_writes():
        spec.loader.exec_module(module)
    return module


def _import_repo_module(module_name: str, root_path: Path) -> ModuleType:
    importlib.invalidate_caches()
    with _repo_root_on_syspath(root_path):
        with _no_bytecode_writes():
            return importlib.import_module(module_name)


def _apply_manifest_name_override(workflow_cls: type[Any], manifest_path: Path | None) -> None:
    declared_name = getattr(workflow_cls, "name", None)
    if isinstance(declared_name, str) and declared_name.strip():
        return
    if manifest_path is None or not manifest_path.is_file():
        return
    manifest_name = _read_manifest_name(manifest_path)
    if manifest_name is not None:
        setattr(workflow_cls, "name", manifest_name)


def _read_manifest_name(manifest_path: Path) -> str | None:
    try:
        with manifest_path.open("rb") as handle:
            payload = tomllib.load(handle)
    except (FileNotFoundError, OSError, tomllib.TOMLDecodeError):
        pass
    else:
        name = payload.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def _split_reference_class(reference: str) -> tuple[str, str | None]:
    if ":" not in reference:
        return reference, None
    base, class_name = reference.rsplit(":", 1)
    if not class_name:
        raise WorkflowDiscoveryError(f"workflow reference {reference!r} ends with an empty class selector")
    return base, class_name


def _is_path_reference(reference: str) -> bool:
    if reference.endswith((".py", ".toml")):
        return True
    if Path(reference).is_absolute():
        return True
    if reference.startswith(("./", "../", ".\\", "..\\")):
        return True
    return "/" in reference or "\\" in reference


def _resolve_reference_path(root_path: Path, reference: str) -> Path:
    path = Path(reference)
    if not path.is_absolute():
        path = root_path / path
    return path.resolve()


def _resolve_catalog_entry_by_reference(
    root_path: Path,
    reference: str,
    *,
    require_manifest: bool = False,
) -> WorkflowCatalogEntry | None:
    key = reference.strip()
    if not key:
        raise WorkflowDiscoveryError("workflow reference must be a non-empty string")
    catalog = discover_workflow_catalog(root_path)
    for source_root_kind in ("workspace", "package"):
        for entry in catalog:
            if entry.source_root_kind != source_root_kind:
                continue
            if require_manifest and entry.manifest_path is None:
                continue
            if entry.workflow_name == key:
                return entry
        for entry in catalog:
            if entry.source_root_kind != source_root_kind:
                continue
            if require_manifest and entry.manifest_path is None:
                continue
            if key in entry.aliases:
                return entry
    return None


def _catalog_entry_for_explicit_path(root_path: Path, path: Path) -> WorkflowCatalogEntry | None:
    resolved = path.resolve()
    for entry in discover_workflow_catalog(root_path, include_shadowed=True):
        if resolved.is_dir() and entry.package_dir.resolve() == resolved:
            return entry
        if entry.manifest_path is not None and entry.manifest_path.resolve() == resolved:
            return entry
        if entry.source_path.resolve() == resolved:
            return entry
    return None


def _workflow_package_from_entry(entry: WorkflowCatalogEntry) -> WorkflowPackage:
    if entry.manifest_path is None:
        raise WorkflowDiscoveryError(f"workflow {entry.workflow_name!r} is not manifest-backed")
    return WorkflowPackage(
        package_name=entry.package_name,
        workflow_name=entry.workflow_name,
        title=entry.title,
        description=entry.description,
        aliases=entry.aliases,
        package_dir=entry.package_dir,
        manifest_path=entry.manifest_path,
        source_path=entry.source_path,
        source_root_kind=entry.source_root_kind,
        source_root=entry.source_root,
        authoring_shape=entry.authoring_shape,
        package_module=entry.package_module,
        workflow_module=entry.workflow_module,
        manifest_class=entry.manifest_class,
    )


def _catalog_entry_for_manifest_package(root_path: Path, package: WorkflowPackage) -> WorkflowCatalogEntry:
    for entry in discover_workflow_catalog(root_path, include_shadowed=True):
        if entry.manifest_path is not None and entry.manifest_path.resolve() == package.manifest_path.resolve():
            return entry
    manifest = read_workflow_manifest(package.manifest_path)
    return WorkflowCatalogEntry(
        workflow_name=package.workflow_name,
        title=package.title or manifest.get("title", package.workflow_name.replace("_", " ").title()),
        description=package.description or manifest.get("description", ""),
        aliases=package.aliases,
        package_name=package.package_name,
        package_dir=package.package_dir.resolve(),
        manifest_path=package.manifest_path.resolve(),
        source_path=package.source_path.resolve(),
        source_root_kind=package.source_root_kind,
        source_root=package.source_root.resolve(),
        import_prefix="autoloop.workflows" if package.source_root_kind == "package" else None,
        precedence=100 if package.source_root_kind == "workspace" else 10,
        package_module=package.package_module,
        workflow_module=package.workflow_module,
        authoring_shape=package.authoring_shape,
        prompts_dir=(package.package_dir / "prompts").resolve() if (package.package_dir / "prompts").is_dir() else None,
        assets_dir=(package.package_dir / "assets").resolve() if (package.package_dir / "assets").is_dir() else None,
        docs_path=(package.package_dir / "docs.md").resolve() if (package.package_dir / "docs.md").is_file() else None,
        params_path=(package.package_dir / "params.py").resolve() if (package.package_dir / "params.py").is_file() else None,
        specs_path=(package.package_dir / "specs.py").resolve() if (package.package_dir / "specs.py").is_file() else None,
        contracts_path=(package.package_dir / "contracts.py").resolve()
        if (package.package_dir / "contracts.py").is_file()
        else None,
        tests_dir=(package.package_dir / "tests").resolve() if (package.package_dir / "tests").is_dir() else None,
        manifest_module=manifest.get("module"),
        manifest_class=package.manifest_class or manifest.get("class"),
        workflow_path=package.source_path.resolve(),
        doc_path=(package.package_dir / "docs.md").resolve() if (package.package_dir / "docs.md").is_file() else None,
        flow_path=package.source_path.resolve() if package.source_path.name == "flow.py" else None,
        workflow_py_path=package.source_path.resolve() if package.source_path.name == "workflow.py" else None,
        package_init_path=(package.package_dir / "__init__.py").resolve() if (package.package_dir / "__init__.py").is_file() else None,
    )


def _resolve_catalog_entry_reference(
    root_path: Path,
    entry: WorkflowCatalogEntry,
    *,
    original: str,
    requested_class_name: str | None,
    kind: Literal["catalog_name", "python_file", "workflow_directory"],
) -> ResolvedWorkflow:
    manifest_class_name = entry.manifest_class
    if requested_class_name is not None and manifest_class_name is not None and requested_class_name != manifest_class_name:
        raise WorkflowDiscoveryError(
            f"workflow reference {original!r} requested class {requested_class_name!r}, "
            f"but manifest {entry.manifest_path} declares {manifest_class_name!r}"
        )
    target_class_name = manifest_class_name or requested_class_name
    if entry.source_root_kind == "package" and entry.package_module is not None and entry.workflow_module is not None:
        try:
            loaded = load_workflow_package_contract(root_path, entry)
        except WorkflowCapabilityInspectionError as exc:
            raise WorkflowDiscoveryError(str(exc)) from exc
        if target_class_name is not None and loaded.workflow_cls.__name__ != target_class_name:
            raise WorkflowDiscoveryError(
                f"workflow reference {original!r} resolved to {loaded.workflow_cls.__name__!r}; "
                f"class {target_class_name!r} was not found"
            )
        reference = WorkflowReference(
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
        )
        return ResolvedWorkflow(reference=reference, workflow_cls=loaded.workflow_cls, parameters_cls=loaded.parameters_cls)
    return _resolve_python_path(
        root_path,
        original=original,
        source=entry.source_path,
        requested_class_name=target_class_name,
        kind=kind,
        source_root_kind=entry.source_root_kind,
        source_root=entry.source_root,
        package_module_name=None,
        workflow_module_name=None,
        title=entry.title,
        description=entry.description,
        aliases=entry.aliases,
    )


def _resolve_manifest_path_reference(
    root_path: Path,
    original_reference: str,
    manifest_path: Path,
    requested_class_name: str | None,
) -> ResolvedWorkflow:
    manifest = read_workflow_manifest(manifest_path)
    source_path = _manifest_source_path(manifest_path, manifest)
    manifest_class_name = manifest.get("class")
    if requested_class_name is not None and manifest_class_name is not None and requested_class_name != manifest_class_name:
        raise WorkflowDiscoveryError(
            f"workflow reference {original_reference!r} requested class {requested_class_name!r}, "
            f"but manifest {manifest_path} declares {manifest_class_name!r}"
        )
    return _resolve_python_path(
        root_path,
        original=original_reference,
        source=source_path,
        requested_class_name=manifest_class_name or requested_class_name,
        kind="python_file",
        source_root_kind=_classify_source_root_kind(root_path, source_path),
        source_root=_classify_source_root(root_path, source_path),
        title=manifest.get("title"),
        description=manifest.get("description"),
        aliases=tuple(manifest.get("aliases", ())),
    )


def _manifest_source_path(manifest_path: Path, manifest: Mapping[str, Any]) -> Path:
    module_name = manifest.get("module")
    package_dir = manifest_path.parent.resolve()
    if module_name is not None:
        candidate = package_dir / Path(str(module_name).replace(".", "/")).with_suffix(".py")
        if not candidate.is_file():
            raise WorkflowDiscoveryError(f"workflow manifest {manifest_path} references missing module source {candidate}")
        return candidate.resolve()
    preferred = package_dir / "flow.py"
    if preferred.is_file():
        return preferred.resolve()
    workflow_py_path = package_dir / "workflow.py"
    if workflow_py_path.is_file():
        return workflow_py_path.resolve()
    raise WorkflowDiscoveryError(f"workflow manifest {manifest_path} requires flow.py or workflow.py in {package_dir}")


def _package_dir_for_source(source_path: Path) -> Path:
    return source_path.parent


def _authoring_shape_for_source(
    source_path: Path,
) -> Literal["single_file", "flow_package", "workflow_package", "manifest_package", "unknown"]:
    manifest_path = _adjacent_manifest_path(source_path)
    if manifest_path is not None:
        return "manifest_package"
    if source_path.name == "flow.py":
        return "flow_package"
    if source_path.name == "workflow.py":
        return "workflow_package"
    if source_path.suffix == ".py":
        return "single_file"
    return "unknown"


def _adjacent_manifest_path(source_path: Path) -> Path | None:
    if source_path.name in {"flow.py", "workflow.py", "__init__.py"}:
        manifest_path = source_path.parent / "workflow.toml"
        return manifest_path if manifest_path.is_file() else None
    return None


def _package_module_name(module_name: str | None) -> str | None:
    if not module_name:
        return None
    parts = module_name.split(".")
    if len(parts) >= 2 and parts[-1] in {"workflow", "flow", "__init__"}:
        return ".".join(parts[:-1])
    if len(parts) >= 2:
        return module_name
    return None


def _package_name_from_module_name(module_name: str) -> str | None:
    package_module = _package_module_name(module_name)
    if not package_module:
        return None
    return package_module.rsplit(".", 1)[-1]


def _package_name_from_source(root_path: Path, source_path: Path) -> str | None:
    resolved = source_path.resolve()
    for search_root in workflow_search_roots(root_path):
        try:
            relative = resolved.relative_to(search_root.path.resolve())
        except ValueError:
            continue
        if len(relative.parts) >= 2 and resolved.name in {"flow.py", "workflow.py", "__init__.py"}:
            return relative.parts[0]
        if len(relative.parts) == 1 and resolved.suffix == ".py":
            return relative.stem
    if resolved.name in {"flow.py", "workflow.py", "__init__.py"}:
        return resolved.parent.name
    return resolved.stem
 

def _source_root_kind_for_module(module_name: str) -> WorkflowSourceKind:
    return "package" if module_name.startswith("autoloop.workflows.") else "workspace"


def _classify_source_root_kind(root_path: Path, source_path: Path, *, module_name: str | None = None) -> WorkflowSourceKind:
    if module_name is not None and module_name.startswith("autoloop.workflows."):
        return "package"
    resolved = source_path.resolve()
    for search_root in workflow_search_roots(root_path):
        try:
            resolved.relative_to(search_root.path.resolve())
        except ValueError:
            continue
        return search_root.kind
    return "workspace"


def _classify_source_root(root_path: Path, source_path: Path) -> Path | None:
    resolved = source_path.resolve()
    for search_root in workflow_search_roots(root_path):
        try:
            resolved.relative_to(search_root.path.resolve())
        except ValueError:
            continue
        return search_root.path.resolve()
    return None


def _should_treat_as_package_module(source_path: Path) -> bool:
    return source_path.name in {"flow.py", "workflow.py", "__init__.py"}


def _load_isolated_python_module(source_path: Path) -> ModuleType:
    source_path = source_path.resolve()
    if _should_treat_as_package_module(source_path):
        package_module_name, module_name = _isolated_package_module_name(source_path)
        _evict_isolated_namespace(package_module_name)
        _ensure_namespace_package("_autoloop_workspace_workflows", ())
        _ensure_namespace_package(".".join(package_module_name.split(".")[:2]), ())
        _ensure_namespace_package(package_module_name, (str(source_path.parent),))
        if source_path.name == "__init__.py":
            spec = importlib.util.spec_from_file_location(
                module_name,
                source_path,
                submodule_search_locations=[str(source_path.parent)],
            )
        else:
            spec = importlib.util.spec_from_file_location(module_name, source_path)
    else:
        module_name = _isolated_module_name(source_path)
        _evict_isolated_namespace(module_name)
        spec = importlib.util.spec_from_file_location(module_name, source_path)
    if spec is None or spec.loader is None:
        raise WorkflowDiscoveryError(f"could not load workflow module from {source_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    with _no_bytecode_writes():
        spec.loader.exec_module(module)
    return module


def _import_repo_module(module_name: str, root_path: Path) -> ModuleType:
    importlib.invalidate_caches()
    with _repo_root_on_syspath(root_path):
        with _no_bytecode_writes():
            return importlib.import_module(module_name)


def _isolated_package_module_name(source_path: Path) -> tuple[str, str]:
    workflow_id = _sanitize_identifier(source_path.parent.name or source_path.stem)
    package_digest = sha1(str(source_path.parent.resolve()).encode("utf-8")).hexdigest()[:12]
    package_module = f"_autoloop_workspace_workflows.{package_digest}.{workflow_id}"
    if source_path.name == "__init__.py":
        return package_module, package_module
    return package_module, f"{package_module}.{source_path.stem}"


def _isolated_module_name(source_path: Path) -> str:
    workflow_id = _sanitize_identifier(source_path.stem)
    digest = sha1(str(source_path.resolve()).encode("utf-8")).hexdigest()[:12]
    return f"_autoloop_workspace_workflows.{digest}.{workflow_id}"


def _sanitize_identifier(value: str) -> str:
    cleaned = "".join(char if char.isalnum() else "_" for char in value.strip())
    cleaned = cleaned.strip("_")
    return cleaned or "workflow"


def _ensure_namespace_package(name: str, search_locations: Sequence[str]) -> None:
    if name in sys.modules:
        module = sys.modules[name]
        if search_locations:
            module.__dict__["__path__"] = list(search_locations)
        return
    module = ModuleType(name)
    module.__package__ = name
    module.__path__ = list(search_locations)
    sys.modules[name] = module


def _evict_isolated_namespace(prefix: str) -> None:
    for cached_name in tuple(sys.modules):
        if cached_name == prefix or cached_name.startswith(f"{prefix}."):
            sys.modules.pop(cached_name, None)


def _module_file(module: ModuleType) -> Path | None:
    module_file = getattr(module, "__file__", None)
    if isinstance(module_file, str) and module_file:
        return Path(module_file)
    module_spec = getattr(module, "__spec__", None)
    origin = getattr(module_spec, "origin", None)
    if isinstance(origin, str) and origin:
        return Path(origin)
    return None


def _require_parameter_type(candidate: Any, label: str) -> type[Any]:
    if not isinstance(candidate, type):
        raise WorkflowDiscoveryError(f"workflow parameter symbol {label!r} must be a type")
    return candidate


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
            except ValueError:  # pragma: no cover
                pass


@contextmanager
def _no_bytecode_writes():
    original = sys.dont_write_bytecode
    original_prefix = getattr(sys, "pycache_prefix", None)
    sys.dont_write_bytecode = True
    with tempfile.TemporaryDirectory(prefix="autoloop-loader-pyc-") as pycache_root:
        sys.pycache_prefix = pycache_root
        try:
            yield
        finally:
            sys.dont_write_bytecode = original
            sys.pycache_prefix = original_prefix


def _cleanup_workflow_pycache(root_path: Path) -> None:
    workspace_root = root_path / ".autoloop" / "workflows"
    if not workspace_root.is_dir():
        return
    for pycache_dir in sorted(workspace_root.rglob("__pycache__"), reverse=True):
        if not pycache_dir.is_dir():
            continue
        for candidate in pycache_dir.iterdir():
            if candidate.is_file():
                candidate.unlink()
        try:
            pycache_dir.rmdir()
        except OSError:
            continue


__all__ = [
    "ResolvedWorkflow",
    "WorkflowCapabilityEntry",
    "WorkflowCatalogEntry",
    "WorkflowDiscoveryError",
    "WorkflowManifestError",
    "WorkflowPackage",
    "WorkflowParameterError",
    "WorkflowParameterField",
    "WorkflowReference",
    "annotation_display_name",
    "coerce_workflow_parameter_mapping",
    "discover_workflow_catalog",
    "discover_workflow_packages",
    "inspect_workflow_capabilities",
    "inspect_workflow_reference",
    "load_compiled_workflow_package",
    "load_workflow_package_class",
    "materialize_workflow_params",
    "resolve_workflow_package",
    "resolve_workflow_reference",
    "validate_workflow_parameters",
    "workflow_parameter_fields",
]
