"""Git delta filtering helpers kept separate from raw repo inspection."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from botpipe.core.extensions import RunBinding
from .policy import GitChange, GitDelta


def pathspec_from_path(repo_root: Path, path: Path) -> str | None:
    """Return a repo-relative pathspec for an absolute path."""

    try:
        relative = path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return None
    return relative.as_posix() or "."


def workflow_workspace_pathspec(repo_root: Path, binding: RunBinding) -> str | None:
    """Return the workflow-workspace pathspec for one bound run."""

    return pathspec_from_path(repo_root, binding.workflow_folder)


def filter_delta_by_prefixes(delta: GitDelta, prefixes: Iterable[str]) -> GitDelta:
    """Select changes whose paths live under any repo-relative prefix."""

    normalized = tuple(_normalize_pathspec(prefix) for prefix in prefixes if prefix)
    if not normalized:
        return GitDelta()
    return GitDelta(
        tuple(change for change in delta.changes if _change_matches_prefixes(change, normalized))
    )


def filter_delta_by_pathspecs(delta: GitDelta, pathspecs: Iterable[str]) -> GitDelta:
    """Select changes that match explicit repo-relative pathspecs."""

    normalized = tuple(_normalize_pathspec(pathspec) for pathspec in pathspecs if pathspec)
    if not normalized:
        return GitDelta()
    return GitDelta(
        tuple(change for change in delta.changes if _change_matches_prefixes(change, normalized))
    )


def delta_pathspecs(delta: GitDelta) -> tuple[str, ...]:
    """Return unique repo-relative pathspecs covering the delta."""

    seen: set[str] = set()
    ordered: list[str] = []
    for change in delta.changes:
        for candidate in (change.path, change.original_path):
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            ordered.append(candidate)
    return tuple(ordered)


def _change_matches_prefixes(change: GitChange, prefixes: tuple[str, ...]) -> bool:
    return any(
        _matches_prefix(change.path, prefix) or _matches_prefix(change.original_path, prefix)
        for prefix in prefixes
    )


def _matches_prefix(candidate: str | None, prefix: str) -> bool:
    if candidate is None:
        return False
    if prefix in {"", "."}:
        return True
    return candidate == prefix or candidate.startswith(prefix + "/")


def _normalize_pathspec(pathspec: str) -> str:
    stripped = pathspec.strip()
    if stripped in {"", "."}:
        return "."
    return stripped.strip("/")
