"""Stable runtime context surface."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
import inspect
from typing import TYPE_CHECKING, Any, Callable, Generic, TypeVar
from uuid import uuid4
from weakref import WeakKeyDictionary

from pydantic import BaseModel, ConfigDict

from .branch_groups.context import BranchMetadata, FanInMetadata, StateCell
from .errors import WorkflowExecutionError
from .mappings import normalize_mapping
from .primitives import Event
from .sessions import Continuity, DEFAULT_SESSION_NAME, SessionKey, derive_session_key
from .step_state import reserved_item_state_field_names, reserved_step_state_field_names
from .stores.protocols import SessionBinding, is_run_key_bound_to_slot
from .steps import Session

if TYPE_CHECKING:
    from .artifacts import ArtifactHandle, ResolvedArtifacts
    from .compiler import CompiledStep
    from .history import HistoryReader
    from .stores.protocols import SessionStore
    from .worklists import Selection, SelectionSnapshot, WorkItem, Worklist


OutputT = TypeVar("OutputT")
_CONTEXT_RUNTIMES: "WeakKeyDictionary[Context, _ContextRuntime]" = WeakKeyDictionary()
_DEFAULT_MESSAGE = object()


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Stable access to persisted request snapshots for one run."""

    file: Path
    task_file: Path | None = None

    @property
    def text(self) -> str:
        try:
            return self.file.read_text(encoding="utf-8").rstrip("\n")
        except OSError as exc:
            raise WorkflowExecutionError(
                f"run request snapshot could not be read: {self.file}"
            ) from exc


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


@dataclass(frozen=True, slots=True)
class WorkflowInputView:
    """Composite attribute view over the run message and typed workflow input."""

    message: str | None
    fields: BaseModel | None = None

    def __getattr__(self, name: str) -> Any:
        if name == "message":
            return self.message
        if self.fields is not None:
            return getattr(self.fields, name)
        raise AttributeError(name)

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        payload = {"message": self.message}
        if self.fields is not None:
            payload.update(self.fields.model_dump(*args, **kwargs))
        return payload


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

    def __eq__(self, other: object) -> bool:
        source = object.__getattribute__(self, "_source")
        if isinstance(source, Mapping):
            return dict(source) == other
        if isinstance(other, Mapping):
            return {
                key: getattr(source, key)
                for key in getattr(type(source), "model_fields", {})
            } == dict(other)
        return source == other


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


