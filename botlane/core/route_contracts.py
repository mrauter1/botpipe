"""Internal route contract values.

Not part of the public botlane authoring API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Literal, TypeAlias

from .identifiers import ArtifactId

if TYPE_CHECKING:
    from .stores.protocols import PendingHandoff


RouteTargetKind: TypeAlias = Literal["step", "finish", "await_input", "fail", "disabled"]


@dataclass(frozen=True, slots=True)
class RouteTarget:
    kind: RouteTargetKind
    step_name: str | None = None

    def __post_init__(self) -> None:
        if self.kind == "step":
            if not isinstance(self.step_name, str) or not self.step_name.strip():
                raise ValueError("step route targets require step_name")
            return
        if self.step_name is not None:
            raise ValueError("non-step route targets must not include step_name")


@dataclass(frozen=True, slots=True)
class PayloadContract:
    schema_mode: str = "inherit"
    schema: dict[str, Any] | None = None
    validator: Any | None = None


@dataclass(frozen=True, slots=True)
class RouteFieldsContract:
    schema: dict[str, Any] | None = None
    validator: Any | None = None


@dataclass(frozen=True, slots=True)
class ProviderRoutePolicy:
    visibility: str
    visible: bool
    visible_interactive: bool
    visible_full_auto: bool


@dataclass(frozen=True, slots=True)
class RequiredWriteContract:
    declared: tuple[ArtifactId, ...]
    explicit: tuple[ArtifactId, ...] | None
    effective: tuple[ArtifactId, ...] | None = None


@dataclass(frozen=True, slots=True)
class RouteContract:
    source_step: str
    tag: str
    target: RouteTarget
    summary: str | None
    required_writes: RequiredWriteContract
    handoff: str | None
    on_taken: Callable[..., Any] | None
    provider: ProviderRoutePolicy
    payload: PayloadContract
    route_fields: RouteFieldsContract
    preset_kind: str
    inheritance_source: str
    disabled: bool
    is_runtime_control: bool


@dataclass(frozen=True, slots=True)
class Continue:
    target_step: str
    reason: str = "route"


@dataclass(frozen=True, slots=True)
class Finish:
    reason: str = "finish"


@dataclass(frozen=True, slots=True)
class AwaitInput:
    pending_input: Any


@dataclass(frozen=True, slots=True)
class FailAction:
    reason: str | None = None
    failure_context: Any | None = None


RouteAction: TypeAlias = Continue | Finish | AwaitInput | FailAction


@dataclass(frozen=True, slots=True)
class RouteDecision:
    final_route: str | None
    contract: RouteContract | None
    action: RouteAction
    runtime_control: str | None = None
    pending_handoffs: tuple["PendingHandoff", ...] = ()
    provider_attributable: bool = False
    source_hook: str | None = None
    source_phase: str | None = None


_MISSING_PENDING_INPUT = object()


def route_action_for_contract(
    contract: RouteContract,
    *,
    pending_input: Any = _MISSING_PENDING_INPUT,
    failure_context: Any | None = None,
    reason: str | None = None,
) -> RouteAction:
    """Build a typed runtime action from an internal route contract."""

    target = contract.target
    if target.kind == "step":
        assert target.step_name is not None
        return Continue(target_step=target.step_name, reason=reason or "route")
    if target.kind == "finish":
        return Finish(reason=reason or "finish")
    if target.kind == "await_input":
        if pending_input is _MISSING_PENDING_INPUT:
            raise ValueError("await_input route actions require pending_input")
        return AwaitInput(pending_input=pending_input)
    if target.kind == "fail":
        return FailAction(reason=reason, failure_context=failure_context)
    raise ValueError("disabled routes do not have a runtime action")


def available_route_tags(plan: Any, step_name: str) -> tuple[str, ...]:
    route_table = getattr(plan, "routes", {}).get(step_name, {})
    return tuple(tag for tag, route in route_table.items() if not route.disabled)


def runtime_control_route_tags(plan: Any, step_name: str) -> tuple[str, ...]:
    route_table = getattr(plan, "routes", {}).get(step_name, {})
    return tuple(
        tag
        for tag, route in route_table.items()
        if not route.disabled and route.is_runtime_control
    )


def provider_visible_route_tags(
    plan: Any,
    step_name: str,
    *,
    mode: Literal["interactive", "full_auto"],
) -> tuple[str, ...]:
    route_table = getattr(plan, "routes", {}).get(step_name, {})
    if mode == "interactive":
        return tuple(
            tag
            for tag, route in route_table.items()
            if not route.disabled and route.provider.visible_interactive
        )
    if mode == "full_auto":
        return tuple(
            tag
            for tag, route in route_table.items()
            if not route.disabled and route.provider.visible_full_auto
        )
    raise ValueError(f"unsupported provider-visible route mode {mode!r}")
