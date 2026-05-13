"""Pure workflow catalog discovery for package-installed and workspace-local workflows."""

from __future__ import annotations

from importlib.resources import files
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal


_WORKFLOW_MANIFEST_FIELDS = frozenset({"aliases", "class", "description", "module", "name", "title"})
_PRIMARY_WORKSPACE_STATE_DIR = ".botpipe"

AuthoringShape = Literal["single_file", "flow_package", "workflow_package", "manifest_package", "unknown"]
WorkflowSourceKind = Literal["workspace", "package"]


class WorkflowCatalogManifestError(ValueError):
    """Raised when workflow catalog manifest metadata is invalid."""


class WorkflowCatalogDiscoveryError(LookupError):
    """Raised when workflow catalog discovery cannot enumerate workflows."""


@dataclass(frozen=True, slots=True)
class WorkflowSearchRoot:
    """One authoritative workflow discovery root."""

    kind: WorkflowSourceKind
    path: Path
    import_prefix: str | None
    precedence: int


@dataclass(frozen=True, slots=True)
class WorkflowCatalogEntry:
    """Pure filesystem metadata for one discovered workflow."""

    workflow_name: str
    title: str
    description: str
    aliases: tuple[str, ...]
    package_name: str
    package_dir: Path
    manifest_path: Path | None
    source_path: Path
    source_root_kind: WorkflowSourceKind
    source_root: Path
    import_prefix: str | None
    precedence: int
    package_module: str | None
    workflow_module: str | None
    authoring_shape: AuthoringShape
    prompts_dir: Path | None
    assets_dir: Path | None
    docs_path: Path | None
    params_path: Path | None
    specs_path: Path | None
    contracts_path: Path | None
    tests_dir: Path | None
    shadowed: bool = False
    shadowed_by: str | None = None
    manifest_module: str | None = None
    manifest_class: str | None = None
    workflow_path: Path | None = None
    doc_path: Path | None = None
    flow_path: Path | None = None
    workflow_py_path: Path | None = None
    package_init_path: Path | None = None
    spec_paths: tuple[Path, ...] = ()
    prompt_paths: tuple[Path, ...] = ()
    asset_paths: tuple[Path, ...] = ()
    doc_paths: tuple[Path, ...] = ()
    test_paths: tuple[Path, ...] = ()


def workspace_workflows_root(workspace_root: Path) -> Path:
    return workspace_root.resolve() / _PRIMARY_WORKSPACE_STATE_DIR / "workflows"


def repo_workflows_root(workspace_root: Path) -> Path:
    return workspace_root.resolve() / "workflows"


def package_workflows_root() -> Path:
    return Path(str(files("botpipe") / "workflows")).resolve()


def workflow_search_roots(workspace_root: str | Path) -> tuple[WorkflowSearchRoot, ...]:
    root = Path(workspace_root).resolve()
    return (
        WorkflowSearchRoot(
            kind="workspace",
            path=repo_workflows_root(root),
            import_prefix="workflows",
            precedence=110,
        ),
        WorkflowSearchRoot(
            kind="workspace",
            path=workspace_workflows_root(root),
            import_prefix=None,
            precedence=120,
        ),
        WorkflowSearchRoot(
            kind="package",
            path=package_workflows_root(),
            import_prefix="botpipe.workflows",
            precedence=10,
        ),
    )


