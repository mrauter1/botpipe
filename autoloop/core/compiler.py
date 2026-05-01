"""Workflow compilation."""

from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel

from .artifacts import CompiledArtifact
from .context import Context
from .effects import Effect
from .extensions import WorkflowExtension
from .errors import RoutingError, WorkflowCompilationError
from .primitives import Event, FAIL, FINISH, GLOBAL, Outcome
from .prompts import PromptSpec
from .providers.retries import ProviderRetryPolicy
from .route_required_writes import route_required_write_payload
from .routes import Route, normalize_route_spec
from .sessions import Continuity, DEFAULT_SESSION_NAME
from .step_state import build_step_item_state_model, build_step_state_model
from .steps import PromptStep, ProduceVerifyStep, Session, Step, PythonStep, ChildWorkflowStep
from .validation import (
    ArtifactInventoryRecord,
    WorkflowDefinition,
    PayloadValidator,
    compile_expected_output_contract,
    collect_artifact_inventory,
    get_workflow_definition,
    has_start_hook,
    normalize_step_route_metadata,
    outcome_middleware_name,
    public_artifact_inventory,
    resolve_optional_read_reference,
    resolve_artifact_reference,
    step_available_route_tags,
)
from .worklists import Worklist

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
    scope_name: str | None
    reads: tuple[str, ...]
    requires: tuple[str, ...]
    writes: tuple[str, ...]
    log_artifacts: tuple[str, ...]
    available_routes: tuple[str, ...]
    expected_output_schema: dict[str, Any] | None
    retry_policy: ProviderRetryPolicy
    prompt: PromptSpec | None
    producer_prompt: PromptSpec | None
    verifier_prompt: PromptSpec | None
    producer_reads: tuple[str, ...]
    producer_requires: tuple[str, ...]
    producer_writes: tuple[str, ...]
    verifier_reads: tuple[str, ...]
    verifier_requires: tuple[str, ...]
    verifier_writes: tuple[str, ...]
    verifier_session_name: str | None
    expected_output_validator: PayloadValidator | None
    outcome_handler: OutcomeHandler | None
    python_handler: SystemHandler | None
    before_hook: Callable[..., Any] | None
    after_hook: Callable[..., Any] | None
    on_route_hook: Callable[..., Any] | None
    before_producer_hook: Callable[..., Any] | None
    after_producer_hook: Callable[..., Any] | None
    before_verifier_hook: Callable[..., Any] | None
    after_verifier_hook: Callable[..., Any] | None
    step_state_model: type[BaseModel]
    step_state_fields: tuple[str, ...]
    step_item_state_model: type[BaseModel] | None
    step_item_state_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompiledRoute:
    """Normalized immutable route metadata."""

    source_step: str
    tag: str
    target: str
    effects: tuple[Effect, ...]
    summary: str | None = None
    required_writes: tuple[str, ...] = ()
    handoff: str | None = None
    on_taken: object | None = None
    provider_visible: bool = True
    _required_writes_explicit: bool = False


