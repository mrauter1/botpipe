"""Recorded source identity for honest comparisons between durable workflow runs."""

from __future__ import annotations

import inspect
import os
from dataclasses import dataclass
from functools import partial
from hashlib import sha256
from pathlib import Path
from types import CodeType, ModuleType
from typing import Any, get_type_hints

from pydantic.errors import PydanticSchemaGenerationError

from ._callables import (
    CallableGraph,
    _canonical_source_path,
    _is_sdk_implementation,
    _is_workflow,
    describe_callable,
)
from ._code_identity import code_identity as _code_binding
from .surface_identity import (
    canonical_workflow_identity,
    derive_workflow_surface_manifest,
)


@dataclass(frozen=True)
class SourceContext:
    """The source origin and bounded ownership projected from one callable graph."""

    origin_target: Any | None
    origin_source: Path | None
    origin_boundary: Path | None
    owned_boundaries: tuple[Path, ...]


class SourceCaptureError(TypeError):
    """An owned Python source was identified but could not be captured."""


def _identified_source_path(target: Any) -> Path | None:
    if target is None:
        return None
    try:
        raw = inspect.getsourcefile(target)
        if raw is None:
            raw = inspect.getfile(target)
    except (TypeError, ValueError):
        return None
    if raw is None or (raw.startswith("<") and raw.endswith(">")):
        return None
    candidate = Path(raw)
    return candidate if candidate.suffix == ".py" else None


def _boundary_for_source(source: Path) -> Path:
    package = (
        (source.parent / "__init__.py").is_file()
        or (source.parent / "workflow.toml").is_file()
        or source.name in {"workflow.py", "flow.py"}
    )
    return source.parent if package else source