def read_workflow_manifest(
    manifest_path: Path,
    *,
    require_title_description: bool = True,
) -> dict[str, Any]:
    with manifest_path.open("rb") as handle:
        payload = tomllib.load(handle)
    if not isinstance(payload, dict):
        raise WorkflowCatalogManifestError(f"workflow manifest {manifest_path} must decode to a table")

    unknown_fields = sorted(set(payload) - _WORKFLOW_MANIFEST_FIELDS)
    if unknown_fields:
        names = ", ".join(unknown_fields)
        raise WorkflowCatalogManifestError(
            f"workflow manifest {manifest_path} declares unsupported fields: {names}"
        )

    normalized: dict[str, Any] = {}
    for field in ("name", "title", "description", "module", "class"):
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
    else:
        if not isinstance(aliases, list):
            raise WorkflowCatalogManifestError(
                f"workflow manifest field 'aliases' in {manifest_path} must be a list of strings"
            )

        seen_aliases: set[str] = set()
        normalized_aliases: list[str] = []
        for alias in aliases:
            if not isinstance(alias, str) or not alias.strip():
                raise WorkflowCatalogManifestError(
                    f"workflow manifest aliases in {manifest_path} must be non-empty strings"
                )
            alias_text = alias.strip()
            if alias_text in seen_aliases:
                raise WorkflowCatalogManifestError(f"workflow manifest {manifest_path} repeats alias {alias_text!r}")
            seen_aliases.add(alias_text)
            normalized_aliases.append(alias_text)
        normalized["aliases"] = tuple(normalized_aliases)
    missing_required = ["name"] if "name" not in normalized else []
    if require_title_description:
        missing_required.extend(field for field in ("title", "description") if field not in normalized)
    if missing_required:
        names = ", ".join(missing_required)
        raise WorkflowCatalogManifestError(
            f"workflow manifest {manifest_path} must define non-empty {names}"
        )
    if not require_title_description:
        normalized.setdefault("title", _default_title(normalized["name"]))
        normalized.setdefault("description", "")
    return normalized


def discover_workflow_catalog(
    workspace_root: str | Path,
    *,
    include_shadowed: bool = False,
) -> tuple[WorkflowCatalogEntry, ...]:
    """Discover authoritative workflow metadata from the workspace and package roots."""

    workspace_root_path = Path(workspace_root).resolve()
    search_roots = workflow_search_roots(workspace_root_path)
    discovered: list[WorkflowCatalogEntry] = []
    for search_root in search_roots:
        if not search_root.path.exists():
            continue
        if not search_root.path.is_dir():
            raise WorkflowCatalogDiscoveryError(f"workflow root {search_root.path} is not a directory")
        entries = _discover_search_root(workspace_root_path, search_root)
        _validate_same_tier_keys(search_root.kind, entries)
        discovered.extend(entries)
    return tuple(_effective_catalog(discovered, include_shadowed=include_shadowed))


def _discover_search_root(workspace_root: Path, search_root: WorkflowSearchRoot) -> tuple[WorkflowCatalogEntry, ...]:
    entries: list[WorkflowCatalogEntry] = []
    seen_sources: set[Path] = set()

    for package_dir in sorted(path for path in search_root.path.iterdir() if path.is_dir()):
        manifest_path = package_dir / "workflow.toml"
        manifest = (
            read_workflow_manifest(
                manifest_path,
                require_title_description=search_root.import_prefix != "workflows",
            )
            if manifest_path.is_file()
            else None
        )
        source_path = _directory_source_path(package_dir, manifest_path if manifest_path.is_file() else None, manifest)
        if source_path is None:
            continue
        entry = _build_entry(
            workspace_root,
            search_root,
            source_path.resolve(),
            manifest_path=manifest_path.resolve() if manifest_path.is_file() else None,
            workflow_name=(manifest or {}).get("name", package_dir.name),
            title=(manifest or {}).get("title", _default_title(package_dir.name)),
            description=(manifest or {}).get("description", ""),
            aliases=(manifest or {}).get("aliases", ()),
            manifest_module=(manifest or {}).get("module"),
            manifest_class=(manifest or {}).get("class"),
        )
        if entry.source_path not in seen_sources:
            seen_sources.add(entry.source_path)
            entries.append(entry)

    if search_root.kind == "package":
        invalid_single_files = [
            path.resolve()
            for path in sorted(search_root.path.glob("*.py"))
            if path.name != "__init__.py"
        ]
        if invalid_single_files:
            joined = ", ".join(str(path) for path in invalid_single_files)
            raise WorkflowCatalogDiscoveryError(
                f"package workflow root {search_root.path} does not support single-file workflows: {joined}"
            )
        return tuple(entries)

    for source_path in sorted(search_root.path.glob("*.py")):
        if source_path.name == "__init__.py":
            continue
        entry = _build_entry(
            workspace_root,
            search_root,
            source_path.resolve(),
            manifest_path=None,
            workflow_name=source_path.stem,
            title=_default_title(source_path.stem),
            description="",
            aliases=(),
            manifest_module=None,
            manifest_class=None,
        )
        if entry.source_path not in seen_sources:
            seen_sources.add(entry.source_path)
            entries.append(entry)
    return tuple(entries)


