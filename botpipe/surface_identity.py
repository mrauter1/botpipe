"""Canonical dependency-neutral identities for workflow file surfaces."""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any

SURFACE_MANIFEST_SCHEMA = "botpipe.surface-manifest.v2"


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def canonical_content_id(value: Any) -> str:
    return "sha256:" + sha256(canonical_json_bytes(value)).hexdigest()


def canonical_workflow_identity(
    reference: Any, *, workflow_name: str | None = None
) -> str:
    """Identify a resolved workflow independent of the alias/path used to select it."""
    if not isinstance(reference, Mapping):
        _, _, reference = workflow_surface_location(Path.cwd(), reference)
    return canonical_content_id(
        {
            "schema": "botpipe.workflow-identity.v2",
            "workflow_name": workflow_name
            or reference.get("workflow_name")
            or reference.get("name"),
            "source": reference.get("source_relative_path"),
            "function": reference.get("function"),
        }
    )


def _normalize(value: Any):
    return json.loads(canonical_json_bytes(value))


def canonical_surface_payload(
    *,
    boundary: Mapping[str, Any],
    files: Sequence[Mapping[str, Any]],
    mode_semantics: str,
) -> dict[str, Any]:
    normalized = []
    seen = set()
    for i, raw in enumerate(files):
        path = raw.get("path", raw.get("relative_path"))
        digest = raw.get("sha256", raw.get("surface_sha256"))
        size = raw.get("size_bytes")
        executable = raw.get("executable")
        if (
            not isinstance(path, str)
            or not path
            or path.startswith("/")
            or "\\" in path
            or ".." in path.split("/")
            or PurePosixPath(path).as_posix() != path
        ):
            raise ValueError(f"files[{i}].path must be normalized relative")
        if path in seen:
            raise ValueError(f"duplicate surface path: {path}")
        seen.add(path)
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f"files[{i}].sha256 must be SHA-256")
        int(digest, 16)
        if (
            isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
            or not isinstance(executable, bool)
        ):
            raise ValueError("invalid surface metadata")
        normalized.append(
            {
                "path": path,
                "sha256": digest.lower(),
                "size_bytes": size,
                "executable": executable,
            }
        )
    return {
        "schema": SURFACE_MANIFEST_SCHEMA,
        "boundary": _normalize(boundary),
        "mode_semantics": mode_semantics,
        "files": sorted(normalized, key=lambda x: x["path"]),
    }


def canonical_surface_id(*, boundary, files, mode_semantics):
    return canonical_content_id(
        canonical_surface_payload(
            boundary=boundary, files=files, mode_semantics=mode_semantics
        )
    )


def _reject_symlinks(path: Path) -> None:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise ValueError(f"surface contains a symlink: {path}")


def _file_entry(source: Path, relative: str) -> dict[str, Any]:
    _reject_symlinks(source)
    resolved = source.resolve(strict=True)
    info = resolved.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"surface path must be regular: {source}")
    content = resolved.read_bytes()
    after = resolved.stat(follow_symlinks=False)
    if (info.st_ino, info.st_size, info.st_mtime_ns, info.st_mode) != (
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_mode,
    ) or len(content) != info.st_size:
        raise ValueError(f"surface changed while being captured: {source}")
    digest = sha256(content).hexdigest()
    return {
        "relative_path": relative,
        "surface_path": str(resolved),
        "surface_sha256": digest,
        "size_bytes": info.st_size,
        "executable": bool(info.st_mode & 0o111) if os.name == "posix" else False,
    }


def _manifest(
    root: Path, boundary: Mapping[str, Any], kind: str, files: list[dict[str, Any]]
) -> dict[str, Any]:
    mode = (
        "posix-executable-bit" if os.name == "posix" else "executable-bit-unsupported"
    )
    full = {"surface_kind": kind, **dict(boundary)}
    identity = [
        {
            "path": x["relative_path"],
            "sha256": x["surface_sha256"],
            "size_bytes": x["size_bytes"],
            "executable": x["executable"],
        }
        for x in files
    ]
    payload = canonical_surface_payload(
        boundary=full, files=identity, mode_semantics=mode
    )
    return {
        "schema": SURFACE_MANIFEST_SCHEMA,
        "surface_kind": kind,
        "root": str(root),
        "surface_root": str(root),
        "boundary": payload["boundary"],
        "mode_semantics": mode,
        "surface_id": canonical_surface_id(
            boundary=payload["boundary"], files=identity, mode_semantics=mode
        ),
        "relative_paths": [x["relative_path"] for x in files],
        "file_count": len(files),
        "size_bytes": sum(x["size_bytes"] for x in files),
        "files": files,
    }


