"""Optional workflow-facing extensions."""

from .git import GitChange, GitCommitPlan, GitDelta, GitPolicy
from .session_paths import SessionPathStrategy, SessionPaths, extract_session_path_strategy

__all__ = [
    "GitChange",
    "GitCommitPlan",
    "GitDelta",
    "GitPolicy",
    "SessionPathStrategy",
    "SessionPaths",
    "extract_session_path_strategy",
]
