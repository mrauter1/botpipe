"""Frozen project trees for candidate compilation and paired evaluation."""

from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from botpipe.surface_identity import canonical_surface_id

from .surface_identity import derive_surface_manifest

DEFAULT_MAX_EXECUTION_TREE_FILES = 100000
DEFAULT_MAX_EXECUTION_TREE_BYTES = 512 * 1024 * 1024
EXECUTION_TREE_SCHEMA = "botpipe.execution-tree.v2"
OWNERSHIP_MARKER = ".botpipe-owned-staging.json"
EXCLUDED_DIRECTORY_NAMES = frozenset(
    {
        ".botpipe",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        "__pycache__",
        "build",
        "dist",
    }
)


@dataclass(frozen=True, slots=True)
class FrozenExecutionTree:
    root: Path
    execution_tree_id: str
    manifest: Mapping[str, Any]
    source_records: tuple[Mapping[str, Any], ...]
    owned_parent: Path
    ownership_token: str


@dataclass(frozen=True, slots=True)
class ExecutionArm:
    root: Path
    execution_tree_id: str
    manifest: Mapping[str, Any]
    surface_id: str | None
    owned_parent: Path
    ownership_token: str


def capture_execution_tree(
    source_root: Path,
    owned_parent: Path,
    *,
    selected_package_root: Path | None = None,
    selected_package_import_path: str | None = None,
    excluded_roots: Sequence[Path] = (),
    max_files: int = DEFAULT_MAX_EXECUTION_TREE_FILES,
    max_bytes: int = DEFAULT_MAX_EXECUTION_TREE_BYTES,
) -> FrozenExecutionTree:
    raw = Path(source_root)
    if _has_symlink(raw):
        raise ValueError("execution source root must not contain a symlink")
    source = raw.resolve(strict=True)
    if not source.is_dir():
        raise ValueError("source_root must be a directory")
    _limits(max_files, max_bytes)
    parent = Path(owned_parent).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    excluded = _excluded_roots(source, [*excluded_roots, parent])
    project = _enumerate(
        source,
        prefix=None,
        excluded=excluded,
        layer="project",
        max_files=max_files,
        max_bytes=max_bytes,
    )
    package: list[dict[str, Any]] = []
    prefix = None
    if selected_package_root is not None:
        raw_package = Path(selected_package_root)
        if _has_symlink(raw_package):
            raise ValueError("selected package root must not be a symlink")
        package_root = raw_package.resolve(strict=True)
        try:
            package_root.relative_to(source)
        except ValueError:
            prefix = _relative(selected_package_import_path or package_root.name)
            package = _enumerate(
                package_root,
                prefix=prefix,
                excluded=(),
                layer="selected_package",
                max_files=max_files - len(project),
                max_bytes=max_bytes - sum(record["size_bytes"] for record in project),
            )
    records = _merge(project, package)
    total = sum(int(r["size_bytes"]) for r in records)
    if len(records) > max_files:
        raise ValueError(
            f"execution tree has {len(records)} files, exceeding max_execution_tree_files={max_files}"
        )
    if total > max_bytes:
        raise ValueError(
            f"execution tree has {total} bytes, exceeding max_execution_tree_bytes={max_bytes}"
        )
    root, token = allocate_owned_directory(parent, prefix="frozen-execution-tree-")
    try:
        for record in records:
            target = root / str(record["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(
                Path(str(record["source_path"])), target, follow_symlinks=False
            )
        manifest = derive_execution_tree_manifest(
            root,
            exclusions=_exclusion_payload(excluded),
            layers={"project": True, "selected_package_import_path": prefix},
        )
        if [x["path"] for x in manifest["files"]] != [x["path"] for x in records]:
            raise ValueError("frozen tree inventory differs from source inventory")
        return FrozenExecutionTree(
            root,
            str(manifest["execution_tree_id"]),
            manifest,
            tuple(dict(r) for r in records),
            parent,
            token,
        )
    except BaseException:
        cleanup_owned_directory(root, owned_parent=parent, ownership_token=token)
        raise


def derive_execution_tree_manifest(
    root: Path,
    *,
    exclusions: Sequence[str] = (),
    layers: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = Path(root).resolve(strict=True)
    records = _enumerate(resolved, prefix=None, excluded=(), layer="frozen")
    files = [
        {
            "path": r["path"],
            "sha256": r["sha256"],
            "size_bytes": r["size_bytes"],
            "executable": r["executable"],
        }
        for r in records
        if r["path"] != OWNERSHIP_MARKER
    ]
    boundary = {
        "kind": "execution_tree",
        "exclusions": sorted(exclusions),
        "layers": dict(layers or {}),
    }
    mode = (
        "posix-executable-bit" if os.name == "posix" else "executable-bit-unsupported"
    )
    identity = canonical_surface_id(boundary=boundary, files=files, mode_semantics=mode)
    return {
        "schema": EXECUTION_TREE_SCHEMA,
        "root": str(resolved),
        "execution_tree_id": identity,
        "boundary": boundary,
        "mode_semantics": mode,
        "file_count": len(files),
        "size_bytes": sum(int(x["size_bytes"]) for x in files),
        "files": files,
    }


def verify_frozen_execution_tree(snapshot: FrozenExecutionTree) -> None:
    actual = derive_execution_tree_manifest(
        snapshot.root,
        exclusions=snapshot.manifest["boundary"]["exclusions"],
        layers=snapshot.manifest["boundary"]["layers"],
    )
    if actual["execution_tree_id"] != snapshot.execution_tree_id:
        raise ValueError("frozen execution tree changed; start a new validation")
    for record in snapshot.source_records:
        path = Path(str(record["source_path"]))
        if (
            _has_symlink(path)
            or not path.is_file()
            or _sha(path) != record["sha256"]
            or (_executable(path) != record["executable"])
        ):
            raise ValueError(
                f"authoritative execution source changed: {record['path']}"
            )


def materialize_execution_arm(
    snapshot: FrozenExecutionTree,
    owned_parent: Path,
    *,
    candidate_manifest: Mapping[str, Any] | None = None,
    removed_paths: Sequence[str] = (),
) -> ExecutionArm:
    verify_frozen_execution_tree(snapshot)
    parent = Path(owned_parent).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    root, token = allocate_owned_directory(parent, prefix="execution-arm-")
    try:
        _copy(snapshot.root, root)
        for value in removed_paths:
            relative = _relative(value)
            target = root / relative
            if _has_symlink(target, stop=root) or not target.is_file():
                raise ValueError(
                    f"removed path must name a staged regular file: {relative}"
                )
            target.unlink()
        surface_id = None
        if candidate_manifest is not None:
            raw = Path(
                _text(
                    candidate_manifest.get(
                        "root", candidate_manifest.get("surface_root")
                    )
                )
            )
            if raw.is_symlink():
                raise ValueError("candidate root must not be a symlink")
            candidate = raw.resolve(strict=True)
            boundary = candidate_manifest.get("boundary")
            surface_kind = candidate_manifest.get("surface_kind")
            if not isinstance(boundary, Mapping) or not isinstance(surface_kind, str):
                raise ValueError(
                    "candidate manifest must define boundary and surface_kind"
                )
            identity_boundary = {
                key: value for key, value in boundary.items() if key != "surface_kind"
            }
            derived_candidate = derive_surface_manifest(
                candidate,
                expected_root=candidate,
                boundary=identity_boundary,
                surface_kind=surface_kind,
            )
            if derived_candidate["surface_id"] != candidate_manifest.get("surface_id"):
                raise ValueError("candidate surface changed after validation")
            paths = candidate_manifest.get("relative_paths")
            if not isinstance(paths, list) or not paths:
                raise ValueError("candidate manifest must define relative_paths")
            for value in paths:
                relative = _relative(value)
                source = candidate / relative
                if _has_symlink(source, stop=candidate) or not source.is_file():
                    raise ValueError(
                        f"candidate surface must contain a regular file: {relative}"
                    )
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target, follow_symlinks=False)
            surface_id = (
                candidate_manifest.get("surface_id")
                if isinstance(candidate_manifest.get("surface_id"), str)
                else None
            )
        manifest = derive_execution_tree_manifest(
            root,
            exclusions=snapshot.manifest["boundary"]["exclusions"],
            layers=snapshot.manifest["boundary"]["layers"],
        )
        return ExecutionArm(
            root,
            str(manifest["execution_tree_id"]),
            manifest,
            surface_id,
            parent,
            token,
        )
    except BaseException:
        cleanup_owned_directory(root, owned_parent=parent, ownership_token=token)
        raise


def snapshot_execution_arm(arm: ExecutionArm) -> dict[str, Any]:
    return derive_execution_tree_manifest(
        arm.root,
        exclusions=arm.manifest["boundary"]["exclusions"],
        layers=arm.manifest["boundary"]["layers"],
    )


def assert_execution_arm_unchanged(
    expected: Mapping[str, Any], root: Path, *, phase: str
) -> None:
    actual = derive_execution_tree_manifest(
        root,
        exclusions=expected["boundary"]["exclusions"],
        layers=expected["boundary"]["layers"],
    )
    if actual["execution_tree_id"] != expected.get("execution_tree_id"):
        raise ValueError(f"execution tree changed during {phase}")


def allocate_owned_directory(parent: Path, *, prefix: str) -> tuple[Path, str]:
    if not isinstance(prefix, str) or not prefix or "/" in prefix or "\\" in prefix:
        raise ValueError("owned-directory prefix must be a nonempty filename prefix")
    if _has_symlink(Path(parent)):
        raise ValueError("owned parent must not contain symlinks")
    parent = Path(parent).resolve(strict=True)
    token = uuid4().hex
    root = Path(tempfile.mkdtemp(prefix=prefix, dir=parent)).resolve()
    (root / OWNERSHIP_MARKER).write_text(
        json.dumps(
            {"schema": "botpipe.owned-staging.v1", "token": token}, sort_keys=True
        ),
        encoding="utf-8",
    )
    return (root, token)


def cleanup_owned_directory(
    path: Path, *, owned_parent: Path, ownership_token: str
) -> None:
    raw = Path(path)
    if not raw.is_absolute() or ".." in raw.parts:
        raise ValueError("cleanup path must be absolute without traversal")
    if _has_symlink(raw):
        raise ValueError("cleanup path must not contain symlinks")
    root = raw.resolve(strict=True)
    parent = Path(owned_parent).resolve(strict=True)
    if root == parent:
        raise ValueError("cleanup path must be a child")
    try:
        root.relative_to(parent)
    except ValueError as exc:
        raise ValueError("cleanup path must stay within owned parent") from exc
    try:
        payload = json.loads((root / OWNERSHIP_MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("cleanup path is not owned") from exc
    if payload != {"schema": "botpipe.owned-staging.v1", "token": ownership_token}:
        raise ValueError("cleanup ownership marker does not match")
    shutil.rmtree(root)


def validate_disjoint_roots(*roots: Path) -> tuple[Path, ...]:
    resolved = tuple(Path(x).resolve() for x in roots)
    for i, left in enumerate(resolved):
        for right in resolved[i + 1 :]:
            if left == right or _under(left, right) or _under(right, left):
                raise ValueError(f"roots must not overlap: {left} and {right}")
    return resolved


def _enumerate(
    root: Path,
    *,
    prefix: str | None,
    excluded: Sequence[Path],
    layer: str,
    max_files: int | None = None,
    max_bytes: int | None = None,
) -> list[dict[str, Any]]:
    records = []
    admitted_bytes = 0

    def visit(directory: Path) -> None:
        nonlocal admitted_bytes
        for entry in sorted(os.scandir(directory), key=lambda e: e.name):
            path = Path(entry.path)
            relative = path.relative_to(root)
            out = (Path(prefix) / relative if prefix else relative).as_posix()
            if any(path == x or _under(path, x) for x in excluded):
                continue
            if entry.is_symlink():
                raise ValueError(f"execution tree source contains a symlink: {out}")
            if entry.is_dir(follow_symlinks=False):
                if entry.name in EXCLUDED_DIRECTORY_NAMES or entry.name.startswith(
                    ".venv"
                ):
                    continue
                visit(path)
                continue
            if not entry.is_file(follow_symlinks=False):
                raise ValueError(
                    f"execution tree source contains a special file: {out}"
                )
            if path.suffix in {".pyc", ".pyo"}:
                continue
            info = entry.stat(follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError(
                    f"execution tree source contains a special file: {out}"
                )
            if max_files is not None and len(records) + 1 > max_files:
                raise ValueError(
                    f"execution tree exceeds max_execution_tree_files={max_files}"
                )
            if max_bytes is not None and admitted_bytes + info.st_size > max_bytes:
                raise ValueError(
                    f"execution tree exceeds max_execution_tree_bytes={max_bytes}"
                )
            admitted_bytes += info.st_size
            records.append(
                {
                    "path": out,
                    "source_path": str(path),
                    "source_layer": layer,
                    "sha256": _sha(path),
                    "size_bytes": info.st_size,
                    "executable": _executable(path),
                }
            )

    visit(root)
    return sorted(records, key=lambda r: str(r["path"]))


def _merge(*groups: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = {}
    for group in groups:
        for record in group:
            path = str(record["path"])
            if path in merged:
                raise ValueError(
                    f"selected package conflicts with project path: {path}"
                )
            merged[path] = record
    return [merged[x] for x in sorted(merged)]


def _copy(source: Path, target: Path) -> None:
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if relative.as_posix() == OWNERSHIP_MARKER:
            continue
        if path.is_symlink():
            raise ValueError(f"frozen tree contains symlink: {relative}")
        if path.is_dir():
            (target / relative).mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            (target / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target / relative, follow_symlinks=False)
        else:
            raise ValueError(f"frozen tree contains special file: {relative}")


def _excluded_roots(root: Path, values: Sequence[Path]) -> tuple[Path, ...]:
    result = []
    for value in values:
        path = Path(value).resolve()
        if path == root:
            raise ValueError("excluded root must not equal source root")
        if _under(path, root):
            result.append(path)
    return tuple(sorted(set(result), key=str))


def _exclusion_payload(values: Sequence[Path]) -> list[str]:
    return sorted(EXCLUDED_DIRECTORY_NAMES) + [
        ".venv*",
        "*.py[cod]",
        *(f"owned:{x.name}" for x in values),
    ]


def _limits(files: int, bytes_: int) -> None:
    if any(
        isinstance(x, bool) or not isinstance(x, int) or x <= 0 for x in (files, bytes_)
    ):
        raise ValueError("execution tree limits must be positive integers")


def _relative(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("path must be non-empty relative string")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() in {"", "."}:
        raise ValueError("path must stay relative")
    return path.as_posix()


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("expected non-empty string")
    return value.strip()


def _sha(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _executable(path: Path) -> bool:
    return (
        bool(path.stat(follow_symlinks=False).st_mode & 73)
        if os.name == "posix"
        else False
    )


def _under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _has_symlink(path: Path, stop: Path | None = None) -> bool:
    current = path.absolute()
    boundary = None if stop is None else stop.absolute()
    while True:
        if current.is_symlink():
            return True
        if boundary is not None and current == boundary:
            return False
        if current.parent == current:
            return False
        current = current.parent


__all__ = [
    "DEFAULT_MAX_EXECUTION_TREE_BYTES",
    "DEFAULT_MAX_EXECUTION_TREE_FILES",
    "ExecutionArm",
    "FrozenExecutionTree",
    "allocate_owned_directory",
    "assert_execution_arm_unchanged",
    "capture_execution_tree",
    "cleanup_owned_directory",
    "derive_execution_tree_manifest",
    "materialize_execution_arm",
    "snapshot_execution_arm",
    "validate_disjoint_roots",
    "verify_frozen_execution_tree",
]
