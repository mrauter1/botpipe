"""Workflow-declared session-path strategy surface."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol

from autoloop.core.extensions import RunBinding


class SessionPathStrategy(Protocol):
    """Resolve one session binding file path for one run."""

    def path_for(self, run_dir: Path, ref_name: str, scope: str | None) -> Path:
        """Return the JSON file path for a session binding."""


class _BoundSessionPaths:
    """No-op bound extension for session-path declarations."""

    def before_step(self, event) -> None:
        return None

    def after_step(self, event) -> None:
        return None

    def on_terminal(self, event) -> None:
        return None


@dataclass(frozen=True, slots=True)
class SessionPaths:
    """Workflow declaration for a generic session-path strategy."""

    strategy: SessionPathStrategy

    def bind(self, binding: RunBinding) -> _BoundSessionPaths:
        return _BoundSessionPaths()


def extract_session_path_strategy(extensions: Iterable[object]) -> SessionPathStrategy | None:
    """Return the single declared session-path strategy, if any."""

    strategy: SessionPathStrategy | None = None
    for extension in extensions:
        if not isinstance(extension, SessionPaths):
            continue
        if strategy is not None:
            raise ValueError("workflow declared multiple SessionPaths extensions")
        strategy = extension.strategy
    return strategy


__all__ = ["SessionPathStrategy", "SessionPaths", "extract_session_path_strategy"]
