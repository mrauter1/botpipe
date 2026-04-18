"""Small control-flow helpers for strict workflows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

from autoloop_v3.workflow import GLOBAL, PAUSE
from autoloop_v3.workflow.primitives import Event, Outcome


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


def pause_on_outcome_tags(*tags: str) -> dict[str, str]:
    """Map outcome tags to the `PAUSE` terminal."""

    return {tag: PAUSE for tag in tags}


def event_on_outcome_tags(*tags: str) -> Callable[[object, Outcome], Event | None]:
    """Build a strict `on_outcome` handler for passthrough control tags."""

    selected = frozenset(tags)

    def handler(state: object, outcome: Outcome) -> Event | None:
        if outcome.tag not in selected:
            return None
        return Event(outcome.tag, reason=outcome.reason, question=outcome.question)

    return handler

