"""Workflow discovery and reference resolution.

Discovery is deliberately about Python callables, not a compiled graph.  A
workflow may branch, loop, or call another workflow at runtime, so the catalog
only describes the callable that can be invoked and the contract visible from
its signature.
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import importlib.util
import inspect
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Iterator, Mapping, get_type_hints

import tomllib


class WorkflowDiscoveryError(LookupError):
    """Raised when a workflow reference cannot be resolved unambiguously."""


class WorkflowInputError(ValueError):
    """Raised when arguments do not satisfy a workflow's Python contract."""


@dataclass(frozen=True, slots=True)
class WorkflowEntry:
    name: str
    reference: str
    source_kind: str
    source_path: Path
    module: str | None = None
    function: str | None = None
    version: str | None = None
    description: str | None = None
    title: str | None = None
    aliases: tuple[str, ...] = ()
    manifest_path: Path | None = None

    @property
    def workflow_name(self) -> str:
        """Descriptive alias useful to catalog consumers."""
        return self.name

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "reference": self.reference,
            "source_kind": self.source_kind,
            "source_path": str(self.source_path),
            "module": self.module,
            "function": self.function,
            "version": self.version,
            "description": self.description,
            "title": self.title,
            "aliases": list(self.aliases),
            "manifest_path": str(self.manifest_path) if self.manifest_path else None,
        }


@dataclass(frozen=True, slots=True)
class BoundInputs:
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


def discover_workflows(
    workspace: str | Path = ".", *, include_labs: bool = True
) -> tuple[WorkflowEntry, ...]:
    """Return the effective workflow catalog.

    Workspace workflows shadow lab and packaged workflows with the same name.
    Listing parses Python and TOML metadata without importing workflow modules.
    """

    root = Path(workspace).expanduser().resolve()
    search_roots: list[tuple[str, Path, str | None]] = [
        ("workspace", root / ".botpipe" / "workflows", None),
    ]
    if include_labs:
        search_roots.extend(
            [
                ("labs", root / "labs" / "workflows", "labs.workflows"),
                (
                    "labs",
                    Path(__file__).resolve().parent.parent / "labs" / "workflows",
                    "labs.workflows",
                ),
            ]
        )
    package_root = Path(__file__).resolve().parent / "workflows"
    search_roots.append(("packaged", package_root, "botpipe.workflows"))

    effective: dict[str, WorkflowEntry] = {}
    for kind, directory, module_prefix in search_roots:
        if not directory.is_dir():
            continue
        for entry in _scan_root(directory, kind=kind, module_prefix=module_prefix):
            effective.setdefault(entry.name, entry)
    return tuple(
        sorted(effective.values(), key=lambda item: (item.name, item.reference))
    )


def resolve_workflow(
    reference: str | Callable[..., Any], workspace: str | Path = "."
) -> Callable[..., Any]:
    """Resolve a callable, catalog name, ``module:function``, or ``file.py:function``."""

    if callable(reference):
        return reference
    if not isinstance(reference, str) or not reference.strip():
        raise WorkflowDiscoveryError(
            "workflow reference must be a callable or non-empty string"
        )
    value = reference.strip()
    root = Path(workspace).expanduser().resolve()

    if ":" in value:
        location, function_name = value.rsplit(":", 1)
        if not function_name:
            raise WorkflowDiscoveryError(
                f"workflow reference {value!r} is missing a function name"
            )
        candidate = Path(location).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        if candidate.suffix == ".py" or candidate.exists():
            module = _load_file_module(candidate.resolve())
        else:
            module = _import_module(location, root)
        return _workflow_attr(module, function_name, value)

    path_candidate = Path(value).expanduser()
    if not path_candidate.is_absolute():
        path_candidate = root / path_candidate
    if path_candidate.suffix == ".py" or path_candidate.is_file():
        module = _load_file_module(path_candidate.resolve())
        return _single_workflow(module, value)

    matches = [
        entry
        for entry in discover_workflows(root)
        if entry.name == value or value in entry.aliases
    ]
    if not matches:
        raise WorkflowDiscoveryError(
            f"workflow {value!r} was not found; use a catalog name, module:function, or file.py:function"
        )
    if len(matches) > 1:
        refs = ", ".join(entry.reference for entry in matches)
        raise WorkflowDiscoveryError(f"workflow {value!r} is ambiguous: {refs}")
    return resolve_workflow(matches[0].reference, root)


