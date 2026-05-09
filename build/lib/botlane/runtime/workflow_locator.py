"""Runtime workflow locator variants.

Internal runtime helper; not part of the public botlane authoring API.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

from .loader import ResolvedWorkflow, resolve_workflow_reference


@dataclass(frozen=True, slots=True)
class CatalogWorkflowLocator:
    workflow_id: str


@dataclass(frozen=True, slots=True)
class PythonFileWorkflowLocator:
    path: Path
    class_name: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))


@dataclass(frozen=True, slots=True)
class PythonModuleWorkflowLocator:
    module: str
    class_name: str | None = None


@dataclass(frozen=True, slots=True)
class WorkflowDirectoryLocator:
    path: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))


WorkflowLocator: TypeAlias = (
    CatalogWorkflowLocator
    | PythonFileWorkflowLocator
    | PythonModuleWorkflowLocator
    | WorkflowDirectoryLocator
)


def workflow_locator_reference(locator: WorkflowLocator) -> str:
    if isinstance(locator, CatalogWorkflowLocator):
        return locator.workflow_id
    if isinstance(locator, PythonFileWorkflowLocator):
        return _reference_with_optional_class(locator.path, locator.class_name)
    if isinstance(locator, PythonModuleWorkflowLocator):
        return _reference_with_optional_class(locator.module, locator.class_name)
    if isinstance(locator, WorkflowDirectoryLocator):
        return str(locator.path)
    raise TypeError(f"unsupported workflow locator {type(locator)!r}")


def resolve_workflow_locator(root: str | Path, locator: WorkflowLocator) -> ResolvedWorkflow:
    return resolve_workflow_reference(root, workflow_locator_reference(locator))


def workflow_locator_from_resolved(resolved: ResolvedWorkflow) -> WorkflowLocator:
    reference = resolved.reference
    if reference.kind == "catalog_name":
        return CatalogWorkflowLocator(workflow_id=reference.original)
    if reference.kind == "python_file":
        if reference.source_path is None:
            raise ValueError("resolved python-file workflow is missing source_path")
        return PythonFileWorkflowLocator(path=reference.source_path, class_name=reference.class_name)
    if reference.kind == "python_module":
        module_name = reference.workflow_module or reference.module_name
        if module_name is None:
            raise ValueError("resolved python-module workflow is missing module name")
        return PythonModuleWorkflowLocator(module=module_name, class_name=reference.class_name)
    if reference.kind == "workflow_directory":
        return WorkflowDirectoryLocator(path=reference.package_dir)
    raise ValueError(f"workflow reference kind {reference.kind!r} does not have a locator variant")


def _reference_with_optional_class(value: str | Path, class_name: str | None) -> str:
    reference = str(value)
    if class_name:
        return f"{reference}:{class_name}"
    return reference
