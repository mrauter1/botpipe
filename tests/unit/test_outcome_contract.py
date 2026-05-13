from __future__ import annotations

from types import SimpleNamespace

from botpipe.core.outcome_contract import (
    NATIVE_SCHEMA_EXCEEDS_LIMIT,
    NATIVE_SCHEMA_HAS_INCOMPLETE_OBJECT,
    NATIVE_SCHEMA_HAS_OPEN_OBJECT,
    NATIVE_SCHEMA_HAS_OPTIONAL_PROPERTIES,
    NATIVE_SCHEMA_HAS_UNKNOWN_REQUIRED_PROPERTIES,
    build_provider_outcome_contract,
    payload_schema_for_route,
)


def _route(*, payload_schema_mode: str = "inherit", payload_schema: dict | None = None):
    return SimpleNamespace(
        payload_schema_mode=payload_schema_mode,
        payload_schema=payload_schema,
        route_fields_schema=None,
    )


def _payload_schema(schema: dict, route_tag: str = "done") -> dict:
    outcome_schema = schema["properties"]["outcome"]
    branch_schema = outcome_schema["anyOf"][0]
    assert branch_schema["properties"]["tag"] == {"type": "string", "const": route_tag}
    return branch_schema["properties"]["payload"]


def test_provider_outcome_contract_uses_closed_empty_payload_when_route_has_no_payload_contract() -> None:
    contract = build_provider_outcome_contract(
        routes={"done": _route()},
        expected_output_schema=None,
    )

    assert contract.native_delivery_available is True
    assert _payload_schema(contract.prompt_schema) == {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }


def test_provider_outcome_contract_keeps_no_payload_route_native_capable() -> None:
    contract = build_provider_outcome_contract(
        routes={"done": _route()},
        expected_output_schema=None,
    )

    assert contract.native_skip_reason is None
    assert contract.native_schema == contract.prompt_schema
    assert _payload_schema(contract.prompt_schema) == {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }


def test_provider_outcome_contract_preserves_inherited_step_payload_contract() -> None:
    expected_output_schema = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
        "additionalProperties": False,
    }

    contract = build_provider_outcome_contract(
        routes={"done": _route()},
        expected_output_schema=expected_output_schema,
    )

    assert contract.native_delivery_available is True
    assert _payload_schema(contract.prompt_schema) == expected_output_schema


def test_provider_outcome_contract_preserves_explicit_route_payload_contract() -> None:
    route_payload_schema = {
        "type": "object",
        "properties": {"approved": {"type": "boolean"}},
        "required": ["approved"],
        "additionalProperties": False,
    }

    contract = build_provider_outcome_contract(
        routes={"publish": _route(payload_schema_mode="explicit", payload_schema=route_payload_schema)},
        expected_output_schema=None,
    )

    assert contract.native_delivery_available is True
    assert _payload_schema(contract.prompt_schema, route_tag="publish") == route_payload_schema


def test_provider_outcome_contract_uses_prompt_only_for_open_explicit_payload_contract() -> None:
    route_payload_schema = {
        "type": "object",
        "additionalProperties": True,
    }

    contract = build_provider_outcome_contract(
        routes={"publish": _route(payload_schema_mode="explicit", payload_schema=route_payload_schema)},
        expected_output_schema=None,
    )

    assert contract.native_schema is None
    assert contract.native_skip_reason == NATIVE_SCHEMA_HAS_OPEN_OBJECT
    assert _payload_schema(contract.prompt_schema, route_tag="publish") == route_payload_schema


def test_provider_outcome_contract_uses_prompt_only_for_missing_object_additional_properties() -> None:
    route_payload_schema = {
        "type": "object",
        "properties": {"approved": {"type": "boolean"}},
        "required": ["approved"],
    }

    contract = build_provider_outcome_contract(
        routes={"publish": _route(payload_schema_mode="explicit", payload_schema=route_payload_schema)},
        expected_output_schema=None,
    )

    assert contract.native_schema is None
    assert contract.native_skip_reason == NATIVE_SCHEMA_HAS_OPEN_OBJECT
    assert _payload_schema(contract.prompt_schema, route_tag="publish") == route_payload_schema


def test_provider_outcome_contract_uses_prompt_only_for_incomplete_object_schema() -> None:
    route_payload_schema = {
        "type": "object",
        "additionalProperties": False,
    }

    contract = build_provider_outcome_contract(
        routes={"publish": _route(payload_schema_mode="explicit", payload_schema=route_payload_schema)},
        expected_output_schema=None,
    )

    assert contract.native_schema is None
    assert contract.native_skip_reason == NATIVE_SCHEMA_HAS_INCOMPLETE_OBJECT
    assert _payload_schema(contract.prompt_schema, route_tag="publish") == route_payload_schema


