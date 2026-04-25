"""Strict workflow primitive shim."""

from __future__ import annotations

try:  # pragma: no branch - prefer installed-package imports when available
    from autoloop_v3.core.primitives import Checkpoint, Event, Outcome, ResolvedArtifacts
    from autoloop_v3.core.context import ChildWorkflowResult
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from core.primitives import Checkpoint, Event, Outcome, ResolvedArtifacts
    from core.context import ChildWorkflowResult

__all__ = [
    "ChildWorkflowResult",
    "Checkpoint",
    "Event",
    "Outcome",
    "ResolvedArtifacts",
]
