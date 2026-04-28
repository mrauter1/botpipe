"""Pure workflow catalog discovery for portfolio-style authoring and runtime helpers."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


_WORKFLOW_MANIFEST_FIELDS = frozenset({"aliases", "description", "name", "title"})

AuthoringShape = Literal["single_file", "flow_package", "workflow_package", "manifest_package", "unknown"]


class WorkflowCatalogManifestError(ValueError):
    """Raised when workflow catalog manifest metadata is invalid."""


class WorkflowCatalogDiscoveryError(LookupError):
    """Raised when workflow catalog discovery cannot enumerate workflows."""


@dataclass(frozen=True, slots=True)
class WorkflowCatalogEntry:
    """Pure filesystem metadata for one discovered workflow."""

    package_name: str
    workflow_name: str
    title: str | None
    description: str | None
    aliases: tuple[str, ...]
    package_dir: Path
    manifest_path: Path | None
    workflow_path: Path
    params_path: Path | None
    doc_path: Path | None
    authoring_shape: AuthoringShape
    source_path: Path
    flow_path: Path | None
    legacy_workflow_path: Path | None
    package_init_path: Path | None
    package_module: str | None
    workflow_module: str | None
    spec_paths: tuple[Path, ...] = ()
    prompt_paths: tuple[Path, ...] = ()
    asset_paths: tuple[Path, ...] = ()
    doc_paths: tuple[Path, ...] = ()
    test_paths: tuple[Path, ...] = ()


def discover_workflow_catalog(root: str | Path) -> tuple[WorkflowCatalogEntry, ...]:
    """Discover workflow metadata plus optional support-file paths under ``<root>/workflows``."""

    root_path = Path(root).resolve()
    workflows_root = root_path / "workflows"
    if not workflows_root.exists():
        return ()
    if not workflows_root.is_dir():
        raise WorkflowCatalogDiscoveryError(f"workflow root {workflows_root} is not a directory")

    entries: list[WorkflowCatalogEntry] = []
    seen_sources: set[Path] = set()
    seen_names: dict[str, Path] = {}

    for manifest_path in sorted(workflows_root.glob("*/workflow.toml")):
        package_dir = manifest_path.parent.resolve()
        source_path = _preferred_workflow_source(package_dir)
        if source_path is None:
            raise WorkflowCatalogDiscoveryError(
                f"workflow manifest {manifest_path} requires flow.py or workflow.py in {package_dir}"
            )
        manifest = _read_workflow_manifest(manifest_path)
        entry = _build_entry(
            root_path,
            workflows_root,
            source_path,
            manifest_path=manifest_path.resolve(),
            workflow_name=manifest.get("name", package_dir.name),
            title=manifest.get("title"),
            description=manifest.get("description"),
            aliases=manifest.get("aliases", ()),
        )
        _register_entry(entries, entry, seen_sources=seen_sources, seen_names=seen_names)

    for flow_path in sorted(workflows_root.glob("*/flow.py")):
        entry = _build_entry(
            root_path,
            workflows_root,
            flow_path.resolve(),
            manifest_path=None,
            workflow_name=flow_path.parent.name,
            title=_default_title(flow_path.parent.name),
            description=None,
            aliases=(),
        )
        _register_entry(entries, entry, seen_sources=seen_sources, seen_names=seen_names)

    for legacy_path in sorted(workflows_root.glob("*/workflow.py")):
        if (legacy_path.parent / "flow.py").is_file():
            continue
        entry = _build_entry(
            root_path,
            workflows_root,
            legacy_path.resolve(),
            manifest_path=None,
            workflow_name=legacy_path.parent.name,
            title=_default_title(legacy_path.parent.name),
            description=None,
            aliases=(),
        )
        _register_entry(entries, entry, seen_sources=seen_sources, seen_names=seen_names)

    for source_path in sorted(workflows_root.glob("*.py")):
        if source_path.name == "__init__.py":
            continue
        entry = _build_entry(
            root_path,
            workflows_root,
            source_path.resolve(),
            manifest_path=None,
            workflow_name=source_path.stem,
            title=_default_title(source_path.stem),
            description=None,
            aliases=(),
        )
        _register_entry(entries, entry, seen_sources=seen_sources, seen_names=seen_names)

    return tuple(sorted(entries, key=lambda entry: (entry.workflow_name, str(entry.source_path))))


def _register_entry(
    entries: list[WorkflowCatalogEntry],
    entry: WorkflowCatalogEntry,
    *,
    seen_sources: set[Path],
    seen_names: dict[str, Path],
) -> None:
    source_path = entry.source_path.resolve()
    if source_path in seen_sources:
        return

    other_source = seen_names.get(entry.workflow_name)
    if other_source is not None:
        raise WorkflowCatalogDiscoveryError(
            f"duplicate workflow name {entry.workflow_name!r} in {source_path} and {other_source}"
        )
    seen_names[entry.workflow_name] = source_path

    seen_sources.add(source_path)
    entries.append(entry)


def _build_entry(
    root_path: Path,
    workflows_root: Path,
    source_path: Path,
    *,
    manifest_path: Path | None,
    workflow_name: str,
    title: str | None,
    description: str | None,
    aliases: tuple[str, ...],
) -> WorkflowCatalogEntry:
    package_dir = _package_dir_for_source(source_path)
    authoring_shape = _authoring_shape_for_source(source_path, manifest_path)
    package_name = _package_name_for_source(source_path)
    package_init_path = _package_init_path(source_path)
    package_module, workflow_module = _module_names_for_source(workflows_root, source_path, package_init_path)
    doc_paths = _discover_doc_paths(root_path, package_dir, package_name=package_name, workflow_name=workflow_name)
    test_paths = _discover_test_paths(root_path, package_dir, workflow_name=workflow_name)

    return WorkflowCatalogEntry(
        package_name=package_name,
        workflow_name=workflow_name,
        title=title,
        description=description,
        aliases=aliases,
        package_dir=package_dir,
        manifest_path=manifest_path,
        workflow_path=source_path,
        params_path=_params_path(source_path),
        doc_path=doc_paths[0] if doc_paths else None,
        authoring_shape=authoring_shape,
        source_path=source_path,
        flow_path=source_path if source_path.name == "flow.py" else None,
        legacy_workflow_path=source_path if source_path.name == "workflow.py" else None,
        package_init_path=package_init_path,
        package_module=package_module,
        workflow_module=workflow_module,
        spec_paths=_spec_paths(source_path),
        prompt_paths=_prompt_paths(source_path),
        asset_paths=_asset_paths(source_path),
        doc_paths=doc_paths,
        test_paths=test_paths,
    )


def _read_workflow_manifest(manifest_path: Path) -> dict[str, Any]:
    with manifest_path.open("rb") as handle:
        payload = tomllib.load(handle)
    if not isinstance(payload, dict):
        raise WorkflowCatalogManifestError(f"workflow manifest {manifest_path} must decode to a table")

    unknown_fields = sorted(set(payload) - _WORKFLOW_MANIFEST_FIELDS)
    if unknown_fields:
        names = ", ".join(unknown_fields)
        raise WorkflowCatalogManifestError(
            f"workflow manifest {manifest_path} declares unsupported fields: {names}. "
            "workflow.toml is metadata-only and may only define name, title, description, and aliases"
        )

    normalized: dict[str, Any] = {}
    for field in ("name", "title", "description"):
        value = payload.get(field)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            raise WorkflowCatalogManifestError(
                f"workflow manifest field {field!r} in {manifest_path} must be a non-empty string"
            )
        normalized[field] = value.strip()

    aliases = payload.get("aliases", ())
    if aliases in (None, ()):
        normalized["aliases"] = ()
        return normalized
    if not isinstance(aliases, list):
        raise WorkflowCatalogManifestError(f"workflow manifest field 'aliases' in {manifest_path} must be a list of strings")

    seen_aliases: set[str] = set()
    normalized_aliases: list[str] = []
    for alias in aliases:
        if not isinstance(alias, str) or not alias.strip():
            raise WorkflowCatalogManifestError(f"workflow manifest aliases in {manifest_path} must be non-empty strings")
        alias_text = alias.strip()
        if alias_text in seen_aliases:
            raise WorkflowCatalogManifestError(f"workflow manifest {manifest_path} repeats alias {alias_text!r}")
        seen_aliases.add(alias_text)
        normalized_aliases.append(alias_text)
    normalized["aliases"] = tuple(normalized_aliases)
    return normalized


def _preferred_workflow_source(package_dir: Path) -> Path | None:
    preferred = package_dir / "flow.py"
    if preferred.is_file():
        return preferred.resolve()
    legacy = package_dir / "workflow.py"
    if legacy.is_file():
        return legacy.resolve()
    return None


def _authoring_shape_for_source(source_path: Path, manifest_path: Path | None) -> AuthoringShape:
    if manifest_path is not None:
        return "manifest_package"
    if source_path.name == "flow.py":
        return "flow_package"
    if source_path.name == "workflow.py":
        return "workflow_package"
    if source_path.suffix == ".py":
        return "single_file"
    return "unknown"


def _package_dir_for_source(source_path: Path) -> Path:
    return source_path.parent.resolve()


def _package_name_for_source(source_path: Path) -> str:
    if source_path.name in {"flow.py", "workflow.py", "__init__.py"}:
        return source_path.parent.name
    return source_path.stem


def _package_init_path(source_path: Path) -> Path | None:
    if source_path.name not in {"flow.py", "workflow.py", "__init__.py"}:
        return None
    init_path = source_path.parent / "__init__.py"
    return init_path.resolve() if init_path.is_file() else None


def _module_names_for_source(
    workflows_root: Path,
    source_path: Path,
    package_init_path: Path | None,
) -> tuple[str | None, str | None]:
    workflows_init = workflows_root / "__init__.py"
    if not workflows_init.is_file():
        return None, None

    try:
        relative = source_path.resolve().relative_to(workflows_root.resolve())
    except ValueError:
        return None, None

    if source_path.name in {"flow.py", "workflow.py"} and package_init_path is not None:
        package_name = relative.parts[0]
        package_module = f"workflows.{package_name}"
        workflow_module = f"{package_module}.{source_path.stem}"
        return package_module, workflow_module
    if len(relative.parts) == 1 and source_path.suffix == ".py" and source_path.name != "__init__.py":
        return None, f"workflows.{source_path.stem}"
    return None, None


def _params_path(source_path: Path) -> Path | None:
    if source_path.name not in {"flow.py", "workflow.py", "__init__.py"}:
        return None
    params_path = source_path.parent / "params.py"
    return params_path.resolve() if params_path.is_file() else None


def _spec_paths(source_path: Path) -> tuple[Path, ...]:
    if source_path.name not in {"flow.py", "workflow.py", "__init__.py"}:
        return ()
    return tuple(
        candidate.resolve()
        for filename in ("specs.py", "contracts.py")
        if (candidate := source_path.parent / filename).is_file()
    )


def _prompt_paths(source_path: Path) -> tuple[Path, ...]:
    if source_path.name not in {"flow.py", "workflow.py", "__init__.py"}:
        return ()
    prompts_root = source_path.parent / "prompts"
    return tuple(sorted(path.resolve() for path in prompts_root.rglob("*") if path.is_file())) if prompts_root.is_dir() else ()


def _asset_paths(source_path: Path) -> tuple[Path, ...]:
    if source_path.name not in {"flow.py", "workflow.py", "__init__.py"}:
        return ()
    assets_root = source_path.parent / "assets"
    return tuple(sorted(path.resolve() for path in assets_root.rglob("*") if path.is_file())) if assets_root.is_dir() else ()


def _discover_doc_paths(
    root_path: Path,
    package_dir: Path,
    *,
    package_name: str,
    workflow_name: str,
) -> tuple[Path, ...]:
    docs_root = root_path / "docs" / "workflows"
    candidates: list[Path] = []
    for name in dict.fromkeys((package_name, workflow_name)):
        candidate = docs_root / f"{name}.md"
        if candidate.is_file():
            candidates.append(candidate.resolve())
    if package_dir.name != "workflows":
        package_doc = package_dir / "docs.md"
        if package_doc.is_file():
            candidates.append(package_doc.resolve())
    return tuple(candidates)


def _discover_test_paths(root_path: Path, package_dir: Path, *, workflow_name: str) -> tuple[Path, ...]:
    candidates: list[Path] = []
    runtime_test = root_path / "tests" / "runtime" / f"test_{workflow_name}.py"
    if runtime_test.is_file():
        candidates.append(runtime_test.resolve())
    package_tests = package_dir / "tests"
    if package_dir.name != "workflows" and package_tests.is_dir():
        candidates.extend(sorted(path.resolve() for path in package_tests.rglob("*") if path.is_file()))
    return tuple(candidates)


def _default_title(name: str) -> str:
    return name.replace("_", " ").title()


__all__ = [
    "AuthoringShape",
    "WorkflowCatalogDiscoveryError",
    "WorkflowCatalogEntry",
    "WorkflowCatalogManifestError",
    "discover_workflow_catalog",
]
