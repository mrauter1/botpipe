"""Generic git repository mechanics for workflow-declared tracking."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .policy import GitChange, GitCommitPlan, GitDelta


class GitRepoError(RuntimeError):
    """Git repository operation failed."""


_REPO_SELECTION_ENV_VARS = frozenset(
    {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CEILING_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_DIR",
        "GIT_INDEX_FILE",
        "GIT_NAMESPACE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_PREFIX",
        "GIT_SUPER_PREFIX",
        "GIT_WORK_TREE",
    }
)


@dataclass(frozen=True, slots=True)
class GitRepo:
    """Thin wrapper around one discovered git repository."""

    root: Path

    @classmethod
    def discover(cls, start: Path) -> "GitRepo | None":
        result = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
            env=_git_environment(),
        )
        if result.returncode != 0:
            return None
        return cls(Path(result.stdout.strip()).resolve())

    def raw_delta(self) -> GitDelta:
        output = self.status_porcelain()
        changes: list[GitChange] = []
        for line in output.splitlines():
            if not line:
                continue
            status = line[:2]
            path_data = line[3:]
            original_path = None
            path = path_data
            if " -> " in path_data:
                original_path, path = path_data.split(" -> ", 1)
            changes.append(GitChange(status=status, path=path, original_path=original_path))
        return GitDelta(tuple(changes))

    def status_porcelain(self) -> str:
        return self._git("status", "--porcelain=v1", "--untracked-files=all")

    def is_dirty(self) -> bool:
        return bool(self.status_porcelain().strip())

    def add_all(self) -> None:
        self._git("add", "--all")

    def commit_all(self, message: str) -> tuple[str, bool]:
        self.add_all()
        staged_paths = self.staged_paths()
        if not staged_paths:
            return self.head(), False
        self._git("commit", "-m", message)
        return self.head(), True

    def commit(self, plan: GitCommitPlan, *, pathspecs: Sequence[str]) -> str | None:
        selected_paths = tuple(path for path in pathspecs if path)
        if selected_paths:
            self._git("add", "--", *selected_paths)
        staged_paths = self.staged_paths()
        if not selected_paths:
            if staged_paths:
                return None
            if not plan.allow_empty:
                return None
            self._git("commit", "--allow-empty", "-m", plan.message)
            return self.head()
        if self._staged_paths_outside_scope(staged_paths, selected_paths):
            raise GitRepoError("refusing to commit staged changes outside the selected git tracking scope")
        if not staged_paths and not plan.allow_empty:
            return None
        commit_args = ["commit", "-m", plan.message]
        if not staged_paths and plan.allow_empty:
            commit_args.append("--allow-empty")
        self._git(*commit_args)
        return self.head()

    def staged_paths(self) -> tuple[str, ...]:
        output = self._git("diff", "--cached", "--name-only", "--relative")
        return tuple(line.strip() for line in output.splitlines() if line.strip())

    def head(self) -> str:
        return self._git("rev-parse", "HEAD").strip()

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.root), *args],
            capture_output=True,
            text=True,
            check=False,
            env=_git_environment(),
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            stdout = result.stdout.strip()
            detail = stderr or stdout or f"git {' '.join(args)!r} failed"
            raise GitRepoError(detail)
        return result.stdout

    @staticmethod
    def _staged_paths_outside_scope(staged_paths: Sequence[str], scopes: Sequence[str]) -> bool:
        normalized = tuple(_normalize_scope(scope) for scope in scopes if scope)
        for path in staged_paths:
            if not any(_path_within_scope(path, scope) for scope in normalized):
                return True
        return False


def _normalize_scope(scope: str) -> str:
    if scope in {"", "."}:
        return "."
    return scope.strip("/")


def _path_within_scope(path: str, scope: str) -> bool:
    if scope == ".":
        return True
    return path == scope or path.startswith(scope + "/")


def _git_environment() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key not in _REPO_SELECTION_ENV_VARS}
