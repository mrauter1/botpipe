"""Internal step-plan values.

Not part of the public botpipe authoring API.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Literal, TypeAlias

from .identifiers import ArtifactId
from .providers.retries import ProviderRetryPolicy

if TYPE_CHECKING:
    from .route_contracts import RouteContract


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
class StepSource:
    authoring_kind: str
    declaration_name: str | None = None
    source_module: str | None = None
    source_qualname: str | None = None


@dataclass(frozen=True, slots=True)
class StepHeader:
    name: str
    kind: str
    source: StepSource | None
    session_name: str | None
    scope_name: str | None
    io: StepIO
    state: StepStateSpec
    hooks: StepHookSpec
    provider_policy: Any


ProviderTurnKind: TypeAlias = Literal["llm", "producer", "verifier"]


@dataclass(frozen=True, slots=True)
class ProviderTurnPlan:
    kind: ProviderTurnKind
    prompt: Any
    session_name: str | None
    io: StepIO
    retry_policy: Any
    expected_output_schema: dict[str, Any] | None
    expected_output_validator: Any | None


class _BaseStepPlan:
    header: StepHeader

    @property
    def name(self) -> str:
        return self.header.name

    @property
    def kind(self) -> str:
        return self.header.kind

    @property
    def source(self) -> StepSource | None:
        return self.header.source

    @property
    def session_name(self) -> str | None:
        return self.header.session_name

    @property
    def scope_name(self) -> str | None:
        return self.header.scope_name

    @property
    def io(self) -> StepIO:
        return self.header.io

    @property
    def reads(self) -> tuple[ReadRef, ...]:
        return self.header.io.reads

    @property
    def requires(self) -> tuple[RequireRef, ...]:
        return self.header.io.requires

    @property
    def writes(self) -> tuple[WriteRef, ...]:
        return self.header.io.writes

    @property
    def log_artifacts(self) -> tuple[WriteRef, ...]:
        return self.header.io.log_artifacts

    @property
    def step_state_model(self) -> type[Any]:
        return self.header.state.step_state_model

    @property
    def step_state_fields(self) -> tuple[str, ...]:
        return self.header.state.step_state_fields

    @property
    def step_item_state_model(self) -> type[Any] | None:
        return self.header.state.step_item_state_model

    @property
    def step_item_state_fields(self) -> tuple[str, ...]:
        return self.header.state.step_item_state_fields

    @property
    def before_hook(self) -> Callable[..., Any] | None:
        return self.header.hooks.before

    @property
    def after_hook(self) -> Callable[..., Any] | None:
        return self.header.hooks.after

    @property
    def before_producer_hook(self) -> Callable[..., Any] | None:
        return self.header.hooks.before_producer

    @property
    def after_producer_hook(self) -> Callable[..., Any] | None:
        return self.header.hooks.after_producer

    @property
    def before_verifier_hook(self) -> Callable[..., Any] | None:
        return self.header.hooks.before_verifier

    @property
    def after_verifier_hook(self) -> Callable[..., Any] | None:
        return self.header.hooks.after_verifier

    @property
    def provider_policy(self) -> Any:
        return self.header.provider_policy

    @property
    def prompt(self) -> Any | None:
        return None

    @property
    def producer_prompt(self) -> Any | None:
        return None

    @property
    def verifier_prompt(self) -> Any | None:
        return None

    @property
    def expected_output_schema(self) -> dict[str, Any] | None:
        return None

    @property
    def expected_output_validator(self) -> Any | None:
        return None

    @property
    def retry_policy(self) -> ProviderRetryPolicy:
        return ProviderRetryPolicy(max_attempts=1)

    @property
    def producer_reads(self) -> tuple[ReadRef, ...]:
        return self.reads

    @property
    def producer_requires(self) -> tuple[RequireRef, ...]:
        return self.requires

    @property
    def producer_writes(self) -> tuple[WriteRef, ...]:
        return self.writes

    @property
    def verifier_reads(self) -> tuple[ReadRef, ...]:
        return ()

    @property
    def verifier_requires(self) -> tuple[RequireRef, ...]:
        return ()

    @property
    def verifier_writes(self) -> tuple[WriteRef, ...]:
        return ()

    @property
    def verifier_session_name(self) -> str | None:
        return None

    @property
    def python_handler(self) -> Callable[..., Any] | None:
        return None

    @property
    def branch_group(self) -> BranchGroupPlan | None:
        return None


@dataclass(frozen=True, slots=True)
class PromptStepPlan(_BaseStepPlan):
    header: StepHeader
    turn: ProviderTurnPlan

    @property
    def prompt(self) -> Any | None:
        return self.turn.prompt

    @property
    def producer_prompt(self) -> Any | None:
        return self.turn.prompt

    @property
    def expected_output_schema(self) -> dict[str, Any] | None:
        return self.turn.expected_output_schema

    @property
    def expected_output_validator(self) -> Any | None:
        return self.turn.expected_output_validator

    @property
    def retry_policy(self) -> ProviderRetryPolicy:
        return self.turn.retry_policy


@dataclass(frozen=True, slots=True)
class ProduceVerifyStepPlan(_BaseStepPlan):
    header: StepHeader
    producer: ProviderTurnPlan
    verifier: ProviderTurnPlan
    verifier_session_name: str | None = None

    @property
    def producer_prompt(self) -> Any | None:
        return self.producer.prompt

    @property
    def verifier_prompt(self) -> Any | None:
        return self.verifier.prompt

    @property
    def retry_policy(self) -> ProviderRetryPolicy:
        return self.producer.retry_policy

    @property
    def producer_reads(self) -> tuple[ReadRef, ...]:
        return self.producer.io.reads

    @property
    def producer_requires(self) -> tuple[RequireRef, ...]:
        return self.producer.io.requires

    @property
    def producer_writes(self) -> tuple[WriteRef, ...]:
        return self.producer.io.writes

    @property
    def verifier_reads(self) -> tuple[ReadRef, ...]:
        return self.verifier.io.reads

    @property
    def verifier_requires(self) -> tuple[RequireRef, ...]:
        return self.verifier.io.requires

    @property
    def verifier_writes(self) -> tuple[WriteRef, ...]:
        return self.verifier.io.writes

    @property
    def expected_output_schema(self) -> dict[str, Any] | None:
        return self.verifier.expected_output_schema

    @property
    def expected_output_validator(self) -> Any | None:
        return self.verifier.expected_output_validator


@dataclass(frozen=True, slots=True)
class PythonStepPlan(_BaseStepPlan):
    header: StepHeader
    handler: Callable[..., Any]

    @property
    def python_handler(self) -> Callable[..., Any] | None:
        return self.handler


@dataclass(frozen=True, slots=True)
class ChildWorkflowStepPlan(_BaseStepPlan):
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
    kind: Literal["parallel", "fan_out"]
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
class BranchGroupStepPlan(_BaseStepPlan):
    header: StepHeader
    branch_group: BranchGroupPlan

    @property
    def retry_policy(self) -> ProviderRetryPolicy:
        return ProviderRetryPolicy()


StepPlan: TypeAlias = (
    PromptStepPlan
    | ProduceVerifyStepPlan
    | PythonStepPlan
    | ChildWorkflowStepPlan
    | BranchGroupStepPlan
)


@dataclass(frozen=True, slots=True)
class SingleStepPlan:
    step: StepPlan
    input_model: type[Any] | None
    params_model: type[Any] | None
    routes: dict[str, RouteContract]
    workflow_policy: Any
