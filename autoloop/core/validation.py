"""Workflow definition discovery and validation."""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, TypeAdapter

from .artifacts import Artifact, validate_artifact_declaration
from .descriptors import ParameterField, StateField, collect_descriptor_fields, effective_parameters_model, effective_state_model
from .effects import Advance, Handoff, Refresh, ResetCompletion, SetStatus
from .extensions import WorkflowExtension
from .errors import WorkflowValidationError
from .primitives import AWAIT_INPUT, Event, FAIL, FINISH, GLOBAL, SELF
from .prompts import resolve_prompt_reference
from .providers.retries import ProviderRetryPolicy
from .routes import Route, normalize_route_spec
from .sessions import DEFAULT_SESSION_NAME
from .step_state import build_step_item_state_model, build_step_state_model
from .steps import PromptStep, ProduceVerifyStep, Session, Step, PythonStep, ChildWorkflowStep
from .worklists import Worklist


TerminalDestination = str
PayloadValidator = Callable[[dict[str, Any]], None]
RESERVED_ROUTE_TAGS = frozenset({"question", "blocked", "failed"})
DeclaredDestination = Step | str | Route
DEFAULT_ROUTE_SUMMARIES = {
    "done": "Step completed and selected the default completion route.",
    "accepted": "Verifier accepted the governed output.",
    "needs_rework": "Verifier requested local repair within the same work boundary.",
    "needs_replan": "The current work boundary appears incorrect and replanning is needed.",
    "question": "Execution is awaiting user input.",
    "blocked": "Execution is awaiting input because the step is blocked.",
    "failed": "Execution failed.",
}
SIMPLE_CONTEXT_BARE_NAMES = frozenset(
    {
        "answer",
        "artifacts",
        "input",
        "item",
        "package_folder",
        "params",
        "request_file",
        "run_folder",
        "state",
        "task_folder",
        "workflow_folder",
        "workflow_params",
    }
)
RESERVED_STEP_PSEUDO_FIELDS = frozenset({"value", "state", "item_state", "meta"})
_PROMPT_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")


class _EmptyWorkflowState(BaseModel):
    pass


def _validate_simple_authoring_models(workflow_cls: type[Any]) -> None:
    if getattr(workflow_cls, "__strict_workflow__", True):
        return

    if getattr(workflow_cls, "Parameters", None) is not None:
        raise WorkflowValidationError("Use Params, not Parameters.")

    state_descriptors = collect_descriptor_fields(workflow_cls, descriptor_type=StateField)
    if state_descriptors:
        names = ", ".join(field.name for field in state_descriptors)
        raise WorkflowValidationError(
            f"{workflow_cls.__name__} must declare workflow state with State = BaseModel, not StateField ({names})."
        )

    param_descriptors = collect_descriptor_fields(workflow_cls, descriptor_type=ParameterField)
    if param_descriptors:
        names = ", ".join(field.name for field in param_descriptors)
        raise WorkflowValidationError(
            f"{workflow_cls.__name__} must declare workflow params with Params = BaseModel, not ParameterField ({names})."
        )

    raw_state = getattr(workflow_cls, "State", None)
    if raw_state is not None:
        if not inspect.isclass(raw_state) or not issubclass(raw_state, BaseModel):
            raise WorkflowValidationError(f"{workflow_cls.__name__}.State must inherit from pydantic.BaseModel")
        try:
            raw_state()
        except Exception as exc:
            raise WorkflowValidationError(
                f"{workflow_cls.__name__}.State must be instantiable with no arguments"
            ) from exc

    raw_params = getattr(workflow_cls, "Params", None)
    if raw_params is not None and (not inspect.isclass(raw_params) or not issubclass(raw_params, BaseModel)):
        raise WorkflowValidationError(f"{workflow_cls.__name__}.Params must inherit from pydantic.BaseModel")


def _snake_case_workflow_name(name: str) -> str:
    normalized = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    collapsed = re.sub(r"[^a-z0-9_]+", "_", normalized)
    return collapsed.strip("_") or name.lower()


def is_workflow_class(candidate: object) -> bool:
    """Return whether a class is a concrete supported workflow class."""

    if not inspect.isclass(candidate):
        return False
    if _is_base_workflow_class(candidate):
        return False
    if not _inherits_supported_workflow_base(candidate):
        return False
    return _has_workflow_members(candidate)


def _is_base_workflow_class(candidate: type[Any]) -> bool:
    return (candidate.__module__, candidate.__name__) in {
        ("autoloop.simple", "Workflow"),
        ("core", "Workflow"),
    }


def _inherits_supported_workflow_base(candidate: type[Any]) -> bool:
    for base in candidate.__mro__[1:]:
        if (base.__module__, base.__name__) in {
            ("autoloop.simple", "Workflow"),
            ("core", "Workflow"),
        }:
            return True
    return False


def _has_workflow_members(candidate: type[Any]) -> bool:
    for _, value in _visible_workflow_namespace_items(candidate):
        if isinstance(value, Step) or _is_simple_step_declaration(value):
            return True
    return False


def _visible_workflow_namespace_items(workflow_cls: type[Any]) -> tuple[tuple[str, object], ...]:
    effective: dict[str, tuple[int, int, str, object]] = {}
    hierarchy = [cls for cls in reversed(workflow_cls.__mro__) if cls is not object]
    for class_order, cls in enumerate(hierarchy):
        for attr_order, (attr_name, value) in enumerate(cls.__dict__.items()):
            effective[attr_name] = (class_order, attr_order, attr_name, value)
    return tuple(
        (attr_name, value)
        for _, _, attr_name, value in sorted(effective.values(), key=lambda item: (item[0], item[1]))
    )


def _iter_visible_workflow_namespace_items(workflow_cls: type[Any]) -> Sequence[tuple[str, object]]:
    return _visible_workflow_namespace_items(workflow_cls)


def resolve_optional_read_reference(
    reference: Artifact | str | Path,
    inventory: dict[str, "ArtifactInventoryRecord"],
) -> str | None:
    """Resolve a declared artifact read when possible, preserving optional path reads."""

    if isinstance(reference, Path):
        return None
    try:
        return resolve_artifact_reference(reference, inventory).qualified_name
    except WorkflowValidationError as exc:
        if isinstance(reference, str) and str(exc).startswith("unknown artifact reference "):
            return None
        raise


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    """Discovered workflow definition state."""

    workflow_cls: type[Any]
    workflow_name: str
    state_cls: type[BaseModel]
    parameters_cls: type[BaseModel] | None
    entry: Step
    steps: tuple[Step, ...]
    steps_by_name: dict[str, Step]
    sessions_by_name: dict[str, Session]
    default_session_name: str
    worklists_by_name: dict[str, Worklist[Any]]
    workflow_artifacts: dict[str, Artifact]
    workflow_log_artifacts: tuple[Artifact, ...]
    extensions: tuple[WorkflowExtension, ...]
    transitions: dict[Step | str, dict[str, DeclaredDestination]]


