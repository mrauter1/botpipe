"""Lazy durable conversation handles.

Sessions carry identity and continuation state. Provider execution lives in
``operations.py``; constructing a Session never resolves configuration or
touches the state store.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .errors import BotpipeError
from .providers import ProviderContinuation


class SessionError(BotpipeError):
    """Base class for conversation identity and ownership failures."""


class SessionAffinityError(SessionError):
    """A conversation was used with an incompatible native environment."""


class SessionBusy(SessionError):
    """Another unresolved operation currently owns the conversation."""


class SessionHistoryConflict(SessionError):
    """The conversation advanced beyond the revision expected by this handle."""


@dataclass(frozen=True)
class SessionLease:
    session_id: str
    revision: int
    continuation: ProviderContinuation | None


def _safe_key(value: str, label: str = "Session key") -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a nonempty string")
    if len(value) > 1000 or "\x00" in value:
        raise ValueError(f"{label} is invalid")
    return value


def _plain_affinity(value: Mapping[str, Any] | None) -> dict[str, Any]:
    result = {} if value is None else dict(value)
    if not all(type(key) is str for key in result):
        raise TypeError("Session affinity keys must be strings")
    try:
        encoded = json.dumps(
            result, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError) as exc:
        raise TypeError("Session affinity must contain JSON values") from exc
    return json.loads(encoded)


class Session:
    """A lazy logical conversation reference."""

    def __init__(self) -> None:
        # This token is only a durable reference token when the handle itself is
        # an input (for example a standalone operation). It is never the
        # canonical conversation identity and is excluded from workflow alias
        # matching, which is based on stable operation position.
        self._token = uuid.uuid4().hex
        self._scope = "anonymous"
        self._key: str | None = None
        self._item: tuple[str, str] | None = None
        self._requested_id: str | None = None
        self._requested_state_dir: Path | None = None
        self._canonical_id: str | None = None
        self._store: str | None = None
        self._affinity: dict[str, Any] | None = None
        self._revision: int | None = None
        self._aliases: set[tuple[str, str]] = set()
        self._guard = threading.RLock()

    @classmethod
    def task(cls, key: str = "default") -> Session:
        result = cls()
        result._scope = "task"
        result._key = _safe_key(key)
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
        result._key = _safe_key(key)
        result._item = (worklist, item_id)
        return result

    @classmethod
    def load(cls, session_id: str, *, state_dir: str | Path | None = None) -> Session:
        if not isinstance(session_id, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}", session_id
        ):
            raise ValueError("session_id must be a safe nonempty identifier")
        result = cls()
        result._scope = "loaded"
        result._requested_id = session_id
        result._requested_state_dir = (
            Path(state_dir).expanduser() if state_dir is not None else None
        )
        return result

    @property
    def id(self) -> str | None:
        """The canonical identity, once selected for use."""

        return self._canonical_id

    @property
    def revision(self) -> int | None:
        return self._revision

    @property
    def scope(self) -> str:
        return self._scope

    def _descriptor(self, ctx: Any) -> dict[str, Any]:
        descriptor: dict[str, Any] = {"scope": self._scope}
        if self._scope == "task":
            descriptor.update(task_id=ctx.task_id, key=self._key)
        elif self._scope == "work_item":
            descriptor.update(
                task_id=ctx.task_id,
                worklist=self._item[0],
                item=self._item[1],
                key=self._key,
            )
        elif self._scope == "loaded":
            descriptor["session_id"] = self._requested_id
        return descriptor

    def bind(
        self,
        ctx: Any,
        backend_name: str,
        workspace: str | Path | None,
        affinity: Mapping[str, Any] | None = None,
    ) -> str:
        """Bind on first selected use and record the handle alias in this scope."""

        _safe_key(backend_name, "backend_name")
        store = str(ctx.journal.path.resolve())
        if self._requested_state_dir is not None:
            actual_state = Path(ctx.client.state_dir).resolve()
            requested_state = self._requested_state_dir.resolve()
            if actual_state != requested_state:
                raise SessionAffinityError(
                    f"Session {self._requested_id} belongs to state directory "
                    f"{requested_state}, not {actual_state}"
                )
        effective_affinity = _plain_affinity(affinity)
        effective_affinity.update(
            backend=backend_name,
            workspace=str(Path(workspace or ctx.workspace).resolve()),
        )
        descriptor = self._descriptor(ctx)
        alias = (ctx.execution_id, ctx.scope)

        with self._guard:
            if self._store is not None and self._store != store:
                raise SessionAffinityError(
                    "A bound Session cannot move to a different state store"
                )
            if self._affinity is not None and self._affinity != effective_affinity:
                raise SessionAffinityError(
                    "Session backend, account, model, or workspace affinity changed"
                )
            if alias in self._aliases:
                assert self._canonical_id is not None
                return self._canonical_id

            inputs = {"session": descriptor, "affinity": effective_affinity}

            def establish() -> dict[str, Any]:
                canonical = self._canonical_id
                if canonical is None:
                    if self._scope == "loaded":
                        canonical = self._requested_id
                    elif self._scope in {"task", "work_item"}:
                        seed = json.dumps(
                            {"store": store, "descriptor": descriptor},
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        canonical = "session-" + hashlib.sha256(
                            seed.encode()
                        ).hexdigest()
                    else:
                        canonical = "session-" + uuid.uuid4().hex
                record = ctx.journal.bind_session(
                    canonical,
                    scope=descriptor,
                    affinity=effective_affinity,
                    require_existing=self._scope == "loaded",
                )
                return {"session_id": canonical, "revision": record["revision"]}

            bound = ctx.operation(
                "session_alias",
                inputs,
                establish,
                retry_safe=True,
                name="session",
            )
            if (
                type(bound) is not dict
                or type(bound.get("session_id")) is not str
                or type(bound.get("revision")) is not int
            ):
                raise SessionError("Recorded session alias is malformed")
            record = ctx.journal.bind_session(
                bound["session_id"],
                scope=descriptor,
                affinity=effective_affinity,
                require_existing=True,
            )
            self._canonical_id = bound["session_id"]
            self._revision = bound["revision"]
            self._store = store
            self._affinity = effective_affinity
            self._aliases.add(alias)
            if record["revision"] < self._revision:
                raise SessionError("Recorded session revision moved backwards")
            return self._canonical_id

    def claim(self, ctx: Any, operation_id: str | None = None) -> SessionLease:
        """Acquire exclusive ownership before an attempt may dispatch."""

        with self._guard:
            if self._canonical_id is None or self._revision is None:
                raise SessionError("Session must be bound before it can be claimed")
            operation_id = operation_id or ctx.operation_id
            if not isinstance(operation_id, str) or not operation_id:
                raise SessionError("A durable operation identity is required")
            record = ctx.journal.claim_session(
                self._canonical_id,
                run_id=ctx.run_id,
                operation_id=operation_id,
                expected_revision=self._revision,
                affinity=self._affinity,
            )
            return SessionLease(
                self._canonical_id,
                record["revision"],
                record.get("continuation"),
            )

    def advancement(
        self, continuation: ProviderContinuation | None = None
    ) -> dict[str, Any]:
        """Describe an atomic response/session advancement for Journal.response."""

        with self._guard:
            if self._canonical_id is None or self._revision is None:
                raise SessionError("Session must be bound before it can advance")
            return {
                "session_id": self._canonical_id,
                "expected_revision": self._revision,
                "continuation": continuation,
            }

    def advanced(self, revision: int) -> None:
        if type(revision) is not int or revision < 1:
            raise SessionError("Committed session revision is malformed")
        with self._guard:
            if self._revision is not None and revision < self._revision:
                raise SessionHistoryConflict("Session revision moved backwards")
            self._revision = revision

    def observe_operation(self, ctx: Any, operation_id: str) -> None:
        """Apply the revision recorded by a replayed provider operation."""

        record = ctx.journal.get(operation_id)
        if record is None or record.get("session_id") != self._canonical_id:
            return
        revision = record.get("session_revision")
        if revision is not None:
            self.advanced(revision)

    def release(self, ctx: Any, operation_id: str | None = None) -> None:
        """Release after authoritative stopped/no-turn evidence."""

        with self._guard:
            if self._canonical_id is None:
                return
            ctx.journal.release_session(
                self._canonical_id,
                run_id=ctx.run_id,
                operation_id=operation_id or ctx.operation_id,
            )

    def to_record(self) -> dict[str, Any]:
        state_dir = self._requested_state_dir
        if state_dir is None and self._store is not None:
            state_dir = Path(self._store).parent
        return {
            "version": 1,
            "token": self._token,
            "scope": self._scope,
            "key": self._key,
            "item": list(self._item) if self._item is not None else None,
            "session_id": self._canonical_id or self._requested_id,
            "state_dir": str(state_dir) if state_dir is not None else None,
            "affinity": self._affinity,
            "revision": self._revision,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> Session:
        expected = {
            "version", "token", "scope", "key", "item", "session_id",
            "state_dir", "affinity", "revision",
        }
        if type(record) is not dict or set(record) != expected:
            raise TypeError("Malformed durable Session reference")
        if record["version"] != 1 or record["scope"] not in {
            "anonymous", "task", "work_item", "loaded",
        }:
            raise TypeError("Unsupported durable Session reference")
        token = record["token"]
        if type(token) is not str or not re.fullmatch(r"[0-9a-f]{32}", token):
            raise TypeError("Malformed Session reference token")
        result = cls()
        result._token = token
        result._scope = record["scope"]
        result._key = record["key"]
        item = record["item"]
        if item is not None:
            if type(item) is not list or len(item) != 2 or not all(
                type(value) is str and value for value in item
            ):
                raise TypeError("Malformed Session work-item reference")
            result._item = (item[0], item[1])
        session_id = record["session_id"]
        if session_id is not None and type(session_id) is not str:
            raise TypeError("Malformed Session identity")
        result._requested_id = session_id if result._scope == "loaded" else None
        result._canonical_id = session_id
        state_dir = record["state_dir"]
        if state_dir is not None and type(state_dir) is not str:
            raise TypeError("Malformed Session state directory")
        result._requested_state_dir = Path(state_dir) if state_dir else None
        affinity = record["affinity"]
        result._affinity = None if affinity is None else _plain_affinity(affinity)
        revision = record["revision"]
        if revision is not None and (type(revision) is not int or revision < 0):
            raise TypeError("Malformed Session revision")
        result._revision = revision
        if result._scope == "anonymous" and (
            result._key is not None or result._item is not None
        ):
            raise TypeError("Malformed anonymous Session reference")
        if result._scope == "task" and (
            not isinstance(result._key, str) or not result._key
        ):
            raise TypeError("Malformed task Session reference")
        if result._scope == "work_item" and (
            not isinstance(result._key, str)
            or not result._key
            or result._item is None
        ):
            raise TypeError("Malformed work-item Session reference")
        if result._scope == "loaded" and result._requested_id is None:
            raise TypeError("Loaded Session reference requires a session identity")
        return result
