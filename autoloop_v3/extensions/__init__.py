"""Optional cross-cutting extensions."""

from .session_paths import SessionPathStrategy, SessionPaths, extract_session_path_strategy

__all__ = ["SessionPathStrategy", "SessionPaths", "extract_session_path_strategy"]