def source_context(
    definition: Any, *, graph: CallableGraph | None = None
) -> SourceContext:
    """Project source origin and ownership once from a callable graph."""

    descriptor = graph or describe_callable(definition)
    locations: dict[Path, tuple[Path | None, Path | None]] = {}

    def location(target: Any) -> tuple[Path | None, Path | None]:
        candidate = _identified_source_path(target)
        if candidate is None:
            return None, None
        if candidate not in locations:
            source = _canonical_source_path(candidate)
            locations[candidate] = (
                (None, None)
                if _is_sdk_implementation(source)
                else (source, _boundary_for_source(source))
            )
        return locations[candidate]

    origin_target = descriptor.origin_target
    origin_source, origin_boundary = location(origin_target)
    owned: list[Path] = []
    for target in descriptor.boundary_targets:
        _, boundary = location(target)
        if boundary is None:
            continue
        if boundary not in owned:
            owned.append(boundary)
    owned_boundaries = tuple(owned)
    return SourceContext(
        origin_target=origin_target,
        origin_source=origin_source,
        origin_boundary=origin_boundary,
        owned_boundaries=owned_boundaries,
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


def capture_definition_sources(
    definition: Any,
    *,
    graph: CallableGraph | None = None,
    context: SourceContext | None = None,
) -> dict[str, Any] | None:
    """Remember source bytes at definition time without importing or walking packages."""
    descriptor = graph or describe_callable(definition)
    projected = context or source_context(definition, graph=descriptor)
    path = projected.origin_source
    if path is None:
        return None
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise SourceCaptureError(f"Cannot read owned Python source {path}") from exc
    return {
        "path": str(path),
        "sha256": sha256(content).hexdigest(),
        "module_code": _active_module_code(path),
    }


def _referenced_names(code: CodeType) -> set[str]:
    names = set(code.co_names)
    for value in code.co_consts:
        if isinstance(value, CodeType):
            names.update(_referenced_names(value))
    return names


def _value_binding(value: Any) -> Any:
    """Describe only directly owned callable code; never traverse object graphs."""
    target = value
    if inspect.isfunction(target):
        return _code_binding(target.__code__)
    if isinstance(target, ModuleType):
        members = {}
        for name, member in vars(target).items():
            if not (inspect.isfunction(member) or isinstance(member, type)):
                continue
            candidate = member
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


def source_boundary(
    definition: Any,
    *,
    graph: CallableGraph | None = None,
    context: SourceContext | None = None,
) -> Path | None:
    """Return the bounded ownership root without making it source identity."""
    descriptor = graph or describe_callable(definition)
    projected = context or source_context(definition, graph=descriptor)
    return projected.origin_boundary


def capture_orchestration_sources(
    definition: Any,
    *,
    boundary: str | Path | None = None,
    graph: CallableGraph | None = None,
    context: SourceContext | None = None,
) -> dict[str, Any] | None:
    """Capture complete, bounded modules that define owned orchestration values."""
    descriptor = graph or describe_callable(definition)
    projected = context or source_context(definition, graph=descriptor)
    descriptor_targets = descriptor.source_targets
    if not descriptor_targets:
        return None
    union_boundary = boundary is None or isinstance(boundary, (tuple, list))
    raw_boundaries = (
        projected.owned_boundaries
        if boundary is None
        else (boundary if isinstance(boundary, (tuple, list)) else (boundary,))
    )
    try:
        boundary_paths = tuple(
            _canonical_source_path(item, strict=True) for item in raw_boundaries
        )
    except (OSError, ValueError) as exc:
        raise SourceCaptureError("Cannot resolve owned source boundary") from exc
    if not boundary_paths:
        return None
    boundary_path = boundary_paths[0]
    anchor = Path(
        os.path.commonpath(
            [str(item if item.is_dir() else item.parent) for item in boundary_paths]
        )
    )
    values: list[tuple[str, Any, Path]] = []
    traversal_values: list[tuple[str, Any]] = []
    seen_values: set[int] = set()
    seen_traversal: set[int] = set()
    source_paths: dict[int, tuple[Any, Path | None]] = {}
    dependency_targets: dict[int, tuple[Any, tuple[Any, ...]]] = {}
    resolving_dependencies: set[int] = set()
    required_targets = {id(target): target for target in descriptor_targets}

    def resolved_source(candidate: Any) -> Path | None:
        cached = source_paths.get(id(candidate))
        if cached is not None and cached[0] is candidate:
            return cached[1]
        source_candidate = _identified_source_path(candidate)
        if source_candidate is None:
            path = None
        else:
            try:
                path = _canonical_source_path(source_candidate, strict=True)
            except OSError as exc:
                unresolved = _canonical_source_path(source_candidate)
                required = required_targets.get(id(candidate)) is candidate
                if unresolved.suffix == ".py" and (required or is_owned(unresolved)):
                    raise SourceCaptureError(
                        f"Cannot resolve owned Python source {unresolved}"
                    ) from exc
                path = None
        source_paths[id(candidate)] = (candidate, path)
        return path

    def callable_source_targets(value: Any) -> tuple[Any, ...]:
        marker = id(value)
        cached = dependency_targets.get(marker)
        if cached is not None and cached[0] is value:
            return cached[1]
        if marker in resolving_dependencies:
            return ()
        resolving_dependencies.add(marker)
        targets: list[Any] = []
        seen_targets: set[int] = set()

        def include(candidate: Any) -> None:
            for target in callable_source_targets(candidate):
                target_marker = id(target)
                if target_marker not in seen_targets:
                    seen_targets.add(target_marker)
                    targets.append(target)

        try:
            if _is_workflow(value):
                include(vars(value)["fn"])
            elif isinstance(value, partial):
                include(value.func)
                for bound in value.args:
                    if callable(bound):
                        include(bound)
                for bound in (value.keywords or {}).values():
                    if callable(bound):
                        include(bound)
            elif inspect.ismethod(value):
                include(value.__func__)
                owner = (
                    value.__self__
                    if isinstance(value.__self__, type)
                    else type(value.__self__)
                )
                include(owner)
            elif inspect.isfunction(value):
                seen_targets.add(marker)
                targets.append(value)
                wrapped = vars(value).get("__wrapped__")
                if callable(wrapped):
                    include(wrapped)
            elif isinstance(value, (type, ModuleType)):
                seen_targets.add(marker)
                targets.append(value)
            elif callable(value) and not inspect.isbuiltin(value):
                include(type(value))
        finally:
            resolving_dependencies.remove(marker)
        result = tuple(targets)
        dependency_targets[marker] = (value, result)
        return result

    def is_owned(path: Path) -> bool:
        return any(
            path == item if item.is_file() else path.is_relative_to(item)
            for item in boundary_paths
        )

    def enqueue(label: str, value: Any) -> None:
        if isinstance(value, (ModuleType, type)):
            candidates = (value,)
        elif callable(value):
            candidates = callable_source_targets(value)
        else:
            return
        for target_index, candidate in enumerate(candidates):
            if not (
                inspect.isfunction(candidate)
                or isinstance(candidate, (type, ModuleType))
            ):
                continue
            target_label = (
                label if len(candidates) == 1 else f"{label}.callable:{target_index}"
            )
            path = resolved_source(candidate)
            if path is None:
                identity = id(candidate)
                if (
                    not isinstance(candidate, ModuleType)
                    and identity not in seen_traversal
                ):
                    seen_traversal.add(identity)
                    traversal_values.append((target_label, candidate))
                continue
            if not is_owned(path) or path.suffix != ".py" or path.is_symlink():
                continue
            identity = id(candidate)
            if identity not in seen_traversal:
                seen_traversal.add(identity)
                traversal_values.append((target_label, candidate))
            if identity in seen_values:
                continue
            seen_values.add(identity)
            values.append((target_label, candidate, path))

    def enqueue_contracts(annotation: Any, label: str) -> None:
        from .codec import preflight_types

        try:
            contracts = preflight_types(annotation, path=f"$.source.{label}")
        except (
            AttributeError,
            NameError,
            PydanticSchemaGenerationError,
            TypeError,
            ValueError,
        ):
            return
        for index, contract in enumerate(contracts):
            enqueue(f"{label}[{index}]", contract)

    ordered_targets: list[Any] = []
    if projected.origin_target is not None:
        ordered_targets.append(projected.origin_target)
    ordered_targets.extend(
        target for target in descriptor_targets if target is not projected.origin_target
    )
    for target_index, callable_target in enumerate(ordered_targets):
        label = (
            "<workflow>" if target_index == 0 else f"<workflow>.callable:{target_index}"
        )
        enqueue(label, callable_target)
    index = 0
    while index < len(traversal_values):
        label, value = traversal_values[index]
        index += 1
        if inspect.isfunction(value):
            namespace = value.__globals__
            for name in sorted(_referenced_names(value.__code__)):
                enqueue(f"{label}.{name}", namespace.get(name))
            try:
                annotations = get_type_hints(value, globalns=namespace)
            except (NameError, TypeError, ValueError):
                annotations = value.__annotations__
            for name, annotation in annotations.items():
                enqueue_contracts(annotation, f"{label}.annotation:{name}")
        elif isinstance(value, ModuleType):
            for name, member in vars(value).items():
                if (
                    inspect.isfunction(member)
                    or isinstance(member, (type, ModuleType))
                    or callable(member)
                ):
                    enqueue(f"{label}.{name}", member)
        else:
            enqueue_contracts(value, f"{label}.contract")
            for mro_index, base in enumerate(value.__mro__[1:]):
                if base is not object:
                    enqueue(f"{label}.mro:{mro_index}", base)
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
    files: dict[str, str] = {}
    bindings: dict[str, Any] = {}
    digests: dict[Path, str] = {}
    for name, value, path in values:
        relative = (
            path.relative_to(anchor).as_posix()
            if union_boundary
            else (
                path.name
                if boundary_path.is_file()
                else path.relative_to(boundary_path).as_posix()
            )
        )
        if path not in digests:
            try:
                content = path.read_bytes()
            except OSError as exc:
                raise SourceCaptureError(
                    f"Cannot read owned Python source {path}"
                ) from exc
            digests[path] = sha256(content).hexdigest()
        files.setdefault(relative, digests[path])
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


def _verify_loaded_source(definition: Any) -> None:
    captured = getattr(definition, "_source_identity_at_definition", None)
    descriptor = describe_callable(definition)
    context = source_context(definition, graph=descriptor)
    current = capture_definition_sources(definition, graph=descriptor, context=context)
    if (
        captured is None
        or current is None
        or any(captured[key] != current[key] for key in ("path", "sha256"))
    ):
        raise ValueError("workflow source changed after its definition was loaded")
    target = context.origin_target
    if not inspect.isfunction(target):
        raise ValueError("workflow source origin is not a Python function")
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
    """Observe compact source identity; unavailable identity stays explicit."""
    try:
        manifest = capture_workflow_surface_manifest(definition, workspace)
        return {
            "schema": "botpipe.workflow-provenance.v1",
            "verified": True,
            "workflow_identity": canonical_workflow_identity(manifest["boundary"]),
            "surface_id": manifest["surface_id"],
            "orchestration_id": definition.fingerprint,
        }
    except Exception as exc:  # noqa: BLE001 - observation cannot block execution
        return {
            "schema": "botpipe.workflow-provenance.v1",
            "verified": False,
            "workflow_identity": None,
            "surface_id": None,
            "orchestration_id": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def capture_workflow_surface_manifest(
    definition: Any, workspace: str | Path
) -> dict[str, Any]:
    """Capture a full verified surface manifest for an explicit consumer."""

    _verify_loaded_source(definition)
    manifest = derive_workflow_surface_manifest(Path(workspace), definition)
    confirmed = derive_workflow_surface_manifest(Path(workspace), definition)
    _verify_loaded_source(definition)
    if confirmed["surface_id"] != manifest["surface_id"]:
        raise ValueError("workflow surface changed during provenance capture")
    return manifest


__all__ = [
    "SourceCaptureError",
    "SourceContext",
    "capture_definition_sources",
    "capture_orchestration_sources",
    "capture_workflow_provenance",
    "capture_workflow_surface_manifest",
    "source_boundary",
    "source_context",
]