def validate_workflow_inputs(
    workflow: Callable[..., Any],
    args: tuple[Any, ...] = (),
    kwargs: Mapping[str, Any] | None = None,
) -> BoundInputs:
    """Bind and type-check invocation values using the callable's annotations."""

    supplied_kwargs = dict(kwargs or {})
    signature = inspect.signature(workflow)
    try:
        bound = signature.bind(*args, **supplied_kwargs)
    except TypeError as exc:
        raise WorkflowInputError(str(exc)) from exc
    bound.apply_defaults()
    try:
        hints = get_type_hints(workflow)
    except Exception:
        hints = dict(getattr(workflow, "__annotations__", {}))

    for name, value in tuple(bound.arguments.items()):
        parameter = signature.parameters[name]
        if parameter.kind in {
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }:
            continue
        annotation = hints.get(name, inspect.Parameter.empty)
        if annotation is inspect.Parameter.empty:
            continue
        try:
            from pydantic import TypeAdapter, ValidationError

            bound.arguments[name] = TypeAdapter(annotation).validate_python(value)
        except ImportError:  # pragma: no cover - pydantic is a package dependency
            continue
        except ValidationError as exc:
            raise WorkflowInputError(f"invalid input {name!r}: {exc}") from exc
    return BoundInputs(tuple(bound.args), dict(bound.kwargs))


def workflow_contract(
    reference: str | Callable[..., Any], workspace: str | Path = "."
) -> dict[str, Any]:
    workflow = resolve_workflow(reference, workspace)
    signature = inspect.signature(workflow)
    try:
        hints = get_type_hints(workflow)
    except Exception:
        hints = dict(getattr(workflow, "__annotations__", {}))
    parameters: list[dict[str, Any]] = []
    for parameter in signature.parameters.values():
        annotation = hints.get(parameter.name, parameter.annotation)
        parameters.append(
            {
                "name": parameter.name,
                "kind": parameter.kind.name.lower(),
                "required": parameter.default is inspect.Parameter.empty
                and parameter.kind
                not in {
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                },
                "default": None
                if parameter.default is inspect.Parameter.empty
                else _json_safe(parameter.default),
                "annotation": _annotation_name(annotation),
                "schema": _type_schema(annotation),
            }
        )
    return_annotation = hints.get("return", signature.return_annotation)
    return {
        "parameters": parameters,
        "return": {
            "annotation": _annotation_name(return_annotation),
            "schema": _type_schema(return_annotation),
        },
    }


def _scan_root(
    directory: Path, *, kind: str, module_prefix: str | None
) -> Iterator[WorkflowEntry]:
    seen_paths: set[Path] = set()
    for manifest in sorted(directory.glob("*/workflow.toml")):
        package_dir = manifest.parent
        metadata = _read_manifest(manifest)
        name = str(metadata.get("name") or package_dir.name)
        source = _default_source(package_dir)
        if source is None:
            continue
        functions = _decorated_functions(source)
        function = str(
            metadata.get("function") or metadata.get("entrypoint") or ""
        ) or (next(iter(functions)) if len(functions) == 1 else "workflow")
        declaration = functions.get(function, {})
        module = (
            f"{module_prefix}.{package_dir.name}.{source.stem}"
            if module_prefix
            else None
        )
        reference = f"{module}:{function}" if module else f"{source}:{function}"
        yield WorkflowEntry(
            name=name,
            reference=reference,
            source_kind=kind,
            source_path=source.resolve(),
            module=module,
            function=function,
            version=_optional_text(
                metadata.get("version") or declaration.get("version")
            ),
            description=_optional_text(
                metadata.get("description") or declaration.get("description")
            ),
            title=_optional_text(metadata.get("title")),
            aliases=_string_tuple(metadata.get("aliases")),
            manifest_path=manifest.resolve(),
        )
        seen_paths.add(source.resolve())

    for source in sorted(directory.rglob("*.py")):
        if (
            source.name == "__init__.py"
            or source.resolve() in seen_paths
            or "__pycache__" in source.parts
        ):
            continue
        functions = _decorated_functions(source)
        for function, declared in functions.items():
            relative = source.relative_to(directory).with_suffix("")
            module = (
                ".".join((module_prefix, *relative.parts)) if module_prefix else None
            )
            reference = f"{module}:{function}" if module else f"{source}:{function}"
            yield WorkflowEntry(
                name=declared.get("name") or function,
                reference=reference,
                source_kind=kind,
                source_path=source.resolve(),
                module=module,
                function=function,
                version=declared.get("version"),
                description=declared.get("description"),
            )


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise WorkflowDiscoveryError(
            f"invalid workflow manifest {path}: {exc}"
        ) from exc
    workflow = payload.get("workflow")
    if isinstance(workflow, dict):
        return {**payload, **workflow}
    return payload


def _default_source(package_dir: Path) -> Path | None:
    for name in ("workflow.py", "flow.py", "__init__.py"):
        candidate = package_dir / name
        if candidate.is_file():
            return candidate
    return None


