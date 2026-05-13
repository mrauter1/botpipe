"""Shared helpers for explicit versus effective route required writes."""

from __future__ import annotations

from typing import Any

from .route_contracts import RouteContract, available_route_tags, required_write_names

def explicit_route_required_writes(route: Any | None) -> tuple[str, ...] | None:
    """Return the explicit required-write override for one route contract."""

    if route is None:
        return None
    if isinstance(route, RouteContract):
        return None if route.required_writes.explicit is None else tuple(
            artifact_id.qualified_name for artifact_id in route.required_writes.explicit
        )
    return None


def effective_route_required_writes(
    compiled: Any,
    *,
    step_name: str,
    route_tag: str,
) -> tuple[str, ...]:
    """Return the runtime-effective required writes for one step route."""

    step = compiled.steps.get(step_name)
    if step is None:
        return ()
    return effective_route_required_writes_for_step(
        compiled,
        step=step,
        route_tag=route_tag,
    )


def effective_route_required_writes_for_step(
    compiled: Any,
    *,
    step: Any,
    route_tag: str,
) -> tuple[str, ...]:
    """Return the runtime-effective required writes for a step route."""

    route = compiled.routes.get(step.name, {}).get(route_tag) or compiled.global_routes.get(route_tag)
    explicit = explicit_route_required_writes(route)
    if explicit is not None:
        return explicit
    return tuple(
        artifact_id.qualified_name
        for artifact_id in step.writes
        if compiled.artifact_spec(artifact_id).required
    )


def effective_route_required_writes_map(
    compiled: Any,
    *,
    step_name: str,
) -> dict[str, tuple[str, ...]]:
    """Return runtime-effective required writes for every available route on a step."""

    step = compiled.steps.get(step_name)
    if step is None:
        return {}
    result: dict[str, tuple[str, ...]] = {}
    composite_route_tags = step.branch_group.composite_route_tags if step.branch_group is not None else ()
    for route_tag in available_route_tags(compiled, step_name, composite_route_tags=composite_route_tags):
        route = compiled.routes.get(step_name, {}).get(route_tag) or compiled.global_routes.get(route_tag)
        if route is None:
            continue
        result[route_tag] = effective_route_required_writes(
            compiled,
            step_name=step_name,
            route_tag=route_tag,
        )
    return result


def route_required_write_payload(
    compiled: Any,
    *,
    step_name: str | None,
    route_tag: str,
    route: Any | None,
) -> dict[str, object]:
    """Return a serialized explicit/effective required-write payload for one route."""

    explicit = explicit_route_required_writes(route)
    payload_required_writes = [] if route is None else list(required_write_names(route) if isinstance(route, RouteContract) else route.required_writes or ())
    payload_explicit = None if explicit is None else list(explicit)
    if route is not None and step_name is None and isinstance(route, RouteContract):
        payload_required_writes = [_public_route_artifact_name(compiled, artifact_id) for artifact_id in route.required_writes.declared]
        if route.required_writes.explicit is None:
            payload_explicit = None
        else:
            payload_explicit = [
                _public_route_artifact_name(compiled, artifact_id)
                for artifact_id in route.required_writes.explicit
            ]
    if route is None:
        effective: list[str] | None = []
    elif step_name is None:
        effective = None if payload_explicit is None else list(payload_explicit)
    else:
        effective = list(
            effective_route_required_writes(
                compiled,
                step_name=step_name,
                route_tag=route_tag,
            )
        )
    return {
        "required_writes": payload_required_writes,
        "explicit_required_writes": payload_explicit,
        "effective_required_writes": effective,
    }


def _public_route_artifact_name(compiled: Any, artifact_id: Any) -> str:
    for public_name, public_artifact_id in getattr(compiled, "public_artifacts", {}).items():
        if public_artifact_id == artifact_id:
            return public_name
    return artifact_id.qualified_name
