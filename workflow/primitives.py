"""Strict workflow primitive shim."""

from __future__ import annotations

try:  # pragma: no branch - prefer installed-package imports when available
    from autoloop_v3.core.primitives import Checkpoint, Event, Outcome, ResolvedArtifacts
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from core.primitives import Checkpoint, Event, Outcome, ResolvedArtifacts

__all__ = [
    "Checkpoint",
    "Event",
    "Outcome",
    "ResolvedArtifacts",
]
