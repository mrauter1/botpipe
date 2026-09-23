"""Recorded work selection and immutable versions of completion progress."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .artifacts import Artifact, ArtifactHandle, ArtifactStore


@dataclass(frozen=True)
class Selector:
    mode: str = "all"
    item: str | None = None
    start: str | None = None
    end: str | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"all", "single", "up_to", "from_to"}:
            raise ValueError(f"Unknown worklist selection mode: {self.mode}")
        for name in ("item", "start", "end"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"Selector {name} must be a nonempty string")
        if self.mode == "all" and any((self.item, self.start, self.end)):
            raise ValueError("Selection mode 'all' does not accept bounds")
        if self.mode == "single" and (self.start or self.end):
            raise ValueError("Selection mode 'single' accepts only item")
        if self.mode == "up_to" and self.start:
            raise ValueError("Selection mode 'up_to' does not accept start")
        if self.item and self.end:
            raise ValueError("Selection accepts item or end, not both")

    @classmethod
    def all(cls) -> Selector:
        return cls()

    @classmethod
    def single(cls, item: str | None = None) -> Selector:
        return cls("single", item=item)

    @classmethod
    def up_to(cls, item: str | None = None) -> Selector:
        return cls("up_to", end=item)

    @classmethod
    def from_to(cls, start: str | None = None, end: str | None = None) -> Selector:
        return cls("from_to", start=start, end=end)

    def to_record(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "item": self.item,
            "start": self.start,
            "end": self.end,
        }

    def select(self, ids: Sequence[str]) -> list[str]:
        positions = {item: index for index, item in enumerate(ids)}
        for value in (self.item, self.start, self.end):
            if value is not None and value not in positions:
                raise ValueError(
                    f"Unknown worklist item {value!r}; known ids: {', '.join(ids)}"
                )
        if self.mode == "all":
            return list(ids)
        if self.mode == "single":
            return [self.item] if self.item else list(ids[:1])
        end = self.end or self.item
        first = positions[self.start] if self.start else 0
        last = positions[end] + 1 if end else len(ids)
        if first >= last and ids:
            raise ValueError("Worklist selection start is after end")
        return list(ids[first:last])


@dataclass(frozen=True)
class WorkItem:
    id: str
    title: str
    payload: dict[str, Any]
    dir_key: str
    worklist: str
    status: str | None = None

    def to_record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "payload": deepcopy(self.payload),
            "dir_key": self.dir_key,
            "worklist": self.worklist,
            "status": self.status,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> WorkItem:
        return cls(**deepcopy(dict(record)))


def _run():
    from .runtime import current_run

    return current_run()


def _dir_key(item_id: str, explicit: Any = None) -> str:
    if explicit is not None:
        if not isinstance(explicit, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]*", explicit
        ):
            raise ValueError(f"Unsafe work item dir_key: {explicit!r}")
        return explicit
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", item_id):
        return item_id
    return "item-" + hashlib.sha256(item_id.encode()).hexdigest()[:24]


class Worklist:
    """An iterable whose original selected items are replayed on every resume.

    Completing an item changes ``artifact``, but never removes an item from this
    iterable. This ensures replay visits the same durable operations in order.
    """

    def __init__(
        self,
        *,
        handle: ArtifactHandle,
        document: dict[str, Any],
        items: Sequence[WorkItem],
        collection: str,
        item_id: str,
        title: str,
        status: str,
        name: str,
        scope: str,
    ):
        self.name = name
        self._artifact = handle
        self._document = deepcopy(document)
        self._items = tuple(items)
        self.collection = collection
        self.item_id = item_id
        self.title = title
        self.status = status
        self.scope = scope

    @classmethod
    def from_artifact(
        cls,
        handle: ArtifactHandle,
        *,
        collection: str = "items",
        item_id: str = "id",
        title: str = "title",
        status: str = "status",
        name: str = "items",
        selection: Selector | Mapping[str, Any] | str | None = None,
    ) -> Worklist:
        if not isinstance(handle, ArtifactHandle):
            raise TypeError(
                "Worklist.from_artifact requires an immutable ArtifactHandle"
            )
        for key, value in {
            "collection": collection,
            "item_id": item_id,
            "title": title,
            "status": status,
            "name": name,
        }.items():
            if not isinstance(value, str) or not value:
                raise ValueError(f"Worklist {key} must be a nonempty string")
        if selection is None:
            selector = Selector()
        elif isinstance(selection, Selector):
            selector = selection
        elif isinstance(selection, str):
            selector = Selector(selection)
        else:
            selector = Selector(**dict(selection))
        run = _run()
        inputs = {
            "artifact": handle.to_record(),
            "collection": collection,
            "item_id": item_id,
            "title": title,
            "status": status,
            "name": name,
            "selection": selector.to_record(),
        }

        def snapshot() -> dict[str, Any]:
            document = handle.read_json()
            if not isinstance(document, dict) or not isinstance(
                document.get(collection), list
            ):
                raise ValueError(f"Worklist artifact must contain list {collection!r}")
            items: dict[str, dict[str, Any]] = {}
            directories: set[str] = set()
            for payload in document[collection]:
                if not isinstance(payload, dict):
                    raise ValueError("Worklist items must be objects")
                identity, label = payload.get(item_id), payload.get(title)
                if not isinstance(identity, str) or not identity.strip():
                    raise ValueError(
                        f"Worklist item {item_id!r} must be a nonempty string"
                    )
                if not isinstance(label, str) or not label.strip():
                    raise ValueError(
                        f"Worklist item {title!r} must be a nonempty string"
                    )
                if identity in items:
                    raise ValueError(f"Duplicate worklist item id: {identity}")
                progress = payload.get(status)
                if progress is not None and not isinstance(progress, str):
                    raise ValueError(
                        f"Worklist item {status!r} must be a string or null"
                    )
                directory = _dir_key(identity, payload.get("dir_key"))
                if directory in directories:
                    raise ValueError(f"Duplicate worklist dir_key: {directory}")
                directories.add(directory)
                items[identity] = WorkItem(
                    identity, label, deepcopy(payload), directory, name, progress
                ).to_record()
            selected = selector.select(list(items))
            return {
                "document": document,
                "items": [items[identity] for identity in selected],
            }

        recorded = run.operation("worklist.select", inputs, snapshot, retry_safe=True)
        return cls(
            handle=handle,
            document=recorded["document"],
            items=[WorkItem.from_record(item) for item in recorded["items"]],
            collection=collection,
            item_id=item_id,
            title=title,
            status=status,
            name=name,
            scope=run.scope,
        )

    def __iter__(self) -> Iterator[WorkItem]:
        # Payload copies prevent a caller's edits from changing replay inputs.
        return iter(
            tuple(WorkItem.from_record(item.to_record()) for item in self._items)
        )

    def __len__(self) -> int:
        return len(self._items)

    @property
    def artifact(self) -> ArtifactHandle:
        return self._artifact

    def complete(self, item: WorkItem, *, status: str = "completed") -> ArtifactHandle:
        if (
            not isinstance(item, WorkItem)
            or item.worklist != self.name
            or item.id not in {entry.id for entry in self._items}
        ):
            raise ValueError("Item is not selected in this worklist")
        if not isinstance(status, str) or not status:
            raise ValueError("Completion status must be a nonempty string")
        run = _run()
        if run.scope != self.scope:
            raise ValueError("Complete a worklist in the scope that created it")
        inputs = {
            "worklist": self.name,
            "artifact": self._artifact.to_record(),
            "collection": self.collection,
            "item_id": self.item_id,
            "item": item.id,
            "status_field": self.status,
            "status": status,
        }
        document = deepcopy(self._document)
        for payload in document[self.collection]:
            if payload[self.item_id] == item.id:
                payload[self.status] = status
        operation_key = (
            "worklist:"
            + hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
        )

        def publish() -> dict[str, Any]:
            store = ArtifactStore(
                run.folder, workspace=run.workspace, allowed_roots=(run.task_folder,)
            )
            declaration = Artifact.json(
                self._artifact.source_path,
                name=self._artifact.name,
                schema=self._artifact.schema,
                required=True,
            )
            handle = store.publish(declaration, document, operation_key)
            store.materialize(handle)
            return handle.to_record()

        record = run.operation("worklist.complete", inputs, publish, retry_safe=True)
        self._artifact = ArtifactHandle.from_record(record)
        self._document = document
        return self._artifact


__all__ = ["Selector", "WorkItem", "Worklist"]
