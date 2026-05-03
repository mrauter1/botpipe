"""Minimal workflow-declared extension seam."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel

from .primitives import Event, Outcome
from .providers.models import StepProviderUsage

ExtensionFailurePolicy = Literal["propagate", "record_and_continue"]


@dataclass(frozen=True, slots=True)
class RunBinding:
    """Filesystem and identity facts for one bound run."""

    root: Path
    task_id: str
    run_id: str
    workflow_name: str
    task_folder: Path
    workflow_folder: Path
    run_folder: Path
    package_folder: Path


@dataclass(frozen=True, slots=True)
class StepStart:
    """Immutable snapshot emitted before a step runs."""

    binding: RunBinding
    step_name: str
    step_kind: str
    state: BaseModel
    answer: str | None = None
    visit: int | None = None
    step_execution_id: str | None = None
    scope: str | None = None
    item_id: str | None = None


@dataclass(frozen=True, slots=True)
class HookRouteRedirect:
    """One hook-driven route redirect hop."""

    hook: str
    phase: str
    from_route: str
    to_route: str
    redirect_index: int | None = None


@dataclass(frozen=True, slots=True)
class StepFinish:
    """Immutable snapshot emitted after a step runs."""

    binding: RunBinding
    step_name: str
    step_kind: str
    state_before: BaseModel
    state_after: BaseModel
    event: Event | None
    outcome: Outcome | None
    producer_raw_output: str | None = None
    verifier_raw_output: str | None = None
    provider_usage: StepProviderUsage | None = None
    candidate_route: str | None = None
    final_route: str | None = None
    runtime_control: str | None = None
    pending_input_id: str | None = None
    target_step: str | None = None
    terminal: str | None = None
    provider_attributable: bool | None = None
    provider_attempted: bool | None = None
    producer_attempted: bool | None = None
    verifier_attempted: bool | None = None
    source_hook: str | None = None
    source_phase: str | None = None
    hook_route_override_from: str | None = None
    hook_route_override_to: str | None = None
    hook_route_redirects: tuple[HookRouteRedirect, ...] = ()
    visit: int | None = None
    step_execution_id: str | None = None
    scope: str | None = None
    item_id: str | None = None


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
    "ExtensionFailurePolicy",
    "HookRouteRedirect",
    "RunBinding",
    "StepFinish",
    "StepStart",
    "TerminalFinish",
    "WorkflowExtension",
]
