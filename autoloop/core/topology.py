"""Topology and route validation ownership."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import validate_artifact_declaration
from .discovery import is_workflow_class
from .errors import WorkflowValidationError
from .inventory import ArtifactInventoryRecord, resolve_artifact_reference
from .lowering import compile_expected_output_contract, normalize_step_route_metadata, step_available_route_tags
from .routes import Route, normalize_route_spec
from .steps import ChildWorkflowStep, ProduceVerifyStep, PythonStep, Step


def validate_required_artifacts(definition: Any, inventory: dict[str, ArtifactInventoryRecord]) -> None:
    step_positions = {step.name: index for index, step in enumerate(definition.steps)}
    for step in definition.steps:
        for artifact_reference in step.requires:
            record = resolve_artifact_reference(artifact_reference, inventory)
            if record.workflow_level:
                continue
            if not any(step_positions[producer] < step_positions[step.name] for producer in record.producer_steps):
                raise WorkflowValidationError(
                    f"step {step.name!r} requires artifact {record.qualified_name!r} before it is produced"
                )
        if not isinstance(step, ProduceVerifyStep):
            continue
        producer_written = set(getattr(step, "producer_writes", ())) or set(step.writes.keys())
        verifier_only_written = set(getattr(step, "verifier_writes", ()))
        for artifact_reference in step.verifier_requires:
            record = resolve_artifact_reference(
                artifact_reference,
                inventory,
                step_name=step.name,
                prefer_step_local=True,
            )
            if record.workflow_level:
                continue
            if record.owner_step == step.name:
                if record.name not in producer_written and record.qualified_name not in producer_written:
                    if record.name in verifier_only_written or record.qualified_name in verifier_only_written:
                        raise WorkflowValidationError(
                            f"step {step.name!r} verifier_requires artifact {record.qualified_name!r} "
                            "is written only during the review phase"
                        )
                continue
            if not any(step_positions[producer] < step_positions[step.name] for producer in record.producer_steps):
                raise WorkflowValidationError(
                    f"step {step.name!r} verifier_requires artifact {record.qualified_name!r} before it is produced"
                )


def validate_artifact_declarations(inventory: dict[str, ArtifactInventoryRecord]) -> None:
    for record in inventory.values():
        errors = validate_artifact_declaration(record.artifact)
        if not errors:
            continue
        owner = f"artifact {record.qualified_name!r}"
        if record.producer_steps:
            owner = f"artifact {record.qualified_name!r} produced by step {record.producer_steps[0]!r}"
        raise WorkflowValidationError(f"{owner} is invalid: {'; '.join(errors)}")


def validate_artifact_graph(definition: Any, inventory: dict[str, ArtifactInventoryRecord]) -> None:
    step_positions = {step.name: index for index, step in enumerate(definition.steps)}
    graph: dict[str, set[str]] = {step.name: set() for step in definition.steps}
    for step in definition.steps:
        for artifact_reference in step.requires:
            record = resolve_artifact_reference(artifact_reference, inventory)
            for producer in record.producer_steps:
                if step_positions[producer] < step_positions[step.name]:
                    graph[producer].add(step.name)
    visiting: set[str] = set()
    visited: set[str] = set()

    def dfs(node: str) -> None:
        if node in visiting:
            raise WorkflowValidationError("artifact dependency graph is cyclic")
        if node in visited:
            return
        visiting.add(node)
        for child in graph[node]:
            dfs(child)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        dfs(node)


def validate_topology(definition: Any) -> None:
    step_identities = {id(step): step for step in definition.steps}
    valid_destinations = _valid_route_destinations(definition)
    for source, routes in definition.transitions.items():
        if source != definition.global_route_sentinel and id(source) not in step_identities:
            raise WorkflowValidationError("transition source step is not declared on the workflow class")
        for tag, destination in routes.items():
            _validate_route_destination(
                definition,
                source=source,
                tag=tag,
                destination=destination,
                step_identities=step_identities,
                valid_destinations=valid_destinations,
            )


def validate_control_contracts(definition: Any, inventory: dict[str, ArtifactInventoryRecord]) -> None:
    for step in definition.steps:
        if isinstance(step, (PythonStep, ChildWorkflowStep)):
            if step.expected_output_schema is not None:
                raise WorkflowValidationError(
                    f"{step.kind} step {step.name!r} cannot declare expected_output_schema"
                )
            if step.retry_policy is not None:
                raise WorkflowValidationError(
                    f"{step.kind} steps do not call a provider and cannot declare provider retry policy."
                )
            if isinstance(step, ChildWorkflowStep):
                _validate_workflow_step_reference(step, definition)
        elif step.expected_output_schema is not None:
            try:
                compile_expected_output_contract(step.expected_output_schema)
            except WorkflowValidationError as exc:
                raise WorkflowValidationError(
                    f"step {step.name!r} has invalid expected_output_schema: {exc}"
                ) from exc

        available_routes = step_available_route_tags(definition, step)
        if step.route_metadata:
            unknown_routes = sorted(route for route in step.route_metadata if route not in available_routes)
            if unknown_routes:
                raise WorkflowValidationError(
                    f"step {step.name!r} declares route metadata for unknown routes {unknown_routes!r}"
                )
        normalize_step_route_metadata(definition, step, inventory)


def _validate_route_destination(
    definition: Any,
    *,
    source: Step | str,
    tag: str,
    destination: Any,
    step_identities: Mapping[int, Step],
    valid_destinations: set[str],
) -> None:
    route = normalize_route_spec(destination)
    target = route.target
    if isinstance(target, Step):
        if id(target) not in step_identities:
            raise WorkflowValidationError(
                f"transition destination step {target.name!r} is not declared on the workflow class"
            )
    elif target not in valid_destinations:
        raise WorkflowValidationError(f"invalid transition destination {target!r}")
    _validate_route_handoff_destination(definition, tag=tag, route=route)

def _validate_workflow_step_reference(step: ChildWorkflowStep, definition: Any) -> None:
    workflow = step.workflow
    if isinstance(workflow, str):
        if not workflow.strip():
            raise WorkflowValidationError(
                f"workflow step {step.name!r} must reference a non-empty workflow name"
            )
        return
    if not is_workflow_class(workflow):
        raise WorkflowValidationError(
            f"workflow step {step.name!r} must reference a workflow class or workflow name"
        )


def _validate_route_handoff_destination(definition: Any, *, route: Route, tag: str) -> None:
    if route.handoff is None:
        return
    target = route.target
    if not isinstance(target, Step):
        return
    resolved = definition.steps_by_name.get(target.name)
    if isinstance(resolved, PythonStep):
        raise WorkflowValidationError(
            f"route {tag!r} cannot deliver handoff metadata to PythonStep {target.name!r}"
        )


def _valid_route_destinations(definition: Any) -> set[str]:
    return {definition.finish_terminal, definition.await_input_terminal, definition.fail_terminal}


__all__ = [
    "validate_artifact_declarations",
    "validate_artifact_graph",
    "validate_control_contracts",
    "validate_required_artifacts",
    "validate_topology",
]
