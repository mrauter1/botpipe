"""Minimal workflow-declared extension seam."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from .primitives import Event, Outcome


@dataclass(frozen=True, slots=True)
class RunBinding:
    """Filesystem and identity facts for one bound run."""

    root: Path
    task_id: str
    run_id: str
    workflow_name: str
    task_folder: Path
    run_folder: Path


@dataclass(frozen=True, slots=True)
class StepStart:
    """Immutable snapshot emitted before a step runs."""

    binding: RunBinding
    step_name: str
    step_kind: str
    state: BaseModel


@dataclass(frozen=True, slots=True)
class StepFinish:
    """Immutable snapshot emitted after a step runs."""

    binding: RunBinding
    step_name: str
    step_kind: str
    state_before: BaseModel
    state_after: BaseModel
    event: Event
    outcome: Outcome | None


@dataclass(frozen=True, slots=True)
class TerminalFinish:
    """Immutable snapshot emitted when a run reaches a terminal state."""

    binding: RunBinding
    terminal: str
    step_name: str | None
    state: BaseModel | None
    event: Event | None
    outcome: Outcome | None


class BoundWorkflowExtension(Protocol):
    """Per-run bound extension hooks."""

    def before_step(self, event: StepStart) -> None:
        """Run before step execution."""

    def after_step(self, event: StepFinish) -> None:
        """Run after step execution."""

    def on_terminal(self, event: TerminalFinish) -> None:
        """Run when execution reaches a terminal state."""


class WorkflowExtension(Protocol):
    """Workflow-declared extension factory."""

    def bind(self, binding: RunBinding) -> BoundWorkflowExtension:
        """Bind one extension instance to one run."""


__all__ = [
    "BoundWorkflowExtension",
    "RunBinding",
    "StepFinish",
    "StepStart",
    "TerminalFinish",
    "WorkflowExtension",
]
