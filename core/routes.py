"""Typed route declarations."""

from __future__ import annotations

from dataclasses import dataclass

from .effects import Effect
from .primitives import FAIL, PAUSE, SUCCESS


@dataclass(frozen=True, slots=True)
class RouteInfo:
    """Optional route metadata for rendering and inspection."""

    summary: str | None = None
    required_outputs: tuple[str, ...] = ()
    handoff: str | None = None


@dataclass(frozen=True, slots=True)
class Route:
    """Explicit route target plus optional side effects."""

    target: object | None = None
    effects: tuple[Effect, ...] = ()
    summary: str | None = None
    required_outputs: tuple[str, ...] = ()
    handoff: str | None = None

    @staticmethod
    def to(
        target: object,
        *effects: Effect,
        summary: str | None = None,
        required_outputs: tuple[str, ...] = (),
        handoff: str | None = None,
    ) -> "Route":
        return Route(
            target=target,
            effects=tuple(effects),
            summary=summary,
            required_outputs=tuple(required_outputs),
            handoff=handoff,
        )

    @staticmethod
    def complete(
        *effects: Effect,
        summary: str | None = None,
        required_outputs: tuple[str, ...] = (),
        handoff: str | None = None,
    ) -> "Route":
        return Route.to(
            SUCCESS,
            *effects,
            summary=summary,
            required_outputs=required_outputs,
            handoff=handoff,
        )

    @staticmethod
    def pause(
        *effects: Effect,
        summary: str | None = None,
        required_outputs: tuple[str, ...] = (),
        handoff: str | None = None,
    ) -> "Route":
        return Route.to(
            PAUSE,
            *effects,
            summary=summary,
            required_outputs=required_outputs,
            handoff=handoff,
        )

    @staticmethod
    def fail(
        *effects: Effect,
        summary: str | None = None,
        required_outputs: tuple[str, ...] = (),
        handoff: str | None = None,
    ) -> "Route":
        return Route.to(
            FAIL,
            *effects,
            summary=summary,
            required_outputs=required_outputs,
            handoff=handoff,
        )


def normalize_route_spec(destination: object) -> Route:
    """Normalize shorthand workflow transition declarations to Route objects."""

    if isinstance(destination, Route):
        return destination
    if destination == SUCCESS:
        return Route.complete()
    if destination == PAUSE:
        return Route.pause()
    if destination == FAIL:
        return Route.fail()
    return Route.to(destination)


__all__ = ["Route", "RouteInfo"]
