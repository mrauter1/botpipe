"""Stable runtime context surface."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
import inspect
from typing import TYPE_CHECKING, Any, Callable, Generic, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from .errors import WorkflowExecutionError
from .mappings import normalize_mapping
from .primitives import Event
from .sessions import Continuity, DEFAULT_SESSION_NAME, SessionKey, derive_session_key
from .stores.protocols import SessionBinding, is_run_key_bound_to_slot
from .steps import Session

if TYPE_CHECKING:
    from .artifacts import ArtifactHandle, ResolvedArtifacts
    from .compiler import CompiledStep
    from .history import HistoryReader
    from .stores.protocols import SessionStore
    from .worklists import Selection, WorkItem, Worklist


OutputT = TypeVar("OutputT")


@dataclass(frozen=True, slots=True)
class ChildWorkflowResult(Generic[OutputT]):
    """Structured result returned by ``ctx.invoke_workflow(...)``."""

    workflow_name: str
    run_id: str
    terminal: str
    status: str
    last_event: Event | None
    output_metadata: dict[str, Any]
    output_artifacts: dict[str, Path]
    task_folder: Path
    workflow_folder: Path
    run_folder: Path
    package_folder: Path
    request_file: Path
    run_meta_file: Path
    events_file: Path
    checkpoint_file: Path
    sessions_dir: Path
    trace_file: Path
    raw_dir: Path
    parent_file: Path
    output: OutputT | None = None
    artifacts: Mapping[str, Path] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    checkpoint: Any | None = None

    def __post_init__(self) -> None:
        if not self.artifacts:
            object.__setattr__(self, "artifacts", dict(self.output_artifacts))
        else:
            object.__setattr__(self, "artifacts", dict(self.artifacts))
        object.__setattr__(self, "metadata", dict(self.metadata))


class EmptyParameters(BaseModel):
    """Immutable fallback used when a workflow does not declare Parameters."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)


class NamespaceProxy:
    """Attribute view over a mapping or object."""

    def __init__(self, source: Mapping[str, Any] | Any | None = None) -> None:
        object.__setattr__(self, "_source", {} if source is None else source)

    def __getattr__(self, item: str) -> Any:
        source = object.__getattribute__(self, "_source")
        if isinstance(source, Mapping):
            if item not in source:
                raise AttributeError(item)
            value = source[item]
        else:
            value = getattr(source, item)
        if isinstance(value, Mapping):
            return NamespaceProxy(value)
        return value

    def __setattr__(self, item: str, value: Any) -> None:
        source = object.__getattribute__(self, "_source")
        if not isinstance(source, dict):
            raise AttributeError(item)
        source[item] = value


class MutableStateProxy(NamespaceProxy):
    """Mutable attribute view over a plain dictionary."""

    def __init__(self, source: dict[str, Any] | None = None) -> None:
        super().__init__({} if source is None else source)

    def __getattr__(self, item: str) -> Any:
        source = object.__getattribute__(self, "_source")
        if item not in source:
            raise AttributeError(item)
        value = source[item]
        if isinstance(value, dict):
            return MutableStateProxy(value)
        return value

    def snapshot(self) -> dict[str, Any]:
        return dict(object.__getattribute__(self, "_source"))


_RUNTIME_STATE_FIELDS = frozenset({"visits", "last_route", "last_reason", "rework_count", "replan_count"})


class StateView:
    """Attribute view that keeps runtime-owned fields read-only."""

    def __init__(self, source: BaseModel | dict[str, Any]) -> None:
        object.__setattr__(self, "_source", source)

    def __getattr__(self, item: str) -> Any:
        source = object.__getattribute__(self, "_source")
        if isinstance(source, BaseModel):
            value = getattr(source, item)
        else:
            if item not in source:
                raise AttributeError(item)
            value = source[item]
        if isinstance(value, dict):
            return MutableStateProxy(value)
        return value

    def __setattr__(self, item: str, value: Any) -> None:
        if item in _RUNTIME_STATE_FIELDS:
            raise AttributeError(f"{item} is runtime-owned and read-only")
        source = object.__getattribute__(self, "_source")
        if isinstance(source, BaseModel):
            setattr(source, item, value)
            return
        source[item] = value

    def __repr__(self) -> str:
        return f"StateView({object.__getattribute__(self, '_source')!r})"


