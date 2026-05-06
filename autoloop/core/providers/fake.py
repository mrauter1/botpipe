"""Deterministic fake provider for tests."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from ..primitives import Outcome
from .models import ProviderArtifactRef, ProviderReadableRef, ProviderRoute
from .models import LLMRequest, OperationRequest, OperationResponse, OutcomeResponse, ProducerRequest, ProducerResponse, VerifierRequest


ProviderTurn = ProducerResponse | OutcomeResponse | Outcome | str | Callable[[Any], Any]


@dataclass(slots=True)
class ProviderCall:
    kind: str
    step_name: str
    prompt_path: str | None
    expected_output_schema: dict[str, Any] | None = None
    available_routes: tuple[str, ...] = ()
    routes: dict[str, ProviderRoute] = field(default_factory=dict)
    readable_artifacts: tuple[ProviderReadableRef, ...] = ()
    required_artifacts: tuple[ProviderArtifactRef, ...] = ()
    writable_artifacts: tuple[ProviderArtifactRef, ...] = ()
    route_required_writes: dict[str, tuple[str, ...]] = field(default_factory=dict)
    retry_feedback: str | None = None
    route_handoff: str | None = None
    attempt: int = 1
    max_attempts: int = 3
    operation_kind: str | None = None
    choices: tuple[str, ...] = ()


class ScriptedLLMProvider:
    """Queue-backed provider that records calls."""

    def __init__(
        self,
        *,
        producer_turns: Iterable[ProviderTurn] | None = None,
        verifier_turns: Iterable[ProviderTurn] | None = None,
        llm_turns: Iterable[ProviderTurn] | None = None,
        operation_turns: Iterable[ProviderTurn] | None = None,
    ) -> None:
        self._producer_turns = deque(producer_turns or ())
        self._verifier_turns = deque(verifier_turns or ())
        self._llm_turns = deque(llm_turns or ())
        self._operation_turns = deque(operation_turns or ())
        self.calls: list[ProviderCall] = []

    async def run_producer(self, request: ProducerRequest) -> ProducerResponse:
        self._record_producer_call(request)
        value = self._pop(self._producer_turns, request)
        if isinstance(value, ProducerResponse):
            return value
        if isinstance(value, str):
            return ProducerResponse(raw_output=value)
        raise TypeError(f"unsupported scripted producer response: {value!r}")

    async def run_verifier(self, request: VerifierRequest) -> OutcomeResponse:
        self._record_verifier_call(request)
        value = self._pop(self._verifier_turns, request)
        if isinstance(value, OutcomeResponse):
            return value
        if isinstance(value, Outcome):
            return OutcomeResponse(outcome=value)
        raise TypeError(f"unsupported scripted verifier response: {value!r}")

    async def run_llm(self, request: LLMRequest) -> OutcomeResponse:
        self._record_llm_call(request)
        value = self._pop(self._llm_turns, request)
        if isinstance(value, OutcomeResponse):
            return value
        if isinstance(value, Outcome):
            return OutcomeResponse(outcome=value)
        raise TypeError(f"unsupported scripted llm response: {value!r}")

    def _record_producer_call(self, request: ProducerRequest) -> None:
        self.calls.append(
            ProviderCall(
                "producer",
                request.step_name,
                request.producer_prompt.path,
                expected_output_schema=deepcopy(request.expected_output_schema),
                available_routes=tuple(request.available_routes),
                routes=deepcopy(dict(request.routes)),
                readable_artifacts=deepcopy(request.readable_artifacts),
                required_artifacts=deepcopy(request.required_artifacts),
                writable_artifacts=deepcopy(request.writable_artifacts),
                route_required_writes=deepcopy(dict(request.route_required_writes)),
                retry_feedback=request.retry_feedback,
                route_handoff=request.route_handoff,
                attempt=request.attempt,
                max_attempts=request.max_attempts,
            )
        )

    def _record_verifier_call(self, request: VerifierRequest) -> None:
        self.calls.append(
            ProviderCall(
                "verifier",
                request.step_name,
                request.verifier_prompt.path,
                expected_output_schema=deepcopy(request.expected_output_schema),
                available_routes=tuple(request.available_routes),
                routes=deepcopy(dict(request.routes)),
                readable_artifacts=deepcopy(request.readable_artifacts),
                required_artifacts=deepcopy(request.required_artifacts),
                writable_artifacts=deepcopy(request.writable_artifacts),
                route_required_writes=deepcopy(dict(request.route_required_writes)),
                retry_feedback=request.retry_feedback,
                route_handoff=request.route_handoff,
                attempt=request.attempt,
                max_attempts=request.max_attempts,
            )
        )

    def _record_llm_call(self, request: LLMRequest) -> None:
        self.calls.append(
            ProviderCall(
                "step",
                request.step_name,
                request.prompt.path,
                expected_output_schema=deepcopy(request.expected_output_schema),
                available_routes=tuple(request.available_routes),
                routes=deepcopy(dict(request.routes)),
                readable_artifacts=deepcopy(request.readable_artifacts),
                required_artifacts=deepcopy(request.required_artifacts),
                writable_artifacts=deepcopy(request.writable_artifacts),
                route_required_writes=deepcopy(dict(request.route_required_writes)),
                retry_feedback=request.retry_feedback,
                route_handoff=request.route_handoff,
                attempt=request.attempt,
                max_attempts=request.max_attempts,
            )
        )

    def run_operation(self, request: OperationRequest) -> OperationResponse:
        self.calls.append(
            ProviderCall(
                "operation",
                request.step_name,
                request.prompt.path,
                expected_output_schema=deepcopy(request.return_schema) if request.return_schema is not None else None,
                retry_feedback=request.retry_feedback,
                attempt=request.attempt,
                max_attempts=request.max_attempts,
                operation_kind=request.operation_kind,
                choices=tuple(request.choices),
            )
        )
        value = self._pop(self._operation_turns, request)
        if isinstance(value, OperationResponse):
            return value
        if isinstance(value, str):
            return OperationResponse(raw_output=value)
        raise TypeError(f"unsupported scripted operation response: {value!r}")

    @staticmethod
    def _pop(queue: deque[ProviderTurn], request: Any) -> Any:
        if not queue:
            raise RuntimeError("scripted provider exhausted")
        value = queue.popleft()
        if callable(value):
            return value(request)
        return value
