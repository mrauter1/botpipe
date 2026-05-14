"""Provider retry policy and retry feedback helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import re
from typing import Any

from ..errors import exception_failure_context, exception_retry_kind


_CANONICAL_OUTCOME_ENVELOPE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["outcome"],
    "properties": {
        "outcome": {
            "type": "object",
            "additionalProperties": False,
            "required": ["tag", "payload", "route_fields"],
            "properties": {
                "tag": {"type": "string"},
                "payload": {"type": "object"},
                "route_fields": {"type": "object"},
            },
        }
    },
}
_BACKTICK_RUN_RE = re.compile(r"`+")


@dataclass(frozen=True, slots=True)
class ProviderRetryPolicy:
    max_attempts: int = 3
    retry_provider_execution_error: bool = True
    retry_illegal_route: bool = True
    retry_invalid_payload: bool = True
    retry_missing_required_output_artifact: bool = True
    retry_invalid_output_artifact: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.max_attempts, bool) or not isinstance(self.max_attempts, int):
            raise TypeError("ProviderRetryPolicy.max_attempts must be an integer.")
        if self.max_attempts < 1:
            raise ValueError("ProviderRetryPolicy.max_attempts must be >= 1.")


def build_retry_feedback(
    exc: Exception,
    *,
    step_name: str,
    attempt: int,
    max_attempts: int,
    response_schema: Mapping[str, Any] | None = None,
    include_outcome_envelope: bool = False,
) -> str:
    """Build a deterministic markdown retry note for the next provider attempt."""

    problem = _problem_summary(exc, step_name=step_name)
    sections = [
        "## Retry Feedback",
        "",
        "The previous attempt could not be accepted.",
        "",
        "Attempt:",
        f"- {attempt} of {max_attempts}",
        "",
        "Problem:",
        f"- {problem}",
    ]
    diagnostics = _diagnostic_lines(exc)
    if diagnostics:
        sections.extend(("", "Diagnostics:", *diagnostics))
    schema_section = _schema_section(
        exc,
        response_schema=response_schema,
        include_outcome_envelope=include_outcome_envelope,
    )
    if schema_section:
        sections.extend(("", *schema_section))
    sections.extend(
        (
            "",
            "Action required:",
            "- Repair the issue using the current Runtime Step Contract.",
            "- Use only an allowed route.",
            "- If selecting a question-style route, include non-empty `outcome.route_fields.questions`.",
            "- Write all artifacts required by the selected route.",
        )
    )
    return "\n".join(sections)


def _problem_summary(exc: Exception, *, step_name: str) -> str:
    kind = exception_retry_kind(exc)
    if kind == "illegal_route":
        return f"The selected route was not allowed for step {step_name!r}."
    if kind == "invalid_payload":
        route = _failure_context_field(exc, "route")
        if route is None:
            route = _failure_context_field(exc, "candidate_route")
        detail = _failure_context_field(exc, "error")
        if detail and route:
            return f"The selected route {route!r} has an invalid payload: {detail}."
        if detail:
            return f"The structured output payload is invalid: {detail}."
        return "The structured output payload did not satisfy the declared output contract."
    if kind == "missing_required_output_artifact":
        artifact_name = _failure_context_field(exc, "artifact_name")
        if artifact_name:
            return f"The selected route is missing required output artifact {artifact_name!r}."
        return "The selected route is missing a required output artifact."
    if kind == "invalid_output_artifact":
        artifact_name = _failure_context_field(exc, "artifact_name")
        if artifact_name:
            return f"Output artifact {artifact_name!r} did not pass runtime validation."
        return "One or more output artifacts did not pass runtime validation."
    if kind == "provider_transport_failure":
        return "The provider transport failed before a usable response was accepted."
    if kind == "malformed_provider_output":
        detail = _failure_context_field(exc, "error")
        if detail:
            return f"The provider response could not be parsed into a valid workflow outcome: {detail}."
        return "The provider response could not be parsed into a valid workflow outcome."
    message = str(exc).strip()
    return message or f"The provider attempt for step {step_name!r} failed."


def _diagnostic_lines(exc: Exception) -> list[str]:
    kind = exception_retry_kind(exc)
    if kind != "malformed_provider_output":
        return []

    lines: list[str] = []
    decoder_message = _failure_context_field(exc, "json_error_message")
    location = _json_error_location(exc)
    if decoder_message and location:
        lines.append(f"- JSON parser error: {decoder_message} at {location}.")
    elif decoder_message:
        lines.append(f"- JSON parser error: {decoder_message}.")

    excerpt = _failure_context_field(exc, "json_error_excerpt")
    if excerpt:
        lines.append("- Output near parse failure:")
        lines.extend(_fenced_text_block(excerpt))

    if lines:
        lines.append("- Return one complete JSON object only; make sure all braces and brackets are balanced.")
        lines.append("- The route-specific allowed tags and route-field schemas remain the current Runtime Step Contract.")
    return lines


def _json_error_location(exc: Exception) -> str | None:
    line = _failure_context_value(exc, "json_error_line")
    column = _failure_context_value(exc, "json_error_column")
    position = _failure_context_value(exc, "json_error_position")
    parts: list[str] = []
    if isinstance(line, int) and isinstance(column, int):
        parts.append(f"line {line}, column {column}")
    if isinstance(position, int):
        parts.append(f"char {position}")
    return ", ".join(parts) if parts else None


def _failure_context_field(exc: Exception, key: str) -> str | None:
    value = _failure_context_value(exc, key)
    if isinstance(value, str) and value:
        return value
    return None


def _failure_context_value(exc: Exception, key: str) -> Any:
    failure_context = exception_failure_context(exc)
    if failure_context is None:
        return None
    return failure_context.to_payload().get(key)


def _schema_section(
    exc: Exception,
    *,
    response_schema: Mapping[str, Any] | None,
    include_outcome_envelope: bool,
) -> list[str]:
    if exception_retry_kind(exc) != "malformed_provider_output":
        return []
    if response_schema is not None:
        rendered = _render_json_mapping(response_schema)
        if rendered is not None:
            return ["Expected outcome schema:", "```json", rendered, "```"]
    if include_outcome_envelope:
        rendered = _render_json_mapping(_CANONICAL_OUTCOME_ENVELOPE)
        assert rendered is not None
        return ["Canonical outcome envelope:", "```json", rendered, "```"]
    return []


def _render_json_mapping(value: Mapping[str, Any]) -> str | None:
    try:
        return json.dumps(dict(value), indent=2, sort_keys=True)
    except (TypeError, ValueError):
        return None


def _fenced_text_block(value: str) -> list[str]:
    fence = _fence_for_text(value)
    return [f"{fence}text", value, fence]


def _fence_for_text(value: str) -> str:
    longest = max((len(match.group(0)) for match in _BACKTICK_RUN_RE.finditer(value)), default=0)
    return "`" * max(3, longest + 1)