@dataclass(frozen=True, slots=True)
class ArtifactInventoryRecord:
    """Artifact registry candidate."""

    artifact: Artifact
    name: str
    qualified_name: str
    owner_step: str | None
    workflow_level: bool
    producer_steps: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _SimpleStepSeed:
    order: int
    attr_name: str
    declaration: object
    name: str
    kind: str
    writes: dict[str, Artifact]
    verifier_writes: dict[str, Artifact]
    output_order: tuple[str, ...]


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

    _validate_simple_authoring_models(workflow_cls)
    _install_simple_system_handler_aliases(workflow_cls)
    state_cls = effective_state_model(workflow_cls, fallback_model=_EmptyWorkflowState)
    parameters_cls = effective_parameters_model(workflow_cls)
    entry = getattr(workflow_cls, "entry", None)
    transitions = getattr(workflow_cls, "transitions", None)
    flow = getattr(workflow_cls, "flow", None)
    if getattr(workflow_cls, "__strict_workflow__", True) is False and (transitions is not None or flow is not None):
        raise WorkflowValidationError(
            "simple workflows must declare topology with step-local routes and optional entry, not transitions or flow"
        )
    extensions = getattr(workflow_cls, "extensions", ())
    declared_workflow_name = getattr(workflow_cls, "name", None)
    if isinstance(declared_workflow_name, str) and declared_workflow_name.strip():
        workflow_name = declared_workflow_name.strip()
    else:
        workflow_name = _snake_case_workflow_name(workflow_cls.__name__)
    workflow_artifacts: dict[str, Artifact] = {}
    sessions_by_name: dict[str, Session] = {}
    worklists_by_name: dict[str, Worklist[Any]] = {}
    steps: list[Step] = []
    steps_by_name: dict[str, Step] = {}
    seen_artifacts: set[int] = set()
    seen_sessions: set[int] = set()
    seen_worklists: set[int] = set()
    seen_steps: set[int] = set()
    seen_simple_declarations: set[int] = set()
    step_order: dict[int, int] = {}
    simple_seeds: list[_SimpleStepSeed] = []

    for attr_order, (attr_name, value) in enumerate(_iter_visible_workflow_namespace_items(workflow_cls)):
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
                value.bind_name("global" if attr_name == "global_session" else attr_name)
            sessions_by_name[value.name] = value
            seen_sessions.add(id(value))
        elif isinstance(value, Worklist):
            if id(value) in seen_worklists:
                continue
            if value.name in worklists_by_name:
                raise WorkflowValidationError(f"duplicate worklist name {value.name!r}")
            worklists_by_name[value.name] = value
            seen_worklists.add(id(value))
        elif isinstance(value, Step):
            if id(value) in seen_steps:
                continue
            if value.name in steps_by_name:
                raise WorkflowValidationError(f"duplicate step name {value.name!r}")
            steps.append(value)
            steps_by_name[value.name] = value
            seen_steps.add(id(value))
            step_order[id(value)] = attr_order
        elif _is_simple_step_declaration(value):
            if id(value) in seen_simple_declarations:
                continue
            simple_name = getattr(value, "name", None)
            if not isinstance(simple_name, str) or not simple_name:
                raise WorkflowValidationError(
                    f"simple step declaration {attr_name!r} must bind a deterministic name"
                )
            if simple_name in steps_by_name:
                raise WorkflowValidationError(f"duplicate step name {simple_name!r}")
            simple_outputs = _lower_simple_outputs(value, simple_name)
            review_outputs = _lower_simple_review_outputs(value, simple_name)
            simple_seeds.append(
                _SimpleStepSeed(
                    order=attr_order,
                    attr_name=attr_name,
                    declaration=value,
                    name=simple_name,
                    kind=str(getattr(value, "kind", "")),
                    writes=simple_outputs,
                    verifier_writes=review_outputs,
                    output_order=tuple((*simple_outputs.keys(), *review_outputs.keys())),
                )
            )
            seen_simple_declarations.add(id(value))

    if simple_seeds:
        lowered_steps = _lower_simple_steps(
            workflow_cls,
            simple_seeds=simple_seeds,
            workflow_artifacts=workflow_artifacts,
            existing_steps=tuple(steps),
        )
        for seed, step in lowered_steps:
            if step.name in steps_by_name:
                raise WorkflowValidationError(f"duplicate step name {step.name!r}")
            steps.append(step)
            steps_by_name[step.name] = step
            step_order[id(step)] = seed.order

        simple_step_map = {
            seed.declaration: step
            for seed, step in lowered_steps
        }
        entry, transitions = _lower_simple_workflow_graph(
            workflow_cls,
            entry=entry,
            ordered_steps=tuple(sorted(steps, key=lambda step: step_order.get(id(step), step._order))),
            simple_step_map=simple_step_map,
        )
    else:
        entry = _lower_simple_entry(entry, {})
        transitions = _lower_simple_transition_table(transitions, {})

    if isinstance(transitions, dict):
        transitions = _resolve_named_transition_targets(transitions, steps_by_name)
        transitions = _inject_reserved_routes(transitions, tuple(steps))

    entry = _resolve_named_entry(entry, steps_by_name)
    ordered_steps = tuple(sorted(steps, key=lambda step: step_order.get(id(step), step._order)))
    if entry is None and ordered_steps:
        entry = ordered_steps[0]
    ordered_steps = _order_steps_from_entry(ordered_steps, entry=entry, transitions=transitions)

    workflow_log_artifacts = tuple(getattr(workflow_cls, "log_artifacts", ()) or ())
    default_session_name = DEFAULT_SESSION_NAME
    global_session = getattr(workflow_cls, "global_session", None)
    if isinstance(global_session, Session):
        if global_session.name is None:
            global_session.bind_name(DEFAULT_SESSION_NAME)
        sessions_by_name.setdefault(global_session.name, global_session)
        default_session_name = global_session.name
    return WorkflowDefinition(
        workflow_cls=workflow_cls,
        workflow_name=workflow_name,
        state_cls=state_cls,
        parameters_cls=parameters_cls,
        entry=entry,
        steps=ordered_steps,
        steps_by_name=steps_by_name,
        sessions_by_name=sessions_by_name,
        default_session_name=default_session_name,
        worklists_by_name=worklists_by_name,
        workflow_artifacts=workflow_artifacts,
        workflow_log_artifacts=workflow_log_artifacts,
        extensions=extensions,
        transitions=transitions,
    )


def validate_workflow_definition(definition: WorkflowDefinition) -> None:
    """Validate a workflow definition."""

    _validate_state(definition)
    _validate_entry(definition)
    _validate_transitions_shape(definition)
    _validate_sessions(definition)
    _validate_worklists(definition)
    _validate_extensions(definition)
    _validate_handlers(definition)
    _validate_step_hooks(definition)
    inventory = collect_artifact_inventory(definition)
    _validate_artifact_declarations(inventory)
    _validate_required_artifacts(definition, inventory)
    _validate_artifact_graph(definition, inventory)
    _validate_topology(definition)
    _validate_control_contracts(definition, inventory)


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


def _is_simple_step_declaration(value: object) -> bool:
    return bool(getattr(value, "__autoloop_simple_declaration__", False))


def _install_simple_system_handler_aliases(workflow_cls: type[Any]) -> None:
    for _, value in _iter_visible_workflow_namespace_items(workflow_cls):
        if not _is_simple_step_declaration(value):
            continue
        if getattr(value, "kind", None) not in {"python", "system"}:
            continue
        step_name = getattr(value, "name", None)
        raw_handler = getattr(value, "fn", None)
        if not isinstance(step_name, str) or not step_name or raw_handler is None:
            continue
        handler_name = f"on_{step_name}"
        if handler_name in workflow_cls.__dict__:
            continue
        setattr(workflow_cls, handler_name, staticmethod(raw_handler))


def _is_simple_artifact_spec(value: object) -> bool:
    return bool(getattr(value, "__autoloop_simple_artifact_spec__", False))


def _is_simple_flow_spec(value: object) -> bool:
    return bool(getattr(value, "__autoloop_simple_flow_spec__", False))


def _lower_simple_outputs(declaration: object, step_name: str) -> dict[str, Artifact]:
    outputs: dict[str, Artifact] = {}
    for output in tuple(getattr(declaration, "outputs", ()) or ()):
        artifact = _materialize_simple_output(output, step_name=step_name)
        if artifact.name is None:
            raise WorkflowValidationError(
                f"simple step {step_name!r} output declarations must define artifact names"
            )
        if artifact.name in outputs:
            raise WorkflowValidationError(
                f"simple step {step_name!r} declares duplicate output artifact {artifact.name!r}"
            )
        outputs[artifact.name] = artifact
    return outputs


def _lower_simple_review_outputs(declaration: object, step_name: str) -> dict[str, Artifact]:
    outputs: dict[str, Artifact] = {}
    for output in tuple(getattr(declaration, "review_outputs", ()) or ()):
        artifact = _materialize_simple_output(output, step_name=step_name)
        if artifact.name is None:
            raise WorkflowValidationError(
                f"simple step {step_name!r} review output declarations must define artifact names"
            )
        if artifact.name in outputs:
            raise WorkflowValidationError(
                f"simple step {step_name!r} declares duplicate review output artifact {artifact.name!r}"
            )
        outputs[artifact.name] = artifact
    return outputs


def _materialize_simple_output(output: object, *, step_name: str) -> Artifact:
    if isinstance(output, Artifact):
        return output
    if _is_simple_artifact_spec(output):
        return output.materialize(step_name)
    raise WorkflowValidationError(
        f"simple step {step_name!r} output must be an Artifact or autoloop.simple artifact helper"
    )