@dataclass(frozen=True, slots=True)
class CompiledWorkflow:
    """Immutable compiled workflow."""

    workflow_cls: type[Any]
    workflow_name: str
    state_cls: type[BaseModel]
    input_model: type[BaseModel] | None
    output_model: type[BaseModel] | None
    output_builder: Callable[[BaseModel, Context], Any] | None
    parameters_cls: type[BaseModel] | None
    entry_step_name: str
    sessions: dict[str, Session]
    default_session_name: str
    default_session_open: bool
    worklists: dict[str, Worklist[Any]]
    steps: dict[str, CompiledStep]
    routes: dict[str, dict[str, CompiledRoute]]
    global_routes: dict[str, CompiledRoute]
    artifacts: dict[str, CompiledArtifact]
    artifacts_by_qualified_name: dict[str, CompiledArtifact]
    extensions: tuple[WorkflowExtension, ...]
    has_start_hook: bool
    source_hash: str | None
    topology_hash: str
    middleware: MiddlewareHandler | None = None

    def artifact_items(self, *, authoritative: bool = False) -> tuple[tuple[str, CompiledArtifact], ...]:
        """Return compiled artifact entries.

        ``authoritative=False`` returns the public short-name artifact view.
        ``authoritative=True`` returns the full canonical qualified inventory.
        """

        source = self.artifacts_by_qualified_name if authoritative else self.artifacts
        return tuple(source.items())

    def route(self, step_name: str, tag: str) -> CompiledRoute:
        compiled_route = self.routes.get(step_name, {}).get(tag)
        if compiled_route is None:
            compiled_route = self.global_routes.get(tag)
        if compiled_route is None:
            raise RoutingError(f"no route for step {step_name!r} and tag {tag!r}")
        return compiled_route

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
        input_model=_compile_optional_model(workflow_cls, "Input"),
        output_model=_compile_optional_model(workflow_cls, "Output"),
        output_builder=_compile_output_builder(workflow_cls),
        parameters_cls=definition.parameters_cls,
        entry_step_name=definition.entry.name,
        sessions=_compile_sessions(definition),
        default_session_name=definition.default_session_name,
        default_session_open=definition.sessions_by_name.get(definition.default_session_name).open
        if definition.default_session_name in definition.sessions_by_name
        else False,
        worklists=dict(definition.worklists_by_name),
        steps=_compile_steps(definition, inventory),
        routes=_compile_routes(definition),
        global_routes=_compile_global_routes(definition),
        artifacts=_compile_public_artifacts(inventory),
        artifacts_by_qualified_name=_compile_artifacts_by_qualified_name(inventory),
        extensions=definition.extensions,
        has_start_hook=has_start_hook(definition),
        source_hash=_workflow_source_hash(workflow_cls),
        topology_hash="",
        middleware=_compile_middleware(definition),
    )
    compiled = _with_topology_hash(compiled)
    workflow_cls.__compiled_workflow__ = compiled
    return compiled


