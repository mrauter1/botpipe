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
from .discovery import WorkflowDefinition, get_workflow_definition
from .extensions import WorkflowExtension
from .errors import RoutingError, WorkflowCompilationError
from .inventory import ArtifactInventoryRecord, collect_artifact_inventory, public_artifact_inventory, resolve_artifact_reference, resolve_optional_read_reference
from .lowering import (
    compile_expected_output_contract,
    normalize_step_route_metadata,
    step_authored_route_tags,
    step_available_route_tags,
    step_runtime_control_route_tags,
)
from .primitives import FAIL, FINISH, GLOBAL
from .prompts import PromptSpec
from .providers.retries import ProviderRetryPolicy
from .route_required_writes import route_required_write_payload
from .routes import Route, normalize_route_spec
from .sessions import Continuity, DEFAULT_SESSION_NAME
from .step_state import build_step_item_state_model, build_step_state_model
from .steps import PromptStep, ProduceVerifyStep, Session, Step, PythonStep, ChildWorkflowStep
from .validation import PayloadValidator
from .worklists import Worklist

SystemHandler = Callable[[Context], Any]

_COMPILED_WORKFLOW_CACHE: dict[tuple[str, str, str], "CompiledWorkflow"] = {}


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
    authored_routes: tuple[str, ...]
    runtime_control_routes: tuple[str, ...]
    provider_visible_routes_interactive: tuple[str, ...]
    provider_visible_routes_full_auto: tuple[str, ...]
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
    python_handler: SystemHandler | None
    before_hook: Callable[..., Any] | None
    after_hook: Callable[..., Any] | None
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
    summary: str | None = None
    required_writes: tuple[str, ...] = ()
    handoff: str | None = None
    on_taken: object | None = None
    provider_visible: bool = True
    provider_visible_interactive: bool = True
    provider_visible_full_auto: bool = True
    is_runtime_control: bool = False
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
    source_hash: str | None
    topology_hash: str

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

    definition = get_workflow_definition(workflow_cls)
    source_hash = _workflow_source_hash(workflow_cls)
    cache_key = _workflow_compile_cache_key(
        workflow_cls,
        definition=definition,
        source_hash=source_hash,
    )
    cached = _COMPILED_WORKFLOW_CACHE.get(cache_key)
    if cached is not None:
        return cached
    inventory = collect_artifact_inventory(definition)
    compiled_routes = _compile_routes(definition)
    compiled_global_routes = _compile_global_routes(definition)
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
        steps=_compile_steps(definition, inventory, compiled_routes, compiled_global_routes),
        routes=compiled_routes,
        global_routes=compiled_global_routes,
        artifacts=_compile_public_artifacts(inventory),
        artifacts_by_qualified_name=_compile_artifacts_by_qualified_name(inventory),
        extensions=definition.extensions,
        source_hash=source_hash,
        topology_hash="",
    )
    compiled = _with_topology_hash(compiled)
    _COMPILED_WORKFLOW_CACHE[cache_key] = compiled
    return compiled


def _compile_steps(
    definition: WorkflowDefinition,
    inventory: dict[str, ArtifactInventoryRecord],
    compiled_routes: dict[str, dict[str, CompiledRoute]],
    compiled_global_routes: dict[str, CompiledRoute],
) -> dict[str, CompiledStep]:
    compiled_steps: dict[str, CompiledStep] = {}
    for step in definition.steps:
        available_routes = step_available_route_tags(definition, step)
        authored_routes = step_authored_route_tags(definition, step)
        runtime_control_routes = step_runtime_control_route_tags(definition, step)
        provider_visible_routes_interactive = _provider_visible_route_tags(
            step,
            available_routes,
            compiled_routes=compiled_routes,
            compiled_global_routes=compiled_global_routes,
            policy="interactive",
        )
        provider_visible_routes_full_auto = _provider_visible_route_tags(
            step,
            available_routes,
            compiled_routes=compiled_routes,
            compiled_global_routes=compiled_global_routes,
            policy="full_auto",
        )
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
        before_producer_hook = getattr(step, "before_producer", None)
        after_producer_hook = getattr(step, "after_producer", None)
        before_verifier_hook = getattr(step, "before_verifier", None)
        after_verifier_hook = getattr(step, "after_verifier", None)
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
                authored_routes=authored_routes,
                runtime_control_routes=runtime_control_routes,
                provider_visible_routes_interactive=provider_visible_routes_interactive,
                provider_visible_routes_full_auto=provider_visible_routes_full_auto,
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
                    step.verifier_session.name
                    if getattr(step, "verifier_session", None) is not None
                    else None
                ),
                expected_output_validator=expected_output_validator,
                python_handler=None,
                before_hook=before_hook,
                after_hook=after_hook,
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
                authored_routes=authored_routes,
                runtime_control_routes=runtime_control_routes,
                provider_visible_routes_interactive=provider_visible_routes_interactive,
                provider_visible_routes_full_auto=provider_visible_routes_full_auto,
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
                python_handler=None,
                before_hook=before_hook,
                after_hook=after_hook,
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
                authored_routes=authored_routes,
                runtime_control_routes=runtime_control_routes,
                provider_visible_routes_interactive=provider_visible_routes_interactive,
                provider_visible_routes_full_auto=provider_visible_routes_full_auto,
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
                python_handler=_compile_system_handler(step),
                before_hook=before_hook,
                after_hook=after_hook,
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
                authored_routes=authored_routes,
                runtime_control_routes=runtime_control_routes,
                provider_visible_routes_interactive=provider_visible_routes_interactive,
                provider_visible_routes_full_auto=provider_visible_routes_full_auto,
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
                python_handler=None,
                before_hook=before_hook,
                after_hook=after_hook,
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


