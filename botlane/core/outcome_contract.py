"""Shared helpers for canonical provider outcome contracts."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Mapping


MAX_PROVIDER_OUTCOME_SCHEMA_CHARS = 12_000


def unconstrained_object_schema() -> dict[str, Any]:
    return {"type": "object", "additionalProperties": True}


def empty_object_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }


def is_question_style_route(route: Any, *, tag: str | None = None) -> bool:
    preset_kind = getattr(route, "preset_kind", None)
    if preset_kind == "question":
        return True
    if tag == "question":
        return True
    route_fields_schema = getattr(route, "route_fields_schema", None)
    if not isinstance(route_fields_schema, Mapping):
        return False
    properties = route_fields_schema.get("properties")
    return isinstance(properties, Mapping) and "questions" in properties


def normalize_route_fields_for_route(route: Any, route_fields: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(route_fields)
    preset_kind = getattr(route, "preset_kind", None)
    if is_question_style_route(route):
        normalized.setdefault("reason", None)
        return normalized
    if preset_kind in {"blocked", "failed"}:
        normalized.setdefault("reason", None)
    return normalized


def project_questions_markdown(value: Any) -> str | None:
    if not isinstance(value, list):
        return None
    questions = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if not questions:
        return None
    if len(questions) == 1:
        return questions[0]
    return "\n".join(f"- {question}" for question in questions)


def payload_schema_for_route(
    route: Any,
    *,
    expected_output_schema: Mapping[str, Any] | None,
) -> dict[str, Any]:
    payload_schema_mode = getattr(route, "payload_schema_mode", "inherit")
    payload_schema = getattr(route, "payload_schema", None)
    if payload_schema_mode == "explicit" and isinstance(payload_schema, Mapping):
        return deepcopy(dict(payload_schema))
    if payload_schema_mode == "inherit" and isinstance(expected_output_schema, Mapping):
        return deepcopy(dict(expected_output_schema))
    return unconstrained_object_schema()


def route_fields_schema_for_route(route: Any) -> dict[str, Any]:
    route_fields_schema = getattr(route, "route_fields_schema", None)
    if isinstance(route_fields_schema, Mapping):
        return deepcopy(dict(route_fields_schema))
    return empty_object_schema()


def build_provider_outcome_schema(
    *,
    routes: Mapping[str, Any],
    expected_output_schema: Mapping[str, Any] | None,
    max_chars: int = MAX_PROVIDER_OUTCOME_SCHEMA_CHARS,
) -> tuple[dict[str, Any], bool]:
    branch_schemas = [
        {
            "type": "object",
            "properties": {
                "tag": {"const": tag},
                "payload": payload_schema_for_route(route, expected_output_schema=expected_output_schema),
                "route_fields": route_fields_schema_for_route(route),
            },
            "required": ["tag", "payload", "route_fields"],
            "additionalProperties": False,
        }
        for tag, route in routes.items()
    ]
    detailed = {
        "type": "object",
        "properties": {
            "outcome": {
                "anyOf": branch_schemas,
            }
        },
        "required": ["outcome"],
        "additionalProperties": False,
    }
    if len(json.dumps(detailed, sort_keys=True)) <= max_chars:
        return detailed, False
    simplified = {
        "type": "object",
        "properties": {
            "outcome": {
                "type": "object",
                "properties": {
                    "tag": {"type": "string", "enum": list(routes.keys())},
                    "payload": unconstrained_object_schema(),
                    "route_fields": unconstrained_object_schema(),
                },
                "required": ["tag", "payload", "route_fields"],
                "additionalProperties": False,
            }
        },
        "required": ["outcome"],
        "additionalProperties": False,
    }
    return simplified, True


def describe_route_target(target: str | None) -> str | None:
    if not isinstance(target, str) or not target:
        return None
    if target == "AWAIT_INPUT":
        return "Await external input before continuing."
    if target == "FAIL":
        return "Terminate the run as failed."
    if target == "FINISH":
        return "Finish the run successfully."
    return f"Transfer execution to `{target}`."