class Context:
    """Runtime context exposed to workflow hooks and system handlers."""

    def __init__(
        self,
        *,
        root: Path | None = None,
        task_id: str,
        run_id: str,
        workflow_name: str,
        task_folder: Path,
        workflow_folder: Path,
        run_folder: Path,
        package_folder: Path,
        state: BaseModel,
        session_store: SessionStore,
        session_definitions: Mapping[str, Session] | None = None,
        worklists: Mapping[str, "Worklist[Any]"] | None = None,
        selections: dict[str, "Selection[Any]"] | None = None,
        active_worklist: str | None = None,
        params: BaseModel | None = None,
        workflow_params: Mapping[str, Any] | None = None,
        workflow_input: BaseModel | None = None,
        workflow_invoker: Callable[..., Any] | None = None,
        answer: str | None = None,
        input_response: Any | None = None,
        step_name: str | None = None,
        default_session_name: str = DEFAULT_SESSION_NAME,
        artifacts: "ResolvedArtifacts | None" = None,
        values: Mapping[str, Any] | None = None,
        route: Mapping[str, Any] | Any | None = None,
        outcome: Mapping[str, Any] | Any | None = None,
        meta: Mapping[str, Any] | Any | None = None,
        step_state_store: BaseModel | dict[str, Any] | None = None,
        item_state_store: BaseModel | dict[str, Any] | None = None,
        step_item_state_store: BaseModel | dict[str, Any] | None = None,
    ) -> None:
        self.root = _resolve_context_root(root=root, task_folder=task_folder, package_folder=package_folder)
        self.task_id = task_id
        self.run_id = run_id
        self.workflow_name = workflow_name
        self.task_folder = task_folder
        self.workflow_folder = workflow_folder
        self.run_folder = run_folder
        self.package_folder = package_folder
        self._state = state
        self._session_store = session_store
        self._session_definitions = normalize_mapping(session_definitions)
        self._worklists = normalize_mapping(worklists)
        self._selections = selections if selections is not None else {}
        self._active_worklist = active_worklist
        self._params = params if params is not None else EmptyParameters()
        self._workflow_params = normalize_mapping(workflow_params)
        self._input = workflow_input
        self._workflow_invoker = workflow_invoker
        self._answer = answer
        self._input_response = input_response
        self._step_name = step_name
        self._default_session_name = default_session_name
        self._artifacts = artifacts
        self._values = normalize_mapping(values)
        self._route = route
        self._event = None
        self._outcome = outcome
        self._meta = meta
        self._step_state = step_state_store if step_state_store is not None else {}
        self._item_state = item_state_store
        self._step_item_state = step_item_state_store
        self._history: HistoryReader | None = None
        self._worklist_items_cache: dict[str, tuple[Any, ...]] = {}

    @property
    def state(self) -> BaseModel:
        return self._state

    @property
    def answer(self) -> str | None:
        return self._answer

    @property
    def input_response(self) -> Any | None:
        return self._input_response

    @property
    def params(self) -> BaseModel:
        return self._params

    @property
    def workflow_params(self) -> dict[str, Any]:
        return dict(self._workflow_params)

    @property
    def input(self) -> BaseModel | None:
        return self._input

    @property
    def artifacts(self) -> "ResolvedArtifacts | None":
        return self._artifacts

    @property
    def values(self) -> NamespaceProxy:
        return NamespaceProxy(self._values)

    @property
    def route(self) -> NamespaceProxy | None:
        if self._route is None:
            return None
        return NamespaceProxy(self._route)

    @property
    def outcome(self) -> NamespaceProxy | None:
        if self._outcome is None:
            return None
        return NamespaceProxy(self._outcome)

    @property
    def event(self) -> NamespaceProxy | None:
        if self._event is None:
            return None
        return NamespaceProxy(self._event)

    @property
    def run(self) -> NamespaceProxy:
        return NamespaceProxy({"id": self.run_id, "folder": self.run_folder})

    @property
    def workflow(self) -> NamespaceProxy:
        return NamespaceProxy({"name": self.workflow_name, "folder": self.workflow_folder})

    @property
    def meta(self) -> NamespaceProxy:
        return NamespaceProxy(self._meta or {})

    @property
    def history(self) -> "HistoryReader":
        if self._history is None:
            from .history import HistoryReader

            self._history = HistoryReader(self.run_folder)
        return self._history

    @property
    def step_state(self) -> StateView:
        return StateView(self._step_state)

    @property
    def item_state(self) -> BaseModel:
        if isinstance(self._item_state, BaseModel):
            return self._item_state
        raise WorkflowExecutionError(
            "item_state is not part of the canonical public surface for this step; declare an explicit model-backed item state before using it"
        )

    @property
    def step_item_state(self) -> StateView:
        if isinstance(self._step_item_state, (BaseModel, dict)):
            return StateView(self._step_item_state)
        raise WorkflowExecutionError(
            "step_item_state is not part of the canonical public surface for this step; declare an explicit model-backed step-item state before using it"
        )

    @property
    def session(self) -> SessionBinding | None:
        return self.get_session(self._default_session_name)

    def selection(self, worklist: "Worklist[Any] | str") -> "Selection[Any]":
        worklist_name = self._worklist_name(worklist)
        try:
            return self._selections[worklist_name]
        except KeyError as exc:
            raise WorkflowExecutionError(f"unknown worklist selection {worklist_name!r}") from exc

    def current(self, worklist: "Worklist[Any] | str") -> "WorkItem[Any] | None":
        return self.selection(worklist).current

    @property
    def item(self) -> "WorkItem[Any] | None":
        if self._active_worklist is None:
            return None
        selection = self._selections.get(self._active_worklist)
        return None if selection is None else selection.current

    def open_session(
        self,
        ref: Session | str = DEFAULT_SESSION_NAME,
        scope: str | None = None,
        *,
        continuity: Continuity | None = None,
        key: str | None = None,
    ) -> SessionBinding:
        session_key = self._session_key_for(ref, scope=scope, continuity=continuity, key=key)
        return self._session_store.open(session_key)

    def get_session(
        self,
        ref: Session | str = DEFAULT_SESSION_NAME,
        scope: str | None = None,
        *,
        continuity: Continuity | None = None,
        key: str | None = None,
    ) -> SessionBinding | None:
        session_key = self._session_key_for(
            ref,
            scope=scope,
            continuity=continuity,
            key=key,
            prefer_active=scope is None and continuity is None and key is None,
        )
        return self._session_store.get(session_key)

    def _session_key_for(
        self,
        ref: Session | str,
        *,
        scope: str | None,
        continuity: Continuity | None,
        key: str | None,
        prefer_active: bool = False,
    ) -> SessionKey:
        if key is not None and scope is not None:
            raise WorkflowExecutionError("ctx.open_session(..., key=...) and scope=... are mutually exclusive")
        slot = _session_name(ref)
        if key is not None:
            return SessionKey(slot=slot, domain="explicit_key", value=key)
        if scope is not None:
            return SessionKey(slot=slot, domain="explicit_scope", value=scope)
        if prefer_active:
            active_key = self._session_store.snapshot().active_keys_by_slot.get(slot)
            if active_key is not None:
                return active_key
        resolved_continuity = continuity or self._continuity_for(ref, slot)
        if resolved_continuity.kind == "run":
            active_key = self._session_store.snapshot().active_keys_by_slot.get(slot)
            if is_run_key_bound_to_slot(active_key, slot=slot):
                return active_key
        return derive_session_key(slot, resolved_continuity, self)

    def reset_global_session(self) -> SessionBinding:
        key = SessionKey(slot=self._default_session_name, domain="fresh", value=uuid4().hex)
        return self._session_store.open(key)

    def set_global_session(self, value: SessionBinding | str | None) -> SessionBinding:
        if value is None:
            return self.reset_global_session()
        if isinstance(value, SessionBinding):
            return self._session_store.upsert(value, activate=True)
        active = self.get_session(self._default_session_name)
        key = active.key if active is not None else SessionKey(
            slot=self._default_session_name,
            domain="fresh",
            value=uuid4().hex,
        )
        binding = SessionBinding(key=key, session_id=value)
        return self._session_store.upsert(binding, activate=True)

    def read(self, target: str | Path | "ArtifactHandle") -> str:
        return self._resolve_io_target(target).read_text()

    def write(self, target: str | Path | "ArtifactHandle", content: str) -> None:
        self._resolve_io_target(target).write_text(content)

    def read_json(self, target: str | Path | "ArtifactHandle") -> object:
        return self._resolve_io_target(target).read_json()

    def write_json(self, target: str | Path | "ArtifactHandle", value: object) -> None:
        self._resolve_io_target(target).write_json(value)

    def _continuity_for(self, ref: Session | str, slot: str) -> Continuity:
        if isinstance(ref, Session):
            return ref.continuity
        definition = self._session_definitions.get(slot)
        if definition is not None:
            return definition.continuity
        return Continuity.run()

    def _set_state(self, state: BaseModel) -> None:
        self._state = state

    def _set_answer(self, answer: str | None) -> None:
        self._answer = answer

    def _set_input_response(self, input_response: Any | None) -> None:
        self._input_response = input_response

    def _set_artifacts(self, artifacts: "ResolvedArtifacts | None") -> None:
        self._artifacts = artifacts

    def _set_values(self, values: Mapping[str, Any] | None) -> None:
        self._values = normalize_mapping(values)

    def _set_route(self, route: Mapping[str, Any] | Any | None) -> None:
        self._route = route

    def _set_outcome(self, outcome: Mapping[str, Any] | Any | None) -> None:
        self._outcome = outcome

    def _set_event(self, event: Mapping[str, Any] | Any | None) -> None:
        self._event = event

    def _set_meta(self, meta: Mapping[str, Any] | Any | None) -> None:
        self._meta = meta

    def _set_step_state_store(self, state: BaseModel | dict[str, Any]) -> None:
        self._step_state = state

    def _set_item_state_store(self, state: BaseModel | dict[str, Any] | None) -> None:
        self._item_state = state

    def _set_step_item_state_store(self, state: BaseModel | dict[str, Any] | None) -> None:
        self._step_item_state = state

    def _set_selection(self, worklist: "Worklist[Any] | str", selection: "Selection[Any]") -> None:
        self._selections[self._worklist_name(worklist)] = selection

    def _set_active_worklist(self, worklist: "Worklist[Any] | str | None") -> None:
        self._active_worklist = None if worklist is None else self._worklist_name(worklist)

    def _set_selections(self, selections: dict[str, "Selection[Any]"]) -> None:
        self._selections = selections

    def invoke_workflow(
        self,
        workflow: str | type[Any],
        *,
        message: str,
        parameters: Mapping[str, Any] | None = None,
        input: BaseModel | Mapping[str, Any] | None = None,
    ) -> ChildWorkflowResult[Any]:
        if self._workflow_invoker is None:
            raise RuntimeError("ctx.invoke_workflow(...) is only available on runtime-backed contexts")
        payload_input: BaseModel | dict[str, Any] | None
        if isinstance(input, BaseModel):
            payload_input = input
        elif input is None:
            payload_input = None
        else:
            payload_input = normalize_mapping(input)
        invocation_parameters = normalize_mapping(parameters)
        signature = inspect.signature(self._workflow_invoker)
        supports_input = "input" in signature.parameters or any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()
        )
        if payload_input is None and not supports_input:
            return self._workflow_invoker(
                workflow,
                message=message,
                parameters=invocation_parameters,
            )
        if payload_input is not None and not supports_input:
            raise TypeError("runtime workflow invoker does not accept typed child input")
        return self._workflow_invoker(
            workflow,
            message=message,
            parameters=invocation_parameters,
            input=payload_input,
        )

    def _get_cached_worklist_items(self, worklist_name: str) -> tuple[Any, ...] | None:
        return self._worklist_items_cache.get(worklist_name)

    def _cache_worklist_items(self, worklist_name: str, items: tuple[Any, ...]) -> tuple[Any, ...]:
        self._worklist_items_cache[worklist_name] = items
        return items

    def _worklist_name(self, worklist: "Worklist[Any] | str") -> str:
        if isinstance(worklist, str):
            return worklist
        name = getattr(worklist, "name", None)
        if not isinstance(name, str) or not name:
            raise WorkflowExecutionError("worklist references must be named")
        if name not in self._worklists:
            raise WorkflowExecutionError(f"unknown worklist {name!r}")
        return name

    def _resolve_io_target(self, target: str | Path | "ArtifactHandle") -> "ArtifactHandle":
        from .artifacts import ArtifactHandle

        if isinstance(target, ArtifactHandle):
            return target
        if isinstance(target, str) and self._artifacts is not None and target in self._artifacts:
            return self._artifacts[target]
        path = Path(target) if isinstance(target, (str, Path)) else None
        if path is None:
            raise WorkflowExecutionError(f"unsupported IO target {target!r}")
        if not path.is_absolute():
            path = (self.root / path).resolve()
        return ArtifactHandle(name=path.name, path=path)


def _session_name(ref: Session | str) -> str:
    if isinstance(ref, Session):
        if ref.name is None:
            raise ValueError("session slot is not bound to a workflow attribute name")
        return ref.name
    return ref


def _resolve_context_root(*, root: Path | None, task_folder: Path, package_folder: Path) -> Path:
    if root is not None:
        return root.resolve()
    resolved_package_folder = package_folder.resolve()
    if resolved_package_folder.parent.name == "workflows":
        return resolved_package_folder.parent.parent.resolve()
    return task_folder.resolve()
