"""Legacy workflow shim.

The active public authoring surface is `autoloop.simple` (or `autoloop`).
This module intentionally no longer re-exports authoring primitives.
"""

from __future__ import annotations

__all__: list[str] = []


def __getattr__(name: str) -> object:
    raise AttributeError(
        "workflow is no longer an active authoring surface; "
        "use autoloop.simple or autoloop instead."
    )
