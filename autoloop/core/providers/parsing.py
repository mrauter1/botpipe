"""Shared outcome parsing for provider-backed turns."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from ..errors import ProviderExecutionError
from ..primitives import Outcome


_JSON_FENCE_RE = re.compile(r"\A```json\s*\n(?P<body>[\s\S]*?)\n?```\s*\Z")
_OUTCOME_OPTIONAL_FIELDS = {"clarification", "payload", "question", "reason"}


def parse_outcome_json(text: str) -> Outcome:
    """Parse a strict provider outcome JSON object."""

    candidate = text.strip()
    match = _JSON_FENCE_RE.fullmatch(candidate)
    if match is not None:
        candidate = match.group("body").strip()

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ProviderExecutionError(f"provider returned malformed outcome JSON: {exc.msg}") from exc

    if not isinstance(payload, dict):
        raise ProviderExecutionError("provider outcome JSON must be an object.")

    unknown = sorted(set(payload) - {"tag", *_OUTCOME_OPTIONAL_FIELDS})
    if unknown:
        rendered = ", ".join(unknown)
        raise ProviderExecutionError(f"provider outcome JSON contains unsupported keys: {rendered}.")

    tag = payload.get("tag")
    if not isinstance(tag, str) or not tag:
        raise ProviderExecutionError("provider outcome JSON must contain a non-empty string 'tag'.")

    parsed_payload = payload.get("payload", {})
    if not isinstance(parsed_payload, dict):
        raise ProviderExecutionError("provider outcome JSON field 'payload' must be an object when provided.")

    reason = _required_string_field(payload, "reason")
    clarification = _optional_string_field(payload, "clarification")
    question = _optional_string_field(payload, "question")

    return Outcome(
        raw_output=text,
        tag=tag,
        reason=reason,
        clarification=clarification,
        question=question,
        payload=deepcopy(parsed_payload),
    )


def _optional_string_field(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProviderExecutionError(f"provider outcome JSON field {key!r} must be a string when provided.")
    return value


def _required_string_field(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ProviderExecutionError(f"provider outcome JSON must contain a non-empty string {key!r}.")
    return value
