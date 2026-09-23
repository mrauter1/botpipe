"""Lazy conversation identities for provider operations."""

from __future__ import annotations

import hashlib
import threading
import uuid
import weakref
from typing import Any

from . import codec
from .errors import SessionError


class Session:
    """A lazy conversation handle.

    Construction performs no I/O.  ``task`` and ``work_item`` describe stable
    identities; the coordinator binds them when the first turn begins.
    """

    def __init__(self) -> None:
        self._scope = "run"
        self._key = "default"
        self._direct_key = uuid.uuid4().hex
        self._item: tuple[str, str] | None = None
        self._bindings: weakref.WeakKeyDictionary[Any, str] = (
            weakref.WeakKeyDictionary()
        )
        self._canonical: str | None = None
        self._guard = threading.RLock()
        self._turn_lock = threading.Lock()

    @classmethod
    def task(cls, key: str = "default") -> Session:
        result = cls()
        result._scope = "task"
        result._key = _key(key)
        return result

    @classmethod
    def work_item(cls, item: Any, key: str = "default") -> Session:
        worklist = getattr(item, "worklist", None)
        item_id = getattr(item, "id", None)
        if not isinstance(worklist, str) or not worklist:
            raise TypeError("work_item requires a WorkItem with a worklist identity")
        if not isinstance(item_id, str) or not item_id:
            raise TypeError("work_item requires a WorkItem with an item identity")
        result = cls()
        result._scope = "work_item"
        result._key = _key(key)
        result._item = (worklist, item_id)
        return result

    def bind(self, ctx: Any) -> str:
        """Bind this handle at its first durable operation position."""
        with self._guard:
            if ctx in self._bindings:
                return self._bindings[ctx]
            identity: dict[str, Any] = {
                "scope": self._scope,
                "key": self._key,
                "provider": ctx.client.provider_name,
            }
            if self._scope != "direct":
                identity.update(workflow=ctx.definition.name, task=ctx.task_id)
            if self._scope == "run":
                identity.update(
                    run=ctx.run_id, scope_path=ctx.scope, ordinal=ctx.ordinal
                )
            elif self._scope == "work_item":
                assert self._item is not None
                identity.update(worklist=self._item[0], item=self._item[1])
            proposed = (
                self._canonical
                or hashlib.sha256(codec.dumps(identity).encode()).hexdigest()
            )
            value = ctx.operation(
                "session", identity, lambda: proposed, retry_safe=True
            )
            if self._canonical is not None and value != self._canonical:
                raise SessionError("Session history resolved to another conversation")
            self._canonical = value
            self._bindings[ctx] = value
            return value

    def descriptor(self, *, direct: bool = False) -> dict[str, Any]:
        if direct:
            return {"scope": "direct", "key": self._direct_key, "item": None}
        return {"scope": self._scope, "key": self._key, "item": self._item}

    @classmethod
    def from_descriptor(cls, value: dict[str, Any]) -> Session:
        result = cls()
        result._scope = value["scope"]
        result._key = _key(value["key"])
        if result._scope == "direct":
            result._direct_key = result._key
        item = value.get("item")
        result._item = tuple(item) if item is not None else None
        return result


def _key(value: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("Session key must be a nonempty string without NUL")
    return value


__all__ = ["Session", "SessionError"]