class StateView:
    """Attribute view that keeps runtime-owned fields read-only."""

    def __init__(self, source: BaseModel | dict[str, Any], *, runtime_fields: frozenset[str] = frozenset()) -> None:
        object.__setattr__(self, "_source", source)
        object.__setattr__(self, "_runtime_fields", runtime_fields)

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
        if item in object.__getattribute__(self, "_runtime_fields"):
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
        request_file: Path | None = None,
        task_request_file: Path | None = None,
        state: BaseModel,
        state_cell: StateCell | None = None,
        session_store: SessionStore,
        session_definitions: Mapping[str, Session] | None = None,
        worklists: Mapping[str, "Worklist[Any]"] | None = None,
        selections: dict[str, "Selection[Any]"] | None = None,
        selection_snapshots: dict[str, "SelectionSnapshot"] | None = None,
        active_worklist: str | None = None,
        params: BaseModel | None = None,
        workflow_params: Mapping[str, Any] | None = None,
        message: str | None | object = _DEFAULT_MESSAGE,
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
        runtime_event_sink: Callable[[str, Mapping[str, Any]], None] | None = None,
        branch: BranchMetadata | None = None,
        fan_in: FanInMetadata | None = None,
        step_execution_id: str | None = None,
    ) -> None:
        self.root = _resolve_context_root(root=root, task_folder=task_folder, package_folder=package_folder)
        self.task_id = task_id
        self.run_id = run_id
        self.workflow_name = workflow_name
        self.task_folder = task_folder
        self.workflow_folder = workflow_folder
        self.run_folder = run_folder
        self.package_folder = package_folder
        self._request_file = Path(request_file) if request_file is not None else run_folder / "request.md"
        if task_request_file is not None:
            self._task_request_file = Path(task_request_file)
        else:
            candidate = task_folder / "request.md"
            self._task_request_file = candidate if candidate.exists() else None
        self._state_cell = state_cell or StateCell(state)
        self._state = self._state_cell.value
        self._session_store = session_store
        self._session_definitions = normalize_mapping(session_definitions)
        self._worklists = normalize_mapping(worklists)
        self._selections = selections if selections is not None else {}
        self._selection_snapshots = selection_snapshots if selection_snapshots is not None else {}
        self._active_worklist = active_worklist
        self._params = params if params is not None else EmptyParameters()
        self._workflow_params = normalize_mapping(workflow_params)
        self._message = message
        self._input_fields = workflow_input
        self._workflow_invoker = workflow_invoker
        self._answer = answer
        self._input_response = input_response
        self._step_name = step_name
        self._default_session_name = default_session_name
        self._artifacts = artifacts
        self._values = values if isinstance(values, dict) else normalize_mapping(values)
        self._route = route
        self._event = None
        self._outcome = outcome
        self._meta = meta
        self._step_state = step_state_store if step_state_store is not None else {}
        self._item_state = item_state_store
        self._step_item_state = step_item_state_store
        self._branch = branch
        self._fan_in = fan_in
        self._step_execution_id = step_execution_id
        self._history: HistoryReader | None = None
        self._worklist_items_cache: dict[str, tuple[Any, ...]] = {}
        self._runtime_event_sink = runtime_event_sink
        self._worklist_selection_sync: Callable[[str], None] | None = None
        self._worklist_selection_resolver: Callable[[str], "Selection[Any]"] | None = None
        self._execution_source_hook: str | None = None
        self._execution_source_phase: str | None = None
        self._execution_hook_invocation_id: str | None = None
        _CONTEXT_RUNTIMES[self] = _ContextRuntime(self)

    @property
    def state(self) -> BaseModel:
        return self._state_cell.value

    @state.setter
    def state(self, value: BaseModel) -> None:
        self._state = self._state_cell.set(value)

    @property
    def state_cell(self) -> StateCell:
        return self._state_cell

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
    def request_file(self) -> Path:
        return self._request_file

    @property
    def request(self) -> RequestContext:
        return RequestContext(file=self._request_file, task_file=self._task_request_file)

    @property
    def message(self) -> str | None:
        if self._message is _DEFAULT_MESSAGE:
            return self.request.text
        return self._message

    @property
    def input_fields(self) -> BaseModel | None:
        return self._input_fields

    @property
    def input(self) -> WorkflowInputView:
        resolved_message = self._message
        if resolved_message is _DEFAULT_MESSAGE:
            resolved_message = self.request.text if self.request_file.exists() else None
        return WorkflowInputView(message=resolved_message, fields=self._input_fields)

    @property
    def artifacts(self) -> "ResolvedArtifacts | None":
        return self._artifacts

    @property
    def values(self) -> NamespaceProxy:
        return NamespaceProxy(self._values)

    @property
    def branch(self) -> NamespaceProxy:
        if self._branch is None:
            raise WorkflowExecutionError("branch metadata is only available during branch execution")
        return NamespaceProxy(self._branch)

    @property
    def fan_in(self) -> NamespaceProxy:
        if self._fan_in is None:
            raise WorkflowExecutionError("fan_in metadata is only available during fan-in execution")
        return NamespaceProxy(self._fan_in)

    @property
    def route(self) -> NamespaceProxy | None:
        if self._route is None:
            return None
        return NamespaceProxy(self._route)

    @property
    def outcome(self) -> Any | None:
        if self._outcome is None:
            return None
        if isinstance(self._outcome, Mapping):
            return NamespaceProxy(self._outcome)
        return self._outcome

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
        return StateView(self._step_state, runtime_fields=_step_runtime_fields(self._step_state))

    @property
    def item_state(self) -> StateView:
        if isinstance(self._item_state, (BaseModel, dict)):
            return StateView(self._item_state, runtime_fields=reserved_item_state_field_names())
        raise WorkflowExecutionError(
            "item_state is only available when there is an active scoped worklist item"
        )

    @property
    def step_item_state(self) -> StateView:
        if isinstance(self._step_item_state, (BaseModel, dict)):
            return StateView(self._step_item_state, runtime_fields=_step_runtime_fields(self._step_item_state))
        raise WorkflowExecutionError(
            "step_item_state is only available when there is an active scoped worklist item"
        )

    @property
    def worklists(self) -> "_WorklistNamespace":
        return _WorklistNamespace(self)

    def worklist(self, name: "Worklist[Any] | str") -> "WorklistRuntimeView[Any]":
        from .worklists import WorklistRuntimeView

        worklist_name = self._worklist_name(name)
        try:
            worklist = self._worklists[worklist_name]
        except KeyError as exc:
            raise WorkflowExecutionError(f"unknown worklist {worklist_name!r}") from exc
        return WorklistRuntimeView(self, worklist)

    @property
    def current_worklist(self) -> "WorklistRuntimeView[Any]":
        if self._active_worklist is None:
            raise WorkflowExecutionError("current_worklist is only available while executing a scoped step")
        return self.worklist(self._active_worklist)

    @property
    def session(self) -> SessionBinding | None:
        return self.get_session(self._default_session_name)

    def ensure_selection(self, worklist: "Worklist[Any] | str") -> "Selection[Any]":
        worklist_name = self._worklist_name(worklist)
        selection = self._selections.get(worklist_name)
        if selection is not None:
            return selection
        if self._worklist_selection_resolver is None:
            raise WorkflowExecutionError(f"unknown worklist selection {worklist_name!r}")
        return self._worklist_selection_resolver(worklist_name)

    def selection(self, worklist: "Worklist[Any] | str") -> "Selection[Any]":
        return self.ensure_selection(worklist)

    def current(self, worklist: "Worklist[Any] | str") -> "WorkItem[Any] | None":
        return self.selection(worklist).current

    @property
    def item(self) -> "WorkItem[Any] | None":
        if self._active_worklist is None:
            return None
        return self.ensure_selection(self._active_worklist).current

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
        try:
            return derive_session_key(slot, resolved_continuity, self)
        except ValueError as exc:
            raise WorkflowExecutionError(str(exc)) from exc

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

    def _worklist_name(self, worklist: "Worklist[Any] | str") -> str:
        if isinstance(worklist, str):
            if worklist not in self._worklists:
                raise WorkflowExecutionError(f"unknown worklist {worklist!r}")
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
    parts = resolved_package_folder.parts
    for marker in (("botlane", "workflows"), (".botlane", "workflows"), (".autoloop", "workflows"), ("workflows",)):
        marker_length = len(marker)
        for index in range(len(parts) - marker_length, -1, -1):
            if parts[index : index + marker_length] != marker:
                continue
            return Path(*parts[:index]).resolve()
    return task_folder.resolve()


