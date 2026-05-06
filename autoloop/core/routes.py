"""Typed route declarations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

from .effects import Effects, WorklistEffect
from .primitives import AWAIT_INPUT, FAIL, FINISH


ProviderVisibility = Literal["hidden", "interactive_only", "always"]
RoutePresetKind = Literal["question", "blocked", "failed", "custom", "hidden", "disabled"]


@dataclass(frozen=True, slots=True)
class _PayloadSchemaSentinel:
    mode: Literal["inherit", "none"]


_INHERIT_PAYLOAD_SCHEMA = _PayloadSchemaSentinel("inherit")
_NO_PAYLOAD_SCHEMA = _PayloadSchemaSentinel("none")


def _route_question_fields_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {
                    "type": "string",
                    "minLength": 1,
                },
                "minItems": 1,
            },
            "reason": {
                "type": ["string", "null"],
            },
        },
        "required": ["questions", "reason"],
        "additionalProperties": False,
    }


def _route_reason_fields_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "reason": {
                "type": ["string", "null"],
            },
        },
        "required": ["reason"],
        "additionalProperties": False,
    }


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
    provider_visibility: ProviderVisibility | None = None
    payload_schema: object = _INHERIT_PAYLOAD_SCHEMA
    route_fields_schema: Any | None = None
    preset_kind: RoutePresetKind = "custom"
    is_disabled: bool = False
    payload_schema_mode: Literal["inherit", "none", "explicit"] = field(init=False, default="inherit")
    _handwritten_route_fields_validation_equivalent: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "summary", _normalize_optional_text(self.summary, field_name="summary"))
        if self.required_writes is None:
            object.__setattr__(self, "required_writes", None)
        else:
            object.__setattr__(self, "required_writes", _normalize_required_writes(self.required_writes))
        object.__setattr__(self, "handoff", _normalize_optional_text(self.handoff, field_name="handoff"))
        normalized_visibility = _normalize_provider_visibility(
            provider_visible=self.provider_visible,
            provider_visibility=self.provider_visibility,
        )
        object.__setattr__(self, "provider_visibility", normalized_visibility)
        object.__setattr__(self, "provider_visible", normalized_visibility != "hidden")
        payload_schema_mode, normalized_payload_schema = _normalize_payload_schema(self.payload_schema)
        object.__setattr__(self, "payload_schema_mode", payload_schema_mode)
        object.__setattr__(self, "payload_schema", normalized_payload_schema)
        if self.is_disabled:
            if self.target is not None:
                raise ValueError("disabled routes must not declare a target")
            if self.handoff is not None or self.on_taken is not None:
                raise ValueError("disabled routes must not declare handoff or on_taken metadata")
            if self.required_writes not in {None, ()}:
                raise ValueError("disabled routes must not declare required_writes")
            object.__setattr__(self, "provider_visibility", "hidden")
            object.__setattr__(self, "provider_visible", False)
            object.__setattr__(self, "preset_kind", "disabled")
        elif self.preset_kind == "hidden":
            object.__setattr__(self, "provider_visibility", "hidden")
            object.__setattr__(self, "provider_visible", False)
        else:
            object.__setattr__(self, "preset_kind", _normalize_preset_kind(self.preset_kind))

    @staticmethod
    def to(
        target: object,
        *,
        summary: str | None = None,
        required_writes: Iterable[str] | None = None,
        handoff: str | None = None,
        on_taken: object | None = None,
        provider_visible: bool = True,
        provider_visibility: ProviderVisibility | None = None,
        payload_schema: object = _INHERIT_PAYLOAD_SCHEMA,
        route_fields_schema: Any | None = None,
        preset_kind: RoutePresetKind = "custom",
    ) -> "Route":
        return Route(
            target=target,
            summary=summary,
            required_writes=(_normalize_required_writes(required_writes) if required_writes is not None else None),
            handoff=handoff,
            on_taken=on_taken,
            provider_visible=provider_visible,
            provider_visibility=provider_visibility,
            payload_schema=payload_schema,
            route_fields_schema=route_fields_schema,
            preset_kind=preset_kind,
        )

    @staticmethod
    def finish(
        *,
        summary: str | None = None,
        required_writes: Iterable[str] | None = None,
        handoff: str | None = None,
        on_taken: object | None = None,
        provider_visible: bool = True,
        provider_visibility: ProviderVisibility | None = None,
        payload_schema: object = _INHERIT_PAYLOAD_SCHEMA,
        route_fields_schema: Any | None = None,
        preset_kind: RoutePresetKind = "custom",
    ) -> "Route":
        return Route.to(
            FINISH,
            summary=summary,
            required_writes=required_writes,
            handoff=handoff,
            on_taken=on_taken,
            provider_visible=provider_visible,
            provider_visibility=provider_visibility,
            payload_schema=payload_schema,
            route_fields_schema=route_fields_schema,
            preset_kind=preset_kind,
        )

    @staticmethod
    def await_input(
        *,
        summary: str | None = None,
        required_writes: Iterable[str] | None = None,
        handoff: str | None = None,
        on_taken: object | None = None,
        provider_visible: bool = True,
        provider_visibility: ProviderVisibility | None = None,
        payload_schema: object = _INHERIT_PAYLOAD_SCHEMA,
        route_fields_schema: Any | None = None,
        preset_kind: RoutePresetKind = "custom",
    ) -> "Route":
        return Route.to(
            AWAIT_INPUT,
            summary=summary,
            required_writes=required_writes,
            handoff=handoff,
            on_taken=on_taken,
            provider_visible=provider_visible,
            provider_visibility=provider_visibility,
            payload_schema=payload_schema,
            route_fields_schema=route_fields_schema,
            preset_kind=preset_kind,
        )

    @staticmethod
    def fail(
        *,
        summary: str | None = None,
        required_writes: Iterable[str] | None = None,
        handoff: str | None = None,
        on_taken: object | None = None,
        provider_visible: bool = True,
        provider_visibility: ProviderVisibility | None = None,
        payload_schema: object = _INHERIT_PAYLOAD_SCHEMA,
        route_fields_schema: Any | None = None,
        preset_kind: RoutePresetKind = "custom",
    ) -> "Route":
        return Route.to(
            FAIL,
            summary=summary,
            required_writes=required_writes,
            handoff=handoff,
            on_taken=on_taken,
            provider_visible=provider_visible,
            provider_visibility=provider_visibility,
            payload_schema=payload_schema,
            route_fields_schema=route_fields_schema,
            preset_kind=preset_kind,
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
        provider_visibility: ProviderVisibility | None = None,
        payload_schema: object = _INHERIT_PAYLOAD_SCHEMA,
        route_fields_schema: Any | None = None,
        preset_kind: RoutePresetKind = "custom",
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
            provider_visibility=provider_visibility,
            payload_schema=payload_schema,
            route_fields_schema=route_fields_schema,
            preset_kind=preset_kind,
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
        provider_visibility: ProviderVisibility | None = None,
        payload_schema: object = _INHERIT_PAYLOAD_SCHEMA,
        route_fields_schema: Any | None = None,
        preset_kind: RoutePresetKind = "custom",
    ) -> "Route":
        return Route.to(
            target,
            summary=summary,
            required_writes=required_writes,
            handoff=handoff,
            on_taken=_route_effect_hook(Effects.refresh(worklist)),
            provider_visible=provider_visible,
            provider_visibility=provider_visibility,
            payload_schema=payload_schema,
            route_fields_schema=route_fields_schema,
            preset_kind=preset_kind,
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
        provider_visibility: ProviderVisibility | None = None,
        payload_schema: object = _INHERIT_PAYLOAD_SCHEMA,
        route_fields_schema: Any | None = None,
        preset_kind: RoutePresetKind = "custom",
    ) -> "Route":
        return Route.to(
            target,
            summary=summary,
            required_writes=required_writes,
            handoff=handoff,
            on_taken=_route_effect_hook(Effects(worklists=(WorklistEffect.complete_current(worklist=worklist),))),
            provider_visible=provider_visible,
            provider_visibility=provider_visibility,
            payload_schema=payload_schema,
            route_fields_schema=route_fields_schema,
            preset_kind=preset_kind,
        )

    @staticmethod
    def complete_and_advance(
        target: object,
        *,
        worklist: str | None = None,
        exhausted: str | object | None = None,
        summary: str | None = None,
        required_writes: Iterable[str] | None = None,
        handoff: str | None = None,
        provider_visible: bool = True,
        provider_visibility: ProviderVisibility | None = None,
        payload_schema: object = _INHERIT_PAYLOAD_SCHEMA,
        route_fields_schema: Any | None = None,
        preset_kind: RoutePresetKind = "custom",
    ) -> "Route":
        return Route.to(
            target,
            summary=summary,
            required_writes=required_writes,
            handoff=handoff,
            on_taken=_route_effect_hook(
                Effects(worklists=(WorklistEffect.complete_and_advance(worklist=worklist, exhausted=exhausted),))
            ),
            provider_visible=provider_visible,
            provider_visibility=provider_visibility,
            payload_schema=payload_schema,
            route_fields_schema=route_fields_schema,
            preset_kind=preset_kind,
        )

    @staticmethod
    def inherit_payload_schema() -> object:
        return _INHERIT_PAYLOAD_SCHEMA

    @staticmethod
    def no_payload_schema() -> object:
        return _NO_PAYLOAD_SCHEMA

    @staticmethod
    def question(
        target: object = AWAIT_INPUT,
        *,
        summary: str | None = None,
        provider_visibility: ProviderVisibility = "interactive_only",
        payload_schema: object = _INHERIT_PAYLOAD_SCHEMA,
        route_fields_schema: Any | None = None,
        required_writes: Iterable[str] = (),
        handoff: str | None = None,
        on_taken: object | None = None,
    ) -> "Route":
        return Route.to(
            target,
            summary=summary or "Clarification or user-input request.",
            required_writes=required_writes,
            handoff=handoff,
            on_taken=on_taken,
            provider_visibility=provider_visibility,
            payload_schema=payload_schema,
            route_fields_schema=_route_question_fields_schema() if route_fields_schema is None else route_fields_schema,
            preset_kind="question",
            _handwritten_route_fields_validation_equivalent=route_fields_schema is None,
        )

    @staticmethod
    def blocked(
        target: object = AWAIT_INPUT,
        *,
        summary: str | None = None,
        provider_visibility: ProviderVisibility = "interactive_only",
        payload_schema: object = _INHERIT_PAYLOAD_SCHEMA,
        route_fields_schema: Any | None = None,
        required_writes: Iterable[str] = (),
        handoff: str | None = None,
        on_taken: object | None = None,
    ) -> "Route":
        return Route.to(
            target,
            summary=summary or "Blocked pending external input or intervention.",
            required_writes=required_writes,
            handoff=handoff,
            on_taken=on_taken,
            provider_visibility=provider_visibility,
            payload_schema=payload_schema,
            route_fields_schema=_route_reason_fields_schema() if route_fields_schema is None else route_fields_schema,
            preset_kind="blocked",
            _handwritten_route_fields_validation_equivalent=route_fields_schema is None,
        )

    @staticmethod
    def failed(
        target: object = FAIL,
        *,
        summary: str | None = None,
        provider_visibility: ProviderVisibility = "always",
        payload_schema: object = _INHERIT_PAYLOAD_SCHEMA,
        route_fields_schema: Any | None = None,
        required_writes: Iterable[str] = (),
        handoff: str | None = None,
        on_taken: object | None = None,
    ) -> "Route":
        return Route.to(
            target,
            summary=summary or "Terminal or unrecoverable failure.",
            required_writes=required_writes,
            handoff=handoff,
            on_taken=on_taken,
            provider_visibility=provider_visibility,
            payload_schema=payload_schema,
            route_fields_schema=_route_reason_fields_schema() if route_fields_schema is None else route_fields_schema,
            preset_kind="failed",
            _handwritten_route_fields_validation_equivalent=route_fields_schema is None,
        )

    @staticmethod
    def hidden(
        target: object,
        *,
        summary: str | None = None,
        payload_schema: object = _INHERIT_PAYLOAD_SCHEMA,
        route_fields_schema: Any | None = None,
        required_writes: Iterable[str] = (),
        handoff: str | None = None,
        on_taken: object | None = None,
    ) -> "Route":
        return Route.to(
            target,
            summary=summary,
            required_writes=required_writes,
            handoff=handoff,
            on_taken=on_taken,
            provider_visible=False,
            provider_visibility="hidden",
            payload_schema=payload_schema,
            route_fields_schema=route_fields_schema,
            preset_kind="hidden",
        )

    @staticmethod
    def disabled() -> "Route":
        return Route(
            target=None,
            provider_visible=False,
            provider_visibility="hidden",
            payload_schema=_INHERIT_PAYLOAD_SCHEMA,
            route_fields_schema=None,
            preset_kind="disabled",
            is_disabled=True,
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


def _normalize_provider_visibility(
    *,
    provider_visible: bool,
    provider_visibility: ProviderVisibility | None,
) -> ProviderVisibility:
    if provider_visibility is None:
        return "always" if provider_visible else "hidden"
    if provider_visibility not in {"hidden", "interactive_only", "always"}:
        raise ValueError(f"unsupported provider_visibility {provider_visibility!r}")
    return provider_visibility


def _normalize_payload_schema(
    value: object,
) -> tuple[Literal["inherit", "none", "explicit"], object | None]:
    if value is None or value == _INHERIT_PAYLOAD_SCHEMA:
        return "inherit", _INHERIT_PAYLOAD_SCHEMA
    if value == _NO_PAYLOAD_SCHEMA:
        return "none", None
    return "explicit", value


def _normalize_preset_kind(value: RoutePresetKind) -> RoutePresetKind:
    if value not in {"question", "blocked", "failed", "custom", "hidden", "disabled"}:
        raise ValueError(f"unsupported route preset kind {value!r}")
    return value


__all__ = ["Route"]
