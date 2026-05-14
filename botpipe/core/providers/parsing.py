"""Shared outcome parsing for provider-backed turns."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from ..errors import FailureContext, ProviderExecutionError
from ..primitives import Outcome


_JSON_FENCE_RE = re.compile(r"\A```json\s*\n(?P<body>[\s\S]*?)\n?```\s*\Z")
_LEGACY_OPTIONAL_FIELDS = {"clarification", "payload", "question", "reason"}
_CANONICAL_OUTCOME_FIELDS = {"tag", "payload", "route_fields"}
_CANONICAL_TOP_LEVEL_FIELDS = {"outcome", "tag", *_LEGACY_OPTIONAL_FIELDS}


def parse_outcome_json(text: str) -> Outcome:
    """Parse canonical or legacy provider outcome JSON."""

    candidate = _normalize_outcome_json_candidate(text.strip())

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        fallback = _last_outcome_json_candidate(candidate)
        if fallback is None:
            raise _malformed_provider_output(
                f"provider returned malformed outcome JSON: {exc.msg}",
                json_error=exc,
                raw_text=candidate,
            ) from exc
        try:
            payload = json.loads(fallback)
        except json.JSONDecodeError as fallback_exc:
            raise _malformed_provider_output(
                f"provider returned malformed outcome JSON: {fallback_exc.msg}",
                json_error=fallback_exc,
                raw_text=fallback,
            ) from fallback_exc

    if not isinstance(payload, dict):
        raise _malformed_provider_output("provider outcome JSON must be an object.")

    unknown = sorted(set(payload) - _CANONICAL_TOP_LEVEL_FIELDS)
    if unknown:
        rendered = ", ".join(unknown)
        raise _malformed_provider_output(f"provider outcome JSON contains unsupported keys: {rendered}.")

    canonical_outcome = payload.get("outcome")
    if canonical_outcome is not None:
        if not isinstance(canonical_outcome, dict):
            raise _malformed_provider_output("provider outcome JSON field 'outcome' must be an object.")
        inner_unknown = sorted(set(canonical_outcome) - _CANONICAL_OUTCOME_FIELDS)
        if inner_unknown:
            rendered = ", ".join(inner_unknown)
            raise _malformed_provider_output(
                f"provider outcome JSON field 'outcome' contains unsupported keys: {rendered}."
            )
        tag = canonical_outcome.get("tag")
        if not isinstance(tag, str) or not tag:
            raise _malformed_provider_output(
                "provider outcome JSON must contain a non-empty string 'outcome.tag'."
            )
        parsed_payload = _optional_object_field(canonical_outcome, "payload", default={})
        route_fields = _optional_object_field(canonical_outcome, "route_fields", default={})
        clarification = _optional_string_field(payload, "clarification")
        reason = ""
        question = None
    else:
        tag = payload.get("tag")
        if not isinstance(tag, str) or not tag:
            raise _malformed_provider_output("provider outcome JSON must contain a non-empty string 'tag'.")
        parsed_payload = _optional_object_field(payload, "payload", default={})
        clarification = _optional_string_field(payload, "clarification")
        question = _optional_string_field(payload, "question")
        reason = _optional_string_field(payload, "reason") or ""
        route_fields = _legacy_route_fields(tag=tag, question=question, reason=reason)

    return Outcome(
        raw_output=text,
        tag=tag,
        reason=reason,
        clarification=clarification,
        question=question,
        payload=deepcopy(parsed_payload),
        route_fields=deepcopy(route_fields),
    )


def _normalize_outcome_json_candidate(candidate: str) -> str:
    match = _JSON_FENCE_RE.fullmatch(candidate)
    if match is not None:
        return match.group("body").strip()
    return candidate


def _last_outcome_json_candidate(text: str) -> str | None:
    chunks = [*re.split(r"\n\s*\n", text), *text.splitlines()]
    for chunk in reversed(chunks):
        candidate = _normalize_outcome_json_candidate(chunk.strip())
        if candidate.startswith("{") and candidate.endswith("}"):
            return candidate
    return None


def _optional_string_field(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise _malformed_provider_output(f"provider outcome JSON field {key!r} must be a string when provided.")
    return value


def _optional_object_field(payload: dict[str, Any], key: str, *, default: dict[str, Any]) -> dict[str, Any]:
    value = payload.get(key, default)
    if not isinstance(value, dict):
        raise ProviderExecutionError(
            f"provider outcome JSON field {key!r} must be an object when provided.",
            failure_context=FailureContext(
                kind="invalid_payload",
                step_name="",
                provider_attributable=True,
                details={"error": f"{key} must be an object"},
            ),
            retry_kind="invalid_payload",
        )
    return value


def _legacy_route_fields(*, tag: str, question: str | None, reason: str) -> dict[str, Any]:
    route_fields: dict[str, Any] = {}
    if tag == "question":
        if not isinstance(question, str) or not question.strip():
            raise ProviderExecutionError(
                "provider returned question route without a non-empty question",
                failure_context=FailureContext(
                    kind="invalid_payload",
                    step_name="",
                    candidate_route="question",
                    provider_attributable=True,
                    details={
                        "route": "question",
                        "error": "question route requires a non-empty question field",
                    },
                ),
                retry_kind="invalid_payload",
            )
        route_fields["questions"] = [question.strip()]
        route_fields["reason"] = reason or None
        return route_fields
    if tag in {"blocked", "failed"}:
        route_fields["reason"] = reason or None
    return route_fields


def _malformed_provider_output(
    message: str,
    *,
    json_error: json.JSONDecodeError | None = None,
    raw_text: str | None = None,
) -> ProviderExecutionError:
    details: dict[str, object] = {"error": message, "provider_failure_stage": "outcome_contract"}
    if json_error is not None:
        details.update(
            {
                "json_error_message": json_error.msg,
                "json_error_line": json_error.lineno,
                "json_error_column": json_error.colno,
                "json_error_position": json_error.pos,
            }
        )
        if raw_text is not None:
            details["json_error_excerpt"] = _json_error_excerpt(raw_text, json_error.pos)
    return ProviderExecutionError(
        message,
        failure_context=FailureContext(
            kind="malformed_provider_output",
            step_name="",
            provider_attributable=True,
            details=details,
        ),
        retry_kind="malformed_provider_output",
    )


def _json_error_excerpt(text: str, position: int, *, radius: int = 80) -> str:
    start = max(position - radius, 0)
    end = min(position + radius, len(text))
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{text[start:end]}{suffix}"
