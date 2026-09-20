"""Safe candidate workspaces and isolated executable validation."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
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
) -> CandidateWorkspace:
    """Snapshot allowed repo files or package trees into baseline and candidate roots."""
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
        if not any(
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
) -> CandidateEvaluationReport:
    """Overlay the candidate into an isolated repo copy and execute an argv command."""
    command = _argv(argv)
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    validate_authoritative_sources_unchanged(workspace)
    manifest = candidate_manifest(workspace)
    with tempfile.TemporaryDirectory(prefix="botpipe-candidate-eval-") as temporary:
        overlay = Path(temporary) / "repo"
        shutil.copytree(
            workspace.repo_root, overlay, symlinks=False, ignore=_ignore_runtime_state
        )
        for relative in manifest.removed_paths:
            target = overlay / relative
            if target.exists():
                target.unlink()
        for relative in _surface_files(workspace.candidate_root):
            source = workspace.candidate_root / relative
            target = overlay / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        stdout_path, stderr_path = (
            Path(temporary) / "stdout",
            Path(temporary) / "stderr",
        )
        with (
            stdout_path.open("w+", encoding="utf-8") as stdout_file,
            stderr_path.open(
                "w+",
                encoding="utf-8",
            ) as stderr_file,
        ):
            process = subprocess.Popen(
                command,
                cwd=overlay,
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
                start_new_session=os.name == "posix",
            )
            timed_out = False
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                _terminate_process_group(process)
                process.wait()
                returncode = -1
            except BaseException:
                _terminate_process_group(process)
                process.wait()
                raise
            else:
                # A successful command can leave servers or test workers in its process group.
                _terminate_process_group(process, direct_process_finished=True)
            stdout_file.seek(0)
            stderr_file.seek(0)
            result = CommandResult(
                command,
                returncode,
                stdout_file.read(),
                stderr_file.read(),
                timed_out,
            )
    validate_authoritative_sources_unchanged(workspace)
    return CandidateEvaluationReport(manifest, result, True)


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


def _terminate_process_group(
    process: subprocess.Popen[str],
    *,
    direct_process_finished: bool = False,
) -> None:
    if os.name != "posix":
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
        return

    def send(sig: signal.Signals) -> bool:
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return False
        return True

    if not send(signal.SIGTERM):
        return
    deadline = time.monotonic() + (0.2 if direct_process_finished else 1.0)
    while time.monotonic() < deadline:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.01)
    send(signal.SIGKILL)


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
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "CandidateEvaluationReport",
    "CandidateFile",
    "CandidateManifest",
    "CandidateWorkspace",
    "CommandResult",
    "candidate_manifest",
    "evaluate_candidate_workspace",
    "prepare_candidate_workspace",
    "repository_root_for",
    "validate_authoritative_sources_unchanged",
]
