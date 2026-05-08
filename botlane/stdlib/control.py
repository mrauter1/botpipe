"""Small control-flow helpers for strict workflows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

from botlane.core.primitives import AWAIT_INPUT, Event, GLOBAL


RouteMap = Mapping[str, Any]
TransitionTable = Mapping[object, RouteMap]


def merge_transitions(*tables: TransitionTable | None) -> dict[object, dict[str, Any]]:
    """Merge transition tables without introducing a second topology DSL."""

    merged: dict[object, dict[str, Any]] = {}
    for table in tables:
        if not table:
            continue
        for source, routes in table.items():
            merged.setdefault(source, {}).update(dict(routes))
    return merged


def global_routes(*route_maps: RouteMap | None, **routes: Any) -> dict[object, dict[str, Any]]:
    """Return one `GLOBAL` transition block from flat route fragments."""

    merged: dict[str, Any] = {}
    for route_map in route_maps:
        if route_map:
            merged.update(dict(route_map))
    merged.update(routes)
    return {GLOBAL: merged}


def await_input_on_outcome_tags(*tags: str) -> dict[str, str]:
    """Map outcome tags to the `AWAIT_INPUT` terminal."""

    return {tag: AWAIT_INPUT for tag in tags}


def event_on_outcome_tags(*tags: str) -> Callable[[Any], Event | None]:
    """Build an explicit `hook(ctx)` passthrough for selected outcome tags."""

    selected = frozenset(tags)

    def handler(ctx: Any) -> Event | None:
        if ctx.outcome.tag not in selected:
            return None
        return Event(ctx.outcome.tag, reason=ctx.outcome.reason, question=ctx.outcome.question)

    return handler
