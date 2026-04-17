"""Typed provider requests and responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..primitives import Outcome
from ..prompts import ResolvedPrompt
from ..stores.protocols import SessionBinding

if TYPE_CHECKING:
    from ..artifacts import ResolvedArtifacts
    from ..context import Context


@dataclass(frozen=True, slots=True)
class ProducerRequest:
    step_name: str
    prompt: ResolvedPrompt
    context: Context
    artifacts: ResolvedArtifacts
    session: SessionBinding | None = None


@dataclass(frozen=True, slots=True)
class VerifierRequest:
    step_name: str
    prompt: ResolvedPrompt
    raw_output: str
    context: Context
    artifacts: ResolvedArtifacts
    session: SessionBinding | None = None


@dataclass(frozen=True, slots=True)
class LLMRequest:
    step_name: str
    prompt: ResolvedPrompt
    context: Context
    artifacts: ResolvedArtifacts
    session: SessionBinding | None = None


@dataclass(frozen=True, slots=True)
class ProducerResponse:
    raw_output: str
    session: SessionBinding | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OutcomeResponse:
    outcome: Outcome
    session: SessionBinding | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

