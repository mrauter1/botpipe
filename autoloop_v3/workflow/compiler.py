"""Workflow compilation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel

from .artifacts import CompiledArtifact
from .context import Context
from .errors import RoutingError, WorkflowCompilationError
from .primitives import Event, FAIL, GLOBAL, Outcome, PAUSE, SUCCESS
from .prompts import PromptSpec
from .steps import LLMStep, PairStep, SessionLifecycle, Step, SystemStep
from .validation import (
    ArtifactInventoryRecord,
    WorkflowDefinition,
    collect_artifact_inventory,
    get_workflow_definition,
    has_start_hook,
    middleware_handler_name,
)

OutcomeHandler = Callable[[BaseModel, Outcome, Any], BaseModel]
SystemHandler = Callable[[BaseModel, Context], tuple[BaseModel, Event]]
MiddlewareHandler = Callable[[BaseModel, Outcome], Event | None]


@dataclass(frozen=True, slots=True)
class CompiledStep:
    """Normalized immutable step metadata."""

    name: str
    kind: str
    step: Step
    session_name: str | None
    requires: tuple[str, ...]
    produces: tuple[str, ...]
    log_artifacts: tuple[str, ...]
    producer_prompt: PromptSpec | None
    verifier_prompt: PromptSpec | None
    outcome_handler: OutcomeHandler | None
    system_handler: SystemHandler | None


@dataclass(frozen=True, slots=True)
class CompiledWorkflow:
    """Immutable compiled workflow."""

    workflow_cls: type[Any]
    workflow_name: str
    state_cls: type[BaseModel]
    entry_step_name: str
    steps: dict[str, CompiledStep]
    routes: dict[str, dict[str, str]]
    global_routes: dict[str, str]
    artifacts: dict[str, CompiledArtifact]
    start_sessions: tuple[str, ...]
    has_start_hook: bool
    middleware: MiddlewareHandler | None = None

    def route(self, step_name: str, tag: str) -> str:
        destination = self.routes.get(step_name, {}).get(tag)
        if destination is None:
            destination = self.global_routes.get(tag)
        if destination is None:
            raise RoutingError(f"no route for step {step_name!r} and tag {tag!r}")
        return destination

    def new_state(self) -> BaseModel:
        try:
            return self.state_cls()
        except Exception as exc:
            raise WorkflowCompilationError(
                f"state model {self.state_cls.__qualname__} requires an explicit initial state"
            ) from exc


def compile_workflow(workflow_cls: type[Any]) -> CompiledWorkflow:
    """Compile a validated workflow class."""

    cached = getattr(workflow_cls, "__compiled_workflow__", None)
    if isinstance(cached, CompiledWorkflow):
        return cached
    definition = get_workflow_definition(workflow_cls)
    inventory = collect_artifact_inventory(definition)
    compiled = CompiledWorkflow(
        workflow_cls=workflow_cls,
        workflow_name=definition.workflow_name,
        state_cls=definition.state_cls,
        entry_step_name=definition.entry.name,
        steps=_compile_steps(definition, inventory),
        routes=_compile_routes(definition),
        global_routes=_compile_global_routes(definition),
        artifacts=_compile_artifacts(inventory),
        start_sessions=tuple(
            name
            for name, session in definition.sessions_by_name.items()
            if session.lifecycle == SessionLifecycle.ON_START
        ),
        has_start_hook=has_start_hook(definition),
        middleware=_compile_middleware(definition),
    )
    workflow_cls.__compiled_workflow__ = compiled
    return compiled


def _compile_steps(
    definition: WorkflowDefinition,
    inventory: dict[str, ArtifactInventoryRecord],
) -> dict[str, CompiledStep]:
    compiled_steps: dict[str, CompiledStep] = {}
    workflow_log_names = tuple(artifact.name or "" for artifact in definition.workflow_log_artifacts)
    for step in definition.steps:
        log_names = tuple(dict.fromkeys((*workflow_log_names, *(artifact.name or "" for artifact in step.log_artifacts))))
        if isinstance(step, PairStep):
            compiled_steps[step.name] = CompiledStep(
                name=step.name,
                kind=step.kind,
                step=step,
                session_name=step.session.name if step.session is not None else None,
                requires=tuple(artifact.name or "" for artifact in step.requires),
                produces=tuple(artifact.name or "" for artifact in step.produces.values()),
                log_artifacts=log_names,
                producer_prompt=step.producer,
                verifier_prompt=step.verifier,
                outcome_handler=_compile_outcome_handler(definition.workflow_cls, step.name),
                system_handler=None,
            )
        elif isinstance(step, LLMStep):
            compiled_steps[step.name] = CompiledStep(
                name=step.name,
                kind=step.kind,
                step=step,
                session_name=step.session.name if step.session is not None else None,
                requires=tuple(artifact.name or "" for artifact in step.requires),
                produces=tuple(artifact.name or "" for artifact in step.produces.values()),
                log_artifacts=log_names,
                producer_prompt=step.producer,
                verifier_prompt=None,
                outcome_handler=_compile_outcome_handler(definition.workflow_cls, step.name),
                system_handler=None,
            )
        elif isinstance(step, SystemStep):
            compiled_steps[step.name] = CompiledStep(
                name=step.name,
                kind=step.kind,
                step=step,
                session_name=step.session.name if step.session is not None else None,
                requires=tuple(artifact.name or "" for artifact in step.requires),
                produces=tuple(artifact.name or "" for artifact in step.produces.values()),
                log_artifacts=log_names,
                producer_prompt=None,
                verifier_prompt=None,
                outcome_handler=None,
                system_handler=_compile_system_handler(definition.workflow_cls, step.name),
            )
        else:
            raise WorkflowCompilationError(f"unsupported step type {type(step)!r}")
    return compiled_steps


def _compile_outcome_handler(workflow_cls: type[Any], step_name: str) -> OutcomeHandler | None:
    raw_handler = getattr(workflow_cls, f"on_{step_name}", None)
    if raw_handler is None:
        return None
    arity = _callable_arity(raw_handler)
    if arity == 3:
        return raw_handler
    if arity == 2:
        return lambda state, outcome, artifacts: raw_handler(state, outcome)
    raise WorkflowCompilationError(f"invalid outcome handler arity for step {step_name!r}")


def _compile_system_handler(workflow_cls: type[Any], step_name: str) -> SystemHandler:
    raw_handler = getattr(workflow_cls, f"on_{step_name}", None)
    if raw_handler is None:
        raise WorkflowCompilationError(f"system step {step_name!r} is missing a handler")
    arity = _callable_arity(raw_handler)
    if arity == 2:
        return raw_handler
    if arity == 1:
        return lambda state, context: raw_handler(state)
    raise WorkflowCompilationError(f"invalid system handler arity for step {step_name!r}")


def _compile_middleware(definition: WorkflowDefinition) -> MiddlewareHandler | None:
    handler_name = middleware_handler_name(definition)
    if handler_name is None:
        return None
    raw = getattr(definition.workflow_cls, handler_name, None)
    if raw is None:
        return None
    if _callable_arity(raw) != 2:
        raise WorkflowCompilationError("middleware must accept exactly two positional arguments")
    return raw


def _compile_routes(definition: WorkflowDefinition) -> dict[str, dict[str, str]]:
    routes: dict[str, dict[str, str]] = {}
    for source, source_routes in definition.transitions.items():
        if source == GLOBAL:
            continue
        if not isinstance(source, Step):
            continue
        routes[source.name] = {
            tag: destination.name if isinstance(destination, Step) else destination
            for tag, destination in source_routes.items()
        }
    return routes


def _compile_global_routes(definition: WorkflowDefinition) -> dict[str, str]:
    source_routes = definition.transitions.get(GLOBAL, {})
    return {
        tag: destination.name if isinstance(destination, Step) else destination
        for tag, destination in source_routes.items()
    }


def _compile_artifacts(inventory: dict[str, ArtifactInventoryRecord]) -> dict[str, CompiledArtifact]:
    return {
        name: CompiledArtifact(
            name=name,
            template=record.artifact.template,
            workflow_level=record.workflow_level,
            producer_steps=record.producer_steps,
        )
        for name, record in inventory.items()
    }


def _callable_arity(func: Callable[..., Any]) -> int:
    import inspect

    signature = inspect.signature(func)
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    return len(positional)