def _lower_simple_steps(
    workflow_cls: type[Any],
    *,
    simple_seeds: Sequence[_SimpleStepSeed],
    workflow_artifacts: Mapping[str, Artifact],
    existing_steps: Sequence[Step],
) -> list[tuple[_SimpleStepSeed, Step]]:
    artifact_name_counts: dict[str, int] = {}
    for artifact in workflow_artifacts.values():
        if artifact.name is not None:
            artifact_name_counts[artifact.name] = artifact_name_counts.get(artifact.name, 0) + 1
    for step in existing_steps:
        for artifact in step.writes.values():
            if artifact.name is not None:
                artifact_name_counts[artifact.name] = artifact_name_counts.get(artifact.name, 0) + 1
    for seed in simple_seeds:
        for artifact in seed.writes.values():
            artifact_name_counts[artifact.name] = artifact_name_counts.get(artifact.name, 0) + 1
        for artifact in seed.verifier_writes.values():
            artifact_name_counts[artifact.name] = artifact_name_counts.get(artifact.name, 0) + 1
    lowered: list[tuple[_SimpleStepSeed, Step]] = []
    for seed in simple_seeds:
        declaration = seed.declaration

        explicit_reads = _normalize_simple_input_references(
            getattr(declaration, "reads", ()),
            step_name=seed.name,
        )
        prompt_references, inferred_reads = _analyze_simple_prompt_references(
            workflow_cls,
            seed=seed,
            existing_steps=existing_steps,
            simple_seeds=simple_seeds,
            artifact_name_counts=artifact_name_counts,
        )
        reads = tuple(dict.fromkeys((*explicit_reads, *inferred_reads)))
        requires = tuple(
            dict.fromkeys(
                _normalize_simple_input_references(
                    getattr(declaration, "requires", ()),
                    step_name=seed.name,
                )
            )
        )
        verifier_requires = tuple(
            dict.fromkeys(
                _normalize_simple_input_references(
                    getattr(declaration, "verifier_requires", ()),
                    step_name=seed.name,
                )
            )
        )
        verifier_reads = tuple(
            dict.fromkeys(
                (
                    *_normalize_simple_input_references(
                        getattr(declaration, "verifier_reads", ()),
                        step_name=seed.name,
                    ),
                    *seed.writes.keys(),
                )
            )
        )
        state_model = _normalize_simple_state_model(
            getattr(declaration, "state", None),
            step_name=seed.name,
            step_kind=seed.kind,
            module_name=workflow_cls.__module__,
        )
        step_item_state_model = _normalize_simple_item_state_model(
            getattr(declaration, "item_state", None),
            step_name=seed.name,
            step_kind=seed.kind,
            scope=getattr(declaration, "scope", None),
            module_name=workflow_cls.__module__,
        )
        retry_policy = _lower_simple_retry_policy(getattr(declaration, "retry", None), step_name=seed.name)
        session = getattr(declaration, "session", None)
        if session is not None and not isinstance(session, Session):
            raise WorkflowValidationError(
                f"simple step {seed.name!r} session must be declared with workflow.Session"
            )
        review_session = getattr(declaration, "verifier_session", None)
        if review_session is not None and not isinstance(review_session, Session):
            raise WorkflowValidationError(
                f"simple step {seed.name!r} verifier_session must be declared with workflow.Session"
            )

        if seed.kind in {"llm", "step"}:
            step = PromptStep(
                name=seed.name,
                producer=getattr(declaration, "prompt"),
                session=session,
                scope=getattr(declaration, "scope", None),
                reads=reads,
                requires=requires,
                writes=seed.writes,
                expected_output_schema=getattr(declaration, "control_schema", None),
                retry_policy=retry_policy,
                before=getattr(declaration, "before", None),
                after=getattr(declaration, "after", None),
                on_route=None,
                item_state=step_item_state_model,
            )
        elif seed.kind == "operation":
            step = PythonStep(
                name=seed.name,
                reads=reads,
                requires=requires,
                writes={},
                handler=getattr(declaration, "build_handler")(),
                retry_policy=None,
                before=None,
                after=None,
                on_route=None,
            )
        elif seed.kind in {"review", "produce_verify"}:
            step = ProduceVerifyStep(
                name=seed.name,
                producer=getattr(declaration, "producer_prompt"),
                verifier=getattr(declaration, "verifier_prompt"),
                session=session,
                review_session=review_session,
                scope=getattr(declaration, "scope", None),
                reads=reads,
                requires=requires,
                verifier_requires=verifier_requires,
                producer_writes=seed.writes,
                verifier_writes=seed.verifier_writes,
                expected_output_schema=getattr(declaration, "control_schema", None),
                retry_policy=retry_policy,
                before=None,
                after=None,
                on_route=None,
                before_do=getattr(declaration, "before_producer", None),
                after_do=getattr(declaration, "after_producer", None),
                before_review=getattr(declaration, "before_verifier", None),
                after_review=getattr(declaration, "after_verifier", None),
                item_state=step_item_state_model,
            )
        elif seed.kind in {"system", "python"}:
            step = PythonStep(
                name=seed.name,
                reads=reads,
                requires=requires,
                writes=seed.writes,
                handler=getattr(declaration, "fn"),
                retry_policy=retry_policy,
                before=getattr(declaration, "before", None),
                after=getattr(declaration, "after", None),
                on_route=None,
            )
        elif seed.kind == "workflow":
            step = ChildWorkflowStep(
                name=seed.name,
                workflow=getattr(declaration, "workflow"),
                message=getattr(declaration, "message", None),
                message_from=getattr(declaration, "message_from", None),
                params=getattr(declaration, "params", None),
                input=getattr(declaration, "input", None),
                reads=reads,
                requires=requires,
                writes=seed.writes,
                retry_policy=retry_policy,
                before=getattr(declaration, "before", None),
                after=getattr(declaration, "after", None),
                on_route=None,
            )
        else:
            raise WorkflowValidationError(f"unsupported simple step kind {seed.kind!r}")

        setattr(step, "simple_declaration", declaration)
        setattr(step, "simple_prompt_references", prompt_references)
        setattr(step, "producer_reads", reads)
        setattr(step, "producer_requires", requires)
        setattr(step, "producer_writes", tuple(seed.writes.keys()))
        setattr(step, "verifier_reads", verifier_reads)
        setattr(step, "verifier_requires", verifier_requires)
        setattr(step, "verifier_writes", tuple(seed.verifier_writes.keys()))
        setattr(step, "state_model", state_model)
        setattr(step, "step_item_state_model", step_item_state_model)
        lowered.append((seed, step))

    return lowered


def _normalize_simple_state_model(
    raw_state: object,
    *,
    step_name: str,
    step_kind: str,
    module_name: str,
) -> type[BaseModel]:
    return build_step_state_model(
        raw_state,
        step_name=step_name,
        step_kind=step_kind,
        module_name=module_name,
    )


def _normalize_simple_item_state_model(
    raw_state: object,
    *,
    step_name: str,
    step_kind: str,
    scope: object | None,
    module_name: str,
) -> type[BaseModel] | None:
    if scope is None:
        if raw_state is None:
            return None
        raise WorkflowValidationError(
            f"simple step {step_name!r} item_state requires scope=... on the same step"
        )
    return build_step_item_state_model(
        raw_state,
        step_name=step_name,
        step_kind=step_kind,
        module_name=module_name,
    )


def _normalize_simple_input_references(references: Sequence[object], *, step_name: str) -> tuple[Artifact | str, ...]:
    normalized: list[Artifact | str] = []
    for reference in references:
        if isinstance(reference, Artifact):
            normalized.append(reference)
            continue
        if _is_simple_artifact_spec(reference):
            normalized.append(str(reference.name))
            continue
        if isinstance(reference, str) and reference.strip():
            normalized.append(reference.strip())
            continue
        raise WorkflowValidationError(
            f"simple step {step_name!r} reads/requires entries must be artifact references or non-empty strings"
        )
    return tuple(normalized)


def _lower_simple_retry_policy(retry: object, *, step_name: str) -> ProviderRetryPolicy | None:
    if retry is None:
        return None
    if isinstance(retry, ProviderRetryPolicy):
        return retry
    if isinstance(retry, int) and not isinstance(retry, bool):
        return ProviderRetryPolicy(max_attempts=retry)
    raise WorkflowValidationError(
        f"simple step {step_name!r} retry must be an integer max-attempts value or ProviderRetryPolicy"
    )


