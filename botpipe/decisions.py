"""Typed native questions and answers for probabilistic decision providers."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, TypeAlias


def _json_value(value: Any, name: str) -> Any:
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise TypeError(f"{name} must be finite JSON data") from exc
    return value


def _instructions(value: Any) -> Any:
    _json_value(value, "instructions")
    if value in (None, "", [], {}):
        raise ValueError("instructions must be non-empty")
    return value


@dataclass(frozen=True, slots=True)
class Choice:
    instructions: Any
    criteria: Mapping[str, Any]
    type: str = "choice"

    def __post_init__(self) -> None:
        object.__setattr__(self, "instructions", _instructions(self.instructions))
        if not isinstance(self.criteria, Mapping) or not (2 <= len(self.criteria) <= 255):
            raise ValueError("Choice criteria must contain 2 to 255 options")
        criteria = dict(self.criteria)
        if any(type(key) is not str or not key for key in criteria):
            raise ValueError("Choice option names must be non-empty strings")
        _json_value(criteria, "Choice criteria")
        object.__setattr__(self, "criteria", MappingProxyType(criteria))

    def to_payload(self) -> dict[str, Any]:
        return {"type": self.type, "instructions": self.instructions, "criteria": dict(self.criteria)}


@dataclass(frozen=True, slots=True)
class Score:
    instructions: Any
    criteria: tuple[Any, ...]
    type: str = "score"

    def __post_init__(self) -> None:
        object.__setattr__(self, "instructions", _instructions(self.instructions))
        criteria = tuple(self.criteria)
        if not 2 <= len(criteria) <= 10:
            raise ValueError("Score criteria must contain 2 to 10 ordered levels")
        _json_value(criteria, "Score criteria")
        object.__setattr__(self, "criteria", criteria)

    def to_payload(self) -> dict[str, Any]:
        return {"type": self.type, "instructions": self.instructions, "criteria": list(self.criteria)}


@dataclass(frozen=True, slots=True)
class Noul:
    instructions: Any
    criteria: Any | None = None
    type: str = "noul"

    def __post_init__(self) -> None:
        object.__setattr__(self, "instructions", _instructions(self.instructions))
        if self.criteria is not None:
            _json_value(self.criteria, "Noul criteria")

    def to_payload(self) -> dict[str, Any]:
        result = {"type": self.type, "instructions": self.instructions}
        if self.criteria is not None:
            result["criteria"] = self.criteria
        return result


DecisionQuestion: TypeAlias = Choice | Score | Noul


def _probability(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be finite and between 0 and 1")
    return result


def _distribution(value: Any, name: str) -> Mapping[str, float]:
    if not isinstance(value, Mapping) or not value:
        raise TypeError(f"{name} must be a non-empty mapping")
    result = {
        str(key): _probability(probability, f"{name}[{key!r}]")
        for key, probability in value.items()
    }
    if any(type(key) is not str for key in value):
        raise TypeError(f"{name} keys must be strings")
    if not math.isclose(sum(result.values()), 1.0, abs_tol=1e-4):
        raise ValueError(f"{name} must sum to 1")
    return MappingProxyType(result)


@dataclass(frozen=True, slots=True)
class ChoiceAnswer:
    choice: str
    probabilities: Mapping[str, float]
    confidence: float
    type: str = "choice"

    def __post_init__(self) -> None:
        if type(self.choice) is not str:
            raise TypeError("choice must be a string")
        probabilities = _distribution(self.probabilities, "choice probabilities")
        if self.choice not in probabilities:
            raise ValueError("choice must be present in probabilities")
        object.__setattr__(self, "probabilities", probabilities)
        object.__setattr__(self, "confidence", _probability(self.confidence, "confidence"))

    def to_record(self) -> dict[str, Any]:
        return {"type": self.type, "choice": self.choice, "probabilities": dict(self.probabilities), "confidence": self.confidence}


@dataclass(frozen=True, slots=True)
class ScoreAnswer:
    score: float
    legend: Mapping[int, Any]
    probabilities: Mapping[int, float]
    confidence: float
    type: str = "score"

    def __post_init__(self) -> None:
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)) or not math.isfinite(float(self.score)):
            raise ValueError("score must be finite")
        legend = {int(key): value for key, value in self.legend.items()}
        probabilities = _distribution(
            {str(key): value for key, value in self.probabilities.items()},
            "score probabilities",
        )
        integer_probabilities = {int(key): value for key, value in probabilities.items()}
        if set(legend) != set(integer_probabilities):
            raise ValueError("score legend and probabilities must have identical levels")
        if not legend or min(legend) != 0 or set(legend) != set(range(len(legend))):
            raise ValueError("score legend levels must be contiguous from zero")
        if not 0 <= float(self.score) <= max(legend):
            raise ValueError("score is outside the legend")
        _json_value(legend, "score legend")
        object.__setattr__(self, "score", float(self.score))
        object.__setattr__(self, "legend", MappingProxyType(legend))
        object.__setattr__(self, "probabilities", MappingProxyType(integer_probabilities))
        object.__setattr__(self, "confidence", _probability(self.confidence, "confidence"))

    def to_record(self) -> dict[str, Any]:
        return {"type": self.type, "score": self.score, "legend": {str(k): v for k, v in self.legend.items()}, "probabilities": {str(k): v for k, v in self.probabilities.items()}, "confidence": self.confidence}


@dataclass(frozen=True, slots=True)
class NoulAnswer:
    noul: float
    type: str = "noul"

    def __post_init__(self) -> None:
        object.__setattr__(self, "noul", _probability(self.noul, "noul"))

    def to_record(self) -> dict[str, Any]:
        return {"type": self.type, "noul": self.noul}


DecisionAnswer: TypeAlias = ChoiceAnswer | ScoreAnswer | NoulAnswer
DecisionAnswers: TypeAlias = Mapping[str, DecisionAnswer]


def question_from_record(value: Mapping[str, Any]) -> DecisionQuestion:
    """Restore a descriptor from its plain durable/native representation."""
    if not isinstance(value, Mapping):
        raise TypeError("decision question record must be a mapping")
    kind = value.get("type")
    allowed = {"type", "instructions", "criteria"}
    if set(value) - allowed:
        raise ValueError("decision question record contains unknown fields")
    if kind == "choice":
        return Choice(value.get("instructions"), value.get("criteria"))
    if kind == "score":
        return Score(value.get("instructions"), tuple(value.get("criteria") or ()))
    if kind == "noul":
        return Noul(value.get("instructions"), value.get("criteria"))
    raise ValueError(f"unsupported decision question type {kind!r}")


__all__ = [
    "Choice", "Score", "Noul", "DecisionQuestion",
    "ChoiceAnswer", "ScoreAnswer", "NoulAnswer", "DecisionAnswer", "DecisionAnswers",
    "question_from_record",
]
