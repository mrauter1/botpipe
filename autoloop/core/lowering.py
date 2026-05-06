"""Compilation-time lowering and route-shape helpers."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Any

from pydantic import TypeAdapter

from .errors import WorkflowValidationError
from .inventory import ArtifactInventoryRecord, resolve_artifact_reference
from .routes import Route, normalize_route_spec
from .steps import Step


PayloadValidator = Callable[[dict[str, Any]], None]


@dataclass(frozen=True, slots=True)
class ResolvedRouteSpec:
    tag: str
    route: Route
    inheritance_source: str
    legacy_runtime_control: bool = False


def outcome_middleware_name(definition: Any) -> str | None:
    """Legacy outcome middleware is no longer part of the public compiler path."""

    return None


def step_available_route_tags(definition: Any, step: Step) -> tuple[str, ...]:
    """Return the ordered legal route tags for a step."""

    return tuple(spec.tag for spec in resolve_step_routes(definition, step) if not spec.route.is_disabled)


def step_authored_route_tags(definition: Any, step: Step) -> tuple[str, ...]:
    """Return the ordered authored route tags for a step."""

    composite_tags = getattr(step, "composite_route_tags", None)
    if composite_tags:
        return tuple(composite_tags)
    step_routes = definition.authored_transitions.get(step, {})
    global_routes = definition.authored_transitions.get(definition.global_route_sentinel, {})
    return tuple(dict.fromkeys((*step_routes.keys(), *global_routes.keys())))


def step_runtime_control_route_tags(definition: Any, step: Step) -> tuple[str, ...]:
    """Return the ordered runtime-control route tags for a step."""

    return tuple(
        spec.tag
        for spec in resolve_step_routes(definition, step)
        if spec.legacy_runtime_control and not spec.route.is_disabled
    )


def resolve_step_routes(definition: Any, step: Step) -> tuple[ResolvedRouteSpec, ...]:
    """Resolve step-local, GLOBAL, and framework-default routes by precedence."""

    step_routes = definition.transitions.get(step, {})
    global_routes = definition.transitions.get(definition.global_route_sentinel, {})
    framework_defaults = getattr(definition, "framework_default_transitions_by_step", {}).get(step.name, {})
    ordered_tags = tuple(dict.fromkeys((*step_routes.keys(), *global_routes.keys(), *framework_defaults.keys())))
    resolved: list[ResolvedRouteSpec] = []
    for tag in ordered_tags:
        if tag in step_routes:
            resolved.append(
                ResolvedRouteSpec(
                    tag=tag,
                    route=normalize_route_spec(step_routes[tag]),
                    inheritance_source="step_local",
                )
            )
            continue
        if tag in global_routes:
            resolved.append(
                ResolvedRouteSpec(
                    tag=tag,
                    route=normalize_route_spec(global_routes[tag]),
                    inheritance_source="global",
                )
            )
            continue
        if tag in framework_defaults:
            resolved.append(
                ResolvedRouteSpec(
                    tag=tag,
                    route=normalize_route_spec(framework_defaults[tag]),
                    inheritance_source="framework_default",
                    legacy_runtime_control=True,
                )
            )
    return tuple(resolved)


def normalize_step_route_metadata(
    definition: Any,
    step: Step,
    inventory: dict[str, ArtifactInventoryRecord],
) -> dict[str, Route]:
    """Normalize one step's route metadata."""

    normalized_routes: dict[str, Route] = {}
    for resolved in resolve_step_routes(definition, step):
        route_name = resolved.tag
        route = resolved.route
        step_metadata = step.route_metadata.get(route_name, Route())
        if step_metadata.target is not None or step_metadata.on_taken is not None:
            raise WorkflowValidationError(
                f"step {step.name!r} route metadata for {route_name!r} may only declare summary, required_writes, or handoff"
            )
        if route.is_disabled:
            normalized_routes[route_name] = route
            continue
        if route.handoff and step_metadata.handoff and route.handoff != step_metadata.handoff:
            raise WorkflowValidationError(
                f"step {step.name!r} route {route_name!r} defines conflicting handoff values"
            )
        if route.required_writes is not None:
            raw_required_writes = route.required_writes
        elif step_metadata.required_writes is not None:
            raw_required_writes = step_metadata.required_writes
        else:
            raw_required_writes = None
        required_writes = (
            None
            if raw_required_writes is None
            else _normalize_route_required_writes(
                raw_required_writes=raw_required_writes,
                step=step,
                inventory=inventory,
            )
        )
        summary = route.summary or step_metadata.summary or _fallback_route_summary(step.name, route_name, route.target)
        handoff = route.handoff or step_metadata.handoff
        normalized_routes[route_name] = replace(
            route,
            summary=summary,
            required_writes=required_writes,
            handoff=handoff,
        )
    return normalized_routes


