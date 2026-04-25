"""Typed route declarations."""

from __future__ import annotations

from dataclasses import dataclass

from .effects import Effect
from .primitives import FAIL, PAUSE, SUCCESS


@dataclass(frozen=True, slots=True)
class Route:
    """Explicit route target plus optional side effects."""

    target: object | None = None
    effects: tuple[Effect, ...] = ()

    @staticmethod
    def to(target: object, *effects: Effect) -> "Route":
        return Route(target=target, effects=tuple(effects))

    @staticmethod
    def complete(*effects: Effect) -> "Route":
        return Route(target=SUCCESS, effects=tuple(effects))

    @staticmethod
    def pause(*effects: Effect) -> "Route":
        return Route(target=PAUSE, effects=tuple(effects))

    @staticmethod
    def fail(*effects: Effect) -> "Route":
        return Route(target=FAIL, effects=tuple(effects))


__all__ = ["Route"]