class _WorklistNamespace:
    def __init__(self, context: Context) -> None:
        self._context = context

    def __getattr__(self, item: str) -> Any:
        try:
            return self._context.worklist(item)
        except WorkflowExecutionError as exc:
            raise AttributeError(f"unknown worklist {item!r}") from exc


class _ContextRuntime:
    def __init__(self, context: Context) -> None:
        self._context = context

    def set_state(self, state: BaseModel) -> None:
        self._context._state = self._context._state_cell.set(state)

    def set_answer(self, answer: str | None) -> None:
        self._context._answer = answer

    def set_input_response(self, input_response: Any | None) -> None:
        self._context._input_response = input_response

    def set_artifacts(self, artifacts: "ResolvedArtifacts | None") -> None:
        self._context._artifacts = artifacts

    def set_values(self, values: Mapping[str, Any] | None) -> None:
        self._context._values = values if isinstance(values, dict) else normalize_mapping(values)

    def set_route(self, route: Mapping[str, Any] | Any | None) -> None:
        self._context._route = route

    def set_outcome(self, outcome: Mapping[str, Any] | Any | None) -> None:
        self._context._outcome = outcome

    def set_event(self, event: Mapping[str, Any] | Any | None) -> None:
        self._context._event = event

    def set_meta(self, meta: Mapping[str, Any] | Any | None) -> None:
        self._context._meta = meta

    def set_step_state_store(self, state: BaseModel | dict[str, Any]) -> None:
        self._context._step_state = state

    def set_item_state_store(self, state: BaseModel | dict[str, Any] | None) -> None:
        self._context._item_state = state

    def set_step_item_state_store(self, state: BaseModel | dict[str, Any] | None) -> None:
        self._context._step_item_state = state

    def set_session_store(self, session_store: SessionStore) -> None:
        self._context._session_store = session_store

    def set_branch(self, branch: BranchMetadata | None) -> None:
        self._context._branch = branch

    def set_fan_in(self, fan_in: FanInMetadata | None) -> None:
        self._context._fan_in = fan_in

    def set_step_execution_id(self, step_execution_id: str | None) -> None:
        self._context._step_execution_id = step_execution_id

    def set_selection(self, worklist: "Worklist[Any] | str", selection: "Selection[Any]") -> None:
        worklist_name = self._context._worklist_name(worklist)
        self._context._selections[worklist_name] = selection
        self._context._selection_snapshots.pop(worklist_name, None)

    def set_active_worklist(self, worklist: "Worklist[Any] | str | None") -> None:
        self._context._active_worklist = None if worklist is None else self._context._worklist_name(worklist)

    def set_selections(self, selections: dict[str, "Selection[Any]"]) -> None:
        self._context._selections = selections

    def set_selection_snapshots(self, snapshots: dict[str, "SelectionSnapshot"]) -> None:
        self._context._selection_snapshots = snapshots

    def set_worklist_selection_sync(self, callback: Callable[[str], None] | None) -> None:
        self._context._worklist_selection_sync = callback

    def set_worklist_selection_resolver(
        self,
        callback: Callable[[str], "Selection[Any]"] | None,
    ) -> None:
        self._context._worklist_selection_resolver = callback

    def set_execution_source(
        self,
        *,
        hook_name: str | None,
        phase: str | None,
        invocation_id: str | None,
    ) -> None:
        self._context._execution_source_hook = hook_name
        self._context._execution_source_phase = phase
        self._context._execution_hook_invocation_id = invocation_id

    def sync_scoped_state_after_worklist_selection_change(self, worklist: "Worklist[Any] | str") -> None:
        if self._context._worklist_selection_sync is None:
            return
        self._context._worklist_selection_sync(self._context._worklist_name(worklist))

    def emit_worklist_runtime_event(
        self,
        event_type: str,
        *,
        worklist_name: str,
        previous_selection: "Selection[Any]",
        new_selection: "Selection[Any]",
    ) -> None:
        if self._context._runtime_event_sink is None:
            return
        previous_current = previous_selection.current
        new_current = new_selection.current
        previous_status = None if previous_current is None else previous_current.status
        new_status = None if new_current is None else new_current.status
        payload: dict[str, Any] = {
            "step_name": self._context._step_name,
            "worklist_name": worklist_name,
            "previous_current_item_id": None if previous_current is None else previous_current.id,
            "new_current_item_id": None if new_current is None else new_current.id,
            "previous_status": previous_status,
            "new_status": new_status,
        }
        visit = _runtime_visits(self._context._step_item_state or self._context._step_state)
        if isinstance(visit, int):
            payload["visit"] = visit
        if self._context._active_worklist is not None:
            payload["scope"] = self._context._active_worklist
        if new_current is not None:
            payload["item_id"] = new_current.id
        elif previous_current is not None:
            payload["item_id"] = previous_current.id
        step_execution_id = _context_step_execution_id(
            self._context,
            visit=visit,
            item_id=None if new_current is None else new_current.id,
        )
        if step_execution_id is not None:
            payload["step_execution_id"] = step_execution_id
        if self._context._execution_source_hook is not None:
            payload["source_hook"] = self._context._execution_source_hook
        if self._context._execution_source_phase is not None:
            payload["source_phase"] = self._context._execution_source_phase
        if self._context._execution_hook_invocation_id is not None:
            payload["hook_invocation_id"] = self._context._execution_hook_invocation_id
        self._context._runtime_event_sink(event_type, payload)

    def emit_worklist_selection_resolved(
        self,
        *,
        worklist_name: str,
        selection: "Selection[Any]",
        lazy: bool = False,
        source: str | None = None,
    ) -> None:
        if self._context._runtime_event_sink is None:
            return
        current = selection.current
        payload: dict[str, Any] = {
            "step_name": self._context._step_name,
            "worklist_name": worklist_name,
            "selection_mode": selection.mode,
            "selection_explicit": selection.explicit,
            "item_ids": [item.id for item in selection.items],
            "current_index": selection.current_index,
            "current_item_id": None if current is None else current.id,
            "lazy": lazy,
            "materialization_state": "materialized",
        }
        if source is not None:
            payload["source"] = source
        worklist = self._context._worklists.get(worklist_name)
        if worklist is not None:
            payload["source_type"] = worklist.source_type
            if worklist.missing_policy is not None:
                payload["missing_policy"] = worklist.missing_policy
        visit = _runtime_visits(self._context._step_item_state or self._context._step_state)
        if isinstance(visit, int):
            payload["visit"] = visit
        if self._context._active_worklist is not None:
            payload["scope"] = self._context._active_worklist
        step_execution_id = _context_step_execution_id(
            self._context,
            visit=visit,
            item_id=None if current is None else current.id,
        )
        if step_execution_id is not None:
            payload["step_execution_id"] = step_execution_id
        if self._context._execution_source_hook is not None:
            payload["source_hook"] = self._context._execution_source_hook
        if self._context._execution_source_phase is not None:
            payload["source_phase"] = self._context._execution_source_phase
        if self._context._execution_hook_invocation_id is not None:
            payload["hook_invocation_id"] = self._context._execution_hook_invocation_id
        self._context._runtime_event_sink("worklist_selection_resolved", payload)

    def emit_runtime_event(self, event_type: str, **payload: Any) -> None:
        if self._context._runtime_event_sink is None:
            return
        event_payload = dict(payload)
        if "step_name" not in event_payload:
            event_payload["step_name"] = self._context._step_name
        visit = _runtime_visits(self._context._step_item_state or self._context._step_state)
        if isinstance(visit, int) and "visit" not in event_payload:
            event_payload["visit"] = visit
        if self._context._active_worklist is not None and "scope" not in event_payload:
            event_payload["scope"] = self._context._active_worklist
        step_execution_id = _context_step_execution_id(
            self._context,
            visit=visit,
            item_id=event_payload.get("item_id"),
        )
        if step_execution_id is not None and "step_execution_id" not in event_payload:
            event_payload["step_execution_id"] = step_execution_id
        if self._context._execution_source_hook is not None and "source_hook" not in event_payload:
            event_payload["source_hook"] = self._context._execution_source_hook
        if self._context._execution_source_phase is not None and "source_phase" not in event_payload:
            event_payload["source_phase"] = self._context._execution_source_phase
        if self._context._execution_hook_invocation_id is not None and "hook_invocation_id" not in event_payload:
            event_payload["hook_invocation_id"] = self._context._execution_hook_invocation_id
        self._context._runtime_event_sink(event_type, event_payload)

    def get_cached_worklist_items(self, worklist_name: str) -> tuple[Any, ...] | None:
        return self._context._worklist_items_cache.get(worklist_name)

    def cache_worklist_items(self, worklist_name: str, items: tuple[Any, ...]) -> tuple[Any, ...]:
        self._context._worklist_items_cache[worklist_name] = items
        return items


