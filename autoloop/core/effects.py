"""Typed runtime effects for deterministic worklist operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .primitives import Event, Fail, Goto, RequestInput

EffectControl = str | Event | RequestInput | Goto | Fail | None


def _normalize_optional_worklist_name(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("worklist must be a string when provided")
    normalized = value.strip()
    if not normalized:
        raise ValueError("worklist must be non-empty when provided")
    return normalized


def _validate_effect_control(value: Any, *, field_name: str) -> None:
    if value is None:
        return
    if isinstance(value, (str, Event, RequestInput, Goto, Fail)):
        return
    raise TypeError(
        f"{field_name} must be a route tag, Event, RequestInput, Goto, Fail, or None"
    )


@dataclass(frozen=True, slots=True)
class WorklistEffect:
    """One deterministic worklist mutation request."""

    worklist: str | None = None
    refresh: bool = False
    set_current_status: str | None = None
    reset_current_status: bool = False
    advance: bool = False
    exhausted: EffectControl = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "worklist", _normalize_optional_worklist_name(self.worklist))
        if self.set_current_status is not None:
            if not isinstance(self.set_current_status, str):
                raise TypeError("set_current_status must be a string when provided")
            normalized = self.set_current_status.strip()
            if not normalized:
                raise ValueError("set_current_status must be non-empty when provided")
            object.__setattr__(self, "set_current_status", normalized)
        if self.set_current_status is not None and self.reset_current_status:
            raise ValueError("set_current_status and reset_current_status cannot both be set")
        _validate_effect_control(self.exhausted, field_name="exhausted")

    @classmethod
    def refresh_current(cls, *, worklist: str | None = None) -> "WorklistEffect":
        return cls(worklist=worklist, refresh=True)

    @classmethod
    def complete_current(cls, *, worklist: str | None = None) -> "WorklistEffect":
        return cls(worklist=worklist, set_current_status="completed")

    @classmethod
    def advance_current(
        cls,
        *,
        worklist: str | None = None,
        exhausted: EffectControl = None,
    ) -> "WorklistEffect":
        return cls(worklist=worklist, advance=True, exhausted=exhausted)

    @classmethod
    def complete_and_advance(
        cls,
        *,
        worklist: str | None = None,
        exhausted: EffectControl = None,
    ) -> "WorklistEffect":
        return cls(
            worklist=worklist,
            set_current_status="completed",
            advance=True,
            exhausted=exhausted,
        )


@dataclass(frozen=True, slots=True)
class Effects:
    """Typed effect bundle accepted from hooks and python steps."""

    worklists: tuple[WorklistEffect, ...] = ()
    event: EffectControl = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "worklists", tuple(self.worklists))
        _validate_effect_control(self.event, field_name="event")

    @classmethod
    def then(cls, event: EffectControl) -> "Effects":
        return cls(event=event)

    @classmethod
    def advance(
        cls,
        *,
        worklist: str | None = None,
        exhausted: EffectControl = None,
    ) -> "Effects":
        return cls(worklists=(WorklistEffect.advance_current(worklist=worklist, exhausted=exhausted),))

    @classmethod
    def complete_and_advance(
        cls,
        *,
        worklist: str | None = None,
        exhausted: EffectControl = None,
    ) -> "Effects":
        return cls(worklists=(WorklistEffect.complete_and_advance(worklist=worklist, exhausted=exhausted),))

    @classmethod
    def refresh(cls, worklist: str | None = None) -> "Effects":
        return cls(worklists=(WorklistEffect.refresh_current(worklist=worklist),))


__all__ = ["Effects", "WorklistEffect"]
