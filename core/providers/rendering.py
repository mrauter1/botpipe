"""Shared provider-turn rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence

from ..errors import ProviderExecutionError
from .models import ProviderArtifactRef, ProviderTurnContext
from .turns import RenderedProviderTurn


_TRUNCATION_MARKER = "[TRUNCATED BY RUNTIME PROMPT BUDGET]"


@dataclass(frozen=True, slots=True)
class ProviderPromptRenderPolicy:
    max_prompt_chars: int | None = None
    overflow_behavior: Literal["fail", "truncate_with_marker"] = "fail"


def render_provider_turn(context: ProviderTurnContext) -> RenderedProviderTurn:
    """Render a provider turn into a shared markdown prompt."""
    return render_provider_turn_with_policy(context)


def render_provider_turn_with_policy(
    context: ProviderTurnContext,
    *,
    policy: ProviderPromptRenderPolicy | None = None,
) -> RenderedProviderTurn:
    """Render a provider turn into a shared markdown prompt using the supplied policy."""

    prompt_text = _require_prompt_text(context)
    sections = [
        f"# Step: {context.step_name}",
        "",
        prompt_text,
        "",
        "## Runtime Step Contract",
        "",
        "### Required inputs",
        _render_required_inputs(context),
        "",
        "### Artifacts this step may write",
        _render_writable_artifacts(context),
        "",
        "### Available routes",
        _render_routes(context),
        "",
        "### Output payload",
        _render_expected_output_schema(context.expected_output_schema),
    ]
    if context.route_handoff and context.route_handoff.strip():
        sections.extend(
            [
                "",
                "### Route handoff",
                context.route_handoff.strip(),
                "",
                "The current Runtime Step Contract remains authoritative.",
            ]
        )
    if context.retry_feedback and context.retry_feedback.strip():
        sections.extend(["", "### Retry feedback", context.retry_feedback.strip()])

    rendered_prompt = _apply_render_policy(
        "\n".join(sections),
        policy=policy or ProviderPromptRenderPolicy(),
    )
    return RenderedProviderTurn(
        step_name=context.step_name,
        turn_kind=context.turn_kind,
        prompt_text=rendered_prompt,
        session=context.session,
        expected_response="raw_text" if context.turn_kind == "producer" else "outcome_json",
    )


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    normalized_rows = [tuple(str(cell) for cell in row) for row in rows]
    header_row = "| " + " | ".join(headers) + " |"
    separator_row = "| " + " | ".join("---" for _ in headers) + " |"
    body_rows = ["| " + " | ".join(row) + " |" for row in normalized_rows]
    return "\n".join((header_row, separator_row, *body_rows))


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _required_by_routes(context: ProviderTurnContext, artifact_name: str) -> str:
    required_by = [
        route
        for route in context.available_routes
        if artifact_name in context.route_required_artifacts.get(route, ())
    ]
    return ", ".join(required_by) if required_by else "none"


def _route_required_artifacts(context: ProviderTurnContext, route: str) -> str:
    required = context.route_required_artifacts.get(route, ())
    return ", ".join(required) if required else "none"


def _schema_name(ref: ProviderArtifactRef) -> str:
    return ref.schema_name or ref.kind


def _render_expected_output_schema(schema: Mapping[str, Any] | None) -> str:
    headers = ("Field", "Required", "Type", "Notes")
    if not isinstance(schema, Mapping):
        return _markdown_table(headers, (("payload", "no", "object", "No structured output payload contract declared."),))

    properties = schema.get("properties")
    required = schema.get("required")
    required_fields = set(required) if isinstance(required, list) else set()
    rows: list[tuple[str, str, str, str]] = []
    if isinstance(properties, Mapping):
        for field_name in sorted(str(key) for key in properties.keys()):
            raw_field_schema = properties.get(field_name)
            field_schema = raw_field_schema if isinstance(raw_field_schema, Mapping) else {}
            notes = []
            description = field_schema.get("description")
            if isinstance(description, str) and description.strip():
                notes.append(description.strip())
            if field_schema.get("type") == "object" and isinstance(field_schema.get("properties"), Mapping):
                notes.append("Nested object details omitted; runtime validation remains authoritative.")
            if field_schema.get("type") == "array" and isinstance(field_schema.get("items"), Mapping):
                notes.append("Array item details omitted; runtime validation remains authoritative.")
            rows.append(
                (
                    field_name,
                    _yes_no(field_name in required_fields),
                    _schema_type_name(field_schema.get("type")),
                    " ".join(notes) if notes else "Top-level payload field.",
                )
            )
    if not rows and required_fields:
        rows.extend(
            (
                field_name,
                "yes",
                "unknown",
                "Required top-level payload field; detailed schema omitted because the runtime contract is complex.",
            )
            for field_name in sorted(required_fields)
        )
    if not rows:
        rows.append(("payload", "no", "object", "No top-level payload properties were declared."))
    return _markdown_table(headers, rows)


def _apply_render_policy(text: str, *, policy: ProviderPromptRenderPolicy) -> str:
    if policy.max_prompt_chars is None or len(text) <= policy.max_prompt_chars:
        return text
    if policy.overflow_behavior == "truncate_with_marker":
        allowed = max(policy.max_prompt_chars - len(_TRUNCATION_MARKER) - 1, 0)
        truncated = text[:allowed].rstrip()
        if truncated:
            return f"{truncated}\n{_TRUNCATION_MARKER}"
        return _TRUNCATION_MARKER
    raise ProviderExecutionError(
        "rendered provider prompt exceeded the configured max_prompt_chars budget."
    )


def _render_required_inputs(context: ProviderTurnContext) -> str:
    rows = [
        (
            ref.name,
            ref.path,
            _yes_no(ref.required),
            _artifact_notes(ref),
        )
        for ref in context.required_artifacts
    ]
    if not rows:
        rows.append(("none", "n/a", "no", "No required input artifacts were declared."))
    return _markdown_table(("Artifact", "Path", "Required", "Notes"), rows)


def _render_writable_artifacts(context: ProviderTurnContext) -> str:
    rows = [
        (
            ref.name,
            ref.path,
            _schema_name(ref),
            _required_by_routes(context, ref.name),
            _artifact_notes(ref),
        )
        for ref in context.writable_artifacts
    ]
    if not rows:
        rows.append(("none", "n/a", "n/a", "none", "No writable artifacts were declared."))
    return _markdown_table(("Artifact", "Path", "Format", "Required by routes", "Notes"), rows)


def _render_routes(context: ProviderTurnContext) -> str:
    rows = [
        (
            route,
            _route_summary(context, route),
            _route_required_artifacts(context, route),
        )
        for route in context.available_routes
    ]
    if not rows:
        rows.append(("none", "No routes were declared.", "none"))
    return _markdown_table(("Route", "Meaning", "Required artifacts before choosing this route"), rows)


def _route_summary(context: ProviderTurnContext, route: str) -> str:
    contract = context.route_contracts.get(route)
    if isinstance(contract, Mapping):
        summary = contract.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
    return "No route summary provided."


def _artifact_notes(ref: ProviderArtifactRef) -> str:
    notes = [f"qualified name: {ref.qualified_name}"]
    notes.append("present at runtime" if ref.exists else "missing at runtime")
    if ref.schema_name:
        notes.append(f"schema: {ref.schema_name}")
    return "; ".join(notes)


def _require_prompt_text(context: ProviderTurnContext) -> str:
    if context.prompt.text is None:
        raise ProviderExecutionError(
            f"cannot render provider turn for step {context.step_name!r}: "
            f"prompt {context.prompt.path!r} did not resolve to text."
        )
    return context.prompt.text


def _schema_type_name(value: Any) -> str:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, list) and value:
        rendered = [str(item) for item in value if isinstance(item, str) and item]
        return " | ".join(rendered) if rendered else "unknown"
    return "unknown"
