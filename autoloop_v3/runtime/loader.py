"""Workflow loading helpers."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from ..workflow.compiler import CompiledWorkflow, compile_workflow
from ..workflow.steps import Step


def load_workflow_module(target: str | Path, *, module_name: str | None = None) -> ModuleType:
    """Load a workflow module without mutating its globals."""

    spec, resolved_name = _resolve_spec(target, module_name=module_name)
    if spec.loader is None:
        raise ImportError(f"workflow target {target!r} does not have a usable loader")

    module = importlib.util.module_from_spec(spec)
    sys.modules[resolved_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(resolved_name, None)
        raise
    return module


def load_workflow_class(
    target: str | Path,
    *,
    class_name: str | None = None,
    module_name: str | None = None,
) -> type[Any]:
    """Load one workflow class from a target module."""

    module = load_workflow_module(target, module_name=module_name)
    return locate_workflow_class(module, class_name=class_name)


def locate_workflow_class(module: ModuleType, *, class_name: str | None = None) -> type[Any]:
    """Return the target workflow class from a loaded module."""

    if class_name is not None:
        candidate = getattr(module, class_name, None)
        if not isinstance(candidate, type):
            raise LookupError(f"workflow class {class_name!r} was not found in module {module.__name__!r}")
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
        raise LookupError(f"no workflow class was found in module {module.__name__!r}")
    if len(candidates) > 1:
        names = ", ".join(sorted(candidate.__name__ for candidate in candidates))
        raise LookupError(
            f"multiple workflow classes were found in module {module.__name__!r}: {names}; specify class_name"
        )
    return candidates[0]


def load_compiled_workflow(
    target: str | Path,
    *,
    class_name: str | None = None,
    module_name: str | None = None,
) -> CompiledWorkflow:
    """Load and compile a workflow from a module target."""

    workflow_cls = load_workflow_class(target, class_name=class_name, module_name=module_name)
    return compile_workflow(workflow_cls)


def _resolve_spec(target: str | Path, *, module_name: str | None = None) -> tuple[importlib.machinery.ModuleSpec, str]:
    path_target = Path(target)
    if path_target.exists():
        resolved_path = path_target.resolve()
        resolved_name = module_name or _generated_module_name(resolved_path)
        spec = importlib.util.spec_from_file_location(resolved_name, resolved_path)
        if spec is None:
            raise ImportError(f"unable to create a module spec for {resolved_path}")
        return spec, resolved_name

    target_name = str(target)
    spec = importlib.util.find_spec(target_name)
    if spec is None:
        raise ImportError(f"unable to locate workflow module {target_name!r}")
    resolved_name = module_name or target_name
    if module_name is not None and spec.origin is not None:
        relocated = importlib.util.spec_from_file_location(module_name, spec.origin)
        if relocated is not None:
            spec = relocated
    return spec, resolved_name


def _generated_module_name(path: Path) -> str:
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:10]
    return f"autoloop_v3.runtime.loaded_{path.stem}_{digest}"
