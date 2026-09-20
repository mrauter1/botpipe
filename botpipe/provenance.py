"""Recorded source identity for honest comparisons between durable workflow runs."""

from __future__ import annotations

import inspect
from hashlib import sha256
from pathlib import Path
from types import CodeType, ModuleType
from typing import Any, get_type_hints

from .surface_identity import (
    canonical_workflow_identity,
    derive_workflow_surface_manifest,
)


def _active_module_code(source: Path) -> CodeType | None:
    """Retain only immutable code, never a live frame or its global namespace."""
    frame = inspect.currentframe()
    try:
        while frame is not None:
            code = frame.f_code
            if (
                code.co_name == "<module>"
                and Path(code.co_filename).resolve() == source
            ):
                return code
            frame = frame.f_back
        return None
    finally:
        del frame


def capture_definition_sources(definition: Any) -> dict[str, Any] | None:
    """Remember source bytes at definition time without importing or walking packages."""
    try:
        target = inspect.unwrap(getattr(definition, "fn", definition))
        source = inspect.getsourcefile(target)
        if source is None:
            return None
        path = Path(source).resolve(strict=True)
        return {
            "path": str(path),
            "sha256": sha256(path.read_bytes()).hexdigest(),
            "module_code": _active_module_code(path),
        }
    except (OSError, TypeError, ValueError):
        return None


def _referenced_names(code: CodeType) -> set[str]:
    names = set(code.co_names)
    for value in code.co_consts:
        if isinstance(value, CodeType):
            names.update(_referenced_names(value))
    return names


def _code_binding(code: CodeType) -> dict[str, Any]:
    def constant(value):
        if isinstance(value, CodeType):
            return _code_binding(value)
        if value is None or type(value) in (str, int, float, bool, bytes):
            return repr(value)
        return f"<{type(value).__module__}:{type(value).__qualname__}>"

    return {
        "code": code.co_code.hex(),
        "names": list(code.co_names),
        "constants": [constant(value) for value in code.co_consts],
    }


def _value_binding(value: Any) -> Any:
    """Describe only directly owned callable code; never traverse object graphs."""
    target = (
        value
        if isinstance(value, ModuleType)
        else inspect.unwrap(getattr(value, "fn", value))
    )
    if inspect.isfunction(target):
        return _code_binding(target.__code__)
    if isinstance(target, ModuleType):
        members = {}
        for name, member in vars(target).items():
            if not (inspect.isfunction(member) or isinstance(member, type)):
                continue
            candidate = inspect.unwrap(member)
            if candidate.__module__ != target.__name__:
                continue
            binding = _value_binding(candidate)
            if binding is not None:
                members[name] = binding
        return members
    if not isinstance(target, type):
        return None
    methods = {}
    for name, member in vars(target).items():
        candidates = ()
        if inspect.isfunction(member):
            candidates = (member,)
        elif isinstance(member, (staticmethod, classmethod)):
            candidates = (member.__func__,)
        elif isinstance(member, property):
            candidates = tuple(
                fn for fn in (member.fget, member.fset, member.fdel) if fn is not None
            )
        for index, function in enumerate(candidates):
            methods[f"{name}:{index}"] = _code_binding(function.__code__)
    return methods


