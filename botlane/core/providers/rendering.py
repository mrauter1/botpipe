"""Shared provider-turn rendering."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

from ..errors import ProviderExecutionError
from ..outcome_contract import describe_route_target
from .models import ProviderArtifactRef, ProviderReadableRef, ProviderTurnContext
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
    if context.turn_kind == "operation":
        sections = _operation_sections(context, prompt_text=prompt_text)
    else:
        sections = [
            f"# Step: {context.step_name}",
            "",
            prompt_text,
            "",
            "## Runtime Step Contract",
            "",
            "### Readable inputs",
            _render_readable_inputs(context),
            "",
            "### Required inputs",
            _render_required_inputs(context),
            "",
            "### Declared artifacts this step may write",
            "Declared writable artifacts are governed output surfaces, not an exclusive allow-list. "
            "Other workspace files remain writable unless runtime policy says otherwise.",
            "",
            _render_writable_artifacts(context),
            "",
            "### Available routes",
            _render_routes(context),
            "",
            *_response_contract_sections(context),
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
        policy=context.policy,
        run_folder=_context_run_folder(context.context),
        workspace_root=_context_workspace_root(context.context),
        step_execution_id=_context_step_execution_id(context.context),
        runtime_event_sink=_context_runtime_event_sink(context.context),
        expected_response="raw_text" if context.turn_kind in {"producer", "operation"} else "outcome_json",
        response_schema=None if context.turn_kind in {"producer", "operation"} else _response_schema_payload(context),
        native_response_schema=None
        if context.turn_kind in {"producer", "operation"}
        else _native_response_schema_payload(context),
        response_schema_native_skip_reason=context.response_schema_native_skip_reason
        if context.turn_kind not in {"producer", "operation"}
        else None,
    )


def _context_run_folder(context: object) -> Path | None:
    run_folder = getattr(context, "run_folder", None)
    if isinstance(run_folder, Path):
        return run_folder
    return None


def _context_workspace_root(context: object) -> Path | None:
    workspace_root = getattr(context, "root", None)
    if isinstance(workspace_root, Path):
        return workspace_root
    return None


def _context_step_execution_id(context: object) -> str | None:
    value = getattr(context, "_step_execution_id", None)
    return value if isinstance(value, str) and value else None


def _context_runtime_event_sink(context: object) -> Callable[[str, Mapping[str, Any]], None] | None:
    sink = getattr(context, "_runtime_event_sink", None)
    return sink if callable(sink) else None


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    normalized_rows = [tuple(str(cell) for cell in row) for row in rows]
    header_row = "| " + " | ".join(headers) + " |"
    separator_row = "| " + " | ".join("---" for _ in headers) + " |"
    body_rows = ["| " + " | ".join(row) + " |" for row in normalized_rows]
    return "\n".join((header_row, separator_row, *body_rows))


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _required_by_routes(context: ProviderTurnContext, ref: ProviderArtifactRef) -> str:
    required_by = [
        route
        for route in _visible_routes(context)
        if ref.name in _route_required_writes(context, route)
        or ref.qualified_name in _route_required_writes(context, route)
    ]
    return ", ".join(required_by) if required_by else "none"


def _visible_routes(context: ProviderTurnContext) -> tuple[str, ...]:
    visible: list[str] = []
    for route in context.available_routes:
        info = context.routes.get(route)
        if isinstance(info, Mapping):
            if info.get("provider_visible") is False:
                continue
        elif info is not None and info.provider_visible is False:
            continue
        visible.append(route)
    return tuple(visible)


def _route_required_writes(context: ProviderTurnContext, route: str) -> tuple[str, ...]:
    return tuple(context.route_required_writes.get(route, ()))


def _explicit_route_required_writes(context: ProviderTurnContext, route: str) -> tuple[str, ...] | None:
    info = context.routes.get(route)
    if isinstance(info, Mapping):
        explicit = info.get("explicit_required_writes")
        if explicit is None:
            return None
        return tuple(str(name) for name in explicit)
    if info is None:
        return None
    explicit = info.explicit_required_writes
    if explicit is None:
        return None
    return tuple(str(name) for name in explicit)


def _render_route_required_writes(context: ProviderTurnContext, route: str) -> str:
    required = _route_required_writes(context, route)
    return ", ".join(required) if required else "none"


def _render_explicit_route_required_writes(context: ProviderTurnContext, route: str) -> str:
    explicit = _explicit_route_required_writes(context, route)
    if explicit is None:
        return "inherit"
    return ", ".join(explicit) if explicit else "none (explicit)"


def _schema_name(ref: ProviderArtifactRef) -> str:
    return ref.schema_name or ref.kind


def _response_contract_sections(context: ProviderTurnContext) -> list[str]:
    if context.turn_kind == "producer":
        return [
            "### Producer response",
            "Return the authored content as raw text. Do not wrap it in JSON. The verifier will choose the final route.",
        ]
    return [
        "### Control response",
        _render_outcome_response(context),
    ]


def _operation_sections(context: ProviderTurnContext, *, prompt_text: str) -> list[str]:
    return [
        f"# Operation: {context.step_name}",
        "",
        prompt_text,
        "",
        "## Runtime Operation Contract",
        _render_operation_response(context),
    ]


def _render_operation_response(context: ProviderTurnContext) -> str:
    visible_routes = _visible_routes(context)
    if visible_routes:
        choices = ", ".join(visible_routes)
        return "\n".join(
            [
                "Return raw text containing exactly one declared choice.",
                f"Allowed choices: {choices}.",
                "Do not wrap the answer in additional prose.",
            ]
        )
    if isinstance(context.expected_output_schema, Mapping):
        return "\n".join(
            [
                "Return exactly one JSON value matching this schema:",
                "```json",
                json.dumps(context.expected_output_schema, indent=2, sort_keys=True),
                "```",
            ]
        )
    return "Return a non-empty raw-text value only."


def _render_outcome_response(context: ProviderTurnContext) -> str:
    response_schema = _response_schema_payload(context) or {
        "type": "object",
        "properties": {
            "outcome": {
                "type": "object",
                "properties": {
                    "tag": {"type": "string", "enum": list(_visible_routes(context))},
                    "payload": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
                    "route_fields": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
                },
                "required": ["tag", "payload", "route_fields"],
                "additionalProperties": False,
            }
        },
        "required": ["outcome"],
        "additionalProperties": False,
    }
    route_sections = []
    for route in _visible_routes(context):
        route_sections.extend(
            [
                f"#### Route `{route}`",
                f"- Summary: {_route_summary(context, route)}",
                f"- Target: {_route_target(context, route)}",
                f"- Required writes: {_render_route_required_writes(context, route)}",
                "",
                "Payload schema:",
                "```json",
                json.dumps(_route_payload_schema(context, route), indent=2, sort_keys=True),
                "```",
                "Route fields schema:",
                "```json",
                json.dumps(_route_fields_schema(context, route), indent=2, sort_keys=True),
                "```",
                "",
            ]
        )
    lines = [
        "Return exactly one JSON object with this shape:",
        "```json",
        json.dumps(
            {
                "outcome": {
                    "tag": "<one available route>",
                    "payload": {},
                    "route_fields": {},
                }
            },
            indent=2,
        ),
        "```",
        "`outcome.tag` selects one visible route.",
        "`outcome.payload` is the business or domain payload for the selected route.",
        "`outcome.route_fields` contains metadata for the selected route only.",
        "For question-style routes, include a non-empty `outcome.route_fields.questions` list.",
        "Route helper reasons belong in `outcome.route_fields.reason` when the selected route defines one.",
        "",
        "#### Required outcome structure",
        "```json",
        json.dumps(response_schema, indent=2, sort_keys=True),
        "```",
    ]
    if context.response_schema_native_skip_reason is not None:
        lines.extend(
            [
                "",
                "Native structured-output delivery may be disabled because this detailed schema exceeds provider limits "
                "or is not accepted by the native schema dialect. "
                "Runtime post-parse validation still enforces the selected route's payload and route-fields schemas.",
            ]
        )
    lines.extend(["", *route_sections])
    return "\n".join(lines)


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
            "yes",
            _artifact_notes(ref),
        )
        for ref in context.required_artifacts
    ]
    if not rows:
        rows.append(("none", "n/a", "no", "No required input artifacts were declared."))
    return _markdown_table(("Artifact", "Path", "Required", "Notes"), rows)


def _render_readable_inputs(context: ProviderTurnContext) -> str:
    rows = [
        (
            ref.name,
            ref.path,
            _yes_no(ref.exists),
            _readable_notes(ref),
        )
        for ref in context.readable_artifacts
    ]
    if not rows:
        rows.append(("none", "n/a", "no", "No optional readable artifacts were declared."))
    return _markdown_table(("Artifact", "Path", "Exists", "Notes"), rows)


def _render_writable_artifacts(context: ProviderTurnContext) -> str:
    rows = [
        (
            ref.name,
            ref.path,
            _schema_name(ref),
            _required_by_routes(context, ref),
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
            _render_explicit_route_required_writes(context, route),
            _render_route_required_writes(context, route),
        )
        for route in _visible_routes(context)
    ]
    if not rows:
        rows.append(("none", "No routes were declared.", "inherit", "none"))
    return _markdown_table(
        ("Route", "Meaning", "Explicit required writes", "Effective required writes"),
        rows,
    )


def _route_summary(context: ProviderTurnContext, route: str) -> str:
    info = context.routes.get(route)
    if isinstance(info, Mapping):
        summary = info.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
    elif info is not None:
        summary = info.summary
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
    return "No route summary provided."


def _route_target(context: ProviderTurnContext, route: str) -> str:
    info = context.routes.get(route)
    target = None
    if isinstance(info, Mapping):
        raw_target = info.get("target")
        if isinstance(raw_target, str):
            target = raw_target
    elif info is not None:
        target = info.target
    description = describe_route_target(target)
    return description or "No explicit target description."


def _route_payload_schema(context: ProviderTurnContext, route: str) -> dict[str, Any]:
    response_schema = _response_schema_payload(context)
    if response_schema is not None:
        branch_schema = _route_branch_schema_from_response_schema(response_schema, route)
        if branch_schema is None:
            return {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
        properties = branch_schema.get("properties")
        if isinstance(properties, Mapping):
            payload_schema = properties.get("payload")
            if isinstance(payload_schema, Mapping):
                return dict(payload_schema)
        return {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
    info = context.routes.get(route)
    if isinstance(info, Mapping):
        schema = info.get("payload_schema")
        if isinstance(schema, Mapping):
            return dict(schema)
    elif info is not None and isinstance(info.payload_schema, Mapping):
        return dict(info.payload_schema)
    if isinstance(context.expected_output_schema, Mapping):
        return dict(context.expected_output_schema)
    return {"type": "object", "properties": {}, "required": [], "additionalProperties": False}


def _route_fields_schema(context: ProviderTurnContext, route: str) -> dict[str, Any]:
    response_schema = _response_schema_payload(context)
    if response_schema is not None:
        branch_schema = _route_branch_schema_from_response_schema(response_schema, route)
        if branch_schema is None:
            return {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
        properties = branch_schema.get("properties")
        if isinstance(properties, Mapping):
            route_fields_schema = properties.get("route_fields")
            if isinstance(route_fields_schema, Mapping):
                return dict(route_fields_schema)
        return {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
    info = context.routes.get(route)
    if isinstance(info, Mapping):
        schema = info.get("route_fields_schema")
        if isinstance(schema, Mapping):
            return dict(schema)
    elif info is not None and isinstance(info.route_fields_schema, Mapping):
        return dict(info.route_fields_schema)
    return {"type": "object", "properties": {}, "required": [], "additionalProperties": False}


def _response_schema_payload(context: ProviderTurnContext) -> dict[str, Any] | None:
    if not isinstance(context.response_schema, Mapping):
        return None
    return dict(context.response_schema)


def _native_response_schema_payload(context: ProviderTurnContext) -> dict[str, Any] | None:
    if not isinstance(context.native_response_schema, Mapping):
        return None
    return dict(context.native_response_schema)


def _route_branch_schema_from_response_schema(
    response_schema: Mapping[str, Any],
    route: str,
) -> Mapping[str, Any] | None:
    properties = response_schema.get("properties")
    if not isinstance(properties, Mapping):
        return None
    outcome_schema = properties.get("outcome")
    if not isinstance(outcome_schema, Mapping):
        return None
    branches = outcome_schema.get("anyOf")
    if not isinstance(branches, list):
        return None
    for branch in branches:
        if not isinstance(branch, Mapping):
            continue
        properties = branch.get("properties")
        if not isinstance(properties, Mapping):
            continue
        tag_schema = properties.get("tag")
        if isinstance(tag_schema, Mapping) and tag_schema.get("const") == route:
            return branch
    return None


def _artifact_notes(ref: ProviderArtifactRef) -> str:
    notes = [f"qualified name: {ref.qualified_name}"]
    notes.append("present at runtime" if ref.exists else "missing at runtime")
    if ref.schema_name:
        notes.append(f"schema: {ref.schema_name}")
    return "; ".join(notes)


def _readable_notes(ref: ProviderReadableRef) -> str:
    notes = ["declared artifact" if ref.declared_artifact else "workspace path"]
    notes.append("present at runtime" if ref.exists else "missing at runtime")
    if ref.qualified_name:
        notes.append(f"qualified name: {ref.qualified_name}")
    if ref.kind:
        notes.append(f"kind: {ref.kind}")
    if ref.schema_name:
        notes.append(f"schema: {ref.schema_name}")
    return "; ".join(notes)


def _require_prompt_text(context: ProviderTurnContext) -> str:
    if context.prompt.text is None:
        prompt_ref = context.prompt.path or "<inline prompt>"
        raise ProviderExecutionError(
            f"cannot render provider turn for step {context.step_name!r}: "
            f"prompt {prompt_ref!r} did not resolve to text."
        )
    return context.prompt.text


def _schema_type_name(value: Any) -> str:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, list) and value:
        rendered = [str(item) for item in value if isinstance(item, str) and item]
        return " | ".join(rendered) if rendered else "unknown"
    return "unknown"
