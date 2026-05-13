"""Shared helpers for route inspection and reporting surfaces."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping

from .outcome_contract import (
    build_provider_outcome_contract,
    payload_schema_for_route,
    route_fields_schema_for_route,
)


def schema_name(schema: Mapping[str, Any] | None) -> str | None:
    """Return a stable human-readable schema name when one is present."""

    if not isinstance(schema, Mapping):
        return None
    title = schema.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    return None


def schema_fingerprint(schema: Mapping[str, Any] | None) -> str | None:
    """Return a deterministic fingerprint for one schema mapping."""

    if not isinstance(schema, Mapping):
        return None
    encoded = json.dumps(dict(schema), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def payload_contract_for_route(
    route: Any,
    *,
    expected_output_schema: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return effective payload-schema metadata for one compiled route."""

    mode = getattr(route, "payload_schema_mode", "inherit")
    schema = payload_schema_for_route(route, expected_output_schema=expected_output_schema)
    if mode == "explicit":
        source = "route"
    elif mode == "inherit" and isinstance(expected_output_schema, Mapping):
        source = "step_expected_output"
    elif mode == "none":
        source = "unconstrained"
    else:
        source = "unconstrained"
    return {
        "mode": mode,
        "source": source,
        "name": schema_name(schema),
        "fingerprint": schema_fingerprint(schema),
        "schema": deepcopy(schema),
    }


def route_fields_contract_for_route(route: Any) -> dict[str, Any]:
    """Return effective route-fields-schema metadata for one compiled route."""

    raw_schema = getattr(route, "route_fields_schema", None)
    schema = route_fields_schema_for_route(route)
    return {
        "source": "route" if isinstance(raw_schema, Mapping) else "empty_object",
        "name": schema_name(schema),
        "fingerprint": schema_fingerprint(schema),
        "schema": deepcopy(schema),
    }


def provider_response_contract_for_routes(
    *,
    routes: Mapping[str, Any],
    expected_output_schema: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return provider-response schema metadata for one visible route set."""

    contract = build_provider_outcome_contract(
        routes=routes,
        expected_output_schema=expected_output_schema,
    )
    schema = contract.prompt_schema
    encoded = json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return {
        "route_tags": list(routes.keys()),
        "schema_delivery_mode": "native" if contract.native_delivery_available else "prompt_only",
        "native_delivery_available": contract.native_delivery_available,
        "native_skip_reason": contract.native_skip_reason,
        "schema_fingerprint": schema_fingerprint(schema),
        "schema_chars": len(encoded),
    }