def _compile_steps(
    definition: WorkflowDefinition,
    inventory: dict[str, ArtifactInventoryRecord],
) -> dict[str, CompiledStep]:
    compiled_steps: dict[str, CompiledStep] = {}
    for step in definition.steps:
        available_routes = step_available_route_tags(definition, step)
        expected_output_schema, expected_output_validator = _compile_expected_output_contract(step)
        reads = tuple(
            _compile_read_reference(artifact_reference, inventory)
            for artifact_reference in step.reads
        )
        requires = tuple(
            resolve_artifact_reference(artifact_reference, inventory).qualified_name
            for artifact_reference in step.requires
        )
        verifier_requires = tuple(
            resolve_artifact_reference(
                artifact_reference,
                inventory,
                step_name=step.name,
                prefer_step_local=True,
            ).qualified_name
            for artifact_reference in getattr(step, "verifier_requires", ())
        )
        writes = tuple(
            resolve_artifact_reference(artifact, inventory).qualified_name
            for artifact in step.writes.values()
        )
        producer_writes = tuple(
            resolve_artifact_reference(step.writes[name], inventory).qualified_name
            for name in getattr(step, "producer_writes", tuple(step.writes.keys()))
        )
        verifier_writes = tuple(
            resolve_artifact_reference(step.writes[name], inventory).qualified_name
            for name in getattr(step, "verifier_writes", ())
        )
        step_log_artifacts = tuple(
            resolve_artifact_reference(artifact, inventory).qualified_name
            for artifact in step.log_artifacts
        )
        workflow_log_artifact_names = tuple(
            resolve_artifact_reference(artifact, inventory).qualified_name
            for artifact in definition.workflow_log_artifacts
        )
        log_names = tuple(dict.fromkeys((*workflow_log_artifact_names, *step_log_artifacts)))
        step_kind = step.kind
        before_hook = getattr(step, "before", None)
        after_hook = getattr(step, "after", None)
        on_route_hook = getattr(step, "on_route", None)
        before_producer_hook = getattr(step, "before_do", None)
        after_producer_hook = getattr(step, "after_do", None)
        before_verifier_hook = getattr(step, "before_review", None)
        after_verifier_hook = getattr(step, "after_review", None)
        step_kind = _compiled_step_kind(step)
        step_state_model = getattr(step, "state_model", None)
        if step_state_model is None:
            step_state_model = build_step_state_model(
                None,
                step_name=step.name,
                step_kind=step_kind,
                module_name=definition.workflow_cls.__module__,
            )
        step_state_fields = tuple(dict.fromkeys(step_state_model.model_fields.keys()))
        step_item_state_model = None
        step_item_state_fields: tuple[str, ...] = ()
        if step.scope is not None:
            step_item_state_model = getattr(step, "step_item_state_model", None)
            if step_item_state_model is None:
                step_item_state_model = build_step_item_state_model(
                    getattr(step, "item_state", None),
                    step_name=step.name,
                    step_kind=step_kind,
                    module_name=definition.workflow_cls.__module__,
                )
            step_item_state_fields = tuple(dict.fromkeys(step_item_state_model.model_fields.keys()))
        compiled_session_name = step.session.name if step.session is not None else definition.default_session_name
        producer_reads = tuple(getattr(step, "producer_reads", reads))
        producer_requires = tuple(getattr(step, "producer_requires", requires))
        verifier_requires = tuple(getattr(step, "verifier_requires", verifier_requires))
        verifier_reads = tuple(
            getattr(step, "verifier_reads", tuple(dict.fromkeys((*reads, *producer_writes, *verifier_requires))))
        )
        if isinstance(step, ProduceVerifyStep):
            compiled_steps[step.name] = CompiledStep(
                name=step.name,
                kind=step_kind,
                step=step,
                session_name=compiled_session_name,
                scope_name=_compile_scope_name(step.scope),
                reads=reads,
                requires=requires,
                writes=writes,
                log_artifacts=log_names,
                available_routes=available_routes,
                expected_output_schema=expected_output_schema,
                retry_policy=step.retry_policy,
                prompt=None,
                producer_prompt=step.producer,
                verifier_prompt=step.verifier,
                producer_reads=producer_reads,
                producer_requires=producer_requires,
                producer_writes=producer_writes,
                verifier_reads=verifier_reads,
                verifier_requires=verifier_requires,
                verifier_writes=verifier_writes or writes,
                verifier_session_name=(
                    step.review_session.name
                    if getattr(step, "review_session", None) is not None
                    else None
                ),
                expected_output_validator=expected_output_validator,
                outcome_handler=_compile_outcome_handler(definition.workflow_cls, step.name),
                python_handler=None,
                before_hook=before_hook,
                after_hook=after_hook,
                on_route_hook=on_route_hook,
                before_producer_hook=before_producer_hook,
                after_producer_hook=after_producer_hook,
                before_verifier_hook=before_verifier_hook,
                after_verifier_hook=after_verifier_hook,
                step_state_model=step_state_model,
                step_state_fields=step_state_fields,
                step_item_state_model=step_item_state_model,
                step_item_state_fields=step_item_state_fields,
            )
        elif isinstance(step, PromptStep):
            compiled_steps[step.name] = CompiledStep(
                name=step.name,
                kind=step_kind,
                step=step,
                session_name=compiled_session_name,
                scope_name=_compile_scope_name(step.scope),
                reads=reads,
                requires=requires,
                writes=writes,
                log_artifacts=log_names,
                available_routes=available_routes,
                expected_output_schema=expected_output_schema,
                retry_policy=step.retry_policy,
                prompt=step.producer,
                producer_prompt=step.producer,
                verifier_prompt=None,
                producer_reads=producer_reads,
                producer_requires=producer_requires,
                producer_writes=writes,
                verifier_reads=(),
                verifier_requires=(),
                verifier_writes=(),
                verifier_session_name=None,
                expected_output_validator=expected_output_validator,
                outcome_handler=_compile_outcome_handler(definition.workflow_cls, step.name),
                python_handler=None,
                before_hook=before_hook,
                after_hook=after_hook,
                on_route_hook=on_route_hook,
                before_producer_hook=None,
                after_producer_hook=None,
                before_verifier_hook=None,
                after_verifier_hook=None,
                step_state_model=step_state_model,
                step_state_fields=step_state_fields,
                step_item_state_model=step_item_state_model,
                step_item_state_fields=step_item_state_fields,
            )
        elif isinstance(step, PythonStep):
            compiled_steps[step.name] = CompiledStep(
                name=step.name,
                kind=step_kind,
                step=step,
                session_name=step.session.name if step.session is not None else None,
                scope_name=None,
                reads=reads,
                requires=requires,
                writes=writes,
                log_artifacts=log_names,
                available_routes=available_routes,
                expected_output_schema=None,
                retry_policy=ProviderRetryPolicy(max_attempts=1),
                prompt=None,
                producer_prompt=None,
                verifier_prompt=None,
                producer_reads=producer_reads,
                producer_requires=producer_requires,
                producer_writes=writes,
                verifier_reads=(),
                verifier_requires=(),
                verifier_writes=(),
                verifier_session_name=None,
                expected_output_validator=None,
                outcome_handler=None,
                python_handler=_compile_system_handler(step, workflow_cls=definition.workflow_cls),
                before_hook=before_hook,
                after_hook=after_hook,
                on_route_hook=on_route_hook,
                before_producer_hook=None,
                after_producer_hook=None,
                before_verifier_hook=None,
                after_verifier_hook=None,
                step_state_model=step_state_model,
                step_state_fields=step_state_fields,
                step_item_state_model=step_item_state_model,
                step_item_state_fields=step_item_state_fields,
            )
        elif isinstance(step, ChildWorkflowStep):
            compiled_steps[step.name] = CompiledStep(
                name=step.name,
                kind=step_kind,
                step=step,
                session_name=step.session.name if step.session is not None else None,
                scope_name=_compile_scope_name(step.scope),
                reads=reads,
                requires=requires,
                writes=writes,
                log_artifacts=log_names,
                available_routes=available_routes,
                expected_output_schema=None,
                retry_policy=ProviderRetryPolicy(max_attempts=1),
                prompt=None,
                producer_prompt=None,
                verifier_prompt=None,
                producer_reads=producer_reads,
                producer_requires=producer_requires,
                producer_writes=writes,
                verifier_reads=(),
                verifier_requires=(),
                verifier_writes=(),
                verifier_session_name=None,
                expected_output_validator=None,
                outcome_handler=None,
                python_handler=None,
                before_hook=before_hook,
                after_hook=after_hook,
                on_route_hook=on_route_hook,
                before_producer_hook=None,
                after_producer_hook=None,
                before_verifier_hook=None,
                after_verifier_hook=None,
                step_state_model=step_state_model,
                step_state_fields=step_state_fields,
                step_item_state_model=step_item_state_model,
                step_item_state_fields=step_item_state_fields,
            )
        else:
            raise WorkflowCompilationError(f"unsupported step type {type(step)!r}")
    return compiled_steps


