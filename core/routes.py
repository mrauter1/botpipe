"""Typed route declarations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .effects import Effect
from .primitives import FAIL, PAUSE, SUCCESS


def _normalize_optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string when provided")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty when provided")
    return normalized


def _normalize_required_outputs(value: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError("required_outputs entries must be strings")
        stripped = item.strip()
        if not stripped:
            raise ValueError("required_outputs entries must be non-empty strings")
        normalized.append(stripped)
    return tuple(normalized)


@dataclass(frozen=True, slots=True)
class RouteInfo:
    """Optional route metadata for rendering and inspection."""

    summary: str | None = None
    required_outputs: tuple[str, ...] = ()
    handoff: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "summary", _normalize_optional_text(self.summary, field_name="summary"))
        object.__setattr__(self, "required_outputs", _normalize_required_outputs(self.required_outputs))
        object.__setattr__(self, "handoff", _normalize_optional_text(self.handoff, field_name="handoff"))


@dataclass(frozen=True, slots=True)
class Route:
    """Explicit route target plus optional side effects."""

    target: object | None = None
    effects: tuple[Effect, ...] = ()
    summary: str | None = None
    required_outputs: tuple[str, ...] = ()
    handoff: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "summary", _normalize_optional_text(self.summary, field_name="summary"))
        object.__setattr__(self, "required_outputs", _normalize_required_outputs(self.required_outputs))
        object.__setattr__(self, "handoff", _normalize_optional_text(self.handoff, field_name="handoff"))

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