def derive_surface_manifest(
    root: Path,
    *,
    expected_root: Path,
    boundary: Mapping[str, Any],
    surface_kind: str,
    relative_paths: Sequence[str] | None = None,
) -> dict[str, Any]:
    _reject_symlinks(Path(root))
    _reject_symlinks(Path(expected_root))
    actual = Path(root).resolve(strict=True)
    expected = Path(expected_root).resolve(strict=True)
    if actual != expected or not actual.is_dir():
        raise ValueError("surface root must match expected directory")
    paths = (
        sorted(relative_paths)
        if relative_paths is not None
        else sorted(
            p.relative_to(actual).as_posix()
            for p in actual.rglob("*")
            if not p.is_dir()
        )
    )
    files = []
    for rel in paths:
        candidate = actual / rel
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(actual):
            raise ValueError("surface path escapes expected root")
        files.append(_file_entry(candidate, rel))
    if not files:
        raise ValueError("surface must contain at least one regular file")
    return _manifest(actual, boundary, surface_kind, files)


_SOURCE_EXCLUSIONS = frozenset(
    {
        ".git",
        ".botpipe",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "__pycache__",
        "build",
        "dist",
    }
)


def workflow_surface_location(
    repo_root: Path, definition: Any
) -> tuple[Path, Path, dict[str, Any]]:
    """Resolve a function's explicit file or containing workflow-package boundary."""
    import inspect

    if isinstance(definition, str):
        from .discovery import resolve_workflow

        definition = resolve_workflow(definition, repo_root)
    if isinstance(definition, Mapping):
        raw = definition.get("source", {}).get("path")
        name, module, function = (
            definition.get("name"),
            definition.get("module"),
            definition.get("function"),
        )
    else:
        context = getattr(definition, "_source_context", None)
        if context is None:
            target = inspect.unwrap(getattr(definition, "fn", definition))
            raw = inspect.getsourcefile(target)
        else:
            target = context.origin_target
            raw = context.origin_source
        if target is None or raw is None:
            raise ValueError("workflow has no inspectable application source file")
        name = getattr(definition, "name", target.__name__)
        module, function = target.__module__, target.__qualname__
    if not raw:
        raise ValueError("workflow has no inspectable source file")
    source = Path(raw).absolute()
    _reject_symlinks(source)
    source = source.resolve(strict=True)
    preferred = Path(repo_root).resolve(strict=True)
    if source.is_relative_to(preferred):
        root = preferred
    else:
        root = next(
            (
                parent
                for parent in source.parents
                if (parent / "pyproject.toml").is_file() or (parent / ".git").exists()
            ),
            None,
        )
        if root is None:
            # An installed module keeps its import-relative path even when the
            # active workspace is a different project.
            root = source.parent
            components = str(module or "").split(".")
            if not str(module).startswith("_botpipe_"):
                count = (
                    len(components)
                    if source.name == "__init__.py"
                    else len(components) - 1
                )
                for _ in range(count):
                    root = root.parent
    is_package = (
        (source.parent / "__init__.py").is_file()
        or (source.parent / "workflow.toml").is_file()
        or source.name in {"workflow.py", "flow.py"}
    )
    selected = source.parent if is_package else source
    info = {
        "workflow_name": name,
        "function": function,
        "source_relative_path": source.relative_to(root).as_posix(),
        "package_root_relative_path": selected.relative_to(root).as_posix()
        if is_package
        else None,
        "editable_boundary_version": 2,
    }
    return root, selected, info


def derive_workflow_surface_manifest(
    repo_root: Path, definition: Any
) -> dict[str, Any]:
    """Derive exact native workflow package bytes, excluding fixed runtime/cache files."""
    root, selected, boundary = workflow_surface_location(repo_root, definition)
    paths: list[str] = []
    if selected.is_file():
        paths.append(selected.relative_to(root).as_posix())
    else:
        for directory, names, files in os.walk(selected, followlinks=False):
            parent = Path(directory)
            names[:] = sorted(
                name
                for name in names
                if name not in _SOURCE_EXCLUSIONS
                and not name.startswith(".venv")
                and not name.endswith(".egg-info")
            )
            for name in names:
                if (parent / name).is_symlink():
                    raise ValueError(
                        f"workflow surface contains a symlink: {parent / name}"
                    )
            for name in sorted(files):
                if name == ".botpipe-workspace.lock" or name.endswith((".pyc", ".pyo")):
                    continue
                paths.append((parent / name).relative_to(root).as_posix())
    return derive_surface_manifest(
        root,
        expected_root=root,
        boundary=boundary,
        surface_kind="workflow",
        relative_paths=paths,
    )


__all__ = [
    "SURFACE_MANIFEST_SCHEMA",
    "canonical_content_id",
    "canonical_json_bytes",
    "canonical_surface_id",
    "canonical_surface_payload",
    "canonical_workflow_identity",
    "derive_surface_manifest",
    "derive_workflow_surface_manifest",
    "workflow_surface_location",
]