def _compile_outcome_handler(workflow_cls: type[Any], step_name: str) -> OutcomeHandler | None:
    raw_handler = getattr(workflow_cls, f"on_{step_name}", None)
    if raw_handler is None:
        return None
    if _callable_arity(raw_handler) != 3:
        raise WorkflowCompilationError(
            f"handler for step {step_name!r} must accept exactly 3 positional arguments"
        )
    return raw_handler


def _compile_optional_model(workflow_cls: type[Any], attribute: str) -> type[BaseModel] | None:
    raw = getattr(workflow_cls, attribute, None)
    if raw is None:
        return None
    if not isinstance(raw, type) or not issubclass(raw, BaseModel):
        raise WorkflowCompilationError(
            f"{workflow_cls.__name__}.{attribute} must inherit from pydantic.BaseModel"
        )
    return raw


def _compile_output_builder(workflow_cls: type[Any]) -> Callable[[BaseModel, Context], Any] | None:
    raw_builder = getattr(workflow_cls, "build_output", None)
    if raw_builder is None:
        return None
    if _callable_arity(raw_builder) != 2:
        raise WorkflowCompilationError("build_output must accept exactly 2 positional arguments")
    return raw_builder


def _compile_sessions(definition: WorkflowDefinition) -> dict[str, Session]:
    compiled: dict[str, Session] = {}
    for name, session in definition.sessions_by_name.items():
        compiled[name] = _compiled_session_copy(name, session)
    if definition.default_session_name not in compiled:
        compiled[definition.default_session_name] = _compiled_session_copy(
            definition.default_session_name,
            definition.sessions_by_name.get(definition.default_session_name),
        )
    if DEFAULT_SESSION_NAME not in compiled:
        compiled[DEFAULT_SESSION_NAME] = _compiled_session_copy(DEFAULT_SESSION_NAME, None)
    return compiled


