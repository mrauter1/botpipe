"""Deterministic fake provider for tests."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from ..primitives import Outcome
from .models import LLMRequest, OutcomeResponse, ProducerRequest, ProducerResponse, VerifierRequest


ProviderTurn = ProducerResponse | OutcomeResponse | Outcome | str | Callable[[Any], Any]


@dataclass(slots=True)
class ProviderCall:
    kind: str
    step_name: str
    prompt_path: str


class ScriptedLLMProvider:
    """Queue-backed provider that records calls."""

    def __init__(
        self,
        *,
        producer_turns: Iterable[ProviderTurn] | None = None,
        verifier_turns: Iterable[ProviderTurn] | None = None,
        llm_turns: Iterable[ProviderTurn] | None = None,
    ) -> None:
        self._producer_turns = deque(producer_turns or ())
        self._verifier_turns = deque(verifier_turns or ())
        self._llm_turns = deque(llm_turns or ())
        self.calls: list[ProviderCall] = []

    def run_producer(self, request: ProducerRequest) -> ProducerResponse:
        self.calls.append(ProviderCall("producer", request.step_name, request.prompt.path))
        value = self._pop(self._producer_turns, request)
        if isinstance(value, ProducerResponse):
            return value
        if isinstance(value, str):
            return ProducerResponse(raw_output=value)
        raise TypeError(f"unsupported scripted producer response: {value!r}")

    def run_verifier(self, request: VerifierRequest) -> OutcomeResponse:
        self.calls.append(ProviderCall("verifier", request.step_name, request.prompt.path))
        value = self._pop(self._verifier_turns, request)
        if isinstance(value, OutcomeResponse):
            return value
        if isinstance(value, Outcome):
            return OutcomeResponse(outcome=value)
        raise TypeError(f"unsupported scripted verifier response: {value!r}")

    def run_llm(self, request: LLMRequest) -> OutcomeResponse:
        self.calls.append(ProviderCall("llm", request.step_name, request.prompt.path))
        value = self._pop(self._llm_turns, request)
        if isinstance(value, OutcomeResponse):
            return value
        if isinstance(value, Outcome):
            return OutcomeResponse(outcome=value)
        raise TypeError(f"unsupported scripted llm response: {value!r}")

    @staticmethod
    def _pop(queue: deque[ProviderTurn], request: Any) -> Any:
        if not queue:
            raise RuntimeError("scripted provider exhausted")
        value = queue.popleft()
        if callable(value):
            return value(request)
        return value

