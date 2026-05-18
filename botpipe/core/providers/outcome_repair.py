"""Narrow repair helpers for malformed provider outcome JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from ..errors import ProviderExecutionError
from ..primitives import Outcome
from .parsing import normalize_outcome_json_candidate, parse_outcome_json


@dataclass(frozen=True, slots=True)
class DeterministicOutcomeRepair:
    outcome: Outcome
    repaired_text: str


@dataclass(frozen=True, slots=True)
class OutcomeRepairConstraints:
    route_tag: str


@dataclass(slots=True)
class _Container:
    kind: Literal["object", "array"]
    path: tuple[str, ...]
    expecting: str
    pending_key: str | None = None


def repair_incomplete_outcome_json(candidate: str) -> DeterministicOutcomeRepair | None:
    """Repair only structurally incomplete JSON by appending missing closing delimiters."""

    normalized = normalize_outcome_json_candidate(candidate.strip())
    repaired = _complete_missing_json_delimiters(normalized)
    if repaired is None:
        repaired = _remove_single_trailing_comma(normalized)
    if repaired is None or repaired == normalized:
        return None
    try:
        outcome = parse_outcome_json(repaired)
    except ProviderExecutionError:
        return None
    return DeterministicOutcomeRepair(outcome=outcome, repaired_text=repaired)


def extract_outcome_repair_constraints(candidate: str) -> OutcomeRepairConstraints | None:
    """Extract semantic anchors that a model-backed JSON repair must preserve."""

    normalized = normalize_outcome_json_candidate(candidate.strip())
    values = _scan_string_values(normalized)
    route_tag = values.get(("outcome", "tag")) or values.get(("tag",))
    if not isinstance(route_tag, str) or not route_tag:
        return None
    return OutcomeRepairConstraints(route_tag=route_tag)


def outcome_preserves_repair_constraints(outcome: Outcome, constraints: OutcomeRepairConstraints) -> bool:
    return outcome.tag == constraints.route_tag


def _complete_missing_json_delimiters(text: str) -> str | None:
    stack: list[str] = []
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append(char)
        elif char in "}]":
            if not stack:
                return None
            opener = stack.pop()
            if (opener, char) not in {("{", "}"), ("[", "]")}:
                return None
    if in_string or escaped or not stack:
        return None
    closers = {"{": "}", "[": "]"}
    return text + "".join(closers[opener] for opener in reversed(stack))


def _remove_single_trailing_comma(text: str) -> str | None:
    stripped = text.rstrip()
    if not stripped.endswith(","):
        return None
    candidate = stripped[:-1].rstrip()
    try:
        parse_outcome_json(candidate)
    except ProviderExecutionError:
        return None
    return candidate


def _scan_string_values(text: str) -> dict[tuple[str, ...], str]:
    values: dict[tuple[str, ...], str] = {}
    stack: list[_Container] = []
    index = 0
    length = len(text)

    def finish_value() -> None:
        if not stack:
            return
        current = stack[-1]
        if current.kind == "object":
            current.expecting = "comma_or_end"
            current.pending_key = None
        else:
            current.expecting = "comma_or_end"

    while index < length:
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if not stack:
            if char == "{":
                stack.append(_Container(kind="object", path=(), expecting="key_or_end"))
            elif char == "[":
                stack.append(_Container(kind="array", path=(), expecting="value_or_end"))
            index += 1
            continue

        current = stack[-1]
        if current.kind == "object":
            if current.expecting == "key_or_end":
                if char == "}":
                    stack.pop()
                    finish_value()
                    index += 1
                    continue
                if char != '"':
                    break
                decoded = _decode_json_string(text, index)
                if decoded is None:
                    break
                current.pending_key, index = decoded
                current.expecting = "colon"
                continue
            if current.expecting == "colon":
                if char != ":":
                    break
                current.expecting = "value"
                index += 1
                continue
            if current.expecting == "value":
                key = current.pending_key
                if key is None:
                    break
                if char == "{":
                    current.expecting = "comma_or_end"
                    current.pending_key = None
                    stack.append(_Container(kind="object", path=(*current.path, key), expecting="key_or_end"))
                    index += 1
                    continue
                if char == "[":
                    current.expecting = "comma_or_end"
                    current.pending_key = None
                    stack.append(_Container(kind="array", path=(*current.path, key), expecting="value_or_end"))
                    index += 1
                    continue
                if char == '"':
                    decoded = _decode_json_string(text, index)
                    if decoded is None:
                        break
                    value, index = decoded
                    values[(*current.path, key)] = value
                    finish_value()
                    continue
                index = _skip_scalar(text, index)
                finish_value()
                continue
            if current.expecting == "comma_or_end":
                if char == ",":
                    current.expecting = "key_or_end"
                    index += 1
                    continue
                if char == "}":
                    stack.pop()
                    finish_value()
                    index += 1
                    continue
                break
        else:
            if current.expecting == "value_or_end":
                if char == "]":
                    stack.pop()
                    finish_value()
                    index += 1
                    continue
                if char == "{":
                    current.expecting = "comma_or_end"
                    stack.append(_Container(kind="object", path=current.path, expecting="key_or_end"))
                    index += 1
                    continue
                if char == "[":
                    current.expecting = "comma_or_end"
                    stack.append(_Container(kind="array", path=current.path, expecting="value_or_end"))
                    index += 1
                    continue
                if char == '"':
                    decoded = _decode_json_string(text, index)
                    if decoded is None:
                        break
                    _, index = decoded
                    finish_value()
                    continue
                index = _skip_scalar(text, index)
                finish_value()
                continue
            if current.expecting == "comma_or_end":
                if char == ",":
                    current.expecting = "value_or_end"
                    index += 1
                    continue
                if char == "]":
                    stack.pop()
                    finish_value()
                    index += 1
                    continue
                break
    return values


def _decode_json_string(text: str, index: int) -> tuple[str, int] | None:
    if index >= len(text) or text[index] != '"':
        return None
    cursor = index + 1
    escaped = False
    while cursor < len(text):
        char = text[cursor]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            raw = text[index : cursor + 1]
            try:
                decoded = json.loads(raw)
            except json.JSONDecodeError:
                return None
            if not isinstance(decoded, str):
                return None
            return decoded, cursor + 1
        cursor += 1
    return None


def _skip_scalar(text: str, index: int) -> int:
    while index < len(text) and text[index] not in ",]}":
        index += 1
    return index