def _compiled_session_copy(name: str, session: Session | None) -> Session:
    continuity = session.continuity if isinstance(session, Session) else Continuity.run()
    compiled = Session(continuity=continuity, open=session.open if isinstance(session, Session) else False)
    compiled.bind_name(name)
    return compiled


def _compile_system_handler(step: PythonStep, *, workflow_cls: type[Any]) -> SystemHandler:
    raw_handler = step.handler
    step_name = step.name
    if raw_handler is None:
        raw_handler = getattr(workflow_cls, f"on_{step_name}", None)
    if raw_handler is None:
        raise WorkflowCompilationError(f"system step {step_name!r} is missing a handler")

    arity = _callable_arity(raw_handler)
    if arity not in {1, 2}:
        raise WorkflowCompilationError(
            f"handler for system step {step_name!r} must accept exactly 1 or 2 positional arguments"
        )

    def handler(state: BaseModel, ctx: Context) -> tuple[BaseModel, Event]:
        if arity == 1:
            result = raw_handler(ctx)
        else:
            result = raw_handler(state, ctx)
        return _normalize_system_handler_result(step_name, state, result)

    return handler


def _normalize_system_handler_result(
    step_name: str,
    state: BaseModel,
    result: Any,
) -> tuple[BaseModel, Event]:
    if result is None:
        return state, Event("done")
    if isinstance(result, BaseModel):
        return result, Event("done")
    if isinstance(result, str):
        return state, Event(result)
    if isinstance(result, Event):
        return state, result
    if isinstance(result, tuple) and len(result) == 2:
        next_state, event_like = result
        if not isinstance(next_state, BaseModel):
            raise WorkflowCompilationError(
                f"system step {step_name!r} must return a BaseModel state when returning a tuple"
            )
        if isinstance(event_like, str):
            return next_state, Event(event_like)
        if isinstance(event_like, Event):
            return next_state, event_like
    raise WorkflowCompilationError(
        f"system step {step_name!r} returned unsupported value {result!r}"
    )


def _compile_middleware(definition: WorkflowDefinition) -> MiddlewareHandler | None:
    handler_name = outcome_middleware_name(definition)
    if handler_name is None:
        return None
    raw = getattr(definition.workflow_cls, handler_name, None)
    if raw is None:
        return None
    if _callable_arity(raw) != 2:
        raise WorkflowCompilationError("middleware must accept exactly two positional arguments")
    return raw


def _compile_routes(definition: WorkflowDefinition) -> dict[str, dict[str, CompiledRoute]]:
    inventory = collect_artifact_inventory(definition)
    route_metadata = {
        step.name: normalize_step_route_metadata(definition, step, inventory)
        for step in definition.steps
    }
    routes: dict[str, dict[str, CompiledRoute]] = {}
    for source, source_routes in definition.transitions.items():
        if source == GLOBAL:
            continue
        if not isinstance(source, Step):
            continue
        routes[source.name] = {
            tag: _compile_route(
                source.name,
                tag,
                destination,
                summary=route_metadata[source.name].get(tag).summary,
                required_writes=route_metadata[source.name].get(tag).required_writes,
                handoff=route_metadata[source.name].get(tag).handoff,
            )
            for tag, destination in source_routes.items()
        }
    return routes


def _compile_global_routes(definition: WorkflowDefinition) -> dict[str, CompiledRoute]:
    source_routes = definition.transitions.get(GLOBAL, {})
    return {
        tag: _compile_route(GLOBAL, tag, destination)
        for tag, destination in source_routes.items()
    }