def _analyze_simple_prompt_references(
    workflow_cls: type[Any],
    *,
    seed: _SimpleStepSeed,
    existing_steps: Sequence[Step],
    simple_seeds: Sequence[_SimpleStepSeed],
    artifact_name_counts: Mapping[str, int],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    prompts: list[object] = []
    if seed.kind in {"llm", "operation", "step"}:
        prompts.append(getattr(seed.declaration, "prompt", None))
    elif seed.kind in {"review", "produce_verify"}:
        prompts.extend(
            (
                getattr(seed.declaration, "producer_prompt", None),
                getattr(seed.declaration, "verifier_prompt", None),
            )
        )
    else:
        return (), ()

    state_fields = _model_field_names(effective_state_model(workflow_cls, fallback_model=_EmptyWorkflowState))
    parameter_fields = _model_field_names(effective_parameters_model(workflow_cls))
    input_fields = _model_field_names(getattr(workflow_cls, "Input", None))
    step_state_fields = _known_simple_step_state_fields(
        workflow_cls=workflow_cls,
        existing_steps=existing_steps,
        simple_seeds=simple_seeds,
    )
    worklist_item_state_fields = _known_worklist_item_state_fields(workflow_cls=workflow_cls)
    step_item_state_fields = _known_simple_step_item_state_fields(
        workflow_cls=workflow_cls,
        existing_steps=existing_steps,
        simple_seeds=simple_seeds,
    )
    scope_name = (
        _resolve_worklist_name(getattr(seed.declaration, "scope", None))
        if getattr(seed.declaration, "scope", None) is not None
        else None
    )
    own_outputs = frozenset(seed.writes.keys())
    step_output_names = _known_simple_step_outputs(existing_steps=existing_steps, simple_seeds=simple_seeds)
    search_roots = _simple_prompt_search_roots(workflow_cls)
    references: list[str] = []
    inferred: list[str] = []
    for prompt in prompts:
        text = _simple_prompt_text(prompt, search_roots=search_roots)
        if not text:
            continue
        for placeholder in _PROMPT_PLACEHOLDER_RE.findall(text):
            reference = placeholder.strip()
            if not reference:
                continue
            references.append(reference)
            inferred_artifact = _validate_simple_prompt_reference(
                reference,
                step_name=seed.name,
                own_outputs=own_outputs,
                state_fields=state_fields,
                parameter_fields=parameter_fields,
                input_fields=input_fields,
                scope_name=scope_name,
                worklist_item_state_fields=worklist_item_state_fields,
                step_state_fields=step_state_fields,
                step_item_state_fields=step_item_state_fields,
                step_output_names=step_output_names,
                artifact_name_counts=artifact_name_counts,
            )
            if inferred_artifact is not None:
                inferred.append(inferred_artifact)
    return tuple(dict.fromkeys(references)), tuple(dict.fromkeys(inferred))


def _known_simple_step_outputs(
    *,
    existing_steps: Sequence[Step],
    simple_seeds: Sequence[_SimpleStepSeed],
) -> dict[str, frozenset[str]]:
    step_outputs: dict[str, frozenset[str]] = {
        step.name: frozenset(
            artifact.name
            for artifact in step.writes.values()
            if artifact.name is not None
        )
        for step in existing_steps
    }
    for seed in simple_seeds:
        step_outputs[seed.name] = frozenset(seed.writes.keys())
    return step_outputs


def _known_simple_step_state_fields(
    *,
    workflow_cls: type[Any],
    existing_steps: Sequence[Step],
    simple_seeds: Sequence[_SimpleStepSeed],
) -> dict[str, frozenset[str]]:
    step_state_fields: dict[str, frozenset[str]] = {
        step.name: frozenset(
            getattr(
                getattr(step, "state_model", None)
                or build_step_state_model(
                    None,
                    step_name=step.name,
                    step_kind=step.kind,
                    module_name=workflow_cls.__module__,
                ),
                "model_fields",
                {},
            ).keys()
        )
        for step in existing_steps
    }
    for seed in simple_seeds:
        state_model = _normalize_simple_state_model(
            getattr(seed.declaration, "state", None),
            step_name=seed.name,
            step_kind=seed.kind,
            module_name=workflow_cls.__module__,
        )
        step_state_fields[seed.name] = frozenset(state_model.model_fields.keys())
    return step_state_fields


def _known_worklist_item_state_fields(
    *,
    workflow_cls: type[Any],
) -> dict[str, frozenset[str]]:
    fields: dict[str, frozenset[str]] = {}
    for _, value in _iter_visible_workflow_namespace_items(workflow_cls):
        if not isinstance(value, Worklist):
            continue
        fields[value.name] = frozenset(
            value.item_state_model.model_fields.keys()
            if value.item_state_model is not None
            else ()
        )
    return fields


def _known_simple_step_item_state_fields(
    *,
    workflow_cls: type[Any],
    existing_steps: Sequence[Step],
    simple_seeds: Sequence[_SimpleStepSeed],
) -> dict[str, frozenset[str]]:
    step_item_state_fields: dict[str, frozenset[str]] = {}
    for step in existing_steps:
        if step.scope is None:
            step_item_state_fields[step.name] = frozenset()
            continue
        model = getattr(step, "step_item_state_model", None) or build_step_item_state_model(
            getattr(step, "item_state", None),
            step_name=step.name,
            step_kind=step.kind,
            module_name=workflow_cls.__module__,
        )
        step_item_state_fields[step.name] = frozenset(model.model_fields.keys())
    for seed in simple_seeds:
        model = _normalize_simple_item_state_model(
            getattr(seed.declaration, "item_state", None),
            step_name=seed.name,
            step_kind=seed.kind,
            scope=getattr(seed.declaration, "scope", None),
            module_name=workflow_cls.__module__,
        )
        step_item_state_fields[seed.name] = frozenset(
            () if model is None else model.model_fields.keys()
        )
    return step_item_state_fields


def _validate_simple_prompt_reference(
    reference: str,
    *,
    step_name: str,
    own_outputs: frozenset[str],
    state_fields: frozenset[str],
    parameter_fields: frozenset[str],
    input_fields: frozenset[str],
    scope_name: str | None,
    worklist_item_state_fields: Mapping[str, frozenset[str]],
    step_state_fields: Mapping[str, frozenset[str]],
    step_item_state_fields: Mapping[str, frozenset[str]],
    step_output_names: Mapping[str, frozenset[str]],
    artifact_name_counts: Mapping[str, int],
) -> str | None:
    parts = reference.split(".")
    if len(parts) == 1:
        name = parts[0]
        context_collision = name in state_fields or name in parameter_fields or name in input_fields or name in SIMPLE_CONTEXT_BARE_NAMES
        artifact_count = artifact_name_counts.get(name, 0)
        if artifact_count > 1 or (artifact_count == 1 and context_collision):
            raise WorkflowValidationError(
                f"simple step {step_name!r} prompt placeholder {{{reference}}} is ambiguous; qualify the artifact reference"
            )
        if artifact_count == 1:
            return name if name not in own_outputs else None
        if context_collision:
            return None
        raise WorkflowValidationError(f"simple step {step_name!r} prompt placeholder {{{reference}}} is unknown")

    root, second, *rest = parts
    if root == "params":
        if second not in parameter_fields:
            raise WorkflowValidationError(
                f"simple step {step_name!r} prompt placeholder {{{reference}}} references unknown params field {second!r}"
            )
        return None
    if root == "self":
        if second not in own_outputs:
            raise WorkflowValidationError(
                f"simple step {step_name!r} prompt placeholder {{{reference}}} references unknown self artifact {second!r}"
            )
        return None
    if root == "state":
        if second not in state_fields:
            raise WorkflowValidationError(
                f"simple step {step_name!r} prompt placeholder {{{reference}}} references unknown state field {second!r}"
            )
        return None
    if root == "input":
        if second not in input_fields:
            raise WorkflowValidationError(
                f"simple step {step_name!r} prompt placeholder {{{reference}}} references unknown input field {second!r}"
            )
        return None
    if root == "run":
        if second not in {"id"}:
            raise WorkflowValidationError(
                f"simple step {step_name!r} prompt placeholder {{{reference}}} references unknown run field {second!r}"
            )
        return None
    if root == "workflow":
        if second not in {"folder"}:
            raise WorkflowValidationError(
                f"simple step {step_name!r} prompt placeholder {{{reference}}} references unknown workflow field {second!r}"
            )
        return None
    if root == "item":
        if second != "state" or not rest:
            raise WorkflowValidationError(
                f"simple step {step_name!r} prompt placeholder {{{reference}}} must use item.state.<field>"
            )
        if scope_name is None:
            raise WorkflowValidationError(
                f"simple step {step_name!r} prompt placeholder {{{reference}}} requires scope=... on the same step"
            )
        field_name = rest[0]
        available_fields = worklist_item_state_fields.get(scope_name, frozenset())
        if not available_fields:
            raise WorkflowValidationError(
                f"simple step {step_name!r} prompt placeholder {{{reference}}} requires worklist {scope_name!r} to declare item_state"
            )
        if field_name not in available_fields:
            raise WorkflowValidationError(
                f"simple step {step_name!r} prompt placeholder {{{reference}}} references unknown item state field {field_name!r} on worklist {scope_name!r}"
            )
        return None
    if root in {"artifacts", "step"} and not rest:
        return _validate_simple_prompt_reference(
            second,
            step_name=step_name,
            own_outputs=own_outputs,
            state_fields=state_fields,
            parameter_fields=parameter_fields,
            input_fields=input_fields,
            scope_name=scope_name,
            worklist_item_state_fields=worklist_item_state_fields,
            step_state_fields=step_state_fields,
            step_item_state_fields=step_item_state_fields,
            step_output_names=step_output_names,
            artifact_name_counts=artifact_name_counts,
        )
    if root not in step_output_names:
        raise WorkflowValidationError(
            f"simple step {step_name!r} prompt placeholder {{{reference}}} references unknown step {root!r}"
        )
    if second == "value":
        return None
    if second == "state":
        if not rest:
            raise WorkflowValidationError(
                f"simple step {step_name!r} prompt placeholder {{{reference}}} must qualify a step state field"
            )
        field_name = rest[0]
        if field_name not in step_state_fields.get(root, frozenset()):
            raise WorkflowValidationError(
                f"simple step {step_name!r} prompt placeholder {{{reference}}} references unknown state field {field_name!r} on step {root!r}"
            )
        return None
    if second == "item_state":
        if not rest:
            raise WorkflowValidationError(
                f"simple step {step_name!r} prompt placeholder {{{reference}}} must qualify a step item_state field"
            )
        field_name = rest[0]
        available_fields = step_item_state_fields.get(root, frozenset())
        if not available_fields:
            raise WorkflowValidationError(
                f"simple step {step_name!r} prompt placeholder {{{reference}}} requires scoped step {root!r} to declare item_state or use built-in scoped runtime state"
            )
        if field_name not in available_fields:
            raise WorkflowValidationError(
                f"simple step {step_name!r} prompt placeholder {{{reference}}} references unknown item_state field {field_name!r} on step {root!r}"
            )
        return None
    if second == "meta":
        return None
    if second not in step_output_names[root]:
        raise WorkflowValidationError(
            f"simple step {step_name!r} prompt placeholder {{{reference}}} references unknown artifact {second!r} on step {root!r}"
        )
    return None if root == step_name else f"{root}.{second}"


def _simple_prompt_search_roots(workflow_cls: type[Any]) -> tuple[Path, ...]:
    module = inspect.getmodule(workflow_cls)
    module_file = getattr(module, "__file__", None)
    if not isinstance(module_file, str) or not module_file:
        return ()
    return (Path(module_file).resolve().parent,)


def _simple_prompt_text(prompt: object, *, search_roots: Sequence[Path]) -> str | None:
    if prompt is None:
        return None
    prompt_text = getattr(prompt, "text", None)
    if isinstance(prompt_text, str) and prompt_text:
        return prompt_text
    prompt_path = getattr(prompt, "path", None)
    prompt_source = getattr(prompt, "source", None)
    if prompt_source == "registry":
        return None
    if isinstance(prompt_path, str) and prompt_path:
        return resolve_prompt_reference(
            prompt_path,
            source=prompt_source if isinstance(prompt_source, str) else "registry",
            search_roots=search_roots,
        ).text
    return None


def _model_field_names(model_cls: object) -> frozenset[str]:
    if not inspect.isclass(model_cls) or not issubclass(model_cls, BaseModel):
        return frozenset()
    return frozenset(getattr(model_cls, "model_fields", {}).keys())


def _placeholder_artifact_reference(placeholder: str) -> tuple[str | None, bool]:
    if not placeholder:
        return None, False
    if placeholder.startswith("artifacts."):
        candidate = placeholder[len("artifacts.") :].strip()
        return (candidate, False) if _is_single_placeholder_segment(candidate) else (None, False)
    if placeholder.startswith("step."):
        candidate = placeholder[len("step.") :].strip()
        return (candidate, False) if _is_single_placeholder_segment(candidate) else (None, False)
    if "." in placeholder:
        return None, False
    return (placeholder, True) if _is_single_placeholder_segment(placeholder) else (None, False)


def _is_single_placeholder_segment(value: str) -> bool:
    return bool(value) and "." not in value and " " not in value


def _lower_simple_workflow_graph(
    workflow_cls: type[Any],
    *,
    entry: object,
    ordered_steps: Sequence[Step],
    simple_step_map: Mapping[object, Step],
) -> tuple[object, object]:
    normalized_transitions = _merge_transition_tables(
        _lower_simple_declared_routes(simple_step_map),
        _lower_simple_default_routes(ordered_steps),
        prefer_existing=True,
    )
    normalized_entry = _lower_simple_entry(entry, simple_step_map)
    if isinstance(normalized_entry, Step):
        return normalized_entry, normalized_transitions
    inferred_entry = _infer_simple_entry(None, ordered_steps, simple_step_map)
    return inferred_entry, normalized_transitions


def _lower_simple_entry(entry: object, simple_step_map: Mapping[object, Step]) -> object:
    return _lower_simple_target(entry, simple_step_map)


def _infer_simple_entry(
    flow: object,
    steps: Sequence[Step],
    simple_step_map: Mapping[object, Step],
) -> Step | None:
    if flow is not None and _is_simple_flow_spec(flow):
        for item in flow.items:
            source = item[0] if isinstance(item, tuple) else item
            lowered = _lower_simple_target(source, simple_step_map)
            if isinstance(lowered, Step):
                return lowered
    return steps[0] if steps else None


def _lower_simple_transition_table(
    transitions: object,
    simple_step_map: Mapping[object, Step],
) -> dict[Step | str, dict[str, object]] | object | None:
    if transitions is None:
        return None
    if not isinstance(transitions, dict):
        return transitions
    lowered: dict[Step | str, dict[str, object]] = {}
    for source, route_map in transitions.items():
        lowered_source = _lower_simple_target(source, simple_step_map)
        if not isinstance(route_map, dict):
            lowered[lowered_source] = route_map
            continue
        lowered[lowered_source] = {
            route_name: _lower_simple_destination(destination, simple_step_map)
            for route_name, destination in route_map.items()
        }
    return lowered


def _lower_simple_declared_routes(
    simple_step_map: Mapping[object, Step],
) -> dict[Step | str, dict[str, object]]:
    lowered: dict[Step | str, dict[str, object]] = {}
    for declaration, step in simple_step_map.items():
        raw_routes = getattr(declaration, "routes", None)
        if not isinstance(raw_routes, dict) or not raw_routes:
            continue
        lowered[step] = {
            route_name: _lower_simple_destination(destination, simple_step_map)
            for route_name, destination in raw_routes.items()
        }
    return lowered


def _lower_simple_flow_transitions(
    items: Sequence[object],
    simple_step_map: Mapping[object, Step],
) -> dict[Step | str, dict[str, object]]:
    if not items:
        return {}

    lowered: dict[Step | str, dict[str, object]] = {}
    for index in range(len(items) - 1):
        current = items[index]
        next_item = items[index + 1]
        source_ref, route_tag = _lower_simple_chain_source(current, simple_step_map)
        if not isinstance(source_ref, Step):
            raise WorkflowValidationError("simple chain sources must be step declarations or step instances")
        destination_ref = next_item[0] if isinstance(next_item, tuple) else next_item
        lowered.setdefault(source_ref, {})[route_tag] = _lower_simple_destination(destination_ref, simple_step_map)

    last_item = items[-1]
    if isinstance(last_item, str) and last_item in {FINISH, AWAIT_INPUT, FAIL}:
        return lowered
    source_ref, route_tag = _lower_simple_chain_source(last_item, simple_step_map)
    if not isinstance(source_ref, Step):
        raise WorkflowValidationError("simple chain cannot terminate from a non-step value")
    lowered.setdefault(source_ref, {})[route_tag] = FINISH
    return lowered


def _lower_simple_default_routes(
    ordered_steps: Sequence[Step],
) -> dict[Step | str, dict[str, object]]:
    lowered: dict[Step | str, dict[str, object]] = {}
    for index, step in enumerate(ordered_steps):
        declaration = getattr(step, "simple_declaration", None)
        if declaration is None:
            continue
        declared_routes = getattr(declaration, "routes", None)
        step_routes = lowered.setdefault(step, {})
        if isinstance(step, ProduceVerifyStep):
            if not declared_routes:
                next_target: object = ordered_steps[index + 1] if index + 1 < len(ordered_steps) else FINISH
                step_routes.setdefault(getattr(step, "simple_accept_route", "accepted"), next_target)
                step_routes.setdefault(getattr(step, "simple_rework_route", "needs_rework"), step)
            continue
        if isinstance(step, ChildWorkflowStep):
            if not declared_routes:
                next_target = ordered_steps[index + 1] if index + 1 < len(ordered_steps) else FINISH
                step_routes.setdefault("done", next_target)
            continue
        if isinstance(step, PythonStep):
            if not declared_routes:
                next_target = ordered_steps[index + 1] if index + 1 < len(ordered_steps) else FINISH
                step_routes.setdefault("done", next_target)
            continue
        if declared_routes:
            continue
        next_target = ordered_steps[index + 1] if index + 1 < len(ordered_steps) else FINISH
        step_routes.setdefault("done", next_target)
    return lowered


def _lower_simple_chain_source(
    item: object,
    simple_step_map: Mapping[object, Step],
) -> tuple[object, str]:
    if isinstance(item, tuple):
        if len(item) != 2 or not isinstance(item[1], str) or not item[1].strip():
            raise WorkflowValidationError("simple chain tuple entries must be (step, route_tag)")
        return _lower_simple_target(item[0], simple_step_map), item[1].strip()
    lowered = _lower_simple_target(item, simple_step_map)
    return lowered, _default_completion_route_for_step(lowered)


def _default_completion_route_for_step(step: object) -> str:
    if isinstance(step, ProduceVerifyStep):
        return str(getattr(step, "simple_accept_route", "accepted"))
    if isinstance(step, (PromptStep, PythonStep, ChildWorkflowStep)):
        return "done"
    if isinstance(step, Step):
        raise WorkflowValidationError(
            f"simple chain cannot infer a completion route for strict step {step.name!r}; specify (step, route_tag)"
        )
    declaration_route = getattr(step, "default_chain_route", None)
    if isinstance(declaration_route, str) and declaration_route:
        return declaration_route
    raise WorkflowValidationError("simple chain nodes must be step declarations or step instances")


def _lower_simple_target(target: object, simple_step_map: Mapping[object, Step]) -> object:
    return simple_step_map.get(target, target)


def _lower_simple_destination(destination: object, simple_step_map: Mapping[object, Step]) -> object:
    if isinstance(destination, Route):
        target = _lower_simple_target(destination.target, simple_step_map)
        if target is destination.target:
            return destination
        return Route(
            target=target,
            effects=destination.effects,
            summary=destination.summary,
            required_writes=destination.required_writes,
            handoff=destination.handoff,
            on_taken=destination.on_taken,
        )
    return _lower_simple_target(destination, simple_step_map)


def _resolve_named_entry(entry: object, steps_by_name: Mapping[str, Step]) -> Step | None | object:
    if entry is None or isinstance(entry, Step):
        return entry
    if isinstance(entry, str):
        return steps_by_name.get(entry, entry)
    return entry


def _order_steps_from_entry(
    steps: Sequence[Step],
    *,
    entry: Step | None | object,
    transitions: Mapping[Step | str, Mapping[str, object]],
) -> tuple[Step, ...]:
    if not steps or not isinstance(entry, Step):
        return tuple(steps)

    ordered: list[Step] = []
    seen: set[int] = set()

    def visit(step: Step) -> None:
        step_id = id(step)
        if step_id in seen:
            return
        seen.add(step_id)
        ordered.append(step)
        for destination in transitions.get(step, {}).values():
            route = normalize_route_spec(destination)
            target = route.target
            if isinstance(target, Step):
                visit(target)

    visit(entry)
    for step in steps:
        visit(step)
    return tuple(ordered)


def _resolve_named_transition_targets(
    transitions: Mapping[Step | str, Mapping[str, object]],
    steps_by_name: Mapping[str, Step],
) -> dict[Step | str, dict[str, object]]:
    resolved: dict[Step | str, dict[str, object]] = {}
    for source, route_map in transitions.items():
        resolved_source = _resolve_transition_source(source, steps_by_name)
        resolved[resolved_source] = {
            route_name: _resolve_transition_destination(
                destination,
                source=resolved_source,
                steps_by_name=steps_by_name,
            )
            for route_name, destination in route_map.items()
        }
    return resolved


def _resolve_transition_source(source: Step | str, steps_by_name: Mapping[str, Step]) -> Step | str:
    if source == GLOBAL or isinstance(source, Step):
        return source
    if isinstance(source, str):
        return steps_by_name.get(source, source)
    return source


def _resolve_transition_destination(
    destination: object,
    *,
    source: Step | str,
    steps_by_name: Mapping[str, Step],
) -> object:
    if isinstance(destination, Route):
        target = _resolve_transition_destination(destination.target, source=source, steps_by_name=steps_by_name)
        if target is destination.target:
            return destination
        return Route(
            target=target,
            effects=destination.effects,
            summary=destination.summary,
            required_writes=destination.required_writes,
            handoff=destination.handoff,
            on_taken=destination.on_taken,
        )
    if destination == SELF:
        return source if isinstance(source, Step) else destination
    if isinstance(destination, str) and destination not in {FINISH, AWAIT_INPUT, FAIL}:
        return steps_by_name.get(destination, destination)
    return destination


def _merge_transition_tables(
    base: Mapping[Step | str, Mapping[str, object]],
    extra: Mapping[Step | str, Mapping[str, object]],
    *,
    prefer_existing: bool = False,
) -> dict[Step | str, dict[str, object]]:
    merged: dict[Step | str, dict[str, object]] = {
        source: dict(route_map)
        for source, route_map in base.items()
    }
    for source, route_map in extra.items():
        existing = merged.setdefault(source, {})
        for route_name, destination in route_map.items():
            current = existing.get(route_name)
            if current is not None and _route_signature(current) != _route_signature(destination):
                if prefer_existing:
                    continue
                source_name = source if isinstance(source, str) else source.name
                raise WorkflowValidationError(
                    f"conflicting transition declarations for step {source_name!r} route {route_name!r}"
                )
            existing[route_name] = destination
    return merged


def _inject_reserved_routes(
    transitions: Mapping[Step | str, Mapping[str, object]],
    steps: Sequence[Step],
) -> dict[Step | str, dict[str, object]]:
    injected: dict[Step | str, dict[str, object]] = {
        source: dict(route_map)
        for source, route_map in transitions.items()
    }
    for step in steps:
        declaration = getattr(step, "simple_declaration", None)
        step_routes = injected.setdefault(step, {})
        control_routes = True if declaration is None else getattr(declaration, "control_routes", True)
        if isinstance(step, ProduceVerifyStep):
            if control_routes:
                step_routes.setdefault("question", AWAIT_INPUT)
                step_routes.setdefault("blocked", AWAIT_INPUT)
                step_routes.setdefault("failed", FAIL)
            continue
        if isinstance(step, PromptStep):
            if control_routes:
                step_routes.setdefault("question", AWAIT_INPUT)
                step_routes.setdefault("blocked", AWAIT_INPUT)
                step_routes.setdefault("failed", FAIL)
            continue
        if isinstance(step, (PythonStep, ChildWorkflowStep)) and control_routes:
            step_routes.setdefault("failed", FAIL)
    return injected


def _route_signature(
    destination: object,
) -> tuple[object, tuple[object, ...], str | None, tuple[str, ...], str | None, object | None]:
    route = normalize_route_spec(destination)
    target = route.target.name if isinstance(route.target, Step) else route.target
    return (
        target,
        tuple(route.effects),
        route.summary,
        None if route.required_writes is None else tuple(route.required_writes),
        route.handoff,
        route.on_taken,
    )


def collect_artifact_inventory(definition: WorkflowDefinition) -> dict[str, ArtifactInventoryRecord]:
    """Collect artifact registry metadata keyed by canonical reference."""

    workflow_level_names_to_identity: dict[str, int] = {}
    qualified_names_to_identity: dict[str, int] = {}
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
        if name in RESERVED_STEP_PSEUDO_FIELDS:
            raise WorkflowValidationError(
                f"artifact name {name!r} is reserved because it collides with prompt pseudo-fields"
            )
        existing_record = records_by_identity.get(artifact_id)
        workflow_level_declared = bool(existing_record and existing_record["workflow_level"])
        allow_producer_rebind = bool(
            existing_record
            and not existing_record["producer_steps"]
            and existing_record["owner_step"] is None
            and producer_step is not None
        )

        if producer_step is not None and artifact.owner_step is None and (
            not workflow_level_declared or allow_producer_rebind
        ):
            artifact.bind_owner_step(producer_step)
            artifact.owner = next(step for step in definition.steps if step.name == producer_step)
        elif artifact.qualified_name is None:
            artifact.qualified_name = name

        qualified_name = artifact.qualified_name or name
        if allow_producer_rebind and existing_record is not None and existing_record["qualified_name"] != qualified_name:
            old_qualified_name = existing_record["qualified_name"]
            if qualified_names_to_identity.get(old_qualified_name) == artifact_id:
                del qualified_names_to_identity[old_qualified_name]
        if workflow_level:
            existing_identity = workflow_level_names_to_identity.get(name)
            if existing_identity is not None and existing_identity != artifact_id:
                raise WorkflowValidationError(f"duplicate artifact name {name!r}")
            workflow_level_names_to_identity[name] = artifact_id
        existing_identity = qualified_names_to_identity.get(qualified_name)
        if existing_identity is not None and existing_identity != artifact_id:
            raise WorkflowValidationError(f"duplicate qualified artifact name {qualified_name!r}")
        qualified_names_to_identity[qualified_name] = artifact_id
        record = records_by_identity.setdefault(
            artifact_id,
            {
                "artifact": artifact,
                "name": name,
                "qualified_name": qualified_name,
                "owner_step": artifact.owner_step,
                "workflow_level": False,
                "producer_steps": [],
            },
        )
        if record["name"] != name:
            raise WorkflowValidationError(f"artifact name drift detected for {artifact!r}")
        if record["qualified_name"] != qualified_name:
            if allow_producer_rebind:
                record["qualified_name"] = qualified_name
                record["owner_step"] = artifact.owner_step
            else:
                raise WorkflowValidationError(f"artifact qualified-name drift detected for {artifact!r}")
        if record["owner_step"] != artifact.owner_step:
            if allow_producer_rebind:
                record["owner_step"] = artifact.owner_step
            else:
                raise WorkflowValidationError(f"artifact owner-step drift detected for {artifact!r}")
        if workflow_level:
            record["workflow_level"] = True
        if producer_step is not None and producer_step not in record["producer_steps"]:
            record["producer_steps"].append(producer_step)

    for attr_name, artifact in definition.workflow_artifacts.items():
        register(artifact, fallback_name=attr_name, workflow_level=True)
    for index, artifact in enumerate(definition.workflow_log_artifacts, start=1):
        register(artifact, fallback_name=f"workflow__log_{index}")
    for step in definition.steps:
        for write_name, artifact in step.writes.items():
            register(artifact, fallback_name=write_name, producer_step=step.name)
        for index, artifact in enumerate(step.reads, start=1):
            if isinstance(artifact, Artifact):
                register(artifact, fallback_name=f"{step.name}__read_{index}")
        for index, artifact in enumerate(step.requires, start=1):
            if isinstance(artifact, Artifact):
                register(artifact, fallback_name=f"{step.name}__require_{index}")
        for index, artifact in enumerate(step.log_artifacts, start=1):
            register(artifact, fallback_name=f"{step.name}__log_{index}")

    inventory = {
        record["qualified_name"]: ArtifactInventoryRecord(
            artifact=record["artifact"],
            name=record["name"],
            qualified_name=record["qualified_name"],
            owner_step=record["owner_step"],
            workflow_level=record["workflow_level"],
            producer_steps=tuple(record["producer_steps"]),
        )
        for record in records_by_identity.values()
    }
    return inventory


def public_artifact_inventory(inventory: dict[str, ArtifactInventoryRecord]) -> dict[str, ArtifactInventoryRecord]:
    """Return unqualified artifact aliases for globally unambiguous artifacts."""

    grouped: dict[str, list[ArtifactInventoryRecord]] = {}
    for record in inventory.values():
        grouped.setdefault(record.name, []).append(record)
    return {
        name: records[0]
        for name, records in grouped.items()
        if len(records) == 1
    }


def resolve_artifact_reference(
    reference: Artifact | str,
    inventory: dict[str, ArtifactInventoryRecord],
    *,
    step_name: str | None = None,
    prefer_step_local: bool = False,
) -> ArtifactInventoryRecord:
    """Resolve an artifact reference deterministically against inventory."""

    if isinstance(reference, Artifact):
        if reference.qualified_name:
            record = inventory.get(reference.qualified_name)
            if record is not None:
                return record
        if reference.name is None:
            raise WorkflowValidationError("artifact reference must have a bound name")
        raw_reference = reference.name
    else:
        raw_reference = reference

    if not isinstance(raw_reference, str) or not raw_reference.strip():
        raise WorkflowValidationError("artifact references must be non-empty strings or Artifact declarations")
    raw_reference = raw_reference.strip()

    if "." in raw_reference and raw_reference in inventory:
        return inventory[raw_reference]

    if prefer_step_local and step_name is not None:
        step_local_name = f"{step_name}.{raw_reference}"
        record = inventory.get(step_local_name)
        if record is not None:
            return record

    if raw_reference in inventory:
        return inventory[raw_reference]

    matches = [record for record in inventory.values() if record.name == raw_reference]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise WorkflowValidationError(f"unknown artifact reference {raw_reference!r}")
    candidates = ", ".join(sorted(record.qualified_name for record in matches))
    raise WorkflowValidationError(
        f"ambiguous artifact reference {raw_reference!r}; use one of: {candidates}"
    )


def normalize_step_route_metadata(
    definition: WorkflowDefinition,
    step: Step,
    inventory: dict[str, ArtifactInventoryRecord],
) -> dict[str, Route]:
    """Normalize one step's route metadata."""

    available_routes = step_available_route_tags(definition, step)
    step_routes = definition.transitions.get(step, {})
    global_routes = definition.transitions.get(GLOBAL, {})
    normalized_routes: dict[str, Route] = {}
    for route_name in available_routes:
        destination = step_routes.get(route_name, global_routes.get(route_name))
        route = normalize_route_spec(destination)
        step_metadata = step.route_metadata.get(route_name, Route())
        if step_metadata.target is not None or step_metadata.effects or step_metadata.on_taken is not None:
            raise WorkflowValidationError(
                f"step {step.name!r} route metadata for {route_name!r} may only declare summary, required_writes, or handoff"
            )
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
        summary = (
            route.summary
            or step_metadata.summary
            or _fallback_route_summary(step.name, route_name, route.target)
        )
        handoff = route.handoff or step_metadata.handoff
        normalized_routes[route_name] = Route(
            target=route.target,
            effects=route.effects,
            summary=summary,
            required_writes=required_writes,
            handoff=handoff,
            on_taken=route.on_taken,
        )
    return normalized_routes


def step_available_route_tags(definition: WorkflowDefinition, step: Step) -> tuple[str, ...]:
    """Return the ordered legal route tags for a step."""

    step_routes = definition.transitions.get(step, {})
    global_routes = definition.transitions.get(GLOBAL, {})
    return tuple(dict.fromkeys((*step_routes.keys(), *global_routes.keys())))


def compile_expected_output_contract(spec: Any) -> tuple[dict[str, Any], PayloadValidator]:
    """Compile a step output contract into JSON schema plus a runtime validator."""

    if isinstance(spec, Mapping):
        schema = deepcopy(dict(spec))
        validator_cls = _load_jsonschema_validator_cls()
        try:
            validator_cls.check_schema(schema)
        except Exception as exc:  # pragma: no cover - backend-specific validation detail
            raise WorkflowValidationError("expected_output_schema must be a valid JSON schema mapping") from exc
        validator = validator_cls(schema)

        def validate_payload(payload: dict[str, Any]) -> None:
            validator.validate(payload)

        return schema, validate_payload

    try:
        adapter = TypeAdapter(spec)
        schema = adapter.json_schema()
    except Exception as exc:  # pragma: no cover - pydantic error surface is not stable
        raise WorkflowValidationError(
            "expected_output_schema must be a JSON schema mapping or pydantic-compatible type"
        ) from exc

    def validate_payload(payload: dict[str, Any]) -> None:
        adapter.validate_python(payload, strict=True)

    return schema, validate_payload


def _load_jsonschema_validator_cls() -> type[Any]:
    try:
        from jsonschema import Draft202012Validator
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency is expected in test/runtime env
        raise WorkflowValidationError(
            "raw expected_output_schema mappings require the optional jsonschema dependency"
        ) from exc
    return Draft202012Validator


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
        for tag in routes:
            if not isinstance(tag, str) or not tag.strip():
                raise WorkflowValidationError("transition route tags must be non-empty strings")


def _validate_sessions(definition: WorkflowDefinition) -> None:
    declared_sessions = {id(session) for session in definition.sessions_by_name.values()}
    for step in definition.steps:
        if step.session is not None and id(step.session) not in declared_sessions:
            raise WorkflowValidationError(
                f"step {step.name!r} references an undeclared session slot"
            )
        if isinstance(step, ProduceVerifyStep) and step.review_session is not None and id(step.review_session) not in declared_sessions:
            raise WorkflowValidationError(
                f"step {step.name!r} references an undeclared review session slot"
            )


def _validate_worklists(definition: WorkflowDefinition) -> None:
    declared_worklists = definition.worklists_by_name
    for step in definition.steps:
        if getattr(step, "item_state", None) is not None and step.scope is None:
            raise WorkflowValidationError(
                f"step {step.name!r} item_state requires scope on the same step"
            )
        if step.scope is None:
            continue
        if isinstance(step, PythonStep):
            raise WorkflowValidationError(f"system step {step.name!r} cannot declare scope")
        scope_name = _resolve_worklist_name(step.scope)
        if scope_name not in declared_worklists:
            raise WorkflowValidationError(
                f"step {step.name!r} references unknown worklist {scope_name!r}"
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
        if isinstance(step, PythonStep):
            active_handler = step.handler if step.handler is not None else raw_handler
            if active_handler is None:
                raise WorkflowValidationError(f"system step {step.name!r} is missing handler {handler_name!r}")
            _validate_callable_arity(handler_name, active_handler, {1, 2})
            continue
        if raw_handler is not None:
            _validate_callable_arity(handler_name, raw_handler, {3})

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


def _validate_step_hooks(definition: WorkflowDefinition) -> None:
    for step in definition.steps:
        if step.before is not None:
            _validate_callable_arity(f"{step.name!r} before hook", step.before, {1, 2})
        if step.after is not None:
            _validate_callable_arity(f"{step.name!r} after hook", step.after, {1, 2, 3, 4})
        if getattr(step, "on_route", None) is not None:
            _validate_callable_arity(f"{step.name!r} on_route hook", step.on_route, {1})
        for route_name, destination in definition.transitions.get(step, {}).items():
            route = normalize_route_spec(destination)
            if route.on_taken is not None:
                _validate_callable_arity(f"{step.name!r} route {route_name!r} on_taken hook", route.on_taken, {1})
        if isinstance(step, ProduceVerifyStep):
            if getattr(step, "before_do", None) is not None:
                _validate_callable_arity(f"{step.name!r} before_do hook", step.before_do, {1, 2})
            if getattr(step, "after_do", None) is not None:
                _validate_callable_arity(f"{step.name!r} after_do hook", step.after_do, {1, 2, 3, 4})
            if getattr(step, "before_review", None) is not None:
                _validate_callable_arity(f"{step.name!r} before_review hook", step.before_review, {1, 2})
            if getattr(step, "after_review", None) is not None:
                _validate_callable_arity(f"{step.name!r} after_review hook", step.after_review, {1, 2, 3, 4})


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


def _validate_artifact_declarations(inventory: dict[str, ArtifactInventoryRecord]) -> None:
    for record in inventory.values():
        errors = validate_artifact_declaration(record.artifact)
        if not errors:
            continue
        owner = f"artifact {record.qualified_name!r}"
        if record.producer_steps:
            owner = f"artifact {record.qualified_name!r} produced by step {record.producer_steps[0]!r}"
        raise WorkflowValidationError(f"{owner} is invalid: {'; '.join(errors)}")


def _validate_artifact_graph(
    definition: WorkflowDefinition,
    inventory: dict[str, ArtifactInventoryRecord],
) -> None:
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


def _validate_topology(definition: WorkflowDefinition) -> None:
    step_identities = {id(step): step for step in definition.steps}
    valid_destinations = _valid_route_destinations(definition)
    for source, routes in definition.transitions.items():
        if source != GLOBAL and id(source) not in step_identities:
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


def _validate_control_contracts(
    definition: WorkflowDefinition,
    inventory: dict[str, ArtifactInventoryRecord],
) -> None:
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
                _validate_workflow_step_reference(step)
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
    definition: WorkflowDefinition,
    *,
    source: Step | str,
    tag: str,
    destination: DeclaredDestination,
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
    _validate_route_effects(definition, source=source, tag=tag, route=route)


def _validate_route_effects(
    definition: WorkflowDefinition,
    *,
    source: Step | str,
    tag: str,
    route: Route,
) -> None:
    has_handoff = route.handoff is not None or any(isinstance(effect, Handoff) for effect in route.effects)
    if has_handoff:
        _validate_handoff_destinations(definition, route=route, tag=tag)
    for effect in route.effects:
        if isinstance(effect, Handoff):
            continue
        if isinstance(effect, Advance):
            if effect.if_exhausted == "route" and effect.route_to is None:
                raise WorkflowValidationError("Advance(..., if_exhausted='route') requires route_to")
            if effect.route_to is not None:
                route_to = effect.route_to
                target = route_to.target if isinstance(route_to, Route) else route_to
                if isinstance(target, Step):
                    if target.name not in definition.steps_by_name:
                        raise WorkflowValidationError(
                            f"Advance(..., route_to=...) references unknown step {target.name!r}"
                        )
                elif target not in _valid_route_destinations(definition):
                    raise WorkflowValidationError(
                        f"Advance(..., route_to=...) references invalid destination {target!r}"
                    )
            _validate_effect_worklist(definition, effect_name="Advance", worklist=effect.worklist)
            _validate_advance_source_scope(source=source, worklist=effect.worklist)
            continue
        if isinstance(effect, (Refresh, ResetCompletion, SetStatus)):
            effect_name = type(effect).__name__
            _validate_effect_worklist(definition, effect_name=effect_name, worklist=effect.worklist)
            continue
        raise WorkflowValidationError(f"unsupported route effect {type(effect).__name__!r} for route {tag!r}")


def _validate_workflow_step_reference(step: ChildWorkflowStep) -> None:
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


def _validate_handoff_destinations(
    definition: WorkflowDefinition,
    *,
    route: Route,
    tag: str,
) -> None:
    possible_targets = [route.target]
    for effect in route.effects:
        if not isinstance(effect, Advance) or effect.route_to is None:
            continue
        advance_route = normalize_route_spec(effect.route_to)
        possible_targets.append(advance_route.target)
    for target in possible_targets:
        if not isinstance(target, Step):
            continue
        resolved = definition.steps_by_name.get(target.name)
        if isinstance(resolved, PythonStep):
            raise WorkflowValidationError(
                f"route {tag!r} cannot deliver Handoff to PythonStep {target.name!r}"
            )


def _validate_effect_worklist(
    definition: WorkflowDefinition,
    *,
    effect_name: str,
    worklist: object | str,
) -> None:
    worklist_name = _resolve_worklist_name(worklist)
    if not isinstance(worklist_name, str) or not worklist_name:
        raise WorkflowValidationError(f"{effect_name} worklist reference must be a non-empty string or named object")
    if worklist_name not in definition.worklists_by_name:
        raise WorkflowValidationError(f"{effect_name} references unknown worklist {worklist_name!r}")


def _validate_advance_source_scope(*, source: Step | str, worklist: object | str) -> None:
    worklist_name = _resolve_worklist_name(worklist)
    if source == GLOBAL:
        raise WorkflowValidationError(
            f"Advance({worklist_name!r}) cannot be declared on a GLOBAL transition"
        )
    if not isinstance(source, Step):
        raise WorkflowValidationError(
            f"Advance({worklist_name!r}) requires a concrete scoped source step"
        )
    source_scope_name = _resolve_worklist_name(source.scope) if source.scope is not None else None
    if source_scope_name is None:
        raise WorkflowValidationError(
            f"step {source.name!r} uses Advance({worklist_name!r}) but is not scoped to that worklist"
        )
    if source_scope_name != worklist_name:
        raise WorkflowValidationError(
            f"step {source.name!r} uses Advance({worklist_name!r}) but is scoped to {source_scope_name!r}"
        )


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


def _valid_route_destinations(definition: WorkflowDefinition) -> set[str]:
    return {FINISH, AWAIT_INPUT, FAIL}


def _fallback_route_summary(source_step: str, route_name: str, target: object | None) -> str:
    default = DEFAULT_ROUTE_SUMMARIES.get(route_name)
    if default is not None:
        return default
    if isinstance(target, Step):
        target_name = target.name
    elif isinstance(target, str):
        target_name = target
    else:
        target_name = "unknown"
    return f"Routes from {source_step!r} to {target_name!r}."


def _resolve_worklist_name(worklist: object | str) -> str:
    return worklist if isinstance(worklist, str) else getattr(worklist, "name", None)
