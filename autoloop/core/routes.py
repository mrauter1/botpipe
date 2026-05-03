"""Typed route declarations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .effects import Effects, WorklistEffect
from .primitives import AWAIT_INPUT, FAIL, FINISH


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
class Route:
    """Explicit route target plus optional metadata and route-local hook."""

    target: object | None = None
    summary: str | None = None
    required_writes: tuple[str, ...] | None = None
    handoff: str | None = None
    on_taken: object | None = None
    provider_visible: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "summary", _normalize_optional_text(self.summary, field_name="summary"))
        if self.required_writes is None:
            object.__setattr__(self, "required_writes", None)
        else:
            object.__setattr__(self, "required_writes", _normalize_required_writes(self.required_writes))
        object.__setattr__(self, "handoff", _normalize_optional_text(self.handoff, field_name="handoff"))
        object.__setattr__(self, "provider_visible", bool(self.provider_visible))

    @staticmethod
    def to(
        target: object,
        *,
        summary: str | None = None,
        required_writes: Iterable[str] | None = None,
        handoff: str | None = None,
        on_taken: object | None = None,
        provider_visible: bool = True,
    ) -> "Route":
        return Route(
            target=target,
            summary=summary,
            required_writes=(_normalize_required_writes(required_writes) if required_writes is not None else None),
            handoff=handoff,
            on_taken=on_taken,
            provider_visible=provider_visible,
        )

    @staticmethod
    def finish(
        *,
        summary: str | None = None,
        required_writes: Iterable[str] | None = None,
        handoff: str | None = None,
        on_taken: object | None = None,
        provider_visible: bool = True,
    ) -> "Route":
        return Route.to(
            FINISH,
            summary=summary,
            required_writes=required_writes,
            handoff=handoff,
            on_taken=on_taken,
            provider_visible=provider_visible,
        )

    @staticmethod
    def await_input(
        *,
        summary: str | None = None,
        required_writes: Iterable[str] | None = None,
        handoff: str | None = None,
        on_taken: object | None = None,
        provider_visible: bool = True,
    ) -> "Route":
        return Route.to(
            AWAIT_INPUT,
            summary=summary,
            required_writes=required_writes,
            handoff=handoff,
            on_taken=on_taken,
            provider_visible=provider_visible,
        )

    @staticmethod
    def fail(
        *,
        summary: str | None = None,
        required_writes: Iterable[str] | None = None,
        handoff: str | None = None,
        on_taken: object | None = None,
        provider_visible: bool = True,
    ) -> "Route":
        return Route.to(
            FAIL,
            summary=summary,
            required_writes=required_writes,
            handoff=handoff,
            on_taken=on_taken,
            provider_visible=provider_visible,
        )

    @staticmethod
    def advance(
        target: object,
        *,
        worklist: str | None = None,
        status: str | None = None,
        exhausted: str | object | None = None,
        summary: str | None = None,
        required_writes: Iterable[str] | None = None,
        handoff: str | None = None,
        provider_visible: bool = True,
    ) -> "Route":
        effect = Effects(
            worklists=(
                WorklistEffect(
                    worklist=worklist,
                    set_current_status=status,
                    advance=True,
                    exhausted=exhausted,
                ),
            ),
        )
        return Route.to(
            target,
            summary=summary,
            required_writes=required_writes,
            handoff=handoff,
            on_taken=_route_effect_hook(effect),
            provider_visible=provider_visible,
        )

    @staticmethod
    def refresh(
        target: object,
        *,
        worklist: str | None,
        summary: str | None = None,
        required_writes: Iterable[str] | None = None,
        handoff: str | None = None,
        provider_visible: bool = True,
    ) -> "Route":
        return Route.to(
            target,
            summary=summary,
            required_writes=required_writes,
            handoff=handoff,
            on_taken=_route_effect_hook(Effects.refresh(worklist)),
            provider_visible=provider_visible,
        )

    @staticmethod
    def complete_current(
        target: object,
        *,
        worklist: str | None = None,
        summary: str | None = None,
        required_writes: Iterable[str] | None = None,
        handoff: str | None = None,
        provider_visible: bool = True,
    ) -> "Route":
        return Route.to(
            target,
            summary=summary,
            required_writes=required_writes,
            handoff=handoff,
            on_taken=_route_effect_hook(
                Effects(worklists=(WorklistEffect(worklist=worklist, set_current_status="completed"),))
            ),
            provider_visible=provider_visible,
        )


def _route_effect_hook(effects: Effects):
    def on_taken(_ctx):
        return effects

    on_taken.__name__ = "route_effect"
    return on_taken


def normalize_route_spec(destination: object) -> Route:
    """Normalize shorthand workflow transition declarations to Route objects."""

    if isinstance(destination, Route):
        return destination
    if destination == FINISH:
        return Route.finish()
    if destination == AWAIT_INPUT:
        return Route.await_input()
    if destination == FAIL:
        return Route.fail()
    return Route.to(destination)


__all__ = ["Route"]