def _compile_route(
    source_step: str,
    tag: str,
    destination: Step | str | Route,
    *,
    summary: str | None = None,
    required_writes: tuple[str, ...] | None = None,
    handoff: str | None = None,
) -> CompiledRoute:
    route = normalize_route_spec(destination)
    target = route.target
    if isinstance(target, Step):
        compiled_target = target.name
    elif isinstance(target, str):
        compiled_target = target
    else:  # pragma: no cover - validation guards this before compilation
        raise WorkflowCompilationError(f"route {tag!r} from {source_step!r} is missing a target")
    required_writes_explicit = required_writes is not None or route.required_writes is not None
    compiled_required_writes = required_writes if required_writes is not None else tuple(route.required_writes or ())
    return CompiledRoute(
        source_step=source_step,
        tag=tag,
        target=compiled_target,
        effects=tuple(route.effects),
        summary=route.summary or summary,
        required_writes=compiled_required_writes,
        handoff=route.handoff or handoff,
        on_taken=route.on_taken,
        provider_visible=route.provider_visible,
        _required_writes_explicit=required_writes_explicit,
    )


def _compiled_step_kind(step: Step) -> str:
    if isinstance(step, ProduceVerifyStep):
        return "produce_verify"
    if isinstance(step, PromptStep):
        return "step"
    if isinstance(step, ChildWorkflowStep):
        return "workflow"
    if isinstance(step, PythonStep):
        declaration = getattr(step, "simple_declaration", None)
        if getattr(declaration, "kind", None) == "operation":
            return "operation"
        return "python"
    return step.kind


def _compile_artifact(record: ArtifactInventoryRecord, *, name: str) -> CompiledArtifact:
    return CompiledArtifact(
        name=name,
        template=record.artifact.template,
        kind=record.artifact.kind,
        schema=record.artifact.schema,
        required=record.artifact.required,
        owner_step=record.artifact.owner_step,
        qualified_name=record.artifact.qualified_name,
        workflow_level=record.workflow_level,
        producer_steps=record.producer_steps,
    )


def _compile_public_artifacts(inventory: dict[str, ArtifactInventoryRecord]) -> dict[str, CompiledArtifact]:
    return {
        name: _compile_artifact(record, name=name)
        for name, record in public_artifact_inventory(inventory).items()
    }


def _compile_artifacts_by_qualified_name(
    inventory: dict[str, ArtifactInventoryRecord],
) -> dict[str, CompiledArtifact]:
    return {
        name: _compile_artifact(record, name=name)
        for name, record in inventory.items()
    }


def _compile_expected_output_contract(step: Step) -> tuple[dict[str, Any] | None, PayloadValidator | None]:
    if step.expected_output_schema is None:
        return None, None
    return compile_expected_output_contract(step.expected_output_schema)


def _compile_read_reference(
    reference: object,
    inventory: dict[str, ArtifactInventoryRecord],
) -> str:
    resolved = resolve_optional_read_reference(reference, inventory)
    if resolved is not None:
        return resolved
    if isinstance(reference, Path):
        return str(reference)
    if isinstance(reference, str):
        return reference
    raise WorkflowCompilationError(f"unsupported read reference {reference!r}")


def _compile_scope_name(scope: object | None) -> str | None:
    if scope is None:
        return None
    if isinstance(scope, str):
        return scope
    name = getattr(scope, "name", None)
    if isinstance(name, str) and name:
        return name
    raise WorkflowCompilationError("scoped steps require a named worklist")


def _callable_arity(func: Callable[..., Any]) -> int:
    signature = inspect.signature(func)
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    return len(positional)


