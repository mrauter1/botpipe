"""Internal compatibility helpers for quarantined bridge behavior."""

from __future__ import annotations

from importlib import import_module
import sys


_CORE_SUBMODULES = (
    "_compat",
    "artifacts",
    "compiler",
    "context",
    "descriptors",
    "effects",
    "engine",
    "errors",
    "extensions",
    "operations",
    "primitives",
    "prompts",
    "providers",
    "providers.fake",
    "providers.models",
    "providers.parsing",
    "providers.protocols",
    "providers.rendered",
    "providers.rendering",
    "providers.retries",
    "providers.turns",
    "routes",
    "schema_registry",
    "sessions",
    "steps",
    "stores",
    "stores.memory",
    "stores.protocols",
    "validation",
    "workflow_capabilities",
    "workflow_catalog",
    "worklists",
)


def bridge_core_package(alias_name: str) -> None:
    """Bind an alias package name to canonical `core` modules."""

    core_module = import_module("core")
    sys.modules[alias_name] = core_module
    for name in _CORE_SUBMODULES:
        sys.modules[f"{alias_name}.{name}"] = import_module(f"core.{name}")


__all__ = ["bridge_core_package"]
