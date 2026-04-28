"""Workflow namespace shim.

Use `autoloop.simple` or `autoloop` for public workflow authoring.
This module intentionally does not re-export authoring primitives.
"""

from __future__ import annotations

__all__: list[str] = []


def __getattr__(name: str) -> object:
    raise AttributeError(
        "workflow is no longer an active authoring surface; "
        "use autoloop.simple or autoloop instead."
    )