def _workflow_source_hash(workflow_cls: type[Any]) -> str | None:
    module = inspect.getmodule(workflow_cls)
    module_file = getattr(module, "__file__", None)
    if not isinstance(module_file, str) or not module_file:
        return None
    path = Path(module_file)
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _topology_hash_payload(compiled: CompiledWorkflow) -> dict[str, Any]:
    return {
        "workflow_name": compiled.workflow_name,
        "entry_step_name": compiled.entry_step_name,
        "global_session": compiled.default_session_name,
        "steps": [
            {
                "name": step.name,
                "kind": step.kind,
                "scope_name": step.scope_name,
                "reads": list(step.reads),
                "requires": list(step.requires),
                "writes": list(step.writes),
                "producer_reads": list(step.producer_reads),
                "producer_requires": list(step.producer_requires),
                "producer_writes": list(step.producer_writes),
                "verifier_reads": list(step.verifier_reads),
                "verifier_requires": list(step.verifier_requires),
                "verifier_writes": list(step.verifier_writes),
                "available_routes": list(step.available_routes),
                "session_name": step.session_name,
                "verifier_session_name": step.verifier_session_name,
                "state_fields": list(step.step_state_fields),
                "state_model": step.step_state_model.__name__,
                "item_state_fields": list(step.step_item_state_fields),
                "item_state_model": step.step_item_state_model.__name__ if step.step_item_state_model is not None else None,
                "before_hook": _callable_name(step.before_hook),
                "after_hook": _callable_name(step.after_hook),
                "on_route_hook": _callable_name(step.on_route_hook),
                "before_producer_hook": _callable_name(step.before_producer_hook),
                "after_producer_hook": _callable_name(step.after_producer_hook),
                "before_verifier_hook": _callable_name(step.before_verifier_hook),
                "after_verifier_hook": _callable_name(step.after_verifier_hook),
                "prompt_refs": [
                    _topology_json_value(reference)
                    for reference in getattr(step.step, "simple_prompt_references", ())
                ],
            }
            for step in compiled.steps.values()
        ],
        "worklists": {
            name: {
                "item_state_model": worklist.item_state_model.__name__ if worklist.item_state_model is not None else None,
                "item_state_fields": list(worklist.item_state_model.model_fields.keys()) if worklist.item_state_model is not None else [],
            }
            for name, worklist in compiled.worklists.items()
        },
        "routes": {
            step_name: {
                tag: {
                    "target": route.target,
                    "summary": route.summary,
                    **route_required_write_payload(
                        compiled,
                        step_name=step_name,
                        route_tag=tag,
                        route=route,
                    ),
                    "handoff": route.handoff,
                    "on_taken": _callable_name(route.on_taken),
                    "provider_visible": route.provider_visible,
                }
                for tag, route in routes.items()
            }
            for step_name, routes in compiled.routes.items()
        },
        "global_routes": {
            tag: {
                "target": route.target,
                "summary": route.summary,
                **route_required_write_payload(
                    compiled,
                    step_name=None,
                    route_tag=tag,
                    route=route,
                ),
                "handoff": route.handoff,
                "on_taken": _callable_name(route.on_taken),
                "provider_visible": route.provider_visible,
            }
            for tag, route in compiled.global_routes.items()
        },
        "workflow_state_fields": sorted(getattr(compiled.state_cls, "model_fields", {}).keys()),
        "parameter_fields": sorted(getattr(compiled.parameters_cls, "model_fields", {}).keys())
        if compiled.parameters_cls is not None
        else [],
    }


def _with_topology_hash(compiled: CompiledWorkflow) -> CompiledWorkflow:
    payload = _topology_hash_payload(compiled)
    topology_hash = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=_topology_json_value,
        ).encode("utf-8")
    ).hexdigest()
    return CompiledWorkflow(
        workflow_cls=compiled.workflow_cls,
        workflow_name=compiled.workflow_name,
        state_cls=compiled.state_cls,
        input_model=compiled.input_model,
        output_model=compiled.output_model,
        output_builder=compiled.output_builder,
        parameters_cls=compiled.parameters_cls,
        entry_step_name=compiled.entry_step_name,
        sessions=compiled.sessions,
        default_session_name=compiled.default_session_name,
        default_session_open=compiled.default_session_open,
        worklists=compiled.worklists,
        steps=compiled.steps,
        routes=compiled.routes,
        global_routes=compiled.global_routes,
        artifacts=compiled.artifacts,
        artifacts_by_qualified_name=compiled.artifacts_by_qualified_name,
        extensions=compiled.extensions,
        has_start_hook=compiled.has_start_hook,
        source_hash=compiled.source_hash,
        topology_hash=topology_hash,
        middleware=compiled.middleware,
    )


def _callable_name(value: object | None) -> str | None:
    if value is None:
        return None
    return getattr(value, "__name__", type(value).__name__)


def _topology_json_value(value: object) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Path):
        return str(value)
    qualified_name = getattr(value, "qualified_name", None)
    if isinstance(qualified_name, str) and qualified_name:
        return qualified_name
    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name
    return repr(value)
