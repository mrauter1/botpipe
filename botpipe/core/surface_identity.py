"""Canonical dependency-neutral identities for workflow file surfaces."""

from __future__ import annotations
from collections.abc import Mapping, Sequence
from hashlib import sha256
import json, os, stat
from pathlib import Path
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
    return canonical_content_id(
        {
            "schema": "botpipe.workflow-identity.v1",
            "workflow_name": workflow_name or reference.workflow_name,
            "package_name": reference.package_name,
            "package_module": reference.package_module,
            "workflow_module": reference.workflow_module,
            "class_name": reference.class_name,
            "authoring_shape": reference.authoring_shape,
            "source_root_kind": reference.source_root_kind,
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
        try:
            info = current.lstat()
        except FileNotFoundError:
            raise
        if stat.S_ISLNK(info.st_mode):
            raise ValueError(f"surface contains a symlink: {path}")


def _file_entry(source: Path, relative: str) -> dict[str, Any]:
    _reject_symlinks(source)
    resolved = source.resolve(strict=True)
    info = resolved.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"surface path must be regular: {source}")
    digest = sha256(resolved.read_bytes()).hexdigest()
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


def derive_workflow_surface_manifest(
    repo_root: Path, capability_entry: Any
) -> dict[str, Any]:
    from .workflow_capabilities import selected_workflow_authoring_surface_payload

    root = Path(repo_root).resolve(strict=True)
    surface = selected_workflow_authoring_surface_payload(capability_entry)
    sources = surface.get("editable_paths")
    relative = surface.get("editable_paths_repo_relative")
    if (
        not isinstance(sources, list)
        or not isinstance(relative, list)
        or len(sources) != len(relative)
    ):
        raise ValueError("workflow editable surface paths are unavailable")
    files = []
    for source, rel in zip(sources, relative, strict=True):
        if not isinstance(source, str) or not isinstance(rel, str) or not rel:
            raise ValueError("workflow editable path lacks canonical relative identity")
        files.append(_file_entry(Path(source), rel))
    files.sort(key=lambda x: x["relative_path"])
    boundary = {
        "workflow_name": surface.get("workflow_name"),
        "package_name": surface.get("package_name"),
        "package_root_relative_path": surface.get("package_dir_repo_relative"),
        "doc_relative_path": surface.get("doc_path_repo_relative"),
        "runtime_test_relative_path": surface.get("runtime_test_path_repo_relative"),
        "editable_boundary_version": 1,
    }
    return _manifest(root, boundary, "workflow", files)


__all__ = [
    "SURFACE_MANIFEST_SCHEMA",
    "canonical_json_bytes",
    "canonical_content_id",
    "canonical_workflow_identity",
    "canonical_surface_payload",
    "canonical_surface_id",
    "derive_surface_manifest",
    "derive_workflow_surface_manifest",
]
