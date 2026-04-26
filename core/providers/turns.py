"""Rendered transport turns for provider-backed execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from ..stores import SessionBinding


ProviderTurnKind = Literal["producer", "verifier", "llm"]
ExpectedProviderResponse = Literal["raw_text", "outcome_json"]


@dataclass(frozen=True, slots=True)
class RenderedProviderTurn:
    step_name: str
    turn_kind: ProviderTurnKind
    prompt_text: str
    session: SessionBinding | None
    expected_response: ExpectedProviderResponse


@dataclass(frozen=True, slots=True)
class ProviderTurnResult:
    raw_text: str
    session: SessionBinding | None
    metadata: dict[str, Any] = field(default_factory=dict)