def capture_orchestration_sources(definition: Any) -> dict[str, Any] | None:
    """Capture complete, bounded modules that define owned orchestration values."""
    try:
        target = inspect.unwrap(getattr(definition, "fn", definition))
        raw = inspect.getsourcefile(target)
        if raw is None:
            return None
        source = Path(raw).resolve(strict=True)
        package = (
            (source.parent / "__init__.py").is_file()
            or (source.parent / "workflow.toml").is_file()
            or source.name in {"workflow.py", "flow.py"}
        )
        boundary = source.parent if package else source
        values = []
        seen_values = set()

        def enqueue(label: str, value: Any) -> None:
            if (
                isinstance(value, ModuleType)
                or inspect.isfunction(value)
                or isinstance(value, type)
            ):
                candidate = inspect.unwrap(value)
            elif (
                type(value).__module__ == "botpipe.runtime"
                and type(value).__name__ == "Workflow"
            ):
                candidate = inspect.unwrap(value.fn)
            else:
                return
            if not (
                inspect.isfunction(candidate)
                or isinstance(candidate, type)
                or isinstance(candidate, ModuleType)
            ):
                return
            try:
                raw_path = inspect.getsourcefile(candidate)
                if raw_path is None:
                    return
                path = Path(raw_path).resolve(strict=True)
            except (OSError, TypeError, ValueError):
                return
            owned = (
                path == boundary
                if boundary.is_file()
                else path.is_relative_to(boundary)
            )
            if not owned or path.suffix != ".py" or path.is_symlink():
                return
            identity = id(candidate)
            if identity in seen_values:
                return
            seen_values.add(identity)
            values.append((label, candidate, path))

        def enqueue_contracts(annotation: Any, label: str) -> None:
            from .codec import preflight_types

            try:
                contracts = preflight_types(annotation, path=f"$.source.{label}")
            except (AttributeError, NameError, TypeError, ValueError):
                return
            for index, contract in enumerate(contracts):
                enqueue(f"{label}[{index}]", contract)

        enqueue("<workflow>", target)
        index = 0
        while index < len(values):
            label, value, _ = values[index]
            index += 1
            if inspect.isfunction(value):
                namespace = value.__globals__
                for name in sorted(_referenced_names(value.__code__)):
                    enqueue(f"{label}.{name}", namespace.get(name))
                try:
                    annotations = get_type_hints(value)
                except (NameError, TypeError, ValueError):
                    annotations = value.__annotations__
                for name, annotation in annotations.items():
                    enqueue_contracts(annotation, f"{label}.annotation:{name}")
            elif isinstance(value, ModuleType):
                for name, member in vars(value).items():
                    if (
                        inspect.isfunction(member)
                        or isinstance(member, type)
                        or isinstance(member, ModuleType)
                    ):
                        enqueue(f"{label}.{name}", member)
            else:
                enqueue_contracts(value, f"{label}.contract")
                for name, member in vars(value).items():
                    methods = ()
                    if inspect.isfunction(member):
                        methods = (member,)
                    elif isinstance(member, (staticmethod, classmethod)):
                        methods = (member.__func__,)
                    elif isinstance(member, property):
                        methods = tuple(
                            method
                            for method in (member.fget, member.fset, member.fdel)
                            if method is not None
                        )
                    for method_index, method in enumerate(methods):
                        enqueue(f"{label}.{name}:{method_index}", method)
        files = {}
        bindings = {}
        for name, value, path in values:
            relative = (
                path.name
                if boundary.is_file()
                else path.relative_to(boundary).as_posix()
            )
            files[relative] = sha256(path.read_bytes()).hexdigest()
            binding = _value_binding(value)
            if binding is not None:
                bindings[name] = binding
        if not files:
            return None
        return {
            "schema": "botpipe.orchestration-sources.v1",
            "files": dict(sorted(files.items())),
            "bindings": dict(sorted(bindings.items())),
        }
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def _verify_loaded_source(definition: Any) -> None:
    captured = getattr(definition, "_source_identity_at_definition", None)
    current = capture_definition_sources(definition)
    if (
        captured is None
        or current is None
        or any(captured[key] != current[key] for key in ("path", "sha256"))
    ):
        raise ValueError("workflow source changed after its definition was loaded")
    target = inspect.unwrap(definition.fn)
    source = Path(current["path"])
    compiled = compile(source.read_bytes(), str(source), "exec", dont_inherit=True)
    # A valid timestamp-based pyc can contain stale module constants even when
    # this function's bytecode is unchanged. Bind the whole executed module too.
    # Late definitions without an observable module frame stay unverified.
    if captured.get("module_code") != compiled:
        raise ValueError("loaded workflow code does not match current module source")

    def matching_codes(code: CodeType):
        for value in code.co_consts:
            if isinstance(value, CodeType):
                if value.co_qualname == target.__qualname__:
                    yield value
                yield from matching_codes(value)

    matches = list(matching_codes(compiled))
    # Do not execute source to resolve dynamic definitions or decorators. Ambiguous
    # definitions and transformed bytecode cannot support verified source evidence.
    if len(matches) != 1 or matches[0] != target.__code__:
        raise ValueError("loaded workflow code does not match its current source")


def capture_workflow_provenance(
    definition: Any, workspace: str | Path
) -> dict[str, Any]:
    """Observe the current editable surface; unavailable identity stays explicit."""
    try:
        _verify_loaded_source(definition)
        manifest = derive_workflow_surface_manifest(Path(workspace), definition)
        confirmed = derive_workflow_surface_manifest(Path(workspace), definition)
        _verify_loaded_source(definition)
        if confirmed["surface_id"] != manifest["surface_id"]:
            raise ValueError("workflow surface changed during provenance capture")
        return {
            "schema": "botpipe.workflow-provenance.v1",
            "verified": True,
            "workflow_identity": canonical_workflow_identity(manifest["boundary"]),
            "surface_id": manifest["surface_id"],
            "orchestration_id": definition.fingerprint,
            "surface_manifest": manifest,
        }
    except (OSError, SyntaxError, TypeError, ValueError) as exc:
        return {
            "schema": "botpipe.workflow-provenance.v1",
            "verified": False,
            "workflow_identity": None,
            "surface_id": None,
            "orchestration_id": getattr(definition, "fingerprint", None),
            "error": f"{type(exc).__name__}: {exc}",
        }


__all__ = [
    "capture_definition_sources",
    "capture_orchestration_sources",
    "capture_workflow_provenance",
]