def context_runtime(context: Context) -> _ContextRuntime:
    try:
        return _CONTEXT_RUNTIMES[context]
    except KeyError as exc:  # pragma: no cover - only reachable for malformed synthetic contexts
        raise WorkflowExecutionError("runtime helpers are unavailable on this context") from exc


def _runtime_visits(state: BaseModel | dict[str, Any] | None) -> int | None:
    if isinstance(state, BaseModel):
        visits = getattr(state, "visits", None)
        return visits if isinstance(visits, int) else None
    if isinstance(state, dict):
        visits = state.get("visits")
        return visits if isinstance(visits, int) else None
    return None


def _step_runtime_fields(state: BaseModel | dict[str, Any] | None) -> frozenset[str]:
    if isinstance(state, BaseModel):
        field_names = set(type(state).model_fields)
    elif isinstance(state, dict):
        field_names = set(state)
    else:
        field_names = set()
    if "rework_count" in field_names or "replan_count" in field_names:
        return reserved_step_state_field_names("produce_verify")
    return reserved_step_state_field_names("step")


def _step_execution_id(
    *,
    step_name: str | None,
    visit: int | None,
    scope_name: str | None,
    item_id: str | None,
) -> str | None:
    if step_name is None or visit is None:
        return None
    if scope_name is not None and item_id is not None:
        return f"{step_name}:{scope_name}:{item_id}:{visit}"
    return f"{step_name}:{visit}"


def _context_step_execution_id(
    context: Context,
    *,
    visit: int | None,
    item_id: str | None,
) -> str | None:
    if context._step_execution_id is not None:
        return context._step_execution_id if visit is None else f"{context._step_execution_id.rsplit(':', 1)[0]}:{visit}"
    return _step_execution_id(
        step_name=context._step_name,
        visit=visit,
        scope_name=context._active_worklist,
        item_id=item_id,
    )
