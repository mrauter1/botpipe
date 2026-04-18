"""Optional cross-cutting extensions."""

from .git import GitChange, GitCommitPlan, GitDelta, GitPolicy, GitTracking, GitTrackingConfig
from .session_paths import SessionPathStrategy, SessionPaths, extract_session_path_strategy
from .tracing import Tracing, TracingConfig

__all__ = [
    "GitChange",
    "GitCommitPlan",
    "GitDelta",
    "GitPolicy",
    "GitTracking",
    "GitTrackingConfig",
    "SessionPathStrategy",
    "SessionPaths",
    "Tracing",
    "TracingConfig",
    "extract_session_path_strategy",
]
