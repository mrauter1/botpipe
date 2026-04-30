"""Internal compatibility surface for legacy low-level workflow authoring names."""

from __future__ import annotations

from dataclasses import dataclass

from .descriptors import Param, StateVar
from .primitives import FINISH
from .routes import Route
from .steps import AfterHookResult
from .steps import LLMStep as _LLMStep
from .steps import PairStep as _PairStep
from .steps import SystemStep as _SystemStep
from .steps import WorkflowStep as _WorkflowStep

SUCCESS = "SUCCESS"


def normalize_legacy_terminal(value: str | None) -> str | None:
    if value == SUCCESS:
        return FINISH
    return value


def legacy_success_terminal() -> str:
    return SUCCESS


def is_legacy_success_terminal(value: object) -> bool:
    return value == SUCCESS


def allows_legacy_contract(value: object) -> bool:
    return bool(getattr(value, "__autoloop_legacy_compat__", False))


@dataclass(frozen=True, slots=True)
class RouteInfo:
    summary: str | None = None
    required_outputs: tuple[str, ...] = ()
    handoff: str | None = None

    def __post_init__(self) -> None:
        route = self.to_route()
        object.__setattr__(self, "summary", route.summary)
        object.__setattr__(self, "required_outputs", tuple(route.required_writes or ()))
        object.__setattr__(self, "handoff", route.handoff)

    def to_route(self) -> Route:
        return Route(
            summary=self.summary,
            required_writes=self.required_outputs,
            handoff=self.handoff,
        )


def _normalize_compat_route_metadata(route_infos: object | None) -> dict[str, Route] | None:
    if route_infos is None:
        return None
    normalized: dict[str, Route] = {}
    for route_name, info in dict(route_infos).items():
        if isinstance(info, str):
            normalized[route_name] = Route(summary=info)
            continue
        if isinstance(info, RouteInfo):
            normalized[route_name] = info.to_route()
            continue
        raise TypeError("route_infos values must be RouteInfo instances or summary strings")
    return normalized


class LLMStep(_LLMStep):
    __autoloop_legacy_compat__ = True

    def __init__(self, *args, route_infos=None, **kwargs):
        super().__init__(*args, route_metadata=_normalize_compat_route_metadata(route_infos), **kwargs)


class PairStep(_PairStep):
    __autoloop_legacy_compat__ = True

    def __init__(self, *args, route_infos=None, **kwargs):
        super().__init__(*args, route_metadata=_normalize_compat_route_metadata(route_infos), **kwargs)


class SystemStep(_SystemStep):
    __autoloop_legacy_compat__ = True

    def __init__(self, *args, route_infos=None, **kwargs):
        super().__init__(*args, route_metadata=_normalize_compat_route_metadata(route_infos), **kwargs)


class WorkflowStep(_WorkflowStep):
    __autoloop_legacy_compat__ = True

    def __init__(self, *args, route_infos=None, **kwargs):
        super().__init__(*args, route_metadata=_normalize_compat_route_metadata(route_infos), **kwargs)

__all__ = [
    "AfterHookResult",
    "LLMStep",
    "PairStep",
    "Param",
    "RouteInfo",
    "SUCCESS",
    "StateVar",
    "SystemStep",
    "WorkflowStep",
]
