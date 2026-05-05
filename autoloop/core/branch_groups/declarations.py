"""Public helper declarations for branch groups."""

from __future__ import annotations

from .models import FanInHelperReference


class FanIn:
    """Helper namespace for fan-in-only runtime-owned evidence reads."""

    @staticmethod
    def results() -> FanInHelperReference:
        return FanInHelperReference("results")

    @staticmethod
    def context() -> FanInHelperReference:
        return FanInHelperReference("context")


__all__ = ["FanIn"]
