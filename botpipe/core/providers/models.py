"""Typed provider requests and responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Mapping

from ..primitives import Outcome
from ..provider_policy import ResolvedProviderPolicy
from ..prompts import ResolvedPrompt
from ..stores.protocols import SessionBinding

if TYPE_CHECKING:
    from ..artifacts import ResolvedArtifacts
    from ..context import Context


@dataclass(frozen=True, slots=True)
class ProviderArtifactRef:
    name: str
    qualified_name: str
    path: str
    kind: str
    required: bool
    exists: bool
    schema_name: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderReadableRef:
    name: str
    path: str
    exists: bool
    declared_artifact: bool
    kind: str | None = None
    qualified_name: str | None = None
    schema_name: str | None = None


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    source: str = "unavailable"
    provider_raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StepProviderUsage:
    producer: TokenUsage | None = None
    verifier: TokenUsage | None = None
    llm: TokenUsage | None = None
    repair: TokenUsage | None = None


@dataclass(frozen=True, slots=True)
class ProviderRoute:
    summary: str | None = None
    target: str | None = None
    required_writes: tuple[str, ...] = ()
    explicit_required_writes: tuple[str, ...] | None = None
    handoff: str | None = None
    provider_visible: bool = True
    provider_visibility: str = "always"
    payload_schema: dict[str, Any] | None = None
    route_fields_schema: dict[str, Any] | None = None
    preset_kind: str = "custom"


@dataclass(frozen=True, slots=True)
class RuntimeInteractionPolicy:
    allow_provider_questions: bool = True


@dataclass(frozen=True, slots=True)
class ProviderTurnContext:
    step_name: str
    turn_kind: Literal["producer", "verifier", "step", "operation", "outcome_repair"]
    prompt: ResolvedPrompt
    context: Context
    artifacts: ResolvedArtifacts
    session: SessionBinding | None
    expected_output_schema: Mapping[str, Any] | None
    available_routes: tuple[str, ...]
    routes: Mapping[str, ProviderRoute] = field(default_factory=dict)
    readable_artifacts: tuple[ProviderReadableRef, ...] = ()
    required_artifacts: tuple[ProviderArtifactRef, ...] = ()
    writable_artifacts: tuple[ProviderArtifactRef, ...] = ()
    route_required_writes: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    response_schema: Mapping[str, Any] | None = None
    native_response_schema: Mapping[str, Any] | None = None
    response_schema_native_skip_reason: str | None = None
    retry_feedback: str | None = None
    route_handoff: str | None = None
    policy: ResolvedProviderPolicy | None = None
    attempt: int = 1
    max_attempts: int = 3
    rendered_prompt_text: str | None = None


@dataclass(frozen=True, slots=True)
class ProducerRequest:
    step_name: str
    producer_prompt: ResolvedPrompt
    context: Context
    artifacts: ResolvedArtifacts
    session: SessionBinding | None = None
    expected_output_schema: dict[str, Any] | None = None
    available_routes: tuple[str, ...] = ()
    routes: Mapping[str, ProviderRoute] = field(default_factory=dict)
    readable_artifacts: tuple[ProviderReadableRef, ...] = ()
    required_artifacts: tuple[ProviderArtifactRef, ...] = ()
    writable_artifacts: tuple[ProviderArtifactRef, ...] = ()
    route_required_writes: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    response_schema: Mapping[str, Any] | None = None
    native_response_schema: Mapping[str, Any] | None = None
    response_schema_native_skip_reason: str | None = None
    retry_feedback: str | None = None
    route_handoff: str | None = None
    policy: ResolvedProviderPolicy | None = None
    attempt: int = 1
    max_attempts: int = 3


@dataclass(frozen=True, slots=True)
class VerifierRequest:
    step_name: str
    verifier_prompt: ResolvedPrompt
    producer_raw_output: str
    context: Context
    artifacts: ResolvedArtifacts
    session: SessionBinding | None = None
    expected_output_schema: dict[str, Any] | None = None
    available_routes: tuple[str, ...] = ()
    routes: Mapping[str, ProviderRoute] = field(default_factory=dict)
    readable_artifacts: tuple[ProviderReadableRef, ...] = ()
    required_artifacts: tuple[ProviderArtifactRef, ...] = ()
    writable_artifacts: tuple[ProviderArtifactRef, ...] = ()
    route_required_writes: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    response_schema: Mapping[str, Any] | None = None
    native_response_schema: Mapping[str, Any] | None = None
    response_schema_native_skip_reason: str | None = None
    retry_feedback: str | None = None
    route_handoff: str | None = None
    policy: ResolvedProviderPolicy | None = None
    attempt: int = 1
    max_attempts: int = 3


@dataclass(frozen=True, slots=True)
class LLMRequest:
    step_name: str
    prompt: ResolvedPrompt
    context: Context
    artifacts: ResolvedArtifacts
    session: SessionBinding | None = None
    expected_output_schema: dict[str, Any] | None = None
    available_routes: tuple[str, ...] = ()
    routes: Mapping[str, ProviderRoute] = field(default_factory=dict)
    readable_artifacts: tuple[ProviderReadableRef, ...] = ()
    required_artifacts: tuple[ProviderArtifactRef, ...] = ()
    writable_artifacts: tuple[ProviderArtifactRef, ...] = ()
    route_required_writes: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    response_schema: Mapping[str, Any] | None = None
    native_response_schema: Mapping[str, Any] | None = None
    response_schema_native_skip_reason: str | None = None
    retry_feedback: str | None = None
    route_handoff: str | None = None
    policy: ResolvedProviderPolicy | None = None
    attempt: int = 1
    max_attempts: int = 3
    turn_kind: Literal["step", "outcome_repair"] = "step"


@dataclass(frozen=True, slots=True)
class OperationRequest:
    step_name: str
    prompt: ResolvedPrompt
    context: Context | None = None
    session: SessionBinding | None = None
    operation_kind: Literal["llm", "classify"] = "llm"
    return_schema: Mapping[str, Any] | None = None
    choices: tuple[str, ...] = ()
    retry_feedback: str | None = None
    policy: ResolvedProviderPolicy | None = None
    attempt: int = 1
    max_attempts: int = 3


@dataclass(frozen=True, slots=True)
class ProducerResponse:
    raw_output: str
    session: SessionBinding | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    usage: TokenUsage | None = None


@dataclass(frozen=True, slots=True)
class OutcomeResponse:
    outcome: Outcome
    session: SessionBinding | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    usage: TokenUsage | None = None


@dataclass(frozen=True, slots=True)
class OperationResponse:
    raw_output: str
    session: SessionBinding | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    usage: TokenUsage | None = None
