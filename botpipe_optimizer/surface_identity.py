"""Runtime-compatible surface identities and strict, independently derived manifests."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from botpipe.surface_identity import (
    SURFACE_MANIFEST_SCHEMA,
    canonical_content_id,
    canonical_json_bytes,
    canonical_surface_id,
    canonical_surface_payload,
)
from botpipe.surface_identity import (
    derive_surface_manifest as _derive_manifest,
)

_RUNTIME_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def _relative(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("surface paths must be normalized relative strings")
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        raise ValueError("surface paths must remain relative")
    return path.as_posix()


def _surface_paths(root: Path) -> list[str]:
    paths = []
    for item in root.rglob("*"):
        relative = item.relative_to(root)
        if (
            item.name == ".botpipe-workspace.lock"
            or set(relative.parts) & _RUNTIME_PARTS
        ):
            continue
        if item.is_symlink():
            raise ValueError(f"surface contains a symlink: {item}")
        if not item.is_dir():
            paths.append(relative.as_posix())
    return sorted(paths)


def derive_surface_manifest(
    root: Path,
    *,
    expected_root: Path,
    boundary: Mapping[str, Any],
    surface_kind: str,
    authoritative_sources: Mapping[str, Path] | None = None,
    relative_paths: Sequence[str] | None = None,
) -> dict[str, Any]:
    root = Path(root)
    derived = _derive_manifest(
        root,
        expected_root=expected_root,
        boundary=boundary,
        surface_kind=surface_kind,
        relative_paths=list(relative_paths)
        if relative_paths is not None
        else _surface_paths(root),
        allow_empty=surface_kind == "baseline",
    )
    files = {entry["relative_path"]: entry for entry in derived["files"]}
    for relative, source in (authoritative_sources or {}).items():
        relative = _relative(relative)
        raw = Path(source).absolute()
        if any(path.is_symlink() for path in (raw, *raw.parents)):
            raise ValueError(f"authoritative source contains a symlink: {source}")
        resolved = raw.resolve(strict=True)
        if relative not in files or not resolved.is_file():
            raise ValueError(f"invalid authoritative source: {relative}")
        files[relative].update(
            source_path=str(resolved),
            authoritative_source_sha256=hashlib.sha256(
                resolved.read_bytes()
            ).hexdigest(),
            authoritative_source_executable=bool(resolved.stat().st_mode & 0o111)
            if os.name == "posix"
            else False,
        )
    return derived


def validate_surface_manifest(
    manifest: Mapping[str, Any],
    *,
    expected_root: Path,
    expected_boundary: Mapping[str, Any],
    expected_surface_kind: str,
    baseline_manifest: Mapping[str, Any] | None = None,
    allowed_added_path_prefixes: Sequence[str] = (),
    allowed_added_exact_paths: Sequence[str] = (),
    allowed_removed_paths: Sequence[str] = (),
) -> dict[str, Any]:
    """Recompute paths, content, modes, counts and identity; reject forged claims."""
    raw_root = manifest.get("root", manifest.get("surface_root"))
    if not isinstance(raw_root, str) or not raw_root:
        raise ValueError("manifest root required")
    raw = Path(raw_root)
    if raw.is_symlink() or raw.resolve(strict=True) != Path(expected_root).resolve(
        strict=True
    ):
        raise ValueError("manifest root must match runtime expected root")
    identity_boundary = {
        key: value for key, value in expected_boundary.items() if key != "surface_kind"
    }
    derived = derive_surface_manifest(
        raw,
        expected_root=expected_root,
        boundary=identity_boundary,
        surface_kind=expected_surface_kind,
        relative_paths=manifest.get("relative_paths")
        if expected_surface_kind == "workflow"
        else None,
    )
    for field in (
        "schema",
        "surface_kind",
        "root",
        "surface_root",
        "boundary",
        "mode_semantics",
        "surface_id",
        "relative_paths",
        "file_count",
        "size_bytes",
    ):
        if manifest.get(field) != derived[field]:
            raise ValueError(f"manifest {field} must match derived surface")
    submitted = manifest.get("files")
    if not isinstance(submitted, list) or len(submitted) != len(derived["files"]):
        raise ValueError("manifest files must match derived surface")
    factual = (
        "relative_path",
        "surface_path",
        "surface_sha256",
        "size_bytes",
        "executable",
    )
    for left, right in zip(submitted, derived["files"], strict=True):
        if not isinstance(left, Mapping) or any(
            left.get(key) != right[key] for key in factual
        ):
            raise ValueError("manifest files must match derived surface")
    if baseline_manifest is not None:
        baseline = {_relative(value) for value in baseline_manifest["relative_paths"]}
        candidate = set(derived["relative_paths"])
        permitted_removed = {_relative(value) for value in allowed_removed_paths}
        if (baseline - candidate) - permitted_removed:
            raise ValueError(
                "candidate must preserve every baseline path outside allowed removals"
            )
        prefixes = tuple(_relative(value) for value in allowed_added_path_prefixes)
        exact = {_relative(value) for value in allowed_added_exact_paths}
        for path in candidate - baseline:
            if path not in exact and not any(
                path.startswith(prefix + "/") for prefix in prefixes
            ):
                raise ValueError(f"candidate added path outside boundary: {path}")
    return derived


__all__ = [
    "SURFACE_MANIFEST_SCHEMA",
    "canonical_content_id",
    "canonical_json_bytes",
    "canonical_surface_id",
    "canonical_surface_payload",
    "derive_surface_manifest",
    "validate_surface_manifest",
]
