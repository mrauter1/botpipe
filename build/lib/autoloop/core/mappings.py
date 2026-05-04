"""Shared mapping normalization helpers for public/runtime boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def normalize_mapping(
    value: Mapping[str, Any] | None,
    *,
    stringify_keys: bool = False,
) -> dict[str, Any]:
    """Copy a mapping once at an ingress boundary."""

    if value is None:
        return {}
    if stringify_keys:
        return {str(key): item for key, item in value.items()}
    if isinstance(value, dict):
        return dict(value)
    return {key: item for key, item in value.items()}


def normalize_optional_mapping(
    value: Mapping[str, Any] | None,
    *,
    stringify_keys: bool = False,
) -> dict[str, Any] | None:
    """Copy an optional mapping once at an ingress boundary."""

    if value is None:
        return None
    return normalize_mapping(value, stringify_keys=stringify_keys)
