"""Typed route declarations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .effects import Effect
from .primitives import FAIL, FINISH, PAUSE


def _normalize_optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string when provided")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty when provided")
    return normalized


def _normalize_required_writes(value: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError("required_writes entries must be strings")
        stripped = item.strip()
        if not stripped:
            raise ValueError("required_writes entries must be non-empty strings")
        normalized.append(stripped)
    return tuple(normalized)


@dataclass(frozen=True, slots=True)
class RouteInfo:
    """Legacy internal route metadata shim."""

    summary: str | None = None
    required_outputs: tuple[str, ...] = ()
    handoff: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "summary", _normalize_optional_text(self.summary, field_name="summary"))
        object.__setattr__(self, "required_outputs", _normalize_required_writes(self.required_outputs))
        object.__setattr__(self, "handoff", _normalize_optional_text(self.handoff, field_name="handoff"))


@dataclass(frozen=True, slots=True)
class Route:
    """Explicit route target plus optional side effects."""

    target: object | None = None
    effects: tuple[Effect, ...] = ()
    summary: str | None = None
    required_writes: tuple[str, ...] | None = None
    handoff: str | None = None
    on_taken: object | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "summary", _normalize_optional_text(self.summary, field_name="summary"))
        if self.required_writes is None:
            object.__setattr__(self, "required_writes", None)
        else:
            object.__setattr__(self, "required_writes", _normalize_required_writes(self.required_writes))
        object.__setattr__(self, "handoff", _normalize_optional_text(self.handoff, field_name="handoff"))

    @staticmethod
    def to(
        target: object,
        *effects: Effect,
        summary: str | None = None,
        required_writes: Iterable[str] | None = None,
        handoff: str | None = None,
        on_taken: object | None = None,
    ) -> "Route":
        return Route(
            target=target,
            effects=tuple(effects),
            summary=summary,
            required_writes=(_normalize_required_writes(required_writes) if required_writes is not None else None),
            handoff=handoff,
            on_taken=on_taken,
        )

    @staticmethod
    def finish(
        *effects: Effect,
        summary: str | None = None,
        required_writes: Iterable[str] | None = None,
        handoff: str | None = None,
        on_taken: object | None = None,
    ) -> "Route":
        return Route.to(
            FINISH,
            *effects,
            summary=summary,
            required_writes=required_writes,
            handoff=handoff,
            on_taken=on_taken,
        )

    @staticmethod
    def pause(
        *effects: Effect,
        summary: str | None = None,
        required_writes: Iterable[str] | None = None,
        handoff: str | None = None,
        on_taken: object | None = None,
    ) -> "Route":
        return Route.to(
            PAUSE,
            *effects,
            summary=summary,
            required_writes=required_writes,
            handoff=handoff,
            on_taken=on_taken,
        )

    @staticmethod
    def fail(
        *effects: Effect,
        summary: str | None = None,
        required_writes: Iterable[str] | None = None,
        handoff: str | None = None,
        on_taken: object | None = None,
    ) -> "Route":
        return Route.to(
            FAIL,
            *effects,
            summary=summary,
            required_writes=required_writes,
            handoff=handoff,
            on_taken=on_taken,
        )


def normalize_route_spec(destination: object) -> Route:
    """Normalize shorthand workflow transition declarations to Route objects."""

    if isinstance(destination, Route):
        return destination
    if destination == FINISH:
        return Route.finish()
    if destination == PAUSE:
        return Route.pause()
    if destination == FAIL:
        return Route.fail()
    return Route.to(destination)


__all__ = ["Route"]