def _decorated_functions(path: Path) -> dict[str, dict[str, str | None]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return {}
    found: dict[str, dict[str, str | None]] = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            decorator_name = (
                target.attr
                if isinstance(target, ast.Attribute)
                else (target.id if isinstance(target, ast.Name) else None)
            )
            if decorator_name != "workflow":
                continue
            values: dict[str, str | None] = {
                "name": node.name,
                "version": None,
                "description": ast.get_docstring(node),
            }
            if isinstance(decorator, ast.Call):
                for keyword in decorator.keywords:
                    if keyword.arg in {"name", "version"} and isinstance(
                        keyword.value, ast.Constant
                    ):
                        values[keyword.arg] = str(keyword.value.value)
            found[node.name] = values
            break
    return found


def _import_module(name: str, workspace: Path) -> ModuleType:
    candidates = (workspace, workspace / ".botpipe" / "workflows")
    with _python_paths(candidates):
        try:
            module = importlib.import_module(name)
            for root in candidates:
                local = root.joinpath(*name.split("."))
                expected = next(
                    (
                        path
                        for path in (local / "__init__.py", local.with_suffix(".py"))
                        if path.is_file()
                    ),
                    None,
                )
                if expected is not None:
                    origin = getattr(module, "__file__", None)
                    if origin is None or Path(origin).resolve() != expected.resolve():
                        raise ImportError(
                            f"module {name!r} is already imported from another location; "
                            "use a separate Python process for this workspace"
                        )
                    break
            return module
        except Exception as exc:
            raise WorkflowDiscoveryError(
                f"could not import workflow module {name!r}: {exc}"
            ) from exc


def _load_file_module(path: Path) -> ModuleType:
    if not path.is_file():
        raise WorkflowDiscoveryError(f"workflow file does not exist: {path}")
    module_name, import_root = _module_name_for_file(path)
    with _python_paths((import_root, path.parent)):
        try:
            if module_name:
                module = importlib.import_module(module_name)
                origin = getattr(module, "__file__", None)
                if origin is None or Path(origin).resolve() != path.resolve():
                    raise ImportError(
                        f"module {module_name!r} is already imported from another location; "
                        "use a separate Python process for this workflow file"
                    )
                return module
            unique = hashlib.sha256(str(path).encode()).hexdigest()[:16]
            spec = importlib.util.spec_from_file_location(
                f"_botpipe_workflow_{unique}", path
            )
            if spec is None or spec.loader is None:
                raise ImportError("Python could not create a module specification")
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            return module
        except Exception as exc:
            raise WorkflowDiscoveryError(
                f"could not import workflow file {path}: {exc}"
            ) from exc


def _module_name_for_file(path: Path) -> tuple[str | None, Path]:
    parts = [path.stem]
    parent = path.parent
    while (parent / "__init__.py").is_file():
        parts.append(parent.name)
        parent = parent.parent
    if len(parts) == 1:
        return None, path.parent
    return ".".join(reversed(parts)), parent


@contextmanager
def _python_paths(paths: tuple[Path, ...] | list[Path]) -> Iterator[None]:
    inserted: list[str] = []
    for path in reversed(paths):
        value = str(path)
        if path.is_dir() and value not in sys.path:
            sys.path.insert(0, value)
            inserted.append(value)
    try:
        yield
    finally:
        for value in inserted:
            try:
                sys.path.remove(value)
            except ValueError:
                pass


def _workflow_attr(module: ModuleType, name: str, reference: str) -> Callable[..., Any]:
    try:
        value = getattr(module, name)
    except AttributeError as exc:
        raise WorkflowDiscoveryError(
            f"workflow reference {reference!r} has no callable {name!r}"
        ) from exc
    if not callable(value):
        raise WorkflowDiscoveryError(
            f"workflow reference {reference!r} does not name a callable"
        )
    return value


def _single_workflow(module: ModuleType, reference: str) -> Callable[..., Any]:
    candidates = [
        value
        for _, value in inspect.getmembers(module, callable)
        if getattr(value, "__module__", None) == module.__name__ and _is_workflow(value)
    ]
    if len(candidates) == 1:
        return candidates[0]
    for conventional in ("workflow", "main", "run"):
        value = getattr(module, conventional, None)
        if callable(value):
            return value
    if not candidates:
        raise WorkflowDiscoveryError(
            f"{reference!r} contains no decorated workflow; add :function"
        )
    raise WorkflowDiscoveryError(
        f"{reference!r} contains multiple workflows; add :function"
    )


def _is_workflow(value: Any) -> bool:
    if any(
        bool(getattr(value, marker, False))
        for marker in ("__botpipe_workflow__", "_botpipe_workflow", "__workflow__")
    ):
        return True
    return (
        callable(value)
        and callable(getattr(value, "fn", None))
        and hasattr(value, "version")
    )


def _type_schema(annotation: Any) -> dict[str, Any] | None:
    if annotation is inspect.Parameter.empty:
        return None
    try:
        from pydantic import TypeAdapter

        return TypeAdapter(annotation).json_schema()
    except Exception:
        return None


def _annotation_name(annotation: Any) -> str | None:
    if annotation is inspect.Parameter.empty:
        return None
    return (
        getattr(annotation, "__qualname__", None)
        or getattr(annotation, "__name__", None)
        or str(annotation)
    )


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    return repr(value)


def _optional_text(value: Any) -> str | None:
    return str(value) if value is not None else None


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    return ()


__all__ = [
    "BoundInputs",
    "WorkflowDiscoveryError",
    "WorkflowEntry",
    "WorkflowInputError",
    "discover_workflows",
    "resolve_workflow",
    "validate_workflow_inputs",
    "workflow_contract",
]
