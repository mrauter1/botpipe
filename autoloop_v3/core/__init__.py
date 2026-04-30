"""Explicit compatibility package for `autoloop_v3.core` imports."""

from __future__ import annotations

import core as _core

__all__ = list(getattr(_core, "__all__", ()))
__path__ = list(getattr(_core, "__path__", ()))

for _name in __all__:
    globals()[_name] = getattr(_core, _name)


def __getattr__(name: str) -> object:
    return getattr(_core, name)
