"""Native TypeSafe Jev decision adapter."""

from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from .decisions import (
    Choice,
    ChoiceAnswer,
    DecisionAnswer,
    DecisionAnswers,
    DecisionQuestion,
    Noul,
    NoulAnswer,
    Score,
    ScoreAnswer,
)
from .providers import (
    CapabilityError,
    JEV_CAPABILITIES,
    ProviderError,
    _atomic_json,
    _read_receipt,
    _safe_id,
)
from .recovery import Completed, RecoveryOutcome, Unknown


@dataclass(frozen=True, slots=True)
class DecisionRequest:
    operation_id: str
    state: Any
    questions: Mapping[str, DecisionQuestion]
    receipt_dir: Path
    timeout: float
    attempt: int = 1
    settings: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if type(self.operation_id) is not str or not self.operation_id:
            raise ValueError("operation_id must be non-empty")
        object.__setattr__(self, "receipt_dir", Path(self.receipt_dir))
        if (
            isinstance(self.timeout, bool)
            or not isinstance(self.timeout, (int, float))
            or self.timeout <= 0
            or not math.isfinite(float(self.timeout))
        ):
            raise ValueError("timeout must be greater than zero")
        if isinstance(self.attempt, bool) or not isinstance(self.attempt, int) or self.attempt < 1:
            raise ValueError("attempt must be at least 1")
        try:
            json.dumps(self.state, allow_nan=False)
        except (TypeError, ValueError, RecursionError) as exc:
            raise TypeError("decision state must be finite JSON data") from exc
        if not isinstance(self.questions, Mapping) or not self.questions:
            raise ValueError("questions must be a non-empty mapping")
        questions = dict(self.questions)
        if any(type(key) is not str or not key for key in questions):
            raise ValueError("question IDs must be non-empty strings")
        if any(not isinstance(value, (Choice, Score, Noul)) for value in questions.values()):
            raise TypeError("questions must contain Choice, Score, or Noul values")
        object.__setattr__(self, "questions", MappingProxyType(questions))
        if not isinstance(self.settings, Mapping):
            raise TypeError("settings must be a mapping")
        object.__setattr__(self, "settings", MappingProxyType(dict(self.settings)))


@dataclass(frozen=True, slots=True)
class DecisionResponse:
    answers: DecisionAnswers
    model: str
    usage: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if type(self.model) is not str or not self.model:
            raise TypeError("decision response model must be a non-empty string")
        if not isinstance(self.answers, Mapping):
            raise TypeError("decision response answers must be a mapping")
        answers = dict(self.answers)
        if any(type(key) is not str or not isinstance(value, (ChoiceAnswer, ScoreAnswer, NoulAnswer)) for key, value in answers.items()):
            raise TypeError("decision response contains an invalid typed answer")
        object.__setattr__(self, "answers", MappingProxyType(answers))
        for name in ("usage", "metadata"):
            value = getattr(self, name)
            if not isinstance(value, Mapping):
                raise TypeError(f"decision response {name} must be a mapping")
            plain = dict(value)
            try:
                json.dumps(plain, allow_nan=False)
            except (TypeError, ValueError, RecursionError) as exc:
                raise TypeError(f"decision response {name} must be finite JSON data") from exc
            object.__setattr__(self, name, MappingProxyType(plain))

    def to_record(self) -> dict[str, Any]:
        record = {
            "answers": {key: answer.to_record() for key, answer in self.answers.items()},
            "model": self.model,
            "usage": dict(self.usage),
            "metadata": dict(self.metadata),
        }
        for name in ("usage", "metadata"):
            if len(json.dumps(record[name], allow_nan=False).encode()) > 1_000_000:
                raise ValueError(
                    f"decision response {name} exceeds the 1 MB evidence limit"
                )
        return record


@runtime_checkable
class DecisionAdapter(Protocol):
    name: str

    def validate_request(self, request: DecisionRequest) -> None: ...
    def decide(self, request: DecisionRequest) -> DecisionResponse: ...
    def recover(self, request: DecisionRequest) -> RecoveryOutcome: ...


DecisionTransport = Callable[[dict[str, Any], float], Mapping[str, Any]]
MAX_JEV_RESPONSE_BYTES = 1_000_000


def _receipt_path(request: DecisionRequest) -> Path:
    return request.receipt_dir / f"{_safe_id(request.operation_id)}.attempt-{request.attempt}.jev.json"


def _answer(value: Any) -> DecisionAnswer:
    if not isinstance(value, Mapping):
        raise ProviderError("Jev answer must be an object")
    kind = value.get("type")
    try:
        if kind == "choice":
            return ChoiceAnswer(
                choice=value.get("choice"),
                probabilities=value.get("probabilities"),
                confidence=value.get("confidence"),
            )
        if kind == "score":
            return ScoreAnswer(
                score=value.get("score"),
                legend=value.get("legend"),
                probabilities=value.get("probabilities"),
                confidence=value.get("confidence"),
            )
        if kind == "noul":
            # Noul deliberately has no fabricated confidence field.
            if set(value) != {"type", "noul"}:
                raise ValueError("Noul answer contains unsupported fields")
            return NoulAnswer(noul=value.get("noul"))
    except (TypeError, ValueError) as exc:
        raise ProviderError(f"Jev returned an invalid {kind!r} answer: {exc}") from exc
    raise ProviderError(f"Jev returned unsupported answer type {kind!r}")


