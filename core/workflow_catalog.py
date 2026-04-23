"""Pure workflow catalog discovery for portfolio-style authoring and runtime helpers."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_WORKFLOW_MANIFEST_FIELDS = frozenset({"aliases", "description", "name", "title"})


class WorkflowCatalogManifestError(ValueError):
    """Raised when workflow catalog manifest metadata is invalid."""


class WorkflowCatalogDiscoveryError(LookupError):
    """Raised when workflow catalog discovery cannot enumerate workflow packages."""


@dataclass(frozen=True, slots=True)
class WorkflowCatalogEntry:
    """Pure filesystem metadata for one discovered workflow package."""

    package_name: str
    workflow_name: str
    title: str | None
    description: str | None
    aliases: tuple[str, ...]
    package_dir: Path
    manifest_path: Path
    workflow_path: Path
    params_path: Path | None
    doc_path: Path | None


def discover_workflow_catalog(root: str | Path) -> tuple[WorkflowCatalogEntry, ...]:
    """Discover workflow package metadata plus linked code/doc paths under ``<root>/workflows``."""

    root_path = Path(root).resolve()
    workflows_root = root_path / "workflows"
    if not workflows_root.exists():
        return ()
    if not workflows_root.is_dir():
        raise WorkflowCatalogDiscoveryError(f"workflow root {workflows_root} is not a directory")
    if not (workflows_root / "__init__.py").is_file():
        raise WorkflowCatalogDiscoveryError(f"workflow root {workflows_root} must be a regular Python package")

    entries: list[WorkflowCatalogEntry] = []
    seen_names: dict[str, Path] = {}
    for manifest_path in sorted(workflows_root.glob("*/workflow.toml")):
        package_dir = manifest_path.parent
        package_name = package_dir.name
        init_path = package_dir / "__init__.py"
        workflow_path = package_dir / "workflow.py"
        if not init_path.is_file():
            raise WorkflowCatalogDiscoveryError(f"workflow package {package_name!r} is missing __init__.py")
        if not workflow_path.is_file():
            raise WorkflowCatalogDiscoveryError(f"workflow package {package_name!r} is missing workflow.py")

        manifest = _read_workflow_manifest(manifest_path)
        workflow_name = manifest.get("name", package_name)
        other_manifest = seen_names.get(workflow_name)
        if other_manifest is not None:
            raise WorkflowCatalogDiscoveryError(
                f"duplicate workflow name {workflow_name!r} in {manifest_path} and {other_manifest}"
            )
        seen_names[workflow_name] = manifest_path

        entries.append(
            WorkflowCatalogEntry(
                package_name=package_name,
                workflow_name=workflow_name,
                title=manifest.get("title"),
                description=manifest.get("description"),
                aliases=manifest.get("aliases", ()),
                package_dir=package_dir,
                manifest_path=manifest_path,
                workflow_path=workflow_path,
                params_path=_optional_file(package_dir / "params.py"),
                doc_path=_discover_workflow_doc(root_path, package_name=package_name, workflow_name=workflow_name),
            )
        )

    return tuple(entries)


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


def _discover_workflow_doc(root_path: Path, *, package_name: str, workflow_name: str) -> Path | None:
    docs_root = root_path / "docs" / "workflows"
    candidates = [docs_root / f"{package_name}.md"]
    if workflow_name != package_name:
        candidates.append(docs_root / f"{workflow_name}.md")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _optional_file(path: Path) -> Path | None:
    return path if path.is_file() else None


__all__ = [
    "WorkflowCatalogDiscoveryError",
    "WorkflowCatalogEntry",
    "WorkflowCatalogManifestError",
    "discover_workflow_catalog",
]
