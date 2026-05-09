"""Internal step-plan values.

Not part of the public botlane authoring API.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal, TypeAlias

from .identifiers import ArtifactId


@dataclass(frozen=True, slots=True)
class ExternalRead:
    value: str | Path


@dataclass(frozen=True, slots=True)
class FanInRead:
    helper: Literal["results", "context"]
    path: str


ReadRef: TypeAlias = ArtifactId | ExternalRead | FanInRead
RequireRef: TypeAlias = ArtifactId | FanInRead
WriteRef: TypeAlias = ArtifactId


@dataclass(frozen=True, slots=True)
class StepIO:
    reads: tuple[ReadRef, ...]
    requires: tuple[RequireRef, ...]
    writes: tuple[WriteRef, ...]
    log_artifacts: tuple[WriteRef, ...]


@dataclass(frozen=True, slots=True)
class StepStateSpec:
    step_state_model: type[Any]
    step_state_fields: tuple[str, ...]
    step_item_state_model: type[Any] | None
    step_item_state_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StepHookSpec:
    before: Callable[..., Any] | None = None
    after: Callable[..., Any] | None = None
    before_producer: Callable[..., Any] | None = None
    after_producer: Callable[..., Any] | None = None
    before_verifier: Callable[..., Any] | None = None
    after_verifier: Callable[..., Any] | None = None


@dataclass(frozen=True, slots=True)
class StepHeader:
    name: str
    kind: str
    original_step: Any
    session_name: str | None
    scope_name: str | None
    io: StepIO
    state: StepStateSpec
    hooks: StepHookSpec
    provider_policy: Any


ProviderTurnKind: TypeAlias = Literal["llm", "producer", "verifier", "operation"]


@dataclass(frozen=True, slots=True)
class ProviderTurnPlan:
    kind: ProviderTurnKind
    prompt: Any
    session_name: str | None
    io: StepIO
    retry_policy: Any
    expected_output_schema: dict[str, Any] | None
    expected_output_validator: Any | None


@dataclass(frozen=True, slots=True)
class PromptStepPlan:
    header: StepHeader
    turn: ProviderTurnPlan


@dataclass(frozen=True, slots=True)
class ProduceVerifyStepPlan:
    header: StepHeader
    producer: ProviderTurnPlan
    verifier: ProviderTurnPlan
    verifier_session_name: str | None


@dataclass(frozen=True, slots=True)
class PythonStepPlan:
    header: StepHeader
    handler: Callable[..., Any]


@dataclass(frozen=True, slots=True)
class ChildWorkflowStepPlan:
    header: StepHeader
    workflow: Any
    message: Any
    message_from: Any
    params: dict[str, Any]
    input: Any


@dataclass(frozen=True, slots=True)
class BranchPlan:
    name: str
    index: int
    input: Any
    step: StepPlan


@dataclass(frozen=True, slots=True)
class BranchGroupPlan:
    name: str
    kind: str
    branches: tuple[BranchPlan, ...]
    concurrency: int | None
    settle: str
    success_routes: tuple[str, ...]
    outcome: str | Callable[..., Any] | None
    fan_in_step: StepPlan | None
    composite_route_tags: tuple[str, ...]
    default_chain_route: str
    rework_chain_route: str | None = None


@dataclass(frozen=True, slots=True)
class BranchGroupStepPlan:
    header: StepHeader
    branch_group: BranchGroupPlan


StepPlan: TypeAlias = (
    PromptStepPlan
    | ProduceVerifyStepPlan
    | PythonStepPlan
    | ChildWorkflowStepPlan
    | BranchGroupStepPlan
)
