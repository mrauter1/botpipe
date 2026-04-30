"""Explicit compatibility package for `autoloop_v3.core` imports."""

from __future__ import annotations

from importlib import import_module
import sys

import core as _core


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


def _bridge_core_submodule(name: str) -> None:
    canonical = import_module(f"core.{name}")
    sys.modules.setdefault(f"{__name__}.{name}", canonical)


sys.modules[__name__] = _core
for _submodule in _CORE_SUBMODULES:
    _bridge_core_submodule(_submodule)
