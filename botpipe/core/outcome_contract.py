"""Shared helpers for canonical provider outcome contracts."""

from __future__ import annotations

from dataclasses import dataclass
import json
from copy import deepcopy
from typing import Any, Mapping


MAX_PROVIDER_OUTCOME_SCHEMA_CHARS = 12_000

NATIVE_SCHEMA_EXCEEDS_LIMIT = "provider_response_schema_exceeds_native_limit"
NATIVE_SCHEMA_HAS_OPEN_OBJECT = "provider_response_schema_has_open_object"
NATIVE_SCHEMA_HAS_INCOMPLETE_OBJECT = "provider_response_schema_has_incomplete_object"
NATIVE_SCHEMA_HAS_OPTIONAL_PROPERTIES = "provider_response_schema_has_optional_properties"
NATIVE_SCHEMA_HAS_UNKNOWN_REQUIRED_PROPERTIES = "provider_response_schema_has_unknown_required_properties"
NATIVE_SCHEMA_USES_UNSUPPORTED_OBJECT_KEYWORD = "provider_response_schema_uses_unsupported_object_keyword"

_UNSUPPORTED_NATIVE_OBJECT_KEYWORDS = frozenset(
    {
        "dependentSchemas",
        "patternProperties",
        "propertyNames",
        "unevaluatedProperties",
    }
)


@dataclass(frozen=True, slots=True)
class ProviderOutcomeContract:
    prompt_schema: dict[str, Any]
    native_schema: dict[str, Any] | None
    native_skip_reason: str | None = None

    @property
    def native_delivery_available(self) -> bool:
        return self.native_schema is not None


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


def provider_payload_schema_for_route(
    route: Any,
    *,
    expected_output_schema: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return the provider-facing payload schema for one route branch.

    Runtime route contracts may intentionally leave payload unconstrained, but
    provider prompts need deterministic route payload instructions. For routes
    with no effective payload contract, expose an empty payload object while
    preserving explicit and inherited payload contracts.
    """

    payload_schema_mode = getattr(route, "payload_schema_mode", "inherit")
    payload_schema = getattr(route, "payload_schema", None)
    if payload_schema_mode == "explicit" and isinstance(payload_schema, Mapping):
        return deepcopy(dict(payload_schema))
    if payload_schema_mode == "inherit" and isinstance(expected_output_schema, Mapping):
        return deepcopy(dict(expected_output_schema))
    return empty_object_schema()


def route_fields_schema_for_route(route: Any) -> dict[str, Any]:
    route_fields_schema = getattr(route, "route_fields_schema", None)
    if isinstance(route_fields_schema, Mapping):
        return deepcopy(dict(route_fields_schema))
    return empty_object_schema()


def build_provider_outcome_contract(
    *,
    routes: Mapping[str, Any],
    expected_output_schema: Mapping[str, Any] | None,
    max_chars: int = MAX_PROVIDER_OUTCOME_SCHEMA_CHARS,
) -> ProviderOutcomeContract:
    prompt_schema = _build_provider_prompt_outcome_schema(
        routes=routes,
        expected_output_schema=expected_output_schema,
    )
    if len(json.dumps(prompt_schema, sort_keys=True)) > max_chars:
        return ProviderOutcomeContract(
            prompt_schema=prompt_schema,
            native_schema=None,
            native_skip_reason=NATIVE_SCHEMA_EXCEEDS_LIMIT,
        )
    skip_reason = provider_native_schema_skip_reason(prompt_schema)
    if skip_reason is not None:
        return ProviderOutcomeContract(
            prompt_schema=prompt_schema,
            native_schema=None,
            native_skip_reason=skip_reason,
        )
    return ProviderOutcomeContract(
        prompt_schema=prompt_schema,
        native_schema=deepcopy(prompt_schema),
        native_skip_reason=None,
    )


def _build_provider_prompt_outcome_schema(
    *,
    routes: Mapping[str, Any],
    expected_output_schema: Mapping[str, Any] | None,
) -> dict[str, Any]:
    branch_schemas = [
        {
            "type": "object",
            "properties": {
                "tag": {"type": "string", "const": tag},
                "payload": provider_payload_schema_for_route(
                    route,
                    expected_output_schema=expected_output_schema,
                ),
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
    return detailed


def provider_native_schema_skip_reason(schema: Mapping[str, Any]) -> str | None:
    return _native_schema_skip_reason_for_schema(schema)


def _native_schema_skip_reason_for_schema(schema: Any) -> str | None:
    if not isinstance(schema, Mapping):
        return None
    if _is_object_schema(schema):
        if any(keyword in schema for keyword in _UNSUPPORTED_NATIVE_OBJECT_KEYWORDS):
            return NATIVE_SCHEMA_USES_UNSUPPORTED_OBJECT_KEYWORD
        if schema.get("additionalProperties") is not False:
            return NATIVE_SCHEMA_HAS_OPEN_OBJECT
        required_skip_reason = _object_required_skip_reason(schema)
        if required_skip_reason is not None:
            return required_skip_reason
    for nested in _child_schemas(schema):
        skip_reason = _native_schema_skip_reason_for_schema(nested)
        if skip_reason is not None:
            return skip_reason
    return None


def _is_object_schema(schema: Mapping[str, Any]) -> bool:
    schema_type = schema.get("type")
    if schema_type == "object":
        return True
    if isinstance(schema_type, list) and "object" in schema_type:
        return True
    if "properties" in schema or "additionalProperties" in schema or "required" in schema:
        return True
    return any(keyword in schema for keyword in _UNSUPPORTED_NATIVE_OBJECT_KEYWORDS)


def _object_required_skip_reason(schema: Mapping[str, Any]) -> str | None:
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        return NATIVE_SCHEMA_HAS_INCOMPLETE_OBJECT
    required = schema.get("required")
    if not isinstance(required, list) or any(not isinstance(item, str) for item in required):
        return NATIVE_SCHEMA_HAS_OPTIONAL_PROPERTIES
    property_names = set(properties)
    required_names = set(required)
    if property_names - required_names:
        return NATIVE_SCHEMA_HAS_OPTIONAL_PROPERTIES
    if required_names - property_names:
        return NATIVE_SCHEMA_HAS_UNKNOWN_REQUIRED_PROPERTIES
    return None


def _child_schemas(schema: Mapping[str, Any]) -> list[Any]:
    children: list[Any] = []
    for keyword in ("properties", "$defs", "definitions", "dependentSchemas"):
        nested = schema.get(keyword)
        if isinstance(nested, Mapping):
            children.extend(nested.values())
    for keyword in ("anyOf", "oneOf", "allOf", "prefixItems"):
        nested = schema.get(keyword)
        if isinstance(nested, list):
            children.extend(nested)
    for keyword in (
        "additionalProperties",
        "contains",
        "else",
        "if",
        "items",
        "not",
        "propertyNames",
        "then",
        "unevaluatedItems",
        "unevaluatedProperties",
    ):
        nested = schema.get(keyword)
        if isinstance(nested, Mapping):
            children.append(nested)
    return children


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