def _provider_visible_route_tags(
    step: Step,
    available_routes: tuple[str, ...],
    *,
    compiled_routes: dict[str, dict[str, CompiledRoute]],
    compiled_global_routes: dict[str, CompiledRoute],
    policy: str,
) -> tuple[str, ...]:
    visible: list[str] = []
    for route_tag in available_routes:
        route = compiled_routes.get(step.name, {}).get(route_tag) or compiled_global_routes.get(route_tag)
        if route is None:
            continue
        if policy == "interactive" and _compiled_step_route_visible(step, route_tag=route_tag, route=route, policy=policy):
            visible.append(route_tag)
        if policy == "full_auto" and _compiled_step_route_visible(step, route_tag=route_tag, route=route, policy=policy):
            visible.append(route_tag)
    return tuple(visible)


def _compiled_step_route_visible(
    step: Step,
    *,
    route_tag: str,
    route: CompiledRoute,
    policy: str,
) -> bool:
    if not route.provider_visible:
        return False
    if not isinstance(step, (PromptStep, ProduceVerifyStep)):
        return False
    if route_tag != "question":
        return True
    question_mode = getattr(getattr(step, "control_routes", None), "question", "never")
    if question_mode == "always":
        return True
    return policy == "interactive"


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


def _compile_system_handler(step: PythonStep) -> SystemHandler:
    raw_handler = step.handler
    step_name = step.name
    if raw_handler is None:
        raise WorkflowCompilationError(f"python_step {step_name!r} is missing a handler")

    arity = _callable_arity(raw_handler)
    if arity != 1:
        raise WorkflowCompilationError(
            f"handler for python_step {step_name!r} must accept exactly 1 positional argument"
        )

    def handler(ctx: Context) -> Any:
        return raw_handler(ctx)

    return handler


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
        runtime_control_routes = set(definition.runtime_control_routes_by_step.get(source.name, ()))
        routes[source.name] = {
            tag: _compile_route(
                source,
                source.name,
                tag,
                destination,
                summary=route_metadata[source.name].get(tag).summary,
                required_writes=route_metadata[source.name].get(tag).required_writes,
                handoff=route_metadata[source.name].get(tag).handoff,
                is_runtime_control=tag in runtime_control_routes,
            )
            for tag, destination in source_routes.items()
        }
    return routes


def _compile_global_routes(definition: WorkflowDefinition) -> dict[str, CompiledRoute]:
    source_routes = definition.transitions.get(GLOBAL, {})
    return {
        tag: _compile_route(None, GLOBAL, tag, destination)
        for tag, destination in source_routes.items()
    }