def _response(value: Any, request: DecisionRequest) -> DecisionResponse:
    if not isinstance(value, Mapping):
        raise ProviderError("Jev response must be an object")
    raw_answers = value.get("answers")
    if not isinstance(raw_answers, Mapping):
        raise ProviderError("Jev response has no answers object")
    if set(raw_answers) != set(request.questions):
        raise ProviderError("Jev response question IDs do not match the request")
    answers = {key: _answer(answer) for key, answer in raw_answers.items()}
    for key, question in request.questions.items():
        expected = question.type
        if answers[key].type != expected:
            raise ProviderError(
                f"Jev answer {key!r} has type {answers[key].type!r}, expected {expected!r}"
            )
        if isinstance(question, Choice) and set(answers[key].probabilities) != set(question.criteria):
            raise ProviderError(f"Jev Choice answer {key!r} changed the option set")
        if isinstance(question, Score) and len(answers[key].legend) != len(question.criteria):
            raise ProviderError(f"Jev Score answer {key!r} changed the level set")
    model = value.get("model")
    if not isinstance(model, str):
        raise ProviderError("Jev response has no model identity")
    usage = value.get("usage", {})
    return DecisionResponse(answers, model, usage, {"provider": "jev"})


def decision_response_from_record(
    value: Mapping[str, Any], questions: Mapping[str, DecisionQuestion]
) -> DecisionResponse:
    """Restore and validate a durable response against its question contract."""
    request = DecisionRequest(
        operation_id="record-validation",
        state=None,
        questions=questions,
        receipt_dir=Path("."),
        timeout=1,
    )
    return _response(value, request)


class JevAdapter:
    name = "jev"
    capabilities = JEV_CAPABILITIES

    def __init__(
        self,
        *,
        model: str = "jev-latest",
        api_key: str | None = None,
        base_url: str = "https://api.typesafe.ai/v1/systemone",
        transport: DecisionTransport | None = None,
    ) -> None:
        if not model:
            raise ValueError("Jev model must be non-empty")
        self.model = model
        self._api_key = api_key
        self.base_url = base_url
        self._transport = transport

    def validate_request(self, request: DecisionRequest) -> None:
        unknown = set(request.settings) - {"model"}
        if unknown:
            raise CapabilityError("unsupported Jev settings: " + ", ".join(sorted(unknown)))
        model = request.settings.get("model", self.model)
        if type(model) is not str or not model:
            raise CapabilityError("Jev model setting must be a non-empty string")
        if self._transport is None and not (
            self._api_key or os.environ.get("TYPESAFE_API_KEY")
        ):
            raise CapabilityError(
                "Jev requires TYPESAFE_API_KEY or an explicit api_key"
            )

    def _http(self, payload: dict[str, Any], timeout: float) -> Mapping[str, Any]:
        api_key = self._api_key or os.environ.get("TYPESAFE_API_KEY")
        if not api_key:
            raise CapabilityError("Jev requires TYPESAFE_API_KEY or an explicit api_key")
        data = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode()
        message = urllib.request.Request(
            self.base_url,
            data=data,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(message, timeout=timeout) as response:
                body = response.read(MAX_JEV_RESPONSE_BYTES + 1)
                if len(body) > MAX_JEV_RESPONSE_BYTES:
                    raise ProviderError(
                        "Jev response exceeds the 1 MB transport limit"
                    )
                result = json.loads(body)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ProviderError(f"Jev request failed: {exc}") from exc
        if not isinstance(result, Mapping):
            raise ProviderError("Jev response must be an object")
        return result

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        self.validate_request(request)
        path = _receipt_path(request)
        if path.exists():
            recovered = self.recover(request)
            if isinstance(recovered, Completed):
                return recovered.response
            raise ProviderError("Jev attempt already exists without an authoritative response")
        model = request.settings.get("model", self.model)
        payload = {
            "state": request.state,
            "model": model,
            "questions": {key: question.to_payload() for key, question in request.questions.items()},
        }
        request.receipt_dir.mkdir(parents=True, exist_ok=True)
        _atomic_json(path, {
            "version": 1,
            "provider": self.name,
            "operation_id": request.operation_id,
            "attempt": request.attempt,
            "status": "dispatched",
            "request": payload,
        })
        raw = (self._transport or self._http)(payload, request.timeout)
        response = _response(raw, request)
        _atomic_json(path, {
            "version": 1,
            "provider": self.name,
            "operation_id": request.operation_id,
            "attempt": request.attempt,
            "status": "completed",
            "request": payload,
            "response": response.to_record(),
        })
        return response

    def recover(self, request: DecisionRequest) -> RecoveryOutcome:
        path = _receipt_path(request)
        if not path.exists():
            return Unknown("no matching Jev receipt")
        try:
            value = _read_receipt(path)
        except Exception as exc:
            return Unknown(str(exc))
        if value.get("operation_id") != request.operation_id or value.get("attempt") != request.attempt:
            return Unknown("Jev receipt identity does not match")
        if value.get("status") != "completed":
            return Unknown("Jev dispatch has no authoritative terminal response")
        try:
            return Completed(_response(value.get("response"), request))
        except ProviderError as exc:
            return Unknown(str(exc))


__all__ = [
    "DecisionAdapter",
    "DecisionRequest",
    "DecisionResponse",
    "JevAdapter",
    "decision_response_from_record",
]
