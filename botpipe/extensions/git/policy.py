"""Typed git delta and policy contracts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from botpipe.core.extensions import StepFinish, StepStart, TerminalFinish


@dataclass(frozen=True, slots=True)
class GitChange:
    """One raw repository change."""

    # Raw two-column git porcelain v1 XY status.
    status: str
    path: str
    original_path: str | None = None


@dataclass(frozen=True, slots=True)
class GitDelta:
    """Raw git delta for one repository snapshot."""

    changes: tuple[GitChange, ...] = ()

    def is_empty(self) -> bool:
        return not self.changes


@dataclass(frozen=True, slots=True)
class GitCommitPlan:
    """Workflow-owned commit intent for the git extension."""

    message: str
    include_paths: tuple[str, ...] = ()
    allow_empty: bool = False


class GitPolicy(Protocol):
    """Workflow-owned git commit policy."""

    def before_step(self, event: StepStart) -> Sequence[GitCommitPlan]:
        """Return any commit plans that should run before the step."""

    def after_step(self, event: StepFinish, delta: GitDelta) -> Sequence[GitCommitPlan]:
        """Return any commit plans that should run after the step."""

    def on_terminal(self, event: TerminalFinish, delta: GitDelta | None) -> Sequence[GitCommitPlan]:
        """Return any commit plans that should run on terminal completion."""