def _compile_route(
    step: Step | None,
    source_step: str,
    tag: str,
    destination: Step | str | Route,
    *,
    summary: str | None = None,
    required_writes: tuple[str, ...] | None = None,
    handoff: str | None = None,
    is_runtime_control: bool = False,
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
    provider_visible_interactive, provider_visible_full_auto = _compiled_provider_visibility(
        step,
        tag=tag,
        provider_visible=route.provider_visible,
        is_runtime_control=is_runtime_control,
    )
    return CompiledRoute(
        source_step=source_step,
        tag=tag,
        target=compiled_target,
        summary=route.summary or summary,
        required_writes=compiled_required_writes,
        handoff=route.handoff or handoff,
        on_taken=route.on_taken,
        provider_visible=route.provider_visible,
        provider_visible_interactive=provider_visible_interactive,
        provider_visible_full_auto=provider_visible_full_auto,
        is_runtime_control=is_runtime_control,
        _required_writes_explicit=required_writes_explicit,
    )


def _compiled_provider_visibility(
    step: Step | None,
    *,
    tag: str,
    provider_visible: bool,
    is_runtime_control: bool,
) -> tuple[bool, bool]:
    if not provider_visible:
        return False, False
    if step is None:
        if tag == "question":
            return True, False
        return True, True
    if not isinstance(step, (PromptStep, ProduceVerifyStep)):
        return False, False
    question_mode = getattr(getattr(step, "control_routes", None), "question", "never")
    if tag != "question":
        return True, True
    if question_mode == "always":
        return True, True
    if is_runtime_control:
        return True, False
    return True, False


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


def _workflow_compile_cache_key(
    workflow_cls: type[Any],
    *,
    definition: WorkflowDefinition,
    source_hash: str | None,
) -> tuple[str, str, str]:
    payload = {
        "module": workflow_cls.__module__,
        "qualname": workflow_cls.__qualname__,
        "source_hash": source_hash,
        "workflow_name": definition.workflow_name,
        "entry_step_name": definition.entry.name,
        "default_session_name": definition.default_session_name,
        "state_fields": sorted(getattr(definition.state_cls, "model_fields", {}).keys()),
        "parameter_fields": sorted(getattr(definition.parameters_cls, "model_fields", {}).keys())
        if definition.parameters_cls is not None
        else [],
        "steps": [
            {
                "name": step.name,
                "type": type(step).__name__,
                "kind": getattr(step, "kind", None),
                "scope_name": _cache_scope_name(getattr(step, "scope", None)),
                "session_name": _cache_session_name(getattr(step, "session", None)),
                "verifier_session_name": _cache_session_name(getattr(step, "verifier_session", None)),
                "before_hook": _callable_name(getattr(step, "before", None)),
                "after_hook": _callable_name(getattr(step, "after", None)),
                "before_producer_hook": _callable_name(getattr(step, "before_producer", None)),
                "after_producer_hook": _callable_name(getattr(step, "after_producer", None)),
                "before_verifier_hook": _callable_name(getattr(step, "before_verifier", None)),
                "after_verifier_hook": _callable_name(getattr(step, "after_verifier", None)),
                "control_routes": {
                    "question": getattr(getattr(step, "control_routes", None), "question", None),
                },
            }
            for step in definition.steps
        ],
        "transitions": _workflow_definition_transition_payload(definition),
        "worklists": {
            name: {
                "item_state_model": worklist.runtime_item_state_model.__name__,
                "item_state_fields": sorted(worklist.runtime_item_state_model.model_fields.keys()),
            }
            for name, worklist in definition.worklists_by_name.items()
        },
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=_topology_json_value,
        ).encode("utf-8")
    ).hexdigest()
    return (
        workflow_cls.__module__,
        workflow_cls.__qualname__,
        fingerprint,
    )


def _workflow_definition_transition_payload(definition: WorkflowDefinition) -> dict[str, dict[str, dict[str, Any]]]:
    payload: dict[str, dict[str, dict[str, Any]]] = {}
    for source, routes in definition.transitions.items():
        source_name = source if isinstance(source, str) else source.name
        payload[source_name] = {}
        for tag, destination in routes.items():
            route = normalize_route_spec(destination)
            target = route.target
            if hasattr(target, "name"):
                target = getattr(target, "name")
            payload[source_name][tag] = {
                "target": target,
                "summary": route.summary,
                "required_writes": list(route.required_writes or ()),
                "handoff": route.handoff,
                "on_taken": _callable_name(route.on_taken),
                "provider_visible": route.provider_visible,
            }
    return payload


def _cache_scope_name(scope: object | None) -> str | None:
    if scope is None:
        return None
    if isinstance(scope, str):
        return scope
    name = getattr(scope, "name", None)
    return name if isinstance(name, str) and name else None


def _cache_session_name(session: object | None) -> str | None:
    name = getattr(session, "name", None)
    return name if isinstance(name, str) and name else None


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
                "authored_routes": list(step.authored_routes),
                "runtime_control_routes": list(step.runtime_control_routes),
                "provider_visible_routes_interactive": list(step.provider_visible_routes_interactive),
                "provider_visible_routes_full_auto": list(step.provider_visible_routes_full_auto),
                "session_name": step.session_name,
                "verifier_session_name": step.verifier_session_name,
                "state_fields": list(step.step_state_fields),
                "state_model": step.step_state_model.__name__,
                "item_state_fields": list(step.step_item_state_fields),
                "item_state_model": step.step_item_state_model.__name__ if step.step_item_state_model is not None else None,
                "before_hook": _callable_name(step.before_hook),
                "after_hook": _callable_name(step.after_hook),
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
                "item_state_model": worklist.runtime_item_state_model.__name__,
                "item_state_fields": list(worklist.runtime_item_state_model.model_fields.keys()),
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
                    "provider_visible_interactive": route.provider_visible_interactive,
                    "provider_visible_full_auto": route.provider_visible_full_auto,
                    "is_runtime_control": route.is_runtime_control,
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
                "provider_visible_interactive": route.provider_visible_interactive,
                "provider_visible_full_auto": route.provider_visible_full_auto,
                "is_runtime_control": route.is_runtime_control,
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
        source_hash=compiled.source_hash,
        topology_hash=topology_hash,
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
