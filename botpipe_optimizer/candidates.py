"""Safe candidate workspaces and isolated executable validation."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class CandidateFile:
    relative_path: str
    authoritative_path: str
    baseline_sha256: str | None
    candidate_sha256: str | None
    changed: bool
    size_bytes: int


@dataclass(frozen=True, slots=True)
class CandidateWorkspace:
    repo_root: Path
    root: Path
    baseline_root: Path
    candidate_root: Path
    allowed_paths: tuple[str, ...]
    allowed_roots: tuple[str, ...]
    authoritative_hashes: dict[str, str]
    # Exact new files, absent from the authoritative workspace and its baseline.
    allowed_added_paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CandidateManifest:
    files: tuple[CandidateFile, ...]
    changed_paths: tuple[str, ...]
    unchanged_paths: tuple[str, ...]
    added_paths: tuple[str, ...]
    removed_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    stdout_truncated: bool = False
    stderr_truncated: bool = False


@dataclass(frozen=True, slots=True)
class CandidateEvaluationReport:
    manifest: CandidateManifest
    command: CommandResult
    authoritative_sources_unchanged: bool

    @property
    def ok(self) -> bool:
        return self.command.returncode == 0 and not self.command.timed_out

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def prepare_candidate_workspace(
    repo_root: str | Path,
    relative_paths: Sequence[str | Path],
    destination: str | Path,
    *,
    max_files: int = 100000,
    max_bytes: int = 512 * 1024 * 1024,
) -> CandidateWorkspace:
    """Snapshot allowed repo files or package trees into baseline and candidate roots."""
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in (max_files, max_bytes)
    ):
        raise ValueError("candidate snapshot limits must be positive integers")
    repo = Path(repo_root).resolve()
    if not repo.is_dir():
        raise FileNotFoundError(f"repository root does not exist: {repo}")
    requested = tuple(sorted({_safe_relative(path) for path in relative_paths}))
    if not requested:
        raise ValueError("relative_paths must contain at least one file")
    destination_path = Path(destination).expanduser()
    _reject_symlink_alias(destination_path)
    root = destination_path.resolve()
    if root == repo or repo.is_relative_to(root):
        raise ValueError(
            "candidate destination must not be the repository or its ancestor"
        )
    paths: set[str] = set()
    allowed_roots: set[str] = set()
    for relative in requested:
        source = _ordinary_path(repo, relative)
        if source.is_dir():
            allowed_roots.add(relative)
            paths.update(_ordinary_tree_files(repo, source))
        else:
            paths.add(relative)
    if not paths:
        raise ValueError("candidate surface must contain at least one ordinary file")
    ordered_paths = tuple(sorted(paths))
    if len(ordered_paths) > max_files:
        raise ValueError(f"candidate baseline exceeds max_files={max_files}")
    total_bytes = sum(
        _ordinary_source(repo, relative).stat().st_size for relative in ordered_paths
    )
    if total_bytes > max_bytes:
        raise ValueError(f"candidate baseline exceeds max_bytes={max_bytes}")
    hashes: dict[str, str] = {}
    for relative in ordered_paths:
        source = _ordinary_source(repo, relative)
        if source.is_relative_to(root):
            raise ValueError(
                f"candidate destination contains authoritative source: {relative}"
            )
        hashes[relative] = _digest(source)
    _reset_managed_root(root)
    marker = {
        "managed_by": "botpipe-candidate-v1",
        "repo_root": str(repo),
        "requested_paths": list(requested),
        "allowed_paths": list(ordered_paths),
        "allowed_roots": sorted(allowed_roots),
        "authoritative_hashes": hashes,
    }
    (root / ".botpipe-candidate.json").write_text(
        json.dumps(marker, sort_keys=True),
        encoding="utf-8",
    )
    baseline, candidate = root / "baseline", root / "candidate"
    for relative in ordered_paths:
        source = _ordinary_source(repo, relative)
        for target_root in (baseline, candidate):
            target = target_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    return CandidateWorkspace(
        repo,
        root,
        baseline,
        candidate,
        ordered_paths,
        tuple(sorted(allowed_roots)),
        hashes,
    )


def candidate_manifest(workspace: CandidateWorkspace) -> CandidateManifest:
    """Hash candidate modifications, additions, and removals inside its bounded surface."""
    actual = _surface_files(workspace.candidate_root)
    baseline = set(workspace.allowed_paths)
    outside = sorted(
        relative
        for relative in actual - baseline
        if relative not in workspace.allowed_added_paths
        and not any(
            Path(relative).is_relative_to(root) for root in workspace.allowed_roots
        )
    )
    if outside:
        raise ValueError(
            f"candidate surface contains paths outside the allowlist: {', '.join(outside)}"
        )
    files: list[CandidateFile] = []
    for relative in sorted(actual | baseline):
        candidate = workspace.candidate_root / relative
        candidate_hash = _digest(candidate) if relative in actual else None
        baseline_hash = workspace.authoritative_hashes.get(relative)
        files.append(
            CandidateFile(
                relative,
                str((workspace.repo_root / relative).resolve()),
                baseline_hash,
                candidate_hash,
                candidate_hash != baseline_hash,
                candidate.stat().st_size if candidate_hash is not None else 0,
            )
        )
    changed = tuple(item.relative_path for item in files if item.changed)
    return CandidateManifest(
        tuple(files),
        changed,
        tuple(item.relative_path for item in files if not item.changed),
        tuple(item.relative_path for item in files if item.baseline_sha256 is None),
        tuple(item.relative_path for item in files if item.candidate_sha256 is None),
    )


def validate_authoritative_sources_unchanged(workspace: CandidateWorkspace) -> None:
    """Fail when original sources drift or a bounded authoritative tree changes shape."""
    for relative in workspace.allowed_added_paths:
        source = workspace.repo_root / relative
        if source.exists() or source.is_symlink():
            raise ValueError(
                f"authoritative source appeared at generated target: {relative}"
            )
    for relative, expected in workspace.authoritative_hashes.items():
        source = _ordinary_source(workspace.repo_root, relative)
        actual = _digest(source)
        if actual != expected:
            raise ValueError(
                f"authoritative source changed during candidate work: {relative}"
            )
    baseline_paths = set(workspace.allowed_paths)
    for relative_root in workspace.allowed_roots:
        current = _ordinary_tree_files(
            workspace.repo_root, workspace.repo_root / relative_root
        )
        expected = {
            relative
            for relative in baseline_paths
            if Path(relative).is_relative_to(relative_root)
        }
        if current != expected:
            added = sorted(current - expected)
            removed = sorted(expected - current)
            details = []
            if added:
                details.append(f"added: {', '.join(added)}")
            if removed:
                details.append(f"removed: {', '.join(removed)}")
            raise ValueError(
                f"authoritative source tree changed during candidate work ({'; '.join(details)})"
            )


def evaluate_candidate_workspace(
    workspace: CandidateWorkspace,
    argv: Sequence[str],
    *,
    timeout: float = 300,
    max_stream_bytes: int = 1024 * 1024,
) -> CandidateEvaluationReport:
    """Execute one bounded command against a private, manifest-checked candidate tree.

    A private working directory and import isolation are not an OS sandbox.
    Call this effect through a non-retry-safe activity when used in a workflow.
    """
    from .execution_trees import (
        assert_execution_arm_unchanged,
        materialize_execution_arm,
        snapshot_execution_arm,
    )
    from .processes import run_bounded_process

    command = _argv(argv)
    with tempfile.TemporaryDirectory(prefix="botpipe-candidate-eval-") as temporary:
        parent = Path(temporary)
        bundle = freeze_candidate_workspace(workspace, parent)
        candidate = candidate_surface_manifest(workspace, bundle)
        manifest = candidate_manifest(workspace)
        arm = materialize_execution_arm(
            bundle.snapshot,
            parent,
            candidate_manifest=candidate,
            removed_paths=manifest.removed_paths,
        )
        expected = snapshot_execution_arm(arm)
        process = run_bounded_process(
            command,
            cwd=arm.root,
            timeout_seconds=timeout,
            max_stream_bytes=max_stream_bytes,
        )
        assert_execution_arm_unchanged(expected, arm.root, phase="candidate command")
        validate_authoritative_sources_unchanged(workspace)
        result = CommandResult(
            command,
            process.exit_code if process.exit_code is not None else -1,
            process.stdout,
            process.stderr,
            process.timed_out,
            process.stdout_truncated,
            process.stderr_truncated,
        )
        return CandidateEvaluationReport(manifest, result, True)


@dataclass(frozen=True, slots=True)
class FrozenCandidateBundle:
    """Captured baseline shared by concrete validation and optional paired evaluation."""

    snapshot: Any
    baseline_surface_manifest: dict[str, Any]
    boundary: dict[str, Any]


def freeze_candidate_workspace(
    workspace: CandidateWorkspace,
    owned_parent: Path,
    *,
    boundary: dict[str, Any] | None = None,
    selected_package_root: Path | None = None,
    selected_package_import_path: str | None = None,
    execution_source_root: Path | None = None,
    max_files: int = 100000,
    max_bytes: int = 512 * 1024 * 1024,
) -> FrozenCandidateBundle:
    """Freeze source before candidate editing; keep this result for the whole run."""
    from .execution_trees import capture_execution_tree
    from .surface_identity import derive_surface_manifest

    validate_authoritative_sources_unchanged(workspace)
    identity_boundary = dict(
        boundary
        or {
            "editable_paths": list(workspace.allowed_paths),
            "editable_roots": list(workspace.allowed_roots),
        }
    )
    if workspace.allowed_added_paths:
        identity_boundary["added_paths"] = list(workspace.allowed_added_paths)
    baseline_kind = identity_boundary.pop("surface_kind", "baseline")
    baseline = derive_surface_manifest(
        workspace.baseline_root,
        expected_root=workspace.baseline_root,
        boundary=identity_boundary,
        surface_kind=baseline_kind,
    )
    # Baseline bytes are independently checked against the originally captured source.
    for entry in baseline["files"]:
        if (
            workspace.authoritative_hashes.get(entry["relative_path"])
            != entry["surface_sha256"]
        ):
            raise ValueError("baseline candidate snapshot changed")
        source = workspace.repo_root / entry["relative_path"]
        executable = (
            bool(source.stat().st_mode & 0o111) if os.name == "posix" else False
        )
        if executable != entry["executable"]:
            raise ValueError(
                "authoritative source executable mode changed before freezing"
            )
    if set(baseline["relative_paths"]) != set(workspace.allowed_paths):
        raise ValueError("baseline candidate file inventory changed")
    snapshot = capture_execution_tree(
        execution_source_root or workspace.repo_root,
        owned_parent,
        selected_package_root=selected_package_root,
        selected_package_import_path=selected_package_import_path,
        excluded_roots=(workspace.root,),
        max_files=max_files,
        max_bytes=max_bytes,
    )
    return FrozenCandidateBundle(snapshot, baseline, identity_boundary)


def candidate_surface_manifest(
    workspace: CandidateWorkspace, bundle: FrozenCandidateBundle
) -> dict[str, Any]:
    """Derive current candidate files and bind them to the frozen edit allowlist."""
    from .execution_trees import verify_frozen_execution_tree
    from .surface_identity import derive_surface_manifest, validate_surface_manifest

    validate_authoritative_sources_unchanged(workspace)
    verify_frozen_execution_tree(bundle.snapshot)
    manifest = candidate_manifest(workspace)
    derived = derive_surface_manifest(
        workspace.candidate_root,
        expected_root=workspace.candidate_root,
        boundary=bundle.boundary,
        surface_kind="candidate",
    )
    return validate_surface_manifest(
        derived,
        expected_root=workspace.candidate_root,
        expected_boundary=bundle.boundary,
        expected_surface_kind="candidate",
        baseline_manifest=bundle.baseline_surface_manifest,
        allowed_added_path_prefixes=workspace.allowed_roots,
        allowed_added_exact_paths=workspace.allowed_added_paths,
        allowed_removed_paths=manifest.removed_paths,
    )


def validate_candidate(
    workspace: CandidateWorkspace,
    bundle: FrozenCandidateBundle,
    *,
    workflow_refs: Sequence[str],
    staging_parent: Path,
    target_test_argv: Sequence[str] | None = None,
    target_test_command: str | None = None,
    **limits: Any,
):
    """Import concrete native workflows and optionally execute tests in fresh staging."""
    from .candidate_validation import validate_frozen_candidate

    candidate = candidate_surface_manifest(workspace, bundle)
    return validate_frozen_candidate(
        bundle.snapshot,
        baseline_surface_manifest=bundle.baseline_surface_manifest,
        candidate_surface_manifest=candidate,
        expected_baseline_root=workspace.baseline_root,
        expected_candidate_root=workspace.candidate_root,
        expected_boundary=bundle.boundary,
        baseline_surface_kind=bundle.baseline_surface_manifest["surface_kind"],
        candidate_surface_kind="candidate",
        workflow_refs=workflow_refs,
        staging_parent=staging_parent,
        allowed_added_path_prefixes=workspace.allowed_roots,
        allowed_added_exact_paths=workspace.allowed_added_paths,
        allowed_removed_paths=candidate_manifest(workspace).removed_paths,
        target_test_argv=target_test_argv,
        target_test_command=target_test_command,
        **limits,
    )


def repository_root_for(
    source_path: str | Path, preferred: str | Path | None = None
) -> Path:
    """Find the nearest repository/package root that contains a selected source file."""
    source = Path(source_path).resolve()
    if preferred is not None:
        candidate = Path(preferred).resolve()
        if source.is_relative_to(candidate):
            return candidate
    for parent in (source.parent, *source.parents):
        if (parent / "pyproject.toml").is_file() or (parent / ".git").exists():
            return parent
    return source.parent


def _safe_relative(value: str | Path) -> str:
    path = Path(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"candidate path must stay repo-relative: {value}")
    if path.parts[0] in {".git", ".botpipe"} or "__pycache__" in path.parts:
        raise ValueError(f"candidate path targets protected runtime state: {value}")
    return path.as_posix()


def _ordinary_source(repo: Path, relative: str) -> Path:
    resolved = _ordinary_path(repo, relative)
    if not resolved.is_file():
        raise FileNotFoundError(
            f"candidate source is not an ordinary repo file: {relative}"
        )
    return resolved


def _ordinary_path(repo: Path, relative: str) -> Path:
    candidate = repo / relative
    if candidate.is_symlink() or any(
        parent.is_symlink() for parent in candidate.parents if parent != repo.parent
    ):
        raise ValueError(f"candidate source path contains a symlink: {relative}")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(repo) or not resolved.exists():
        raise FileNotFoundError(
            f"candidate source does not exist in the repo: {relative}"
        )
    return resolved


def _ordinary_tree_files(repo: Path, root: Path) -> set[str]:
    files: set[str] = set()
    for path in root.rglob("*"):
        relative_parts = path.relative_to(root).parts
        if any(
            part in {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
            for part in relative_parts
        ):
            continue
        if path.is_symlink():
            raise ValueError(f"candidate source tree contains a symlink: {path}")
        if path.is_file():
            files.add(path.relative_to(repo).as_posix())
    return files


def _reset_managed_root(root: Path) -> None:
    if not root.exists():
        root.mkdir(parents=True)
        return
    if not root.is_dir():
        raise ValueError(f"candidate destination is not a directory: {root}")
    marker = root / ".botpipe-candidate.json"
    if not marker.is_file():
        if any(root.iterdir()):
            raise ValueError(
                f"candidate destination already exists and is not managed: {root}"
            )
    else:
        try:
            record = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(
                f"candidate destination has an invalid management marker: {root}"
            ) from error
        if record.get("managed_by") != "botpipe-candidate-v1":
            raise ValueError(
                f"candidate destination is not managed by this optimizer: {root}"
            )
        shutil.rmtree(root)
        root.mkdir(parents=True)


def _reject_symlink_alias(path: Path) -> None:
    absolute = path if path.is_absolute() else Path.cwd() / path
    for candidate in (absolute, *absolute.parents):
        if candidate.is_symlink():
            raise ValueError(f"candidate destination contains a symlink alias: {path}")


def _surface_files(root: Path) -> set[str]:
    result: set[str] = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if path.name == ".botpipe-workspace.lock" or any(
            part in {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
            for part in relative.parts
        ):
            continue
        if path.is_symlink():
            raise ValueError(f"candidate surface contains a symlink: {path}")
        if path.is_file():
            result.add(relative.as_posix())
    return result


def _argv(value: Sequence[str]) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(
            "validation command must be an argv sequence, not a shell string"
        )
    result = tuple(value)
    if not result or any(not isinstance(item, str) or not item for item in result):
        raise ValueError("validation argv must contain non-empty strings")
    return result


def _ignore_runtime_state(_directory: str, names: list[str]) -> set[str]:
    ignored = {
        ".git",
        ".botpipe",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "__pycache__",
        ".venv",
    }
    return set(names) & ignored


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "CandidateEvaluationReport",
    "CandidateFile",
    "CandidateManifest",
    "CandidateWorkspace",
    "CommandResult",
    "FrozenCandidateBundle",
    "candidate_manifest",
    "candidate_surface_manifest",
    "evaluate_candidate_workspace",
    "freeze_candidate_workspace",
    "prepare_candidate_workspace",
    "repository_root_for",
    "validate_authoritative_sources_unchanged",
    "validate_candidate",
]