def _directory_source_path(
    package_dir: Path,
    manifest_path: Path | None,
    manifest: dict[str, Any] | None,
) -> Path | None:
    if manifest_path is not None:
        if manifest is None:
            manifest = read_workflow_manifest(manifest_path)
        module_name = manifest.get("module")
        if module_name is not None:
            candidate = package_dir / Path(module_name.replace(".", "/")).with_suffix(".py")
            if not candidate.is_file():
                raise WorkflowCatalogManifestError(
                    f"workflow manifest {manifest_path} references missing module source {candidate}"
                )
            return candidate.resolve()

    preferred = package_dir / "flow.py"
    if preferred.is_file():
        return preferred.resolve()
    workflow_py_path = package_dir / "workflow.py"
    if workflow_py_path.is_file():
        return workflow_py_path.resolve()
    if manifest_path is not None:
        raise WorkflowCatalogDiscoveryError(
            f"workflow manifest {manifest_path} requires flow.py or workflow.py in {package_dir}"
        )
    return None


def _build_entry(
    workspace_root: Path,
    search_root: WorkflowSearchRoot,
    source_path: Path,
    *,
    manifest_path: Path | None,
    workflow_name: str,
    title: str,
    description: str,
    aliases: tuple[str, ...],
    manifest_module: str | None,
    manifest_class: str | None,
) -> WorkflowCatalogEntry:
    package_dir = _package_dir_for_source(source_path)
    package_name = _package_name_for_source(source_path)
    if not workflow_name.strip():
        raise WorkflowCatalogDiscoveryError(f"workflow at {source_path} has an empty workflow name")
    if not package_name.strip():
        raise WorkflowCatalogDiscoveryError(f"workflow at {source_path} has an empty package name")
    if not source_path.is_file():
        raise WorkflowCatalogDiscoveryError(f"workflow source file {source_path} does not exist")
    if not package_dir.is_dir():
        raise WorkflowCatalogDiscoveryError(f"workflow package directory {package_dir} does not exist")

    package_init_path = _package_init_path(source_path)
    if search_root.kind == "package" and package_init_path is None:
        raise WorkflowCatalogDiscoveryError(
            f"package workflow {package_dir} must define __init__.py for import via {search_root.import_prefix}"
        )

    normalized_aliases = _normalize_aliases(aliases, workflow_name=workflow_name, source_path=source_path)
    prompts_dir = _optional_dir(package_dir / "prompts")
    assets_dir = _optional_dir(package_dir / "assets")
    docs_path = _discover_docs_path(workspace_root, package_dir, workflow_name=workflow_name, package_name=package_name)
    params_path = _optional_file(package_dir / "params.py") if source_path.name in {"flow.py", "workflow.py", "__init__.py"} else None
    specs_path = _optional_file(package_dir / "specs.py") if source_path.name in {"flow.py", "workflow.py", "__init__.py"} else None
    contracts_path = (
        _optional_file(package_dir / "contracts.py") if source_path.name in {"flow.py", "workflow.py", "__init__.py"} else None
    )
    tests_dir = _optional_dir(package_dir / "tests")
    prompt_paths = _iter_file_tree(prompts_dir)
    asset_paths = _iter_file_tree(assets_dir)
    doc_paths = () if docs_path is None else (docs_path,)
    spec_paths = tuple(path for path in (specs_path, contracts_path) if path is not None)
    test_paths = _discover_test_paths(
        workspace_root,
        package_dir,
        workflow_name=workflow_name,
        package_name=package_name,
    )
    package_module, workflow_module = _module_names_for_source(search_root, source_path, package_name=package_name)

    return WorkflowCatalogEntry(
        workflow_name=workflow_name.strip(),
        title=title.strip(),
        description=description.strip(),
        aliases=normalized_aliases,
        package_name=package_name,
        package_dir=package_dir,
        manifest_path=manifest_path,
        source_path=source_path,
        source_root_kind=search_root.kind,
        source_root=search_root.path.resolve(),
        import_prefix=search_root.import_prefix,
        precedence=search_root.precedence,
        package_module=package_module,
        workflow_module=workflow_module,
        authoring_shape=_authoring_shape_for_source(source_path, manifest_path),
        prompts_dir=prompts_dir,
        assets_dir=assets_dir,
        docs_path=docs_path,
        params_path=params_path,
        specs_path=specs_path,
        contracts_path=contracts_path,
        tests_dir=tests_dir,
        manifest_module=manifest_module,
        manifest_class=manifest_class,
        workflow_path=source_path,
        doc_path=docs_path,
        flow_path=source_path if source_path.name == "flow.py" else None,
        workflow_py_path=source_path if source_path.name == "workflow.py" else None,
        package_init_path=package_init_path,
        spec_paths=spec_paths,
        prompt_paths=prompt_paths,
        asset_paths=asset_paths,
        doc_paths=doc_paths,
        test_paths=test_paths,
    )


