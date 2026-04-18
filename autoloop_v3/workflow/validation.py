"""Workflow definition discovery and validation."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from .artifacts import Artifact
from .extensions import WorkflowExtension
from .errors import WorkflowValidationError
from .primitives import FAIL, GLOBAL, PAUSE, SUCCESS
from .steps import LLMStep, PairStep, Session, Step, SystemStep

if TYPE_CHECKING:
    from collections.abc import Mapping


TerminalDestination = str


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    """Discovered workflow definition state."""

    workflow_cls: type[Any]
    workflow_name: str
    state_cls: type[BaseModel]
    entry: Step
    steps: tuple[Step, ...]
    steps_by_name: dict[str, Step]
    sessions_by_name: dict[str, Session]
    workflow_artifacts: dict[str, Artifact]
    workflow_log_artifacts: tuple[Artifact, ...]
    extensions: tuple[WorkflowExtension, ...]
    transitions: dict[Step | str, dict[str, Step | str]]


@dataclass(frozen=True, slots=True)
class ArtifactInventoryRecord:
    """Artifact registry candidate."""

    artifact: Artifact
    name: str
    workflow_level: bool
    producer_steps: tuple[str, ...]


class WorkflowMeta(type):
    """Metaclass that validates workflow subclasses at definition time."""

    def __new__(mcls, name: str, bases: tuple[type[Any], ...], namespace: dict[str, Any]) -> type[Any]:
        cls = super().__new__(mcls, name, bases, namespace)
        if namespace.get("__workflow_abstract__", False) or name == "Workflow":
            return cls
        definition = describe_workflow_class(cls)
        validate_workflow_definition(definition)
        cls.__workflow_definition__ = definition
        return cls


def get_workflow_definition(workflow_cls: type[Any]) -> WorkflowDefinition:
    """Return the cached or freshly validated workflow definition."""

    definition = getattr(workflow_cls, "__workflow_definition__", None)
    if isinstance(definition, WorkflowDefinition):
        return definition
    definition = describe_workflow_class(workflow_cls)
    validate_workflow_definition(definition)
    workflow_cls.__workflow_definition__ = definition
    return definition


def describe_workflow_class(workflow_cls: type[Any]) -> WorkflowDefinition:
    """Discover workflow definition components from a class."""

    state_cls = getattr(workflow_cls, "State", None)
    entry = getattr(workflow_cls, "entry", None)
    transitions = getattr(workflow_cls, "transitions", None)
    extensions = getattr(workflow_cls, "extensions", ())
    workflow_name = getattr(workflow_cls, "name", workflow_cls.__name__)
    workflow_artifacts: dict[str, Artifact] = {}
    sessions_by_name: dict[str, Session] = {}
    steps: list[Step] = []
    steps_by_name: dict[str, Step] = {}
    seen_artifacts: set[int] = set()
    seen_sessions: set[int] = set()
    seen_steps: set[int] = set()

    for attr_name, value in workflow_cls.__dict__.items():
        if isinstance(value, Artifact):
            if id(value) in seen_artifacts:
                continue
            if value.name is None:
                value.bind_name(attr_name)
            workflow_artifacts[attr_name] = value
            seen_artifacts.add(id(value))
        elif isinstance(value, Session):
            if id(value) in seen_sessions:
                continue
            if value.name is None:
                value.bind_name(attr_name)
            sessions_by_name[attr_name] = value
            seen_sessions.add(id(value))
        elif isinstance(value, Step):
            if id(value) in seen_steps:
                continue
            if value.name in steps_by_name:
                raise WorkflowValidationError(f"duplicate step name {value.name!r}")
            steps.append(value)
            steps_by_name[value.name] = value
            seen_steps.add(id(value))

    workflow_log_artifacts = tuple(getattr(workflow_cls, "log_artifacts", ()) or ())
    return WorkflowDefinition(
        workflow_cls=workflow_cls,
        workflow_name=workflow_name,
        state_cls=state_cls,
        entry=entry,
        steps=tuple(sorted(steps, key=lambda step: step._order)),
        steps_by_name=steps_by_name,
        sessions_by_name=sessions_by_name,
        workflow_artifacts=workflow_artifacts,
        workflow_log_artifacts=workflow_log_artifacts,
        extensions=extensions,
        transitions=dict(transitions or {}) if isinstance(transitions, dict) else transitions,
    )


def validate_workflow_definition(definition: WorkflowDefinition) -> None:
    """Validate a workflow definition."""

    _validate_state(definition)
    _validate_entry(definition)
    _validate_transitions_shape(definition)
    _validate_sessions(definition)
    _validate_extensions(definition)
    _validate_handlers(definition)
    inventory = collect_artifact_inventory(definition)
    _validate_required_artifacts(definition, inventory)
    _validate_artifact_graph(definition, inventory)
    _validate_topology(definition)


def has_start_hook(definition: WorkflowDefinition) -> bool:
    """Return whether the lifecycle on_start hook is active."""

    if "start" in definition.steps_by_name:
        return False
    return getattr(definition.workflow_cls, "on_start", None) is not None


def outcome_middleware_name(definition: WorkflowDefinition) -> str | None:
    """Return the active global outcome middleware hook name, if any."""

    if "outcome" in definition.steps_by_name:
        return None
    if getattr(definition.workflow_cls, "on_outcome", None) is None:
        return None
    return "on_outcome"


def collect_artifact_inventory(definition: WorkflowDefinition) -> dict[str, ArtifactInventoryRecord]:
    """Collect artifact registry metadata with canonical names."""

    names_to_identity: dict[str, int] = {}
    records_by_identity: dict[int, dict[str, Any]] = {}

    def register(
        artifact: Artifact,
        *,
        fallback_name: str,
        workflow_level: bool = False,
        producer_step: str | None = None,
    ) -> None:
        if artifact.name is None:
            artifact.bind_name(fallback_name)
        artifact_id = id(artifact)
        name = artifact.name or fallback_name
        existing_identity = names_to_identity.get(name)
        if existing_identity is not None and existing_identity != artifact_id:
            raise WorkflowValidationError(f"duplicate artifact name {name!r}")
        names_to_identity[name] = artifact_id
        record = records_by_identity.setdefault(
            artifact_id,
            {
                "artifact": artifact,
                "name": name,
                "workflow_level": False,
                "producer_steps": [],
            },
        )
        if record["name"] != name:
            raise WorkflowValidationError(f"artifact name drift detected for {artifact!r}")
        if workflow_level:
            record["workflow_level"] = True
        if producer_step is not None and producer_step not in record["producer_steps"]:
            record["producer_steps"].append(producer_step)

    for attr_name, artifact in definition.workflow_artifacts.items():
        register(artifact, fallback_name=attr_name, workflow_level=True)
    for index, artifact in enumerate(definition.workflow_log_artifacts, start=1):
        register(artifact, fallback_name=f"workflow__log_{index}")
    for step in definition.steps:
        for produced_name, artifact in step.produces.items():
            register(artifact, fallback_name=produced_name, producer_step=step.name)
        for index, artifact in enumerate(step.requires, start=1):
            register(artifact, fallback_name=f"{step.name}__require_{index}")
        for index, artifact in enumerate(step.log_artifacts, start=1):
            register(artifact, fallback_name=f"{step.name}__log_{index}")

    inventory = {
        record["name"]: ArtifactInventoryRecord(
            artifact=record["artifact"],
            name=record["name"],
            workflow_level=record["workflow_level"],
            producer_steps=tuple(record["producer_steps"]),
        )
        for record in records_by_identity.values()
    }
    return inventory


def _validate_state(definition: WorkflowDefinition) -> None:
    if not inspect.isclass(definition.state_cls) or not issubclass(definition.state_cls, BaseModel):
        raise WorkflowValidationError("workflow must define nested State inheriting from pydantic.BaseModel")


def _validate_entry(definition: WorkflowDefinition) -> None:
    if not isinstance(definition.entry, Step):
        raise WorkflowValidationError("workflow entry must exist and be a step")
    if definition.entry.name not in definition.steps_by_name:
        raise WorkflowValidationError("workflow entry step must be declared on the workflow class")


def _validate_transitions_shape(definition: WorkflowDefinition) -> None:
    if not isinstance(definition.transitions, dict):
        raise WorkflowValidationError("workflow transitions must be a dict")
    for source, routes in definition.transitions.items():
        if source != GLOBAL and not isinstance(source, Step):
            raise WorkflowValidationError(f"transition source {source!r} must be a step or GLOBAL")
        if not isinstance(routes, dict):
            raise WorkflowValidationError("each transition table must be a dict")


def _validate_sessions(definition: WorkflowDefinition) -> None:
    declared_sessions = {id(session) for session in definition.sessions_by_name.values()}
    for step in definition.steps:
        if step.session is not None and id(step.session) not in declared_sessions:
            raise WorkflowValidationError(
                f"step {step.name!r} references an undeclared session slot"
            )


def _validate_extensions(definition: WorkflowDefinition) -> None:
    if not isinstance(definition.extensions, tuple):
        raise WorkflowValidationError("workflow extensions must be declared as a tuple")
    for extension in definition.extensions:
        if not callable(getattr(extension, "bind", None)):
            raise WorkflowValidationError(
                f"workflow extension {extension!r} must define a callable bind(binding) method"
            )


def _validate_handlers(definition: WorkflowDefinition) -> None:
    handler_names = {name for name in definition.workflow_cls.__dict__ if name.startswith("on_")}

    for step in definition.steps:
        handler_name = f"on_{step.name}"
        raw_handler = getattr(definition.workflow_cls, handler_name, None)
        if isinstance(step, SystemStep) and raw_handler is None:
            raise WorkflowValidationError(f"system step {step.name!r} is missing handler {handler_name!r}")
        if raw_handler is not None:
            expected = {2} if isinstance(step, SystemStep) else {3}
            _validate_callable_arity(handler_name, raw_handler, expected)

    active_middleware = outcome_middleware_name(definition)
    raw_middleware = getattr(definition.workflow_cls, active_middleware, None) if active_middleware else None
    if raw_middleware is not None:
        _validate_callable_arity(active_middleware, raw_middleware, {2})

    if has_start_hook(definition):
        raw_start = getattr(definition.workflow_cls, "on_start", None)
        if raw_start is not None:
            _validate_callable_arity("on_start", raw_start, {2})

    reserved_handler_names: set[str] = set()
    if has_start_hook(definition):
        reserved_handler_names.add("on_start")
    if active_middleware is not None:
        reserved_handler_names.add(active_middleware)

    for handler_name in handler_names:
        if handler_name in reserved_handler_names:
            continue
        step_name = handler_name[3:]
        if step_name not in definition.steps_by_name:
            raise WorkflowValidationError(f"orphan handler {handler_name!r} does not match any step")


def _validate_callable_arity(name: str, func: Any, expected: set[int]) -> None:
    signature = inspect.signature(func)
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if len(positional) not in expected:
        expected_text = " or ".join(str(value) for value in sorted(expected))
        raise WorkflowValidationError(f"{name!r} must accept {expected_text} positional arguments")


def _validate_required_artifacts(
    definition: WorkflowDefinition,
    inventory: dict[str, ArtifactInventoryRecord],
) -> None:
    step_positions = {step.name: index for index, step in enumerate(definition.steps)}
    for step in definition.steps:
        for artifact in step.requires:
            record = inventory[artifact.name or ""]
            if record.workflow_level:
                continue
            if not any(step_positions[producer] < step_positions[step.name] for producer in record.producer_steps):
                raise WorkflowValidationError(
                    f"step {step.name!r} requires artifact {record.name!r} before it is produced"
                )


def _validate_artifact_graph(
    definition: WorkflowDefinition,
    inventory: dict[str, ArtifactInventoryRecord],
) -> None:
    step_positions = {step.name: index for index, step in enumerate(definition.steps)}
    graph: dict[str, set[str]] = {step.name: set() for step in definition.steps}
    for step in definition.steps:
        for artifact in step.requires:
            record = inventory[artifact.name or ""]
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


def _validate_topology(definition: WorkflowDefinition) -> None:
    step_identities = {id(step): step for step in definition.steps}
    valid_destinations = {SUCCESS, PAUSE, FAIL}
    for source, routes in definition.transitions.items():
        if source != GLOBAL and id(source) not in step_identities:
            raise WorkflowValidationError("transition source step is not declared on the workflow class")
        for destination in routes.values():
            if isinstance(destination, Step):
                if id(destination) not in step_identities:
                    raise WorkflowValidationError(
                        f"transition destination step {destination.name!r} is not declared on the workflow class"
                    )
                continue
            if destination not in valid_destinations:
                raise WorkflowValidationError(f"invalid transition destination {destination!r}")
