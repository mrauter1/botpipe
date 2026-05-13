"""Worklist declarations, selection state, and artifact-backed sources."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
import inspect
from typing import TYPE_CHECKING, Any, Generic, Literal, Protocol, TypeVar

from pydantic import BaseModel

from .errors import WorkflowExecutionError, WorkflowValidationError
from .step_state import build_worklist_item_state_model, built_in_item_state_model, reserved_item_state_field_names

if TYPE_CHECKING:
    from .artifacts import Artifact
    from .context import Context
    from .primitives import Event, Fail, Goto, RequestInput


T = TypeVar("T")
SAFE_DIR_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
MissingSourcePolicy = Literal["error", "scaffold"]

@dataclass(frozen=True, slots=True)
class WorkItem(Generic[T]):
    """One selected work item."""

    id: str
    title: str
    payload: T
    status: str | None = None
    dir_key: str | None = None


@dataclass(frozen=True, slots=True)
class Selector:
    """Declarative selection policy for a worklist."""

    item_param: str | None = None
    start_param: str | None = None
    end_param: str | None = None
    mode_param: str | None = None
    default_mode: Literal["all", "single", "up_to", "from_to"] = "all"
    allowed_modes: tuple[str, ...] = ("all", "single", "up_to", "from_to")

    def __post_init__(self) -> None:
        for field_name in ("item_param", "start_param", "end_param", "mode_param"):
            raw_value = getattr(self, field_name)
            if raw_value is None:
                continue
            if not isinstance(raw_value, str):
                raise ValueError(f"Selector.{field_name} must be a string when provided")
            normalized = raw_value.strip()
            if not normalized:
                raise ValueError(f"Selector.{field_name} must not be empty")
            object.__setattr__(self, field_name, normalized)

        if not isinstance(self.default_mode, str):
            raise ValueError("Selector.default_mode must be a string")
        default_mode = self.default_mode.strip()
        if not default_mode:
            raise ValueError("Selector.default_mode must not be empty")

        if not self.allowed_modes:
            raise ValueError("Selector.allowed_modes must contain at least one mode")
        normalized_modes: list[str] = []
        seen_modes: set[str] = set()
        supported_modes = {"all", "single", "up_to", "from_to"}
        for raw_mode in self.allowed_modes:
            if not isinstance(raw_mode, str):
                raise ValueError("Selector.allowed_modes must contain only strings")
            mode = raw_mode.strip()
            if not mode:
                raise ValueError("Selector.allowed_modes must not contain empty values")
            if mode not in supported_modes:
                raise ValueError(
                    "Selector.allowed_modes entries must be one of: all, single, up_to, from_to"
                )
            if mode in seen_modes:
                raise ValueError(f"Selector.allowed_modes must not contain duplicate mode {mode!r}")
            seen_modes.add(mode)
            normalized_modes.append(mode)
        object.__setattr__(self, "default_mode", default_mode)
        object.__setattr__(self, "allowed_modes", tuple(normalized_modes))
        if default_mode not in normalized_modes:
            raise ValueError("Selector.default_mode must be included in allowed_modes")


@dataclass(frozen=True, slots=True)
class Selection(Generic[T]):
    """Current runtime selection for a worklist."""

    worklist_name: str
    mode: str
    items: tuple[WorkItem[T], ...]
    explicit: bool
    current_index: int = 0

    @property
    def current(self) -> WorkItem[T] | None:
        if not self.items:
            return None
        if self.current_index >= len(self.items):
            return None
        return self.items[self.current_index]

    def advance(self) -> "Selection[T]":
        return replace(self, current_index=self.current_index + 1)


@dataclass(frozen=True, slots=True)
class WorkItemSnapshot:
    """Serializable snapshot of one selected work item."""

    id: str
    title: str
    status: str | None = None
    dir_key: str | None = None


@dataclass(frozen=True, slots=True)
class SelectionSnapshot:
    """Serializable snapshot of one worklist selection."""

    worklist_name: str
    mode: str
    items: tuple[WorkItemSnapshot, ...]
    explicit: bool
    current_index: int = 0


def _snapshot_worklist_selections(
    worklists: Mapping[str, Any],
    selections: Mapping[str, Selection[Any]] | None,
    *,
    snapshots: Mapping[str, SelectionSnapshot] | None = None,
) -> dict[str, SelectionSnapshot] | None:
    if not selections and not snapshots:
        return None
    serialized: dict[str, SelectionSnapshot] = {}
    if snapshots:
        for name, snapshot in snapshots.items():
            if name in worklists:
                serialized[name] = snapshot
    for name, selection in (selections or {}).items():
        worklist = worklists.get(name)
        if worklist is None:
            continue
        serialized[name] = worklist.snapshot_selection(selection)
    return serialized or None


class WorklistSource(Protocol[T]):
    """Backend contract for materializing and persisting worklist items."""

    mutable: bool
    artifact_backed: bool

    def ensure(self, ctx: "Context") -> None:
        ...

    def load(self, ctx: "Context") -> Sequence[WorkItem[T]]:
        ...

    def save(self, ctx: "Context", items: Sequence[WorkItem[T]]) -> None:
        ...

    def validate(self, ctx: "Context", items: Sequence[WorkItem[T]]) -> str | None:
        ...


@dataclass(frozen=True, slots=True)
class Worklist(Generic[T]):
    """Named collection of scoped work items."""

    name: str
    source: WorklistSource[T]
    selector: Selector = Selector()
    item_state_model: type[BaseModel] | None = None
    runtime_item_state_model: type[BaseModel] = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("worklist name must be a non-empty string")
        if self.item_state_model is not None:
            _validate_worklist_item_state_model(self.item_state_model, worklist_name=self.name)
        module_name = (
            self.item_state_model.__module__
            if self.item_state_model is not None
            else built_in_item_state_model().__module__
        )
        object.__setattr__(
            self,
            "runtime_item_state_model",
            build_worklist_item_state_model(
                self.item_state_model,
                worklist_name=self.name,
                module_name=module_name,
            ),
        )

    @classmethod
    def from_items(
        cls,
        name: str,
        items: Sequence[T],
        *,
        item_id: Callable[[T], str] | str = "id",
        title: Callable[[T], str] | str = "title",
        status: Callable[[T], str | None] | str | None = None,
        selector: Selector = Selector(),
        item_state: type[BaseModel] | None = None,
    ) -> "Worklist[T]":
        source = _StaticWorklistSource(
            items=tuple(items),
            item_id=item_id,
            title=title,
            status=status,
        )
        return cls(name=name, source=source, selector=selector, item_state_model=item_state)

    @classmethod
    def from_param(
        cls,
        name: str,
        param_name: str | None = None,
        *,
        item_id: Callable[[Any], str] | str = "id",
        title: Callable[[Any], str] | str = "title",
        status: Callable[[Any], str | None] | str | None = None,
        selector: Selector = Selector(),
        item_state: type[BaseModel] | None = None,
    ) -> "Worklist[Any]":
        source = _ParameterWorklistSource(
            param_name=param_name or name,
            item_id=item_id,
            title=title,
            status=status,
        )
        return cls(name=name, source=source, selector=selector, item_state_model=item_state)

    @classmethod
    def from_artifact(
        cls,
        name: str,
        artifact: "Artifact",
        *,
        collection: str,
        item_id: str,
        title: str,
        status: str | None = None,
        missing: MissingSourcePolicy = "error",
        selector: Selector = Selector(),
        item_state: type[BaseModel] | None = None,
    ) -> "Worklist[Mapping[str, object]]":
        source = _ArtifactWorklistSource(
            artifact=artifact,
            collection=collection,
            item_id=item_id,
            title=title,
            status=status,
            missing=missing,
        )
        return cls(name=name, source=source, selector=selector, item_state_model=item_state)

    @property
    def mutable(self) -> bool:
        return bool(getattr(self.source, "mutable", False))

    @property
    def artifact_backed(self) -> bool:
        return bool(getattr(self.source, "artifact_backed", False))

    @property
    def artifact(self) -> "Artifact | None":
        return getattr(self.source, "artifact", None)

    @property
    def source_type(self) -> str:
        source = self.source
        if getattr(source, "artifact_backed", False):
            return "artifact"
        param_name = getattr(source, "param_name", None)
        if isinstance(param_name, str) and param_name:
            return "parameter"
        if type(source).__name__ == "_StaticWorklistSource":
            return "static"
        return type(source).__name__

    @property
    def missing_policy(self) -> MissingSourcePolicy | None:
        policy = getattr(self.source, "missing", None)
        if policy in {"error", "scaffold"}:
            return policy
        return None

    def source_descriptor(self, ctx: "Context | None" = None) -> str:
        if self.artifact_backed:
            artifact = getattr(self.source, "artifact", None)
            if artifact is not None:
                if ctx is not None:
                    try:
                        from .artifacts import resolve_artifact_template

                        path = resolve_artifact_template(artifact, ctx)
                        return f"artifact:{path}"
                    except Exception:
                        pass
                template = getattr(artifact, "template", None)
                if isinstance(template, str) and template:
                    return f"artifact:{template}"
            return "artifact"
        param_name = getattr(self.source, "param_name", None)
        if isinstance(param_name, str) and param_name:
            return f"parameter:{param_name}"
        return self.source_type

    def load_items(self, ctx: "Context") -> tuple[WorkItem[T], ...]:
        return self._load_items_snapshot(ctx)

    def reload_items(self, ctx: "Context") -> tuple[WorkItem[T], ...]:
        return self._load_items_snapshot(ctx, force_reload=True)

    def _load_items_snapshot(
        self,
        ctx: "Context",
        *,
        force_reload: bool = False,
    ) -> tuple[WorkItem[T], ...]:
        cached = None if force_reload else ctx._execution_frame.get_cached_worklist_items(self.name)
        if cached is not None:
            return cached
        items = self._load_source_items(ctx)
        self._validate_loaded_items(ctx, items)
        return self._cache_loaded_items(ctx, items)

    def ensure_source(self, ctx: "Context") -> None:
        ensure = getattr(self.source, "ensure", None)
        if callable(ensure):
            ensure(ctx)

    def _load_source_items(
        self,
        ctx: "Context",
        *,
        ensure: bool = True,
    ) -> tuple[WorkItem[T], ...]:
        if ensure:
            self.ensure_source(ctx)
        return tuple(self.source.load(ctx))

    def _validate_loaded_items(self, ctx: "Context", items: Sequence[WorkItem[T]]) -> None:
        validation_error = self.source.validate(ctx, items)
        if validation_error:
            raise WorkflowExecutionError(f"worklist {self.name!r} is invalid: {validation_error}")
        duplicate_ids = _duplicate_item_ids(items)
        if duplicate_ids:
            duplicates = ", ".join(duplicate_ids)
            raise WorkflowExecutionError(
                f"worklist {self.name!r} contains duplicate item id(s): {duplicates}"
            )

    def _cache_loaded_items(self, ctx: "Context", items: tuple[WorkItem[T], ...]) -> tuple[WorkItem[T], ...]:
        return ctx._execution_frame.cache_worklist_items(self.name, items)

    def initial_selection(self, ctx: "Context") -> Selection[T]:
        items = self.load_items(ctx)
        return self._selection_from_loaded_items(ctx, items)

    def restore_selection(
        self,
        ctx: "Context",
        snapshot: SelectionSnapshot,
        *,
        items: Sequence[WorkItem[T]] | None = None,
    ) -> Selection[T]:
        loaded_items = {item.id: item for item in (tuple(items) if items is not None else self.load_items(ctx))}
        restored_items: list[WorkItem[T]] = []
        for item_snapshot in snapshot.items:
            loaded = loaded_items.get(item_snapshot.id)
            if loaded is None:
                raise WorkflowExecutionError(
                    f"worklist {self.name!r} cannot restore missing item {item_snapshot.id!r}"
                )
            restored_items.append(
                replace(
                    loaded,
                    title=item_snapshot.title,
                    status=item_snapshot.status,
                    dir_key=item_snapshot.dir_key,
                )
            )
        return Selection(
            worklist_name=self.name,
            mode=snapshot.mode,
            items=tuple(restored_items),
            explicit=snapshot.explicit,
            current_index=snapshot.current_index,
        )

    def _selection_from_loaded_items(
        self,
        ctx: "Context",
        items: Sequence[WorkItem[T]],
        *,
        snapshot: SelectionSnapshot | None = None,
    ) -> Selection[T]:
        if snapshot is not None:
            return self.restore_selection(ctx, snapshot, items=items)
        mode, selected_items, explicit = self._resolve_selection(ctx, tuple(items))
        return Selection(
            worklist_name=self.name,
            mode=mode,
            items=selected_items,
            explicit=explicit,
            current_index=0,
        )

    def snapshot_selection(self, selection: Selection[T]) -> SelectionSnapshot:
        return SelectionSnapshot(
            worklist_name=selection.worklist_name,
            mode=selection.mode,
            items=tuple(
                WorkItemSnapshot(
                    id=item.id,
                    title=item.title,
                    status=item.status,
                    dir_key=item.dir_key,
                )
                for item in selection.items
            ),
            explicit=selection.explicit,
            current_index=selection.current_index,
        )

    def refresh_selection(self, ctx: "Context", selection: Selection[T]) -> Selection[T]:
        loaded_items = {item.id: item for item in self.reload_items(ctx)}
        refreshed_items: list[WorkItem[T]] = []
        for selected in selection.items:
            loaded = loaded_items.get(selected.id)
            if loaded is None:
                raise WorkflowExecutionError(
                    f"worklist {self.name!r} cannot refresh missing item {selected.id!r}"
                )
            refreshed_items.append(loaded)
        return replace(selection, items=tuple(refreshed_items))

    def set_current_status(self, ctx: "Context", selection: Selection[T], status: str | None) -> Selection[T]:
        current = selection.current
        if current is None:
            raise WorkflowExecutionError(f"worklist {self.name!r} has no current item to update")
        updated_items = list(selection.items)
        updated_items[selection.current_index] = replace(current, status=status)
        updated_selection = replace(selection, items=tuple(updated_items))
        if self.mutable:
            self.source.save(ctx, updated_selection.items)
            self.reload_items(ctx)
            return updated_selection
        cached_items = self.load_items(ctx)
        ctx._execution_frame.cache_worklist_items(self.name, _replace_items_by_id(cached_items, updated_selection.items))
        return updated_selection

    def validate_items(self, ctx: "Context", items: Sequence[WorkItem[T]]) -> str | None:
        return self.source.validate(ctx, items)

    def _resolve_selection(
        self,
        ctx: "Context",
        items: tuple[WorkItem[T], ...],
    ) -> tuple[str, tuple[WorkItem[T], ...], bool]:
        mode = _selector_mode(ctx, self.selector, self.name)
        item_indexes = _item_indexes(items)

        item_value = self._selector_value(ctx, self.selector.item_param, mode=mode)
        start_value = self._selector_value(ctx, self.selector.start_param, mode=mode)
        end_value = self._selector_value(ctx, self.selector.end_param, mode=mode)

        if mode == "all":
            self._reject_selector_param(mode, self.selector.item_param, item_value)
            self._reject_selector_param(mode, self.selector.start_param, start_value)
            self._reject_selector_param(mode, self.selector.end_param, end_value)
            return mode, items, False

        if mode == "single":
            self._reject_selector_param(mode, self.selector.start_param, start_value)
            self._reject_selector_param(mode, self.selector.end_param, end_value)
            if item_value is None:
                return mode, items[:1], False
            index = _require_item_id(
                items,
                item_indexes,
                worklist_name=self.name,
                mode=mode,
                parameter_name=self.selector.item_param,
                item_id=item_value,
            )
            return mode, (items[index],), True

        if mode == "up_to":
            self._reject_selector_param(mode, self.selector.start_param, start_value)
            end_name, end_bound = self._end_bound(
                mode=mode,
                primary_name=self.selector.end_param,
                primary_value=end_value,
                fallback_name=self.selector.item_param,
                fallback_value=item_value,
            )
            if end_bound is None:
                return mode, items, False
            end_index = _require_item_id(
                items,
                item_indexes,
                worklist_name=self.name,
                mode=mode,
                parameter_name=end_name,
                item_id=end_bound,
            )
            return mode, items[: end_index + 1], True

        start_index: int | None = None
        end_name, end_bound = self._end_bound(
            mode=mode,
            primary_name=self.selector.end_param,
            primary_value=end_value,
            fallback_name=self.selector.item_param,
            fallback_value=item_value,
        )
        if start_value is not None:
            start_index = _require_item_id(
                items,
                item_indexes,
                worklist_name=self.name,
                mode=mode,
                parameter_name=self.selector.start_param,
                item_id=start_value,
            )
        end_index: int | None = None
        if end_bound is not None:
            end_index = _require_item_id(
                items,
                item_indexes,
                worklist_name=self.name,
                mode=mode,
                parameter_name=end_name,
                item_id=end_bound,
            )
        if start_index is not None and end_index is not None and start_index > end_index:
            raise WorkflowExecutionError(
                f"worklist {self.name!r} selector mode {mode!r} has invalid range: "
                f"parameter {self.selector.start_param!r} value {start_value!r} resolves after "
                f"parameter {end_name!r} value {end_bound!r}"
            )
        if start_index is None and end_index is None:
            return mode, items, False
        if start_index is None:
            assert end_index is not None
            return mode, items[: end_index + 1], True
        if end_index is None:
            return mode, items[start_index:], True
        return mode, items[start_index : end_index + 1], True

    def _selector_value(
        self,
        ctx: "Context",
        parameter_name: str | None,
        *,
        mode: str,
    ) -> str | None:
        if parameter_name is None:
            return None
        raw_value = ctx.workflow_params.get(parameter_name)
        if raw_value is None:
            return None
        if isinstance(raw_value, str):
            normalized = raw_value.strip()
            return normalized or None
        raise WorkflowExecutionError(
            f"worklist {self.name!r} selector mode {mode!r} parameter {parameter_name!r} "
            f"must be a string; received {raw_value!r}"
        )

    def _reject_selector_param(
        self,
        mode: str,
        parameter_name: str | None,
        parameter_value: str | None,
    ) -> None:
        if parameter_name is None or parameter_value is None:
            return
        raise WorkflowExecutionError(
            f"worklist {self.name!r} selector mode {mode!r} does not accept parameter "
            f"{parameter_name!r} with value {parameter_value!r}"
        )

    def _end_bound(
        self,
        *,
        mode: str,
        primary_name: str | None,
        primary_value: str | None,
        fallback_name: str | None,
        fallback_value: str | None,
    ) -> tuple[str | None, str | None]:
        if primary_value is not None and fallback_value is not None:
            raise WorkflowExecutionError(
                f"worklist {self.name!r} selector mode {mode!r} received conflicting parameters "
                f"{fallback_name!r}={fallback_value!r} and {primary_name!r}={primary_value!r}"
            )
        if primary_value is not None:
            return primary_name, primary_value
        return fallback_name, fallback_value


class WorklistRuntimeView(Generic[T]):
    """Public runtime helper surface bound to one context/worklist pair."""

    def __init__(self, context: "Context", worklist: Worklist[T]) -> None:
        self._context = context
        self._worklist = worklist

    @property
    def name(self) -> str:
        return self._worklist.name

    @property
    def selection(self) -> Selection[T]:
        return self._context.selection(self._worklist)

    @property
    def current(self) -> WorkItem[T] | None:
        return self.selection.current

    @property
    def current_id(self) -> str | None:
        current = self.current
        return None if current is None else current.id

    @property
    def current_index(self) -> int:
        return self.selection.current_index

    @property
    def item_ids(self) -> tuple[str, ...]:
        return tuple(item.id for item in self.selection.items)

    @property
    def is_exhausted(self) -> bool:
        return self.current is None

    def refresh(self) -> Selection[T]:
        previous = self.selection
        updated = self._worklist.refresh_selection(self._context, previous)
        self._context._set_worklist_selection(self._worklist.name, updated)
        self._context._emit_worklist_runtime_event(
            "worklist_refreshed",
            worklist_name=self._worklist.name,
            previous_selection=previous,
            new_selection=updated,
        )
        return updated

    def set_current_status(self, status: str | None) -> Selection[T]:
        previous = self.selection
        updated = self._worklist.set_current_status(self._context, previous, status)
        self._context._set_worklist_selection(self._worklist.name, updated)
        self._context._emit_worklist_runtime_event(
            "worklist_status_set",
            worklist_name=self._worklist.name,
            previous_selection=previous,
            new_selection=updated,
        )
        return updated

    def reset_current_status(self) -> Selection[T]:
        previous = self.selection
        updated = self._worklist.set_current_status(self._context, previous, None)
        self._context._set_worklist_selection(self._worklist.name, updated)
        self._context._emit_worklist_runtime_event(
            "worklist_status_reset",
            worklist_name=self._worklist.name,
            previous_selection=previous,
            new_selection=updated,
        )
        return updated

    def advance(self) -> bool:
        previous = self.selection
        updated = previous.advance()
        self._context._set_worklist_selection(self._worklist.name, updated)
        self._context._emit_worklist_runtime_event(
            "worklist_advanced",
            worklist_name=self._worklist.name,
            previous_selection=previous,
            new_selection=updated,
        )
        if updated.current is None:
            self._context._emit_worklist_runtime_event(
                "worklist_exhausted",
                worklist_name=self._worklist.name,
                previous_selection=previous,
                new_selection=updated,
            )
            return False
        return True

    def advance_or(
        self,
        exhausted: "str | Event | RequestInput | Goto | Fail | None" = None,
    ) -> "None | str | Event | RequestInput | Goto | Fail":
        if self.advance():
            return None
        return exhausted

    def validate(self) -> None:
        error = self.validation_error()
        if error is not None:
            raise WorkflowExecutionError(error)

    def validation_error(self) -> str | None:
        try:
            items = self._worklist.reload_items(self._context)
        except WorkflowExecutionError as exc:
            return str(exc)
        selected_ids = {item.id for item in self.selection.items}
        loaded_ids = {item.id for item in items}
        missing = sorted(selected_ids - loaded_ids)
        if missing:
            return f"worklist {self._worklist.name!r} selection references missing item id(s): {', '.join(missing)}"
        return self._worklist.validate_items(self._context, items)


@dataclass(frozen=True, slots=True)
class _StaticWorklistSource(Generic[T]):
    items: tuple[T, ...]
    item_id: Callable[[T], str] | str
    title: Callable[[T], str] | str
    status: Callable[[T], str | None] | str | None
    mutable: bool = False
    artifact_backed: bool = False

    def ensure(self, ctx: "Context") -> None:
        return None

    def load(self, ctx: "Context") -> Sequence[WorkItem[T]]:
        return tuple(_build_work_item(item, item_id=self.item_id, title=self.title, status=self.status) for item in self.items)

    def save(self, ctx: "Context", items: Sequence[WorkItem[T]]) -> None:
        return None

    def validate(self, ctx: "Context", items: Sequence[WorkItem[T]]) -> str | None:
        return None


@dataclass(frozen=True, slots=True)
class _ParameterWorklistSource:
    param_name: str
    item_id: Callable[[Any], str] | str
    title: Callable[[Any], str] | str
    status: Callable[[Any], str | None] | str | None
    mutable: bool = False
    artifact_backed: bool = False

    def ensure(self, ctx: "Context") -> None:
        return None

    def load(self, ctx: "Context") -> Sequence[WorkItem[Any]]:
        raw_items = ctx.workflow_params.get(self.param_name)
        if raw_items is None:
            raise WorkflowExecutionError(
                f"worklist source parameter {self.param_name!r} is missing from workflow_params"
            )
        if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes, bytearray)):
            raise WorkflowExecutionError(
                f"worklist source parameter {self.param_name!r} must be a sequence of items"
            )
        return tuple(
            _build_work_item(item, item_id=self.item_id, title=self.title, status=self.status)
            for item in raw_items
        )

    def save(self, ctx: "Context", items: Sequence[WorkItem[Any]]) -> None:
        return None

    def validate(self, ctx: "Context", items: Sequence[WorkItem[Any]]) -> str | None:
        return None


@dataclass(frozen=True, slots=True)
class _ArtifactWorklistSource:
    artifact: "Artifact"
    collection: str
    item_id: str
    title: str
    status: str | None = None
    missing: MissingSourcePolicy = "error"
    mutable: bool = True
    artifact_backed: bool = True

    def ensure(self, ctx: "Context") -> None:
        if self.missing != "scaffold":
            return None
        handle = self._handle(ctx)
        if handle.exists():
            return None
        handle.write_json({self.collection: []})
        return None

    def load(self, ctx: "Context") -> Sequence[WorkItem[Mapping[str, object]]]:
        handle = self._handle(ctx)
        if not handle.exists():
            raise WorkflowExecutionError(
                f"worklist artifact {self.artifact.name or self.collection!r} does not exist"
            )
        payload = handle.read_json()
        if not isinstance(payload, Mapping):
            raise WorkflowExecutionError(f"worklist {self.collection!r} artifact payload must be a mapping")
        raw_items = payload.get(self.collection)
        if not isinstance(raw_items, list):
            raise WorkflowExecutionError(
                f"worklist collection {self.collection!r} must be a list in artifact {self.artifact.name!r}"
            )
        items: list[WorkItem[Mapping[str, object]]] = []
        for entry in raw_items:
            if not isinstance(entry, Mapping):
                raise WorkflowExecutionError(
                    f"worklist collection {self.collection!r} must contain only object items"
                )
            item_payload = dict(entry)
            items.append(
                WorkItem(
                    id=_string_field(item_payload, self.item_id, worklist_name=self.collection),
                    title=_string_field(item_payload, self.title, worklist_name=self.collection),
                    payload=item_payload,
                    status=_optional_string_field(item_payload, self.status),
                    dir_key=_mapping_dir_key(item_payload, item_id=_string_field(item_payload, self.item_id, worklist_name=self.collection)),
                )
            )
        return tuple(items)

    def save(self, ctx: "Context", items: Sequence[WorkItem[Mapping[str, object]]]) -> None:
        handle = self._handle(ctx)
        payload = handle.read_json()
        if not isinstance(payload, Mapping):
            raise WorkflowExecutionError(f"worklist {self.collection!r} artifact payload must be a mapping")
        raw_items = payload.get(self.collection)
        if not isinstance(raw_items, list):
            raise WorkflowExecutionError(
                f"worklist collection {self.collection!r} must be a list in artifact {self.artifact.name!r}"
            )

        items_by_id = {item.id: item for item in items}
        rewritten: list[dict[str, object]] = []
        for entry in raw_items:
            if not isinstance(entry, Mapping):
                raise WorkflowExecutionError(
                    f"worklist collection {self.collection!r} must contain only object items"
                )
            updated_entry = dict(entry)
            item_id = _string_field(updated_entry, self.item_id, worklist_name=self.collection)
            updated = items_by_id.get(item_id)
            if updated is not None and self.status is not None:
                if updated.status is None:
                    updated_entry.pop(self.status, None)
                else:
                    updated_entry[self.status] = updated.status
            rewritten.append(updated_entry)

        next_payload = dict(payload)
        next_payload[self.collection] = rewritten
        handle.write_json(next_payload)

    def validate(self, ctx: "Context", items: Sequence[WorkItem[Mapping[str, object]]]) -> str | None:
        return None

    def _handle(self, ctx: "Context"):
        from .artifacts import ArtifactHandle, resolve_artifact_template

        return ArtifactHandle(
            name=self.artifact.name or self.collection,
            path=resolve_artifact_template(self.artifact, ctx),
            artifact=self.artifact,
        )


def _selector_mode(ctx: "Context", selector: Selector, worklist_name: str) -> str:
    parameter_name = selector.mode_param
    if parameter_name is None:
        return selector.default_mode
    raw_value = ctx.workflow_params.get(parameter_name)
    if raw_value is None:
        return selector.default_mode
    if not isinstance(raw_value, str):
        raise WorkflowExecutionError(
            f"worklist {worklist_name!r} selector parameter {parameter_name!r} "
            f"must be a string; received {raw_value!r}"
        )
    mode = raw_value.strip()
    if not mode:
        return selector.default_mode
    if mode not in selector.allowed_modes:
        allowed = ", ".join(selector.allowed_modes)
        raise WorkflowExecutionError(
            f"worklist {worklist_name!r} selector parameter {parameter_name!r} "
            f"received invalid mode {mode!r}; allowed modes: {allowed}"
        )
    return mode


def _item_indexes(items: Sequence[WorkItem[T]]) -> dict[str, int]:
    return {item.id: index for index, item in enumerate(items)}


def _require_item_id(
    items: Sequence[WorkItem[T]],
    item_indexes: Mapping[str, int],
    *,
    worklist_name: str,
    mode: str,
    parameter_name: str | None,
    item_id: str,
) -> int:
    index = item_indexes.get(item_id)
    if index is not None:
        return index
    known_ids = ", ".join(item.id for item in items) or "(none)"
    raise WorkflowExecutionError(
        f"worklist {worklist_name!r} selector mode {mode!r} parameter {parameter_name!r} "
        f"references unknown item id {item_id!r}; known ids: {known_ids}"
    )


def _build_work_item(
    item: T,
    *,
    item_id: Callable[[T], str] | str,
    title: Callable[[T], str] | str,
    status: Callable[[T], str | None] | str | None,
) -> WorkItem[T]:
    resolved_id = _resolve_selector_value(item, item_id, field_name="id")
    resolved_title = _resolve_selector_value(item, title, field_name="title")
    resolved_status = _resolve_optional_selector_value(item, status)
    item_dir_key = _resolve_optional_selector_value(item, "dir_key")
    return WorkItem(
        id=resolved_id,
        title=resolved_title,
        payload=item,
        status=resolved_status,
        dir_key=item_dir_key or _default_dir_key(resolved_id),
    )


def _resolve_selector_value(item: object, accessor: Callable[[Any], str] | str, *, field_name: str) -> str:
    if callable(accessor):
        value = accessor(item)
    else:
        if isinstance(item, Mapping):
            value = item.get(accessor)
        else:
            value = getattr(item, accessor, None)
    if not isinstance(value, str) or not value.strip():
        raise WorkflowExecutionError(f"worklist item {field_name!r} must resolve to a non-empty string")
    return value.strip()


def _resolve_optional_selector_value(
    item: object,
    accessor: Callable[[Any], str | None] | str | None,
) -> str | None:
    if accessor is None:
        return None
    if callable(accessor):
        value = accessor(item)
    else:
        if isinstance(item, Mapping):
            value = item.get(accessor)
        else:
            value = getattr(item, accessor, None)
    if value is None:
        return None
    if not isinstance(value, str):
        return str(value)
    normalized = value.strip()
    return normalized or None


def _default_dir_key(item_id: str) -> str:
    normalized = item_id.strip()
    if SAFE_DIR_KEY_RE.fullmatch(normalized):
        return normalized
    return f"_item-{normalized.encode('utf-8').hex()}"


def _duplicate_item_ids(items: Sequence[WorkItem[Any]]) -> tuple[str, ...]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for item in items:
        if item.id in seen and item.id not in duplicates:
            duplicates.append(item.id)
            continue
        seen.add(item.id)
    return tuple(duplicates)


def _replace_items_by_id(
    items: Sequence[WorkItem[T]],
    replacements: Sequence[WorkItem[T]],
) -> tuple[WorkItem[T], ...]:
    replacements_by_id = {item.id: item for item in replacements}
    return tuple(replacements_by_id.get(item.id, item) for item in items)


def _string_field(payload: Mapping[str, object], field_name: str, *, worklist_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise WorkflowExecutionError(
            f"worklist {worklist_name!r} item field {field_name!r} must be a non-empty string"
        )
    return value.strip()


def _optional_string_field(payload: Mapping[str, object], field_name: str | None) -> str | None:
    if field_name is None:
        return None
    value = payload.get(field_name)
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return str(value)


def _mapping_dir_key(payload: Mapping[str, object], *, item_id: str) -> str:
    dir_key = payload.get("dir_key")
    if isinstance(dir_key, str) and dir_key.strip():
        return dir_key.strip()
    return _default_dir_key(item_id)


def _validate_worklist_item_state_model(
    raw_state: type[BaseModel],
    *,
    worklist_name: str,
) -> None:
    if not inspect.isclass(raw_state) or not issubclass(raw_state, BaseModel):
        raise WorkflowValidationError(
            f"worklist {worklist_name!r} item_state must inherit from pydantic.BaseModel"
        )
    try:
        raw_state()
    except Exception as exc:
        raise WorkflowValidationError(
            f"worklist {worklist_name!r} item_state model {raw_state.__name__} must be instantiable with no arguments"
        ) from exc
    for field_name in raw_state.model_fields:
        if field_name in reserved_item_state_field_names():
            raise WorkflowValidationError(
                f"worklist {worklist_name!r} item_state field {field_name!r} conflicts with built-in scoped item runtime state"
            )


__all__ = [
    "Selection",
    "SelectionSnapshot",
    "Selector",
    "WorkItem",
    "WorkItemSnapshot",
    "Worklist",
    "WorklistRuntimeView",
    "WorklistSource",
]