def _validate_same_tier_keys(tier: WorkflowSourceKind, entries: tuple[WorkflowCatalogEntry, ...]) -> None:
    seen: dict[str, WorkflowCatalogEntry] = {}
    for entry in sorted(entries, key=lambda item: (item.workflow_name, str(item.source_path))):
        for key in _resolution_keys(entry):
            other = seen.get(key)
            if other is None:
                seen[key] = entry
                continue
            raise WorkflowCatalogDiscoveryError(
                f"duplicate workflow resolution key {key!r} in source tier {tier!r}: "
                f"{other.source_path} and {entry.source_path}"
            )


def _effective_catalog(
    entries: list[WorkflowCatalogEntry],
    *,
    include_shadowed: bool,
) -> list[WorkflowCatalogEntry]:
    ordered = sorted(entries, key=lambda entry: (-_resolution_precedence(entry), entry.workflow_name, str(entry.source_path)))
    claimed_keys: dict[str, WorkflowCatalogEntry] = {}
    effective: list[WorkflowCatalogEntry] = []
    for entry in ordered:
        shadowing_entries = [claimed_keys[key] for key in _resolution_keys(entry) if key in claimed_keys]
        if shadowing_entries:
            if include_shadowed:
                effective.append(
                    replace(
                        entry,
                        shadowed=True,
                        shadowed_by=shadowing_entries[0].workflow_name,
                    )
                )
            continue
        effective.append(entry)
        for key in _resolution_keys(entry):
            claimed_keys[key] = entry
    return effective


def _resolution_precedence(entry: WorkflowCatalogEntry) -> int:
    return entry.precedence


def _resolution_keys(entry: WorkflowCatalogEntry) -> tuple[str, ...]:
    keys = [_normalize_resolution_key(entry.workflow_name, label="workflow name", source_path=entry.source_path)]
    seen = {keys[0]}
    for alias in entry.aliases:
        key = _normalize_resolution_key(alias, label="workflow alias", source_path=entry.source_path)
        if key in seen:
            raise WorkflowCatalogDiscoveryError(
                f"workflow {entry.source_path} repeats resolution key {key!r} across its name and aliases"
            )
        seen.add(key)
        keys.append(key)
    return tuple(keys)


