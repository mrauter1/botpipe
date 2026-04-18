"""Optional git tracking extension surface."""

from .declaration import GitTracking, GitTrackingConfig
from .filters import (
    delta_pathspecs,
    filter_delta_by_pathspecs,
    filter_delta_by_prefixes,
    pathspec_from_path,
    task_workspace_pathspec,
)
from .policy import GitChange, GitCommitPlan, GitDelta, GitPolicy
from .repo import GitRepo, GitRepoError

__all__ = [
    "GitChange",
    "GitCommitPlan",
    "GitDelta",
    "GitPolicy",
    "GitRepo",
    "GitRepoError",
    "GitTracking",
    "GitTrackingConfig",
    "delta_pathspecs",
    "filter_delta_by_pathspecs",
    "filter_delta_by_prefixes",
    "pathspec_from_path",
    "task_workspace_pathspec",
]