def compile_expected_output_contract(spec: Any) -> tuple[dict[str, Any], PayloadValidator]:
    """Compile a step output contract into JSON schema plus a runtime validator."""

    if isinstance(spec, Mapping):
        schema = deepcopy(dict(spec))
        validator_cls = _load_jsonschema_validator_cls()
        try:
            validator_cls.check_schema(schema)
        except Exception as exc:  # pragma: no cover
            raise WorkflowValidationError("expected_output_schema must be a valid JSON schema mapping") from exc
        validator = validator_cls(schema)

        def validate_payload(payload: dict[str, Any]) -> None:
            validator.validate(payload)

        return schema, validate_payload

    try:
        adapter = TypeAdapter(spec)
        schema = adapter.json_schema()
    except Exception as exc:  # pragma: no cover
        raise WorkflowValidationError(
            "expected_output_schema must be a JSON schema mapping or pydantic-compatible type"
        ) from exc

    def validate_payload(payload: dict[str, Any]) -> None:
        adapter.validate_python(payload, strict=True)

    return schema, validate_payload


def _load_jsonschema_validator_cls() -> type[Any]:
    try:
        from jsonschema import Draft202012Validator
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise WorkflowValidationError(
            "raw expected_output_schema mappings require the optional jsonschema dependency"
        ) from exc
    return Draft202012Validator


def _normalize_route_required_writes(
    *,
    raw_required_writes: tuple[str, ...] | list[str],
    step: Step,
    inventory: dict[str, ArtifactInventoryRecord],
) -> tuple[str, ...]:
    produced_artifact_names = {
        resolve_artifact_reference(
            artifact,
            inventory,
            step_name=step.name,
            prefer_step_local=True,
        ).qualified_name
        for artifact in step.writes.values()
    }
    resolved_required_writes: list[str] = []
    for artifact_name in raw_required_writes:
        resolved_name = resolve_artifact_reference(
            artifact_name,
            inventory,
            step_name=step.name,
            prefer_step_local=True,
        ).qualified_name
        if resolved_name not in produced_artifact_names:
            raise WorkflowValidationError(
                f"step {step.name!r} route required write {resolved_name!r} is not produced by the step"
            )
        resolved_required_writes.append(resolved_name)
    return tuple(resolved_required_writes)


def _fallback_route_summary(source_step: str, route_name: str, target: object | None) -> str:
    default = definition_default_route_summaries().get(route_name)
    if default is not None:
        return default
    if isinstance(target, Step):
        target_name = target.name
    elif isinstance(target, str):
        target_name = target
    else:
        target_name = "unknown"
    return f"Routes from {source_step!r} to {target_name!r}."


def definition_default_route_summaries() -> dict[str, str]:
    return {
        "done": "Step completed and selected the default completion route.",
        "accepted": "Verifier accepted the governed output.",
        "needs_rework": "Verifier requested local repair within the same work boundary.",
        "needs_replan": "The current work boundary appears incorrect and replanning is needed.",
        "question": "Execution is awaiting user input.",
        "blocked": "Execution cannot continue until an external blocker is resolved.",
        "failed": "Execution cannot continue because the route represents failure.",
    }


__all__ = [
    "PayloadValidator",
    "compile_expected_output_contract",
    "normalize_step_route_metadata",
    "outcome_middleware_name",
    "resolve_step_routes",
    "step_authored_route_tags",
    "step_available_route_tags",
    "step_runtime_control_route_tags",
]
