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
from .steps import Step
from .workflow_catalog import WorkflowCatalogEntry, discover_workflow_catalog


class WorkflowCapabilityInspectionError(LookupError):
    """Raised when rich workflow capability inspection cannot load a workflow package."""


@dataclass(frozen=True, slots=True)
class WorkflowLoadedPackage:
    """Loaded package contract for importing inspection and runtime resolution."""

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
class WorkflowStepCapability:
    """Normalized compiled-step capability summary."""

    name: str
    kind: str
    session_name: str | None
    requires: tuple[str, ...]
    produces: tuple[str, ...]
    log_artifacts: tuple[str, ...]
    available_routes: tuple[str, ...]
    expected_output_schema: dict[str, Any] | None
    route_contracts: dict[str, dict[str, Any]]
    producer_prompt: str | None
    verifier_prompt: str | None


@dataclass(frozen=True, slots=True)
class WorkflowCapabilityEntry:
    """Rich importing inspection for one discovered workflow package."""

    package_name: str
    workflow_name: str
    workflow_class: str
    title: str | None
    description: str | None
    aliases: tuple[str, ...]
    package_dir: Path
    manifest_path: Path
    workflow_path: Path
    params_path: Path | None
    doc_path: Path | None
    entry_step_name: str
    parameters_supported: bool
    parameters: tuple[WorkflowParameterField, ...]
    steps: tuple[WorkflowStepCapability, ...]


def inspect_workflow_capabilities(root: str | Path) -> tuple[WorkflowCapabilityEntry, ...]:
    """Inspect all discovered workflow packages with importing capability detail."""

    root_path = Path(root).resolve()
    return tuple(_inspect_catalog_entry(root_path, entry) for entry in discover_workflow_catalog(root_path))


def load_workflow_package_contract(root: str | Path, entry: WorkflowCatalogEntry) -> WorkflowLoadedPackage:
    """Load the main workflow class, parameters model, and compiled workflow for one catalog entry."""

    root_path = Path(root).resolve()
    workflow_module = _import_discovered_module(f"workflows.{entry.package_name}.workflow", root_path)
    workflow_cls = locate_workflow_class(workflow_module)
    compiled = compile_workflow(workflow_cls)
    if compiled.workflow_name != entry.workflow_name:
        raise WorkflowCapabilityInspectionError(
            f"workflow package {entry.package_name!r} declares workflow name {entry.workflow_name!r}, "
            f"but its main workflow class compiles to {compiled.workflow_name!r}"
        )
    package_module = _import_discovered_module(f"workflows.{entry.package_name}", root_path)
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
        "description": entry.description,
        "doc_path": None if entry.doc_path is None else str(entry.doc_path),
        "entry_step_name": entry.entry_step_name,
        "manifest_path": str(entry.manifest_path),
        "package_dir": str(entry.package_dir),
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
        "parameters_supported": entry.parameters_supported,
        "params_path": None if entry.params_path is None else str(entry.params_path),
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
                "requires": list(step.requires),
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
        "title": entry.title,
        "workflow_class": entry.workflow_class,
        "workflow_name": entry.workflow_name,
        "workflow_path": str(entry.workflow_path),
    }


def _inspect_catalog_entry(root_path: Path, entry: WorkflowCatalogEntry) -> WorkflowCapabilityEntry:
    loaded = load_workflow_package_contract(root_path, entry)
    return WorkflowCapabilityEntry(
        package_name=entry.package_name,
        workflow_name=entry.workflow_name,
        workflow_class=loaded.workflow_cls.__name__,
        title=entry.title,
        description=entry.description,
        aliases=entry.aliases,
        package_dir=entry.package_dir,
        manifest_path=entry.manifest_path,
        workflow_path=entry.workflow_path,
        params_path=entry.params_path,
        doc_path=entry.doc_path,
        entry_step_name=loaded.compiled.entry_step_name,
        parameters_supported=loaded.parameters_cls is not None,
        parameters=workflow_parameter_fields(loaded.parameters_cls),
        steps=tuple(_compiled_step_capability(step) for step in loaded.compiled.steps.values()),
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


def _prompt_path(prompt: Any) -> str | None:
    if prompt is None:
        return None
    return getattr(prompt, "path", prompt)


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
    "WorkflowCapabilityEntry",
    "WorkflowCapabilityInspectionError",
    "WorkflowParameterField",
    "WorkflowStepCapability",
    "annotation_display_name",
    "inspect_workflow_capabilities",
    "json_safe_parameter_mapping",
    "json_safe_parameter_value",
    "load_workflow_package_contract",
    "workflow_capability_payload",
    "workflow_parameter_fields",
]