def _normalize_aliases(
    aliases: tuple[str, ...],
    *,
    workflow_name: str,
    source_path: Path,
) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = {_normalize_resolution_key(workflow_name, label="workflow name", source_path=source_path)}
    for alias in aliases:
        key = _normalize_resolution_key(alias, label="workflow alias", source_path=source_path)
        if key in seen:
            raise WorkflowCatalogManifestError(
                f"workflow {source_path} repeats resolution key {key!r} across its name and aliases"
            )
        seen.add(key)
        normalized.append(alias.strip())
    return tuple(normalized)


def _normalize_resolution_key(value: str, *, label: str, source_path: Path) -> str:
    text = value.strip()
    if not text:
        raise WorkflowCatalogDiscoveryError(f"{label} in {source_path} must be a non-empty string")
    return text


def _package_dir_for_source(source_path: Path) -> Path:
    return source_path.parent.resolve()


def _package_name_for_source(source_path: Path) -> str:
    if source_path.name in {"flow.py", "workflow.py", "__init__.py"}:
        return source_path.parent.name
    return source_path.stem


def _package_init_path(source_path: Path) -> Path | None:
    if source_path.name not in {"flow.py", "workflow.py", "__init__.py"}:
        return None
    return _optional_file(source_path.parent / "__init__.py")


def _module_names_for_source(
    search_root: WorkflowSearchRoot,
    source_path: Path,
    *,
    package_name: str,
) -> tuple[str | None, str | None]:
    if search_root.import_prefix is None:
        return None, None
    if source_path.name not in {"flow.py", "workflow.py", "__init__.py"}:
        return None, None
    package_module = f"{search_root.import_prefix}.{package_name}"
    if source_path.name == "__init__.py":
        return package_module, package_module
    return package_module, f"{package_module}.{source_path.stem}"


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


def _discover_docs_path(
    workspace_root: Path,
    package_dir: Path,
    *,
    workflow_name: str,
    package_name: str,
) -> Path | None:
    for filename in ("README.md", "docs.md"):
        package_docs = _optional_file(package_dir / filename)
        if package_docs is not None:
            return package_docs
    return None


def _optional_file(path: Path) -> Path | None:
    return path.resolve() if path.is_file() else None


def _optional_dir(path: Path) -> Path | None:
    return path.resolve() if path.is_dir() else None


def _iter_file_tree(root: Path | None) -> tuple[Path, ...]:
    if root is None:
        return ()
    return tuple(sorted(path.resolve() for path in root.rglob("*") if path.is_file()))


def _discover_test_paths(
    workspace_root: Path,
    package_dir: Path,
    *,
    workflow_name: str,
    package_name: str,
) -> tuple[Path, ...]:
    paths = list(_iter_file_tree(_optional_dir(package_dir / "tests")))
    seen = {path.resolve() for path in paths}
    repo_tests_root = workspace_root / "tests"
    if repo_tests_root.is_dir():
        for name in dict.fromkeys((package_name, workflow_name)):
            for candidate in sorted(repo_tests_root.rglob(f"test_{name}.py")):
                resolved = candidate.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                paths.append(resolved)
    return tuple(paths)


def _default_title(name: str) -> str:
    return name.replace("_", " ").title()


__all__ = [
    "AuthoringShape",
    "WorkflowCatalogDiscoveryError",
    "WorkflowCatalogEntry",
    "WorkflowCatalogManifestError",
    "repo_workflows_root",
    "WorkflowSearchRoot",
    "WorkflowSourceKind",
    "discover_workflow_catalog",
    "package_workflows_root",
    "read_workflow_manifest",
    "workflow_search_roots",
    "workspace_workflows_root",
]
