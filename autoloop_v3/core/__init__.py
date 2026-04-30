"""Explicit compatibility package for `autoloop_v3.core` imports."""

from __future__ import annotations

import sys

import core as _core

sys.modules[__name__] = _core
