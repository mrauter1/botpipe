"""Workflow definition discovery ownership."""

from __future__ import annotations

import inspect
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from botlane.policy import Policy, PolicyInput

from .artifacts import Artifact
from .branch_groups.lowering import build_branch_group_declaration_spec, declared_internal_route_tags
from .branch_groups.models import BranchStepDeclarationSpec
from .branch_groups.validation import (
    ensure_json_serializable,
    validate_branch_placeholder_reference,
    validate_branch_step_kind,
    validate_branch_step_session_requirements,
    validate_fan_in_helper_placement,
    validate_fan_in_placeholder_reference,
    validate_fan_in_step_kind,
    validate_path_safe_name,
)
from .context_placeholders import CTX_MODEL_ROOTS, CTX_NESTED_FIELDS, CTX_SCALAR_FIELDS, validate_safe_ctx_reference
from .descriptors import (
    ParameterField,
    StateField,
    collect_descriptor_fields,
    effective_parameters_model,
    effective_state_model,
)
from .errors import WorkflowValidationError
from .primitives import AWAIT_INPUT, FAIL, FINISH, GLOBAL, SELF
from .prompts import resolve_prompt_reference
from .provider_policy import ProviderPolicy, ProviderPolicyOverride
from .providers.retries import ProviderRetryPolicy
from .routes import Route, _replace_route, normalize_route_spec
from .sessions import DEFAULT_SESSION_NAME
from .step_state import build_step_item_state_model, build_step_state_model
from .steps import BranchGroupStep, ChildWorkflowStep, ProduceVerifyStep, PromptStep, PythonStep, Session, Step
from .worklists import Worklist


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


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    workflow_cls: type[Any]
    workflow_name: str
    workflow_policy: PolicyInput
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
    extensions: tuple[Any, ...]
    authored_transitions: dict[Step | str, dict[str, Any]]
    transitions: dict[Step | str, dict[str, Any]]
    framework_default_transitions_by_step: dict[str, dict[str, Any]]
    runtime_control_routes_by_step: dict[str, tuple[str, ...]]

    @property
    def global_route_sentinel(self) -> str:
        return GLOBAL

    @property
    def finish_terminal(self) -> str:
        return FINISH

    @property
    def await_input_terminal(self) -> str:
        return AWAIT_INPUT

    @property
    def fail_terminal(self) -> str:
        return FAIL

    @property
    def reserved_step_pseudo_fields(self) -> frozenset[str]:
        return RESERVED_STEP_PSEUDO_FIELDS


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
        if cls.__module__ == "botlane.core" and name == "Workflow":
            return cls
        from .validation import validate_workflow_definition

        definition = describe_workflow_class(cls)
        validate_workflow_definition(definition)
        cls.__workflow_definition__ = definition
        return cls


def is_workflow_class(candidate: object) -> bool:
    if not inspect.isclass(candidate):
        return False
    if _is_base_workflow_class(candidate):
        return False
    if not _inherits_supported_workflow_base(candidate):
        return False
    return _has_workflow_members(candidate)


def get_workflow_definition(workflow_cls: type[Any]) -> WorkflowDefinition:
    from .validation import validate_workflow_definition

    definition = getattr(workflow_cls, "__workflow_definition__", None)
    if isinstance(definition, WorkflowDefinition):
        return definition
    definition = describe_workflow_class(workflow_cls)
    validate_workflow_definition(definition)
    workflow_cls.__workflow_definition__ = definition
    return definition


