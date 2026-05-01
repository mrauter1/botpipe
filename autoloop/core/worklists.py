"""Worklist declarations, selection state, and artifact-backed sources."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
import inspect
from typing import TYPE_CHECKING, Any, Generic, Literal, Protocol, TypeVar

from pydantic import BaseModel

from .errors import WorkflowExecutionError, WorkflowValidationError

if TYPE_CHECKING:
    from .artifacts import Artifact
    from .context import Context


T = TypeVar("T")
SAFE_DIR_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


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
    mode_param: str | None = None
    default_mode: Literal["all", "single", "up_to"] = "all"
    allowed_modes: tuple[str, ...] = ("all",)

    def __post_init__(self) -> None:
        if not self.allowed_modes:
            raise ValueError("Selector.allowed_modes must contain at least one mode")
        if self.default_mode not in self.allowed_modes:
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


class WorklistSource(Protocol[T]):
    """Backend contract for materializing and persisting worklist items."""

    mutable: bool
    artifact_backed: bool

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

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("worklist name must be a non-empty string")
        if self.item_state_model is not None:
            _validate_worklist_item_state_model(self.item_state_model, worklist_name=self.name)

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
        selector: Selector = Selector(),
        item_state: type[BaseModel] | None = None,
    ) -> "Worklist[Mapping[str, object]]":
        source = _ArtifactWorklistSource(
            artifact=artifact,
            collection=collection,
            item_id=item_id,
            title=title,
            status=status,
        )
        return cls(name=name, source=source, selector=selector, item_state_model=item_state)

    @property
    def mutable(self) -> bool:
        return bool(getattr(self.source, "mutable", False))

    @property
    def artifact_backed(self) -> bool:
        return bool(getattr(self.source, "artifact_backed", False))

    def load_items(self, ctx: "Context") -> tuple[WorkItem[T], ...]:
        cached = ctx._get_cached_worklist_items(self.name)
        if cached is not None:
            return cached
        items = tuple(self.source.load(ctx))
        validation_error = self.source.validate(ctx, items)
        if validation_error:
            raise WorkflowExecutionError(f"worklist {self.name!r} is invalid: {validation_error}")
        duplicate_ids = _duplicate_item_ids(items)
        if duplicate_ids:
            duplicates = ", ".join(duplicate_ids)
            raise WorkflowExecutionError(
                f"worklist {self.name!r} contains duplicate item id(s): {duplicates}"
            )
        return ctx._cache_worklist_items(self.name, items)

    def initial_selection(self, ctx: "Context") -> Selection[T]:
        items = self.load_items(ctx)
        return Selection(
            worklist_name=self.name,
            mode=self._resolve_mode(ctx),
            items=self._select_items(items, ctx=ctx),
            explicit=self._has_explicit_selection(ctx),
            current_index=0,
        )

    def restore_selection(self, ctx: "Context", snapshot: SelectionSnapshot) -> Selection[T]:
        loaded_items = {item.id: item for item in self.load_items(ctx)}
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
        loaded_items = {item.id: item for item in self.load_items(ctx)}
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
        ctx._cache_worklist_items(self.name, updated_selection.items)
        return updated_selection

    def validate_items(self, ctx: "Context", items: Sequence[WorkItem[T]]) -> str | None:
        return self.source.validate(ctx, items)

    def _resolve_mode(self, ctx: "Context") -> str:
        if self.selector.mode_param is None:
            return self.selector.default_mode
        raw_mode = ctx.workflow_params.get(self.selector.mode_param, self.selector.default_mode)
        if not isinstance(raw_mode, str) or raw_mode not in self.selector.allowed_modes:
            allowed = ", ".join(self.selector.allowed_modes)
            raise WorkflowExecutionError(
                f"worklist {self.name!r} mode must be one of: {allowed}"
            )
        return raw_mode

    def _has_explicit_selection(self, ctx: "Context") -> bool:
        if self.selector.item_param is None:
            return False
        return self.selector.item_param in ctx.workflow_params

    def _select_items(self, items: tuple[WorkItem[T], ...], *, ctx: "Context") -> tuple[WorkItem[T], ...]:
        mode = self._resolve_mode(ctx)
        if self.selector.item_param is None or self.selector.item_param not in ctx.workflow_params:
            if mode == "single":
                return items[:1]
            return items

        requested_ids = _normalize_requested_item_ids(ctx.workflow_params[self.selector.item_param], worklist_name=self.name)
        item_map = {item.id: item for item in items}
        missing = [item_id for item_id in requested_ids if item_id not in item_map]
        if missing:
            raise WorkflowExecutionError(
                f"worklist {self.name!r} received unknown item id(s): {', '.join(missing)}"
            )
        selected_items = tuple(item_map[item_id] for item_id in requested_ids)
        if mode == "single":
            return selected_items[:1]
        return selected_items


@dataclass(frozen=True, slots=True)
class _StaticWorklistSource(Generic[T]):
    items: tuple[T, ...]
    item_id: Callable[[T], str] | str
    title: Callable[[T], str] | str
    status: Callable[[T], str | None] | str | None
    mutable: bool = False
    artifact_backed: bool = False

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
    mutable: bool = True
    artifact_backed: bool = True

    def load(self, ctx: "Context") -> Sequence[WorkItem[Mapping[str, object]]]:
        from .artifacts import ArtifactHandle, resolve_artifact_template

        handle = ArtifactHandle(
            name=self.artifact.name or self.collection,
            path=resolve_artifact_template(self.artifact, ctx),
            artifact=self.artifact,
        )
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
        from .artifacts import ArtifactHandle, resolve_artifact_template

        handle = ArtifactHandle(
            name=self.artifact.name or self.collection,
            path=resolve_artifact_template(self.artifact, ctx),
            artifact=self.artifact,
        )
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


def _normalize_requested_item_ids(value: object, *, worklist_name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            raise WorkflowExecutionError(f"worklist {worklist_name!r} item selector cannot be empty")
        return (normalized,)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        item_ids = tuple(str(item).strip() for item in value)
        if not item_ids or any(not item_id for item_id in item_ids):
            raise WorkflowExecutionError(f"worklist {worklist_name!r} item selector must contain non-empty ids")
        return item_ids
    raise WorkflowExecutionError(
        f"worklist {worklist_name!r} item selector must be a string or a sequence of strings"
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


__all__ = [
    "Selection",
    "SelectionSnapshot",
    "Selector",
    "WorkItem",
    "WorkItemSnapshot",
    "Worklist",
    "WorklistSource",
]