def test_provider_outcome_contract_uses_prompt_only_for_optional_object_properties() -> None:
    route_payload_schema = {
        "type": "object",
        "properties": {
            "required_field": {"type": "string"},
            "optional_field": {"type": "string"},
        },
        "required": ["required_field"],
        "additionalProperties": False,
    }

    contract = build_provider_outcome_contract(
        routes={"publish": _route(payload_schema_mode="explicit", payload_schema=route_payload_schema)},
        expected_output_schema=None,
    )

    assert contract.native_schema is None
    assert contract.native_skip_reason == NATIVE_SCHEMA_HAS_OPTIONAL_PROPERTIES
    assert _payload_schema(contract.prompt_schema, route_tag="publish") == route_payload_schema


def test_provider_outcome_contract_uses_prompt_only_for_nested_optional_object_properties() -> None:
    route_payload_schema = {
        "type": "object",
        "properties": {
            "nested": {
                "type": "object",
                "properties": {
                    "required_field": {"type": "string"},
                    "optional_field": {"type": "string"},
                },
                "required": ["required_field"],
                "additionalProperties": False,
            }
        },
        "required": ["nested"],
        "additionalProperties": False,
    }

    contract = build_provider_outcome_contract(
        routes={"publish": _route(payload_schema_mode="explicit", payload_schema=route_payload_schema)},
        expected_output_schema=None,
    )

    assert contract.native_schema is None
    assert contract.native_skip_reason == NATIVE_SCHEMA_HAS_OPTIONAL_PROPERTIES
    assert _payload_schema(contract.prompt_schema, route_tag="publish") == route_payload_schema


def test_provider_outcome_contract_keeps_fully_required_nested_object_native_capable() -> None:
    route_payload_schema = {
        "type": "object",
        "properties": {
            "nested": {
                "type": "object",
                "properties": {
                    "required_field": {"type": "string"},
                    "second_field": {"type": "string"},
                },
                "required": ["required_field", "second_field"],
                "additionalProperties": False,
            }
        },
        "required": ["nested"],
        "additionalProperties": False,
    }

    contract = build_provider_outcome_contract(
        routes={"publish": _route(payload_schema_mode="explicit", payload_schema=route_payload_schema)},
        expected_output_schema=None,
    )

    assert contract.native_skip_reason is None
    assert contract.native_schema == contract.prompt_schema


def test_provider_outcome_contract_uses_prompt_only_for_unknown_required_properties() -> None:
    route_payload_schema = {
        "type": "object",
        "properties": {"known": {"type": "string"}},
        "required": ["known", "missing"],
        "additionalProperties": False,
    }

    contract = build_provider_outcome_contract(
        routes={"publish": _route(payload_schema_mode="explicit", payload_schema=route_payload_schema)},
        expected_output_schema=None,
    )

    assert contract.native_schema is None
    assert contract.native_skip_reason == NATIVE_SCHEMA_HAS_UNKNOWN_REQUIRED_PROPERTIES
    assert _payload_schema(contract.prompt_schema, route_tag="publish") == route_payload_schema


def test_provider_outcome_contract_does_not_treat_property_container_names_as_object_schemas() -> None:
    route_payload_schema = {
        "type": "object",
        "properties": {
            "properties": {"type": "string"},
        },
        "required": ["properties"],
        "additionalProperties": False,
    }

    contract = build_provider_outcome_contract(
        routes={"publish": _route(payload_schema_mode="explicit", payload_schema=route_payload_schema)},
        expected_output_schema=None,
    )

    assert contract.native_skip_reason is None
    assert contract.native_schema == contract.prompt_schema


def test_provider_outcome_contract_returns_detailed_schema_when_native_limit_is_exceeded() -> None:
    route_payload_schema = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
        "additionalProperties": False,
    }

    contract = build_provider_outcome_contract(
        routes={"done": _route(payload_schema_mode="explicit", payload_schema=route_payload_schema)},
        expected_output_schema=None,
        max_chars=1,
    )

    assert contract.native_delivery_available is False
    assert _payload_schema(contract.prompt_schema) == route_payload_schema
    assert contract.prompt_schema["properties"]["outcome"]["anyOf"][0]["properties"]["tag"] == {
        "type": "string",
        "const": "done",
    }


def test_provider_outcome_contract_uses_prompt_only_when_native_limit_is_exceeded() -> None:
    route_payload_schema = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
        "additionalProperties": False,
    }

    contract = build_provider_outcome_contract(
        routes={"done": _route(payload_schema_mode="explicit", payload_schema=route_payload_schema)},
        expected_output_schema=None,
        max_chars=1,
    )

    assert contract.native_schema is None
    assert contract.native_skip_reason == NATIVE_SCHEMA_EXCEEDS_LIMIT
    assert _payload_schema(contract.prompt_schema) == route_payload_schema


def test_semantic_route_payload_schema_still_reports_unconstrained_when_no_payload_contract_exists() -> None:
    assert payload_schema_for_route(_route(), expected_output_schema=None) == {
        "type": "object",
        "additionalProperties": True,
    }
