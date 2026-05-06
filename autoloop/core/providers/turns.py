"""Rendered transport turns for provider-backed execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Callable, Mapping
from typing import Any, Literal

from ..provider_policy import ResolvedProviderPolicy
from .models import TokenUsage
from ..stores import SessionBinding


ProviderTurnKind = Literal["producer", "verifier", "step", "operation"]
ExpectedProviderResponse = Literal["raw_text", "outcome_json"]


@dataclass(frozen=True, slots=True)
class RenderedProviderTurn:
    step_name: str
    turn_kind: ProviderTurnKind
    prompt_text: str
    session: SessionBinding | None
    expected_response: ExpectedProviderResponse
    policy: ResolvedProviderPolicy | None = None
    run_folder: Path | None = None
    step_execution_id: str | None = None
    runtime_event_sink: Callable[[str, Mapping[str, Any]], None] | None = None
    response_schema: dict[str, Any] | None = None
    response_schema_simplified: bool = False


@dataclass(frozen=True, slots=True)
class ProviderTurnResult:
    raw_text: str
    session: SessionBinding | None
    metadata: dict[str, Any] = field(default_factory=dict)
    usage: TokenUsage | None = None