def describe_workflow_class(workflow_cls: type[Any]) -> WorkflowDefinition:
    _validate_simple_authoring_models(workflow_cls)
    workflow_policy = _validate_workflow_policy(workflow_cls)
    state_cls = effective_state_model(workflow_cls, fallback_model=_EmptyWorkflowState)
    parameters_cls = effective_parameters_model(workflow_cls)
    entry = getattr(workflow_cls, "entry", None)
    transitions = getattr(workflow_cls, "transitions", None)
    flow = getattr(workflow_cls, "flow", None)
    if _uses_simple_authoring_model(workflow_cls) and (transitions is not None or flow is not None):
        raise WorkflowValidationError(
            "simple workflows must declare topology with step-local routes and optional entry, not transitions or flow"
        )
    extensions = getattr(workflow_cls, "extensions", ())
    declared_workflow_name = getattr(workflow_cls, "name", None)
    workflow_name = declared_workflow_name.strip() if isinstance(declared_workflow_name, str) and declared_workflow_name.strip() else _snake_case_workflow_name(workflow_cls.__name__)
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
    branch_group_consumed_declarations = _collect_branch_group_nested_declaration_ids(workflow_cls)

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
            if id(value) in branch_group_consumed_declarations and not _is_branch_group_declaration(value):
                continue
            if id(value) in seen_simple_declarations:
                continue
            simple_name = getattr(value, "name", None)
            if not isinstance(simple_name, str) or not simple_name:
                raise WorkflowValidationError(f"simple step declaration {attr_name!r} must bind a deterministic name")
            if simple_name in steps_by_name:
                raise WorkflowValidationError(f"duplicate step name {simple_name!r}")
            simple_writes = _lower_simple_writes(value, simple_name)
            verifier_writes = _lower_simple_verifier_writes(value, simple_name)
            simple_seeds.append(
                _SimpleStepSeed(
                    order=attr_order,
                    attr_name=attr_name,
                    declaration=value,
                    name=simple_name,
                    kind=str(getattr(value, "kind", "")),
                    writes=simple_writes,
                    verifier_writes=verifier_writes,
                    output_order=tuple((*simple_writes.keys(), *verifier_writes.keys())),
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

        simple_step_map = {seed.declaration: step for seed, step in lowered_steps}
        entry, transitions = _lower_simple_workflow_graph(
            workflow_cls,
            entry=entry,
            ordered_steps=tuple(sorted(steps, key=lambda step: step_order.get(id(step), step._order))),
            simple_step_map=simple_step_map,
        )
    else:
        entry = _lower_simple_entry(entry, {})
        transitions = _lower_simple_transition_table(transitions, {})

    authored_transitions: dict[Step | str, dict[str, Any]] = {}
    framework_default_transitions_by_step: dict[str, dict[str, Any]] = {}
    runtime_control_routes_by_step: dict[str, tuple[str, ...]] = {}
    if isinstance(transitions, dict):
        authored_transitions = _resolve_named_transition_targets(transitions, steps_by_name)
        framework_default_transitions_by_step, runtime_control_routes_by_step = _lower_control_route_defaults(
            authored_transitions,
            tuple(steps),
        )
        transitions = authored_transitions

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
        workflow_policy=workflow_policy,
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
        authored_transitions=authored_transitions,
        transitions=transitions,
        framework_default_transitions_by_step=framework_default_transitions_by_step,
        runtime_control_routes_by_step=runtime_control_routes_by_step,
    )


def has_start_hook(definition: WorkflowDefinition) -> bool:
    return False


def _validate_simple_authoring_models(workflow_cls: type[Any]) -> None:
    if not _uses_simple_authoring_model(workflow_cls):
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


def _validate_workflow_policy(workflow_cls: type[Any]) -> PolicyInput:
    workflow_policy = getattr(workflow_cls, "policy", None)
    if workflow_policy is None:
        return None
    if not isinstance(workflow_policy, (Policy, ProviderPolicy, ProviderPolicyOverride)):
        raise WorkflowValidationError(f"{workflow_cls.__name__}.policy must be a Policy or core provider policy object")
    return workflow_policy


def _snake_case_workflow_name(name: str) -> str:
    normalized = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    collapsed = re.sub(r"[^a-z0-9_]+", "_", normalized)
    return collapsed.strip("_") or name.lower()


def _is_base_workflow_class(candidate: type[Any]) -> bool:
    return (candidate.__module__, candidate.__name__) in {("botlane.simple", "Workflow"), ("core", "Workflow")}


def _inherits_supported_workflow_base(candidate: type[Any]) -> bool:
    for base in candidate.__mro__[1:]:
        if (base.__module__, base.__name__) in {("botlane.simple", "Workflow"), ("core", "Workflow")}:
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
    return tuple((attr_name, value) for _, _, attr_name, value in sorted(effective.values(), key=lambda item: (item[0], item[1])))


def _iter_visible_workflow_namespace_items(workflow_cls: type[Any]) -> Sequence[tuple[str, object]]:
    return _visible_workflow_namespace_items(workflow_cls)


def _is_simple_step_declaration(value: object) -> bool:
    from botlane.simple import _NamedDeclaration

    return isinstance(value, _NamedDeclaration)


def _is_branch_group_declaration(value: object) -> bool:
    return bool(getattr(value, "kind", None) == "branch_group" and getattr(value, "branch_group_kind", None))


def _collect_branch_group_nested_declaration_ids(workflow_cls: type[Any]) -> set[int]:
    consumed: set[int] = set()
    for _, value in _iter_visible_workflow_namespace_items(workflow_cls):
        if not _is_branch_group_declaration(value):
            continue
        nested = getattr(value, "nested_declarations", None)
        if not callable(nested):
            continue
        for declaration in nested():
            if _is_simple_step_declaration(declaration):
                consumed.add(id(declaration))
    return consumed


def _is_simple_artifact_spec(value: object) -> bool:
    from botlane.simple import ArtifactSpec

    return isinstance(value, ArtifactSpec)


def _is_simple_flow_spec(value: object) -> bool:
    return bool(
        getattr(value, "__botlane_simple_flow_spec__", False)
        or getattr(value, "__auto" + "loop_simple_flow_spec__", False)
    )


def _lower_simple_writes(declaration: object, step_name: str) -> dict[str, Artifact]:
    writes: dict[str, Artifact] = {}
    for artifact_spec in tuple(getattr(declaration, "writes", ()) or ()):
        artifact = _materialize_simple_output(artifact_spec, step_name=step_name)
        if artifact.name is None:
            raise WorkflowValidationError(
                f"simple step {step_name!r} write declarations must define artifact names"
            )
        if artifact.name in writes:
            raise WorkflowValidationError(f"simple step {step_name!r} declares duplicate write artifact {artifact.name!r}")
        writes[artifact.name] = artifact
    return writes


def _lower_simple_verifier_writes(declaration: object, step_name: str) -> dict[str, Artifact]:
    writes: dict[str, Artifact] = {}
    for artifact_spec in tuple(getattr(declaration, "verifier_writes", ()) or ()):
        artifact = _materialize_simple_output(artifact_spec, step_name=step_name)
        if artifact.name is None:
            raise WorkflowValidationError(
                f"simple step {step_name!r} verifier write declarations must define artifact names"
            )
        if artifact.name in writes:
            raise WorkflowValidationError(
                f"simple step {step_name!r} declares duplicate verifier write artifact {artifact.name!r}"
            )
        writes[artifact.name] = artifact
    return writes


def _materialize_simple_output(output: object, *, step_name: str) -> Artifact:
    if isinstance(output, Artifact):
        return output
    if _is_simple_artifact_spec(output):
        return output.materialize(step_name)
    raise WorkflowValidationError(
        f"simple step {step_name!r} output must be an Artifact or botlane.simple artifact helper"
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
        step = _lower_one_simple_seed(
            workflow_cls,
            seed=seed,
            existing_steps=existing_steps,
            simple_seeds=simple_seeds,
            artifact_name_counts=artifact_name_counts,
        )
        lowered.append((seed, step))
    return lowered


def _lower_one_simple_seed(
    workflow_cls: type[Any],
    *,
    seed: _SimpleStepSeed,
    existing_steps: Sequence[Step],
    simple_seeds: Sequence[_SimpleStepSeed],
    artifact_name_counts: Mapping[str, int],
    allow_branch_placeholders: bool = False,
    allow_fan_in_placeholders: bool = False,
    allow_fan_in_helpers: bool = False,
) -> Step:
    declaration = seed.declaration
    if seed.kind == "branch_group":
        return _lower_simple_branch_group_step(
            workflow_cls,
            seed=seed,
            existing_steps=existing_steps,
            simple_seeds=simple_seeds,
            artifact_name_counts=artifact_name_counts,
        )

    explicit_reads = _normalize_simple_input_references(
        getattr(declaration, "reads", ()),
        step_name=seed.name,
        allow_fan_in_helpers=allow_fan_in_helpers,
    )
    prompt_references, inferred_reads = _analyze_simple_prompt_references(
        workflow_cls,
        seed=seed,
        existing_steps=existing_steps,
        simple_seeds=simple_seeds,
        artifact_name_counts=artifact_name_counts,
        allow_branch_placeholders=allow_branch_placeholders,
        allow_fan_in_placeholders=allow_fan_in_placeholders,
    )
    reads = tuple(dict.fromkeys((*explicit_reads, *inferred_reads)))
    requires = tuple(
        dict.fromkeys(
            _normalize_simple_input_references(
                getattr(declaration, "requires", ()),
                step_name=seed.name,
                allow_fan_in_helpers=allow_fan_in_helpers,
            )
        )
    )
    verifier_requires = tuple(
        dict.fromkeys(
            _normalize_simple_input_references(
                getattr(declaration, "verifier_requires", ()),
                step_name=seed.name,
                allow_fan_in_helpers=allow_fan_in_helpers,
            )
        )
    )
    verifier_reads = tuple(
        dict.fromkeys(
            (
                *_normalize_simple_input_references(
                    getattr(declaration, "verifier_reads", ()),
                    step_name=seed.name,
                    allow_fan_in_helpers=allow_fan_in_helpers,
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
        raise WorkflowValidationError(f"simple step {seed.name!r} session must be declared with workflow.Session")
    verifier_session = getattr(declaration, "verifier_session", None)
    if verifier_session is not None and not isinstance(verifier_session, Session):
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
            item_state=step_item_state_model,
            control_routes=getattr(declaration, "control_routes", None),
            provider_policy=getattr(declaration, "policy", None),
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
            control_routes=getattr(declaration, "control_routes", None),
        )
    elif seed.kind in {"review", "produce_verify"}:
        step = ProduceVerifyStep(
            name=seed.name,
            producer=getattr(declaration, "producer_prompt"),
            verifier=getattr(declaration, "verifier_prompt"),
            session=session,
            verifier_session=verifier_session,
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
            before_producer=getattr(declaration, "before_producer", None),
            after_producer=getattr(declaration, "after_producer", None),
            before_verifier=getattr(declaration, "before_verifier", None),
            after_verifier=getattr(declaration, "after_verifier", None),
            item_state=step_item_state_model,
            control_routes=getattr(declaration, "control_routes", None),
            provider_policy=getattr(declaration, "policy", None),
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
            control_routes=getattr(declaration, "control_routes", None),
            provider_policy=getattr(declaration, "policy", None),
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
            control_routes=getattr(declaration, "control_routes", None),
            provider_policy=getattr(declaration, "policy", None),
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
    return step


def _lower_simple_branch_group_step(
    workflow_cls: type[Any],
    *,
    seed: _SimpleStepSeed,
    existing_steps: Sequence[Step],
    simple_seeds: Sequence[_SimpleStepSeed],
    artifact_name_counts: Mapping[str, int],
) -> BranchGroupStep:
    declaration = seed.declaration
    group_name = seed.name
    validate_path_safe_name(kind="name", value=group_name, owner="branch group")
    if getattr(declaration, "fan_in", None) is not None and getattr(declaration, "routes", None):
        raise WorkflowValidationError(
            f"branch group {group_name!r} must not declare composite routes when fan_in is present"
        )
    concurrency = getattr(declaration, "concurrency", None)
    if concurrency is not None and (not isinstance(concurrency, int) or isinstance(concurrency, bool) or concurrency <= 0):
        raise WorkflowValidationError(f"branch group {group_name!r} concurrency must be a positive integer when provided")
    settle = getattr(declaration, "settle", "all")
    if settle not in {"all", "fail_fast"}:
        raise WorkflowValidationError(f"branch group {group_name!r} settle must be 'all' or 'fail_fast'")
    success_routes = tuple(getattr(declaration, "success_routes", ("done", "accepted")))
    if not success_routes or not all(isinstance(route, str) and route.strip() for route in success_routes):
        raise WorkflowValidationError(f"branch group {group_name!r} success_routes must contain non-empty strings")

    lowered_branches: list[BranchStepDeclarationSpec] = []
    if getattr(declaration, "branch_group_kind", None) == "parallel":
        raw_branches = dict(getattr(declaration, "branches", {}))
        if not raw_branches:
            raise WorkflowValidationError(f"branch group {group_name!r} requires a non-empty branches mapping")
        for index, (branch_name, branch_declaration) in enumerate(raw_branches.items()):
            validate_path_safe_name(kind="branch name", value=branch_name, owner=f"branch group {group_name!r}")
            branch_step = _lower_branch_group_internal_step(
                workflow_cls,
                group_name=group_name,
                branch_name=branch_name,
                declaration=branch_declaration,
                existing_steps=existing_steps,
                simple_seeds=simple_seeds,
                artifact_name_counts=artifact_name_counts,
                allow_branch_placeholders=True,
                allow_fan_in_placeholders=False,
                allow_fan_in_helpers=False,
                step_name=_internal_branch_step_name(group_name=group_name, branch_name=branch_name, declaration=branch_declaration),
            )
            validate_branch_step_kind(group_name=group_name, step=branch_step)
            validate_branch_step_session_requirements(group_name=group_name, step=branch_step)
            _validate_branch_group_artifact_templates(
                step=branch_step,
                step_name=branch_step.name,
                allow_branch_placeholders=True,
                allow_fan_in_placeholders=False,
            )
            setattr(branch_step, "_branch_group_name", group_name)
            lowered_branches.append(BranchStepDeclarationSpec(name=branch_name, index=index, input={}, step=branch_step))
    else:
        raw_branches = dict(getattr(declaration, "branches", {}))
        if not raw_branches:
            raise WorkflowValidationError(f"branch group {group_name!r} requires a non-empty branches mapping")
        shared_declaration = getattr(declaration, "step", None)
        for index, (branch_name, branch_input) in enumerate(raw_branches.items()):
            validate_path_safe_name(kind="branch name", value=branch_name, owner=f"branch group {group_name!r}")
            ensure_json_serializable(branch_input, label=f"branch group {group_name!r} branch {branch_name!r} input")
            branch_step = _lower_branch_group_internal_step(
                workflow_cls,
                group_name=group_name,
                branch_name=branch_name,
                declaration=shared_declaration,
                existing_steps=existing_steps,
                simple_seeds=simple_seeds,
                artifact_name_counts=artifact_name_counts,
                allow_branch_placeholders=True,
                allow_fan_in_placeholders=False,
                allow_fan_in_helpers=False,
                step_name=_internal_fan_out_step_name(group_name=group_name, declaration=shared_declaration),
            )
            validate_branch_step_kind(group_name=group_name, step=branch_step)
            validate_branch_step_session_requirements(group_name=group_name, step=branch_step)
            _validate_branch_group_artifact_templates(
                step=branch_step,
                step_name=branch_step.name,
                allow_branch_placeholders=True,
                allow_fan_in_placeholders=False,
            )
            setattr(branch_step, "_branch_group_name", group_name)
            lowered_branches.append(BranchStepDeclarationSpec(name=branch_name, index=index, input=branch_input, step=branch_step))

    fan_in_declaration = getattr(declaration, "fan_in", None)
    fan_in_step: Step | None = None
    composite_route_tags: tuple[str, ...]
    default_chain_route = getattr(declaration, "default_chain_route", "done")
    rework_chain_route = getattr(declaration, "rework_chain_route", None)
    if fan_in_declaration is not None:
        fan_in_step = _lower_branch_group_internal_step(
            workflow_cls,
            group_name=group_name,
            branch_name="fan_in",
            declaration=fan_in_declaration,
            existing_steps=existing_steps,
            simple_seeds=simple_seeds,
            artifact_name_counts=artifact_name_counts,
            allow_branch_placeholders=False,
            allow_fan_in_placeholders=True,
            allow_fan_in_helpers=True,
            step_name=_internal_fan_in_step_name(group_name=group_name, declaration=fan_in_declaration),
        )
        validate_fan_in_step_kind(group_name=group_name, step=fan_in_step)
        validate_fan_in_helper_placement(
            (*fan_in_step.reads, *fan_in_step.requires, *getattr(fan_in_step, "verifier_requires", ())),
            group_name=group_name,
            step_name=fan_in_step.name,
            allow_helpers=True,
        )
        _validate_branch_group_artifact_templates(
            step=fan_in_step,
            step_name=fan_in_step.name,
            allow_branch_placeholders=False,
            allow_fan_in_placeholders=True,
        )
        setattr(fan_in_step, "_branch_group_name", group_name)
        composite_route_tags = declared_internal_route_tags(fan_in_declaration, step=fan_in_step)
        if isinstance(fan_in_step, ProduceVerifyStep):
            default_chain_route = "accepted"
            rework_chain_route = "needs_rework"
        else:
            default_chain_route = "done"
            rework_chain_route = None
    else:
        composite_route_tags = ("done", "partial", "question", "failed")

    branch_group = build_branch_group_declaration_spec(
        name=group_name,
        kind=str(getattr(declaration, "branch_group_kind")),
        branches=tuple(lowered_branches),
        concurrency=concurrency,
        settle=settle,
        success_routes=tuple(dict.fromkeys(route.strip() for route in success_routes)),
        outcome=getattr(declaration, "outcome", None),
        fan_in_step=fan_in_step,
        composite_route_tags=composite_route_tags,
        default_chain_route=default_chain_route,
        rework_chain_route=rework_chain_route,
    )
    step = BranchGroupStep(name=group_name, branch_group=branch_group)
    setattr(step, "simple_declaration", declaration)
    setattr(step, "simple_prompt_references", ())
    setattr(step, "state_model", build_step_state_model(None, step_name=group_name, step_kind=seed.kind, module_name=workflow_cls.__module__))
    setattr(step, "step_item_state_model", None)
    setattr(step, "composite_route_tags", composite_route_tags)
    setattr(step, "default_chain_route", default_chain_route)
    setattr(step, "rework_chain_route", rework_chain_route)
    return step


def _lower_branch_group_internal_step(
    workflow_cls: type[Any],
    *,
    group_name: str,
    branch_name: str,
    declaration: object,
    existing_steps: Sequence[Step],
    simple_seeds: Sequence[_SimpleStepSeed],
    artifact_name_counts: Mapping[str, int],
    allow_branch_placeholders: bool,
    allow_fan_in_placeholders: bool,
    allow_fan_in_helpers: bool,
    step_name: str,
) -> Step:
    if not _is_simple_step_declaration(declaration):
        raise WorkflowValidationError(
            f"branch group {group_name!r} branch {branch_name!r} must reference an authored step declaration"
        )
    nested_seed = _SimpleStepSeed(
        order=-1,
        attr_name=step_name,
        declaration=declaration,
        name=step_name,
        kind=str(getattr(declaration, "kind", "")),
        writes=_lower_simple_writes(declaration, step_name),
        verifier_writes=_lower_simple_verifier_writes(declaration, step_name),
        output_order=(),
    )
    return _lower_one_simple_seed(
        workflow_cls,
        seed=nested_seed,
        existing_steps=existing_steps,
        simple_seeds=simple_seeds,
        artifact_name_counts=artifact_name_counts,
        allow_branch_placeholders=allow_branch_placeholders,
        allow_fan_in_placeholders=allow_fan_in_placeholders,
        allow_fan_in_helpers=allow_fan_in_helpers,
    )


def _internal_branch_step_name(*, group_name: str, branch_name: str, declaration: object) -> str:
    authored = getattr(declaration, "name", None)
    if isinstance(authored, str) and authored.strip():
        return authored
    return f"{group_name}__{branch_name}"


def _internal_fan_out_step_name(*, group_name: str, declaration: object) -> str:
    authored = getattr(declaration, "name", None)
    if isinstance(authored, str) and authored.strip():
        return authored
    return f"{group_name}__branch"


def _internal_fan_in_step_name(*, group_name: str, declaration: object) -> str:
    authored = getattr(declaration, "name", None)
    if isinstance(authored, str) and authored.strip():
        return authored
    return f"{group_name}__fan_in"


def _validate_branch_group_artifact_templates(
    *,
    step: Step,
    step_name: str,
    allow_branch_placeholders: bool,
    allow_fan_in_placeholders: bool,
) -> None:
    for artifact in step.writes.values():
        template = getattr(artifact, "template", None)
        if not isinstance(template, str) or "{" not in template:
            continue
        for placeholder in _PROMPT_PLACEHOLDER_RE.findall(template):
            reference = placeholder.strip()
            if not reference:
                continue
            if validate_branch_placeholder_reference(
                reference,
                step_name=step_name,
                allowed=allow_branch_placeholders,
            ):
                continue
            validate_fan_in_placeholder_reference(
                reference,
                step_name=step_name,
                allowed=allow_fan_in_placeholders,
            )


def _normalize_simple_state_model(raw_state: object, *, step_name: str, step_kind: str, module_name: str) -> type[BaseModel]:
    return build_step_state_model(raw_state, step_name=step_name, step_kind=step_kind, module_name=module_name)


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
        raise WorkflowValidationError(f"simple step {step_name!r} item_state requires scope=... on the same step")
    return build_step_item_state_model(raw_state, step_name=step_name, step_kind=step_kind, module_name=module_name)


def _normalize_simple_input_references(
    references: Sequence[object],
    *,
    step_name: str,
    allow_fan_in_helpers: bool = False,
) -> tuple[object, ...]:
    from .branch_groups.models import FanInHelperReference

    normalized: list[object] = []
    for reference in references:
        if isinstance(reference, Artifact):
            normalized.append(reference)
            continue
        if allow_fan_in_helpers and isinstance(reference, FanInHelperReference):
            normalized.append(reference)
            continue
        if isinstance(reference, FanInHelperReference):
            raise WorkflowValidationError(
                f"simple step {step_name!r} uses {reference}, which is only valid inside fan-in"
            )
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
    allow_branch_placeholders: bool = False,
    allow_fan_in_placeholders: bool = False,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    prompts: list[object] = []
    if seed.kind in {"llm", "operation", "step"}:
        prompts.append(getattr(seed.declaration, "prompt", None))
    elif seed.kind in {"review", "produce_verify"}:
        prompts.extend((getattr(seed.declaration, "producer_prompt", None), getattr(seed.declaration, "verifier_prompt", None)))
    else:
        return (), ()
    state_fields = _model_field_names(effective_state_model(workflow_cls, fallback_model=_EmptyWorkflowState))
    parameter_fields = _model_field_names(effective_parameters_model(workflow_cls))
    input_fields = _model_field_names(getattr(workflow_cls, "Input", None))
    step_state_fields = _known_simple_step_state_fields(workflow_cls=workflow_cls, existing_steps=existing_steps, simple_seeds=simple_seeds)
    worklist_item_state_fields = _known_worklist_item_state_fields(workflow_cls=workflow_cls)
    step_item_state_fields = _known_simple_step_item_state_fields(workflow_cls=workflow_cls, existing_steps=existing_steps, simple_seeds=simple_seeds)
    scope_name = _resolve_worklist_name(getattr(seed.declaration, "scope", None)) if getattr(seed.declaration, "scope", None) is not None else None
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
                allow_branch_placeholders=allow_branch_placeholders,
                allow_fan_in_placeholders=allow_fan_in_placeholders,
            )
            if inferred_artifact is not None:
                inferred.append(inferred_artifact)
    return tuple(dict.fromkeys(references)), tuple(dict.fromkeys(inferred))


def _known_simple_step_outputs(*, existing_steps: Sequence[Step], simple_seeds: Sequence[_SimpleStepSeed]) -> dict[str, frozenset[str]]:
    step_outputs: dict[str, frozenset[str]] = {
        step.name: frozenset(artifact.name for artifact in step.writes.values() if artifact.name is not None) for step in existing_steps
    }
    for seed in simple_seeds:
        step_outputs[seed.name] = frozenset(seed.writes.keys())
    return step_outputs


def _known_simple_step_state_fields(*, workflow_cls: type[Any], existing_steps: Sequence[Step], simple_seeds: Sequence[_SimpleStepSeed]) -> dict[str, frozenset[str]]:
    step_state_fields: dict[str, frozenset[str]] = {
        step.name: frozenset(
            getattr(
                getattr(step, "state_model", None)
                or build_step_state_model(None, step_name=step.name, step_kind=step.kind, module_name=workflow_cls.__module__),
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


def _known_worklist_item_state_fields(*, workflow_cls: type[Any]) -> dict[str, frozenset[str]]:
    fields: dict[str, frozenset[str]] = {}
    for _, value in _iter_visible_workflow_namespace_items(workflow_cls):
        if not isinstance(value, Worklist):
            continue
        fields[value.name] = frozenset(value.runtime_item_state_model.model_fields.keys())
    return fields


def _known_simple_step_item_state_fields(*, workflow_cls: type[Any], existing_steps: Sequence[Step], simple_seeds: Sequence[_SimpleStepSeed]) -> dict[str, frozenset[str]]:
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
        step_item_state_fields[seed.name] = frozenset(() if model is None else model.model_fields.keys())
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
    allow_branch_placeholders: bool = False,
    allow_fan_in_placeholders: bool = False,
) -> str | None:
    if validate_branch_placeholder_reference(
        reference,
        step_name=step_name,
        allowed=allow_branch_placeholders,
    ):
        return None
    if validate_fan_in_placeholder_reference(
        reference,
        step_name=step_name,
        allowed=allow_fan_in_placeholders,
    ):
        return None
    if reference == "message":
        raise WorkflowValidationError(
            f"simple step {step_name!r} prompt placeholder {{message}} is unknown; use {{ctx.message}}"
        )
    if reference == "ctx":
        raise WorkflowValidationError(
            f"simple step {step_name!r} prompt placeholder {{ctx}} must qualify a runtime context field"
        )
    if reference.startswith("ctx."):
        return _validate_ctx_prompt_reference(
            reference,
            step_name=step_name,
            state_fields=state_fields,
            parameter_fields=parameter_fields,
            input_fields=input_fields,
        )
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
        if second == "message" and not rest:
            return None
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
        if scope_name is None:
            raise WorkflowValidationError(
                f"simple step {step_name!r} prompt placeholder {{{reference}}} requires scope=... on the same step"
            )
        if second in {"id", "title", "status", "dir_key"} and not rest:
            return None
        if second == "payload":
            return None
        if second != "state" or not rest:
            raise WorkflowValidationError(
                f"simple step {step_name!r} prompt placeholder {{{reference}}} must use item.id, item.title, "
                "item.status, item.dir_key, item.payload, item.payload.<path>, or item.state.<field>"
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
    if root == "worklist":
        worklist_name = second
        if worklist_name not in worklist_item_state_fields:
            raise WorkflowValidationError(
                f"simple step {step_name!r} prompt placeholder {{{reference}}} references unknown worklist {worklist_name!r}"
            )
        if not rest:
            raise WorkflowValidationError(
                f"simple step {step_name!r} prompt placeholder {{{reference}}} must qualify a worklist runtime field"
            )
        worklist_field, *worklist_rest = rest
        if worklist_field == "current":
            if not worklist_rest:
                raise WorkflowValidationError(
                    f"simple step {step_name!r} prompt placeholder {{{reference}}} must qualify a current work item field"
                )
            current_field, *current_rest = worklist_rest
            if current_field in {"id", "title", "status", "dir_key"} and not current_rest:
                return None
            if current_field == "payload":
                return None
            raise WorkflowValidationError(
                f"simple step {step_name!r} prompt placeholder {{{reference}}} must use "
                "worklist.<name>.current.id, .title, .status, .dir_key, .payload, or .payload.<path>"
            )
        if worklist_field in {"item_ids", "current_index", "is_exhausted"} and not worklist_rest:
            return None
        raise WorkflowValidationError(
            f"simple step {step_name!r} prompt placeholder {{{reference}}} must use "
            "worklist.<name>.current..., worklist.<name>.item_ids, worklist.<name>.current_index, "
            "or worklist.<name>.is_exhausted"
        )
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
            allow_branch_placeholders=allow_branch_placeholders,
            allow_fan_in_placeholders=allow_fan_in_placeholders,
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


def _validate_ctx_prompt_reference(
    reference: str,
    *,
    step_name: str,
    state_fields: frozenset[str],
    parameter_fields: frozenset[str],
    input_fields: frozenset[str],
) -> None:
    model_labels = {
        "input": "Input",
        "state": "State",
        "params": "Params",
    }
    qualifier_labels = {
        "request": "request",
        "input": "input",
        "state": "state",
        "params": "params",
    }
    parts = tuple(reference.split("."))
    if len(parts) == 2 and parts[1] in qualifier_labels:
        label = qualifier_labels[parts[1]]
        raise WorkflowValidationError(
            f"simple step {step_name!r} prompt placeholder {{{reference}}} must qualify a {label} field"
        )

    def _is_safe_field_candidate(segment: str) -> bool:
        forbidden_characters = {'"', "'", "(", ")", "[", "]"}
        return (
            bool(segment)
            and not segment.startswith("_")
            and "__" not in segment
            and not any(character.isspace() for character in segment)
            and not any(character in forbidden_characters for character in segment)
        )

    try:
        validated = validate_safe_ctx_reference(reference)
    except ValueError as exc:
        if len(parts) == 3 and parts[1] in CTX_MODEL_ROOTS and _is_safe_field_candidate(parts[2]):
            field_name = parts[2]
            available_fields = {
                "input": input_fields,
                "state": state_fields,
                "params": parameter_fields,
            }[parts[1]]
            if field_name not in available_fields:
                label = model_labels[parts[1]]
                raise WorkflowValidationError(
                    f"simple step {step_name!r} prompt placeholder {{{reference}}} references unknown {label} field {field_name!r}"
                ) from exc
        raise WorkflowValidationError(
            f"simple step {step_name!r} prompt placeholder {{{reference}}} is not a supported safe dotted path"
        ) from exc

    root_name = validated[1]
    if root_name in CTX_SCALAR_FIELDS or root_name in CTX_NESTED_FIELDS:
        return None
    field_name = validated[2]
    if root_name == "input" and field_name == "message":
        return None
    available_fields = {
        "input": input_fields,
        "state": state_fields,
        "params": parameter_fields,
    }[root_name]
    if field_name not in available_fields:
        label = model_labels[root_name]
        raise WorkflowValidationError(
            f"simple step {step_name!r} prompt placeholder {{{reference}}} references unknown {label} field {field_name!r}"
        )
    return None


def _model_field_names(model_cls: object) -> frozenset[str]:
    if not inspect.isclass(model_cls) or not issubclass(model_cls, BaseModel):
        return frozenset()
    return frozenset(getattr(model_cls, "model_fields", {}).keys())


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


def _infer_simple_entry(flow: object, steps: Sequence[Step], simple_step_map: Mapping[object, Step]) -> Step | None:
    if flow is not None and _is_simple_flow_spec(flow):
        for item in flow.items:
            source = item[0] if isinstance(item, tuple) else item
            lowered = _lower_simple_target(source, simple_step_map)
            if isinstance(lowered, Step):
                return lowered
    return steps[0] if steps else None


def _lower_simple_transition_table(transitions: object, simple_step_map: Mapping[object, Step]) -> dict[Step | str, dict[str, object]] | object | None:
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
        lowered[lowered_source] = {route_name: _lower_simple_destination(destination, simple_step_map) for route_name, destination in route_map.items()}
    return lowered


def _lower_simple_declared_routes(simple_step_map: Mapping[object, Step]) -> dict[Step | str, dict[str, object]]:
    lowered: dict[Step | str, dict[str, object]] = {}
    for declaration, step in simple_step_map.items():
        raw_routes, implicit_routes = _simple_declaration_route_sources(declaration)
        merged_routes: dict[str, object] = {}
        if isinstance(raw_routes, dict):
            merged_routes.update(raw_routes)
        if isinstance(implicit_routes, dict):
            merged_routes.update(implicit_routes)
        if not merged_routes:
            continue
        lowered[step] = {
            route_name: _lower_simple_destination(destination, simple_step_map)
            for route_name, destination in merged_routes.items()
        }
    return lowered


def _simple_declaration_route_sources(declaration: object) -> tuple[object | None, object | None]:
    if _is_branch_group_declaration(declaration) and getattr(declaration, "fan_in", None) is not None:
        fan_in = getattr(declaration, "fan_in", None)
        return getattr(fan_in, "routes", None), getattr(fan_in, "implicit_routes", None)
    return getattr(declaration, "routes", None), getattr(declaration, "implicit_routes", None)


def _lower_simple_default_routes(ordered_steps: Sequence[Step]) -> dict[Step | str, dict[str, object]]:
    lowered: dict[Step | str, dict[str, object]] = {}
    for index, step in enumerate(ordered_steps):
        declaration = getattr(step, "simple_declaration", None)
        if declaration is None:
            continue
        declared_routes, declared_implicit_routes = _simple_declaration_route_sources(declaration)
        has_declared_routes = bool(declared_routes) or bool(declared_implicit_routes)
        step_routes = lowered.setdefault(step, {})
        if isinstance(step, ProduceVerifyStep):
            if not has_declared_routes:
                next_target: object = ordered_steps[index + 1] if index + 1 < len(ordered_steps) else FINISH
                step_routes.setdefault(getattr(step, "simple_accept_route", "accepted"), next_target)
                step_routes.setdefault(getattr(step, "simple_rework_route", "needs_rework"), step)
            continue
        if isinstance(step, ChildWorkflowStep):
            if not has_declared_routes:
                step_routes.setdefault("done", ordered_steps[index + 1] if index + 1 < len(ordered_steps) else FINISH)
            continue
        if isinstance(step, BranchGroupStep):
            if getattr(declaration, "fan_in", None) is None:
                next_target = ordered_steps[index + 1] if index + 1 < len(ordered_steps) else FINISH
                # Mechanical-outcome composites always expose `done` and `partial`;
                # implicit control routes must not suppress those destinations.
                step_routes.setdefault(getattr(step, "default_chain_route", "done"), next_target)
                step_routes.setdefault("partial", next_target)
                continue
            if not has_declared_routes:
                next_target: object = ordered_steps[index + 1] if index + 1 < len(ordered_steps) else FINISH
                step_routes.setdefault(getattr(step, "default_chain_route", "done"), next_target)
                rework_route = getattr(step, "rework_chain_route", None)
                if isinstance(rework_route, str) and rework_route:
                    step_routes.setdefault(rework_route, step)
            continue
        if isinstance(step, PythonStep):
            if not has_declared_routes:
                step_routes.setdefault("done", ordered_steps[index + 1] if index + 1 < len(ordered_steps) else FINISH)
            continue
        if has_declared_routes:
            continue
        step_routes.setdefault("done", ordered_steps[index + 1] if index + 1 < len(ordered_steps) else FINISH)
    return lowered


def _default_completion_route_for_step(step: object) -> str:
    if isinstance(step, ProduceVerifyStep):
        return str(getattr(step, "simple_accept_route", "accepted"))
    if isinstance(step, BranchGroupStep):
        return str(getattr(step, "default_chain_route", "done"))
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
        return _replace_route(destination, target=target)
    return _lower_simple_target(destination, simple_step_map)


def _resolve_named_entry(entry: object, steps_by_name: Mapping[str, Step]) -> Step | None | object:
    if entry is None or isinstance(entry, Step):
        return entry
    if isinstance(entry, str):
        return steps_by_name.get(entry, entry)
    return entry


def _order_steps_from_entry(steps: Sequence[Step], *, entry: Step | None | object, transitions: Mapping[Step | str, Mapping[str, object]]) -> tuple[Step, ...]:
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


def _resolve_named_transition_targets(transitions: Mapping[Step | str, Mapping[str, object]], steps_by_name: Mapping[str, Step]) -> dict[Step | str, dict[str, object]]:
    resolved: dict[Step | str, dict[str, object]] = {}
    for source, route_map in transitions.items():
        resolved_source = _resolve_transition_source(source, steps_by_name)
        resolved[resolved_source] = {
            route_name: _resolve_transition_destination(destination, source=resolved_source, steps_by_name=steps_by_name)
            for route_name, destination in route_map.items()
        }
    return resolved


def _resolve_transition_source(source: Step | str, steps_by_name: Mapping[str, Step]) -> Step | str:
    if source == GLOBAL or isinstance(source, Step):
        return source
    if isinstance(source, str):
        return steps_by_name.get(source, source)
    return source


def _resolve_transition_destination(destination: object, *, source: Step | str, steps_by_name: Mapping[str, Step]) -> object:
    if isinstance(destination, Route):
        if destination.is_disabled:
            return destination
        target = _resolve_transition_destination(destination.target, source=source, steps_by_name=steps_by_name)
        if target is destination.target:
            return destination
        return _replace_route(destination, target=target)
    if destination == SELF:
        return source if isinstance(source, Step) else destination
    if isinstance(destination, str) and destination not in {FINISH, AWAIT_INPUT, FAIL}:
        return steps_by_name.get(destination, destination)
    return destination


def _merge_transition_tables(base: Mapping[Step | str, Mapping[str, object]], extra: Mapping[Step | str, Mapping[str, object]], *, prefer_existing: bool = False) -> dict[Step | str, dict[str, object]]:
    merged: dict[Step | str, dict[str, object]] = {source: dict(route_map) for source, route_map in base.items()}
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


def _lower_control_route_defaults(
    transitions: Mapping[Step | str, Mapping[str, object]],
    steps: Sequence[Step],
) -> tuple[dict[Step | str, dict[str, object]], dict[str, tuple[str, ...]]]:
    framework_defaults_by_step: dict[str, dict[str, object]] = {}
    runtime_control_routes_by_step: dict[str, tuple[str, ...]] = {}
    for step in steps:
        default_routes: dict[str, object] = {}
        runtime_routes: list[str] = []
        question_mode = getattr(getattr(step, "control_routes", None), "question", "never")
        if question_mode != "never":
            provider_visibility = "always" if question_mode == "always" else "interactive_only"
            default_routes["question"] = Route.question(provider_visibility=provider_visibility)
            runtime_routes.append("question")
        framework_defaults_by_step[step.name] = default_routes
        runtime_control_routes_by_step[step.name] = tuple(runtime_routes)
    return framework_defaults_by_step, runtime_control_routes_by_step


def _route_signature(destination: object) -> tuple[object, str | None, tuple[str, ...], str | None, object | None]:
    route = normalize_route_spec(destination)
    target = route.target.name if isinstance(route.target, Step) else route.target
    return (
        target,
        route.summary,
        None if route.required_writes is None else tuple(route.required_writes),
        route.handoff,
        route.on_taken,
        route.provider_visibility,
        route.payload_schema_mode,
        route.preset_kind,
        route.is_disabled,
    )


def _resolve_worklist_name(worklist: object | str) -> str:
    return worklist if isinstance(worklist, str) else getattr(worklist, "name", None)


def _uses_simple_authoring_model(workflow_cls: type[Any]) -> bool:
    return any((base.__module__, base.__name__) == ("botlane.simple", "Workflow") for base in workflow_cls.__mro__)


__all__ = [
    "RESERVED_STEP_PSEUDO_FIELDS",
    "SIMPLE_CONTEXT_BARE_NAMES",
    "WorkflowDefinition",
    "WorkflowMeta",
    "describe_workflow_class",
    "get_workflow_definition",
    "has_start_hook",
    "is_workflow_class",
]
