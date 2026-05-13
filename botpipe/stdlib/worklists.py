"""Canonical progress-backed worklist helpers."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from botpipe.core.artifacts import Artifact, ArtifactHandle, resolve_artifact_template
from botpipe.core.errors import WorkflowExecutionError
from botpipe.core.worklists import Selector, WorkItem, Worklist, WorklistSource

if TYPE_CHECKING:
    from botpipe.core.context import Context


SAFE_DIR_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class WorkStatus(str, Enum):
    planned = "planned"
    in_progress = "in_progress"
    blocked = "blocked"
    completed = "completed"
    failed = "failed"


def _normalize_status_token(raw: str) -> str:
    return raw.strip().lower().replace(" ", "_")


@dataclass(frozen=True, slots=True)
class WorkStatusPolicy:
    extra_statuses: tuple[str, ...] = ()
    initial: str = WorkStatus.planned.value
    active: str = WorkStatus.in_progress.value
    success: str = WorkStatus.completed.value
    blocked: str = WorkStatus.blocked.value
    failed: str = WorkStatus.failed.value
    terminal: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                WorkStatus.completed.value,
                WorkStatus.blocked.value,
                WorkStatus.failed.value,
            }
        )
    )
    aliases: Mapping[str, str] = field(
        default_factory=lambda: {
            "todo": "planned",
            "queued": "planned",
            "started": "in_progress",
            "in-progress": "in_progress",
            "done": "completed",
            "complete": "completed",
            "finished": "completed",
        }
    )

    def __post_init__(self) -> None:
        normalized_statuses: list[str] = []
        seen_statuses: set[str] = set()
        for raw_status in (
            WorkStatus.planned.value,
            WorkStatus.in_progress.value,
            WorkStatus.blocked.value,
            WorkStatus.completed.value,
            WorkStatus.failed.value,
            *self.extra_statuses,
        ):
            if not isinstance(raw_status, str):
                raise ValueError("work statuses must be strings")
            normalized = _normalize_status_token(raw_status)
            if not normalized:
                raise ValueError("work statuses must be non-empty strings")
            if normalized in seen_statuses:
                raise ValueError(f"duplicate work status {normalized!r}")
            seen_statuses.add(normalized)
            normalized_statuses.append(normalized)
        if not normalized_statuses:
            raise ValueError("WorkStatusPolicy must define at least one supported status")

        object.__setattr__(self, "extra_statuses", tuple(normalized_statuses[5:]))
        object.__setattr__(self, "initial", self._normalize_role_status("initial", self.initial))
        object.__setattr__(self, "active", self._normalize_role_status("active", self.active))
        object.__setattr__(self, "success", self._normalize_role_status("success", self.success))
        object.__setattr__(self, "blocked", self._normalize_role_status("blocked", self.blocked))
        object.__setattr__(self, "failed", self._normalize_role_status("failed", self.failed))

        statuses = self.statuses
        for field_name in ("initial", "active", "success", "blocked", "failed"):
            value = getattr(self, field_name)
            if value not in statuses:
                raise ValueError(f"WorkStatusPolicy.{field_name} must be included in statuses")

        normalized_terminal: set[str] = set()
        for raw_status in self.terminal:
            if not isinstance(raw_status, str):
                raise ValueError("WorkStatusPolicy.terminal must contain only strings")
            normalized = _normalize_status_token(raw_status)
            if not normalized:
                raise ValueError("WorkStatusPolicy.terminal must not contain empty values")
            if normalized not in statuses:
                raise ValueError(f"unsupported terminal work status {normalized!r}")
            normalized_terminal.add(normalized)
        object.__setattr__(self, "terminal", frozenset(normalized_terminal))

        normalized_aliases: dict[str, str] = {}
        for raw_key, raw_value in self.aliases.items():
            if not isinstance(raw_key, str) or not isinstance(raw_value, str):
                raise ValueError("WorkStatusPolicy.aliases must map strings to strings")
            key = _normalize_status_token(raw_key)
            value = _normalize_status_token(raw_value)
            if not key or not value:
                raise ValueError("WorkStatusPolicy.aliases must not contain empty keys or values")
            if value not in statuses:
                raise ValueError(f"alias {key!r} resolves to unsupported status {value!r}")
            normalized_aliases[key] = value
        object.__setattr__(self, "aliases", dict(normalized_aliases))

    @property
    def statuses(self) -> tuple[str, ...]:
        return (
            WorkStatus.planned.value,
            WorkStatus.in_progress.value,
            WorkStatus.blocked.value,
            WorkStatus.completed.value,
            WorkStatus.failed.value,
            *self.extra_statuses,
        )

    def normalize(self, raw: str | None) -> str:
        if raw is None:
            return self.initial
        normalized = _normalize_status_token(raw)
        if not normalized:
            return self.initial
        resolved = self.aliases.get(normalized, normalized)
        if resolved not in self.statuses:
            raise ValueError(f"unsupported work status {resolved!r}")
        return resolved

    def is_supported(self, raw: str | None) -> bool:
        try:
            self.normalize(raw)
        except ValueError:
            return False
        return True

    def is_terminal(self, raw: str | None) -> bool:
        return self.normalize(raw) in self.terminal

    @staticmethod
    def _normalize_role_status(field_name: str, raw: str) -> str:
        if not isinstance(raw, str):
            raise ValueError(f"WorkStatusPolicy.{field_name} must be a string")
        normalized = _normalize_status_token(raw)
        if not normalized:
            raise ValueError(f"WorkStatusPolicy.{field_name} must not be empty")
        return normalized


SKIPPABLE_WORK_STATUS_POLICY = WorkStatusPolicy(
    extra_statuses=("skipped",),
    terminal=frozenset(
        {
            WorkStatus.completed.value,
            WorkStatus.blocked.value,
            WorkStatus.failed.value,
            "skipped",
        }
    ),
)


class ProgressItem(BaseModel):
    id: str
    title: str
    status: str = WorkStatus.planned.value


ItemT = TypeVar("ItemT", bound=ProgressItem)


class ProgressBoard(BaseModel, Generic[ItemT]):
    items: list[ItemT]


@dataclass(frozen=True, slots=True)
class ProgressJsonCollectionSource(WorklistSource[Mapping[str, Any]]):
    artifact: Artifact
    model: type[BaseModel] | None = None
    fallback: Callable[[Context], Mapping[str, Any] | BaseModel] | None = None
    write_fallback: bool = True
    status_policy: WorkStatusPolicy = field(default_factory=WorkStatusPolicy)

    mutable: bool = True
    artifact_backed: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, Artifact):
            raise TypeError("ProgressJsonCollectionSource.artifact must be an Artifact")
        if self.model is not None and (
            not isinstance(self.model, type) or not issubclass(self.model, BaseModel)
        ):
            raise TypeError("ProgressJsonCollectionSource.model must inherit from pydantic.BaseModel")
        if self.fallback is not None and not callable(self.fallback):
            raise TypeError("ProgressJsonCollectionSource.fallback must be callable")
        if not isinstance(self.status_policy, WorkStatusPolicy):
            raise TypeError("ProgressJsonCollectionSource.status_policy must be a WorkStatusPolicy")

    def ensure(self, ctx: "Context") -> None:
        handle = self._handle(ctx)
        if handle.exists() or self.fallback is None or not self.write_fallback:
            return None
        payload = self._materialize_fallback(ctx, handle.path)
        handle.write_json(payload)
        return None

    def load(self, ctx: "Context") -> Sequence[WorkItem[Mapping[str, Any]]]:
        handle = self._handle(ctx)
        if handle.exists():
            payload = self._read_existing_payload(handle)
            return self._items_from_payload(payload, handle.path)
        if self.fallback is None:
            raise WorkflowExecutionError(
                f"worklist artifact for {self.artifact.name or 'items'!r} is missing at {handle.path}"
            )
        payload = self._materialize_fallback(ctx, handle.path)
        if self.write_fallback:
            handle.write_json(payload)
        return self._items_from_payload(payload, handle.path)

    def save(self, ctx: "Context", items: Sequence[WorkItem[Mapping[str, Any]]]) -> None:
        handle = self._handle(ctx)
        if handle.exists():
            payload = self._read_existing_payload(handle, canonicalize_with_model=False)
        elif self.fallback is not None:
            payload = self._materialize_fallback(ctx, handle.path)
        else:
            raise WorkflowExecutionError(
                f"worklist artifact for {self.artifact.name or 'items'!r} is missing at {handle.path}"
            )

        raw_items = payload.get("items")
        if not isinstance(raw_items, list):
            raise WorkflowExecutionError(
                f"worklist artifact {handle.path} must contain an 'items' list"
            )

        status_by_id = {item.id: self._normalize_status(item.status, path=handle.path, item_id=item.id) for item in items}
        rewritten_items: list[dict[str, Any]] = []
        for entry in raw_items:
            if not isinstance(entry, Mapping):
                raise WorkflowExecutionError(
                    f"worklist artifact {handle.path} has non-object entry in 'items'"
                )
            updated_entry = dict(entry)
            item_id = self._require_item_field(updated_entry, "id", path=handle.path)
            if item_id in status_by_id:
                updated_entry["status"] = status_by_id[item_id]
            rewritten_items.append(updated_entry)

        next_payload = dict(payload)
        next_payload["items"] = rewritten_items
        if self.model is not None:
            self._validate_model(next_payload, path=handle.path)
        handle.write_json(next_payload)

    def validate(self, ctx: "Context", items: Sequence[WorkItem[Mapping[str, Any]]]) -> str | None:
        duplicate_ids = self._duplicate_ids(items)
        if duplicate_ids:
            return "duplicate item id(s): " + ", ".join(duplicate_ids)
        for item in items:
            if not isinstance(item.id, str) or not item.id.strip():
                return "item id must be a non-empty string"
            if not isinstance(item.title, str) or not item.title.strip():
                return f"item {item.id!r} title must be a non-empty string"
            if not self.status_policy.is_supported(item.status):
                return f"item {item.id!r} has unsupported status {item.status!r}"
        return None

    def _handle(self, ctx: "Context") -> ArtifactHandle:
        return ArtifactHandle(
            name=self.artifact.name or "items",
            path=resolve_artifact_template(self.artifact, ctx),
            artifact=self.artifact,
        )

    def _read_existing_payload(
        self,
        handle: ArtifactHandle,
        *,
        canonicalize_with_model: bool = True,
    ) -> dict[str, Any]:
        try:
            payload = handle.read_json()
        except json.JSONDecodeError as exc:
            raise WorkflowExecutionError(
                f"worklist artifact {handle.path} contains invalid JSON: {exc.msg}"
            ) from exc
        if not isinstance(payload, Mapping):
            raise WorkflowExecutionError(f"worklist artifact {handle.path} must contain a top-level object")
        candidate = dict(payload)
        if self.model is not None:
            validated = self._validate_model(candidate, path=handle.path)
            if canonicalize_with_model:
                return validated.model_dump(mode="json")
        return candidate

    def _materialize_fallback(self, ctx: "Context", path: Path) -> dict[str, Any]:
        assert self.fallback is not None
        raw_payload = self.fallback(ctx)
        if isinstance(raw_payload, BaseModel):
            candidate = raw_payload.model_dump(mode="json")
        elif isinstance(raw_payload, Mapping):
            candidate = dict(raw_payload)
        else:
            raise WorkflowExecutionError(
                f"worklist fallback for artifact {path} must return a mapping or BaseModel; received {type(raw_payload).__name__}"
            )
        normalized = self._normalize_fallback_payload(candidate, path=path)
        if self.model is not None:
            validated = self._validate_model(normalized, path=path)
            return validated.model_dump(mode="json")
        return normalized

    def _normalize_fallback_payload(self, payload: Mapping[str, Any], *, path: Path) -> dict[str, Any]:
        raw_items = payload.get("items")
        if not isinstance(raw_items, list):
            raise WorkflowExecutionError(f"worklist fallback for artifact {path} must contain an 'items' list")
        normalized_items: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for entry in raw_items:
            if not isinstance(entry, Mapping):
                raise WorkflowExecutionError(f"worklist fallback for artifact {path} has non-object entry in 'items'")
            item_payload = dict(entry)
            item_id = self._require_item_field(item_payload, "id", path=path)
            if item_id in seen_ids:
                raise WorkflowExecutionError(
                    f"worklist fallback for artifact {path} contains duplicate item id {item_id!r} in 'items'"
                )
            seen_ids.add(item_id)
            self._require_item_field(item_payload, "title", path=path, item_id=item_id)
            item_payload["status"] = self._normalize_status(item_payload.get("status"), path=path, item_id=item_id)
            normalized_items.append(item_payload)
        next_payload = dict(payload)
        next_payload["items"] = normalized_items
        return next_payload

    def _items_from_payload(self, payload: Mapping[str, Any], path: Path) -> tuple[WorkItem[Mapping[str, Any]], ...]:
        raw_items = payload.get("items")
        if not isinstance(raw_items, list):
            raise WorkflowExecutionError(f"worklist artifact {path} must contain an 'items' list")
        items: list[WorkItem[Mapping[str, Any]]] = []
        seen_ids: set[str] = set()
        for entry in raw_items:
            if not isinstance(entry, Mapping):
                raise WorkflowExecutionError(f"worklist artifact {path} has non-object entry in 'items'")
            item_payload = dict(entry)
            item_id = self._require_item_field(item_payload, "id", path=path)
            if item_id in seen_ids:
                raise WorkflowExecutionError(
                    f"worklist artifact {path} contains duplicate item id {item_id!r} in 'items'"
                )
            seen_ids.add(item_id)
            title = self._require_item_field(item_payload, "title", path=path, item_id=item_id)
            status = self._normalize_status(item_payload.get("status"), path=path, item_id=item_id)
            item_payload["status"] = status
            items.append(
                WorkItem(
                    id=item_id,
                    title=title,
                    payload=item_payload,
                    status=status,
                    dir_key=self._dir_key(item_payload, item_id=item_id),
                )
            )
        return tuple(items)

    def _validate_model(self, payload: Mapping[str, Any], *, path: Path) -> BaseModel:
        assert self.model is not None
        try:
            return self.model.model_validate(payload)
        except ValidationError as exc:
            raise WorkflowExecutionError(
                f"worklist artifact {path} failed schema validation: {exc}"
            ) from exc

    def _normalize_status(self, raw: Any, *, path: Path, item_id: str) -> str:
        try:
            if raw is None:
                return self.status_policy.normalize(None)
            if not isinstance(raw, str):
                raise WorkflowExecutionError(
                    f"worklist artifact {path} item {item_id!r} field 'status' must be a string"
                )
            return self.status_policy.normalize(raw)
        except ValueError as exc:
            raise WorkflowExecutionError(
                f"worklist artifact {path} item {item_id!r} has unsupported status {raw!r}: {exc}"
            ) from exc

    @staticmethod
    def _require_item_field(
        payload: Mapping[str, Any],
        field_name: str,
        *,
        path: Path,
        item_id: str | None = None,
    ) -> str:
        value = payload.get(field_name)
        if not isinstance(value, str) or not value.strip():
            item_prefix = f" item {item_id!r}" if item_id is not None else ""
            raise WorkflowExecutionError(
                f"worklist artifact {path}{item_prefix} field {field_name!r} must be a non-empty string"
            )
        return value.strip()

    @staticmethod
    def _duplicate_ids(items: Sequence[WorkItem[Mapping[str, Any]]]) -> tuple[str, ...]:
        seen: set[str] = set()
        duplicates: list[str] = []
        for item in items:
            if item.id in seen and item.id not in duplicates:
                duplicates.append(item.id)
                continue
            seen.add(item.id)
        return tuple(duplicates)

    @staticmethod
    def _dir_key(payload: Mapping[str, Any], *, item_id: str) -> str:
        dir_key = payload.get("dir_key")
        if isinstance(dir_key, str) and dir_key.strip():
            return dir_key.strip()
        normalized = item_id.strip()
        if SAFE_DIR_KEY_RE.fullmatch(normalized):
            return normalized
        return f"_item-{normalized.encode('utf-8').hex()}"


def progress_selector(name: str) -> Selector:
    return Selector(
        item_param=name,
        start_param=f"from_{name}",
        end_param=f"to_{name}",
        mode_param=f"{name}_mode",
        default_mode="all",
        allowed_modes=("all", "single", "up_to", "from_to"),
    )


def progress_artifact_worklist(
    name: str,
    *,
    model: type[BaseModel] | None = None,
    fallback: Callable[[Context], Mapping[str, Any] | BaseModel] | None = None,
    artifact: Artifact | None = None,
    selector: Selector | None = None,
    status_policy: WorkStatusPolicy | None = None,
    write_fallback: bool = True,
    item_state: type[BaseModel] | None = None,
) -> Worklist[Mapping[str, Any]]:
    source_artifact = artifact or Artifact.json(
        f"{{{{ workflow.folder }}}}/worklists/{name}.json",
        schema=model,
        required=False,
        name=f"{name}_board",
    )
    source = ProgressJsonCollectionSource(
        artifact=source_artifact,
        model=model,
        fallback=fallback,
        write_fallback=write_fallback,
        status_policy=status_policy or WorkStatusPolicy(),
    )
    return Worklist(
        name=name,
        source=source,
        selector=selector or progress_selector(name),
        item_state_model=item_state,
    )


__all__ = [
    "ItemT",
    "ProgressBoard",
    "ProgressItem",
    "ProgressJsonCollectionSource",
    "SKIPPABLE_WORK_STATUS_POLICY",
    "WorkStatus",
    "WorkStatusPolicy",
    "progress_artifact_worklist",
    "progress_selector",
]
