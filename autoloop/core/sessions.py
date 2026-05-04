"""Session continuity and key helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Literal
from uuid import uuid4

if TYPE_CHECKING:
    from .context import Context


ContinuityKind = Literal["run", "task", "work_item", "fresh", "key"]
SessionKeyDomain = Literal["run", "task", "work_item", "fresh", "explicit_scope", "explicit_key"]
DEFAULT_SESSION_NAME = "global"
LEGACY_DEFAULT_SESSION_NAME = "default"


def canonical_session_slot_name(name: str) -> str:
    """Normalize persisted legacy session slot names to the canonical slot."""

    if name == LEGACY_DEFAULT_SESSION_NAME:
        return DEFAULT_SESSION_NAME
    return name


@dataclass(frozen=True, slots=True)
class Continuity:
    """Declarative default reuse policy for a session slot."""

    kind: ContinuityKind
    worklist_name: str | None = None
    key_fn: Callable[["Context"], str] | None = None

    @staticmethod
    def run() -> "Continuity":
        return Continuity("run")

    @staticmethod
    def task() -> "Continuity":
        return Continuity("task")

    @staticmethod
    def work_item(worklist: object | str) -> "Continuity":
        name = worklist if isinstance(worklist, str) else getattr(worklist, "name", None)
        if not isinstance(name, str) or not name:
            raise ValueError("work_item continuity requires a worklist name or object with a name attribute")
        return Continuity("work_item", worklist_name=name)

    @staticmethod
    def fresh() -> "Continuity":
        return Continuity("fresh")

    @staticmethod
    def key(fn: Callable[["Context"], str]) -> "Continuity":
        return Continuity("key", key_fn=fn)


@dataclass(frozen=True, slots=True)
class SessionKey:
    """Authoritative storage/runtime key for one session binding."""

    slot: str
    domain: SessionKeyDomain
    value: str


def derive_session_key(slot: str, continuity: Continuity, context: "Context") -> SessionKey:
    """Resolve a continuity policy into a concrete key."""

    if continuity.kind == "run":
        return SessionKey(slot=slot, domain="run", value=context.run_id)
    if continuity.kind == "task":
        return SessionKey(slot=slot, domain="task", value=context.task_id)
    if continuity.kind == "fresh":
        return SessionKey(slot=slot, domain="fresh", value=uuid4().hex)
    if continuity.kind == "key":
        if continuity.key_fn is None:
            raise ValueError(f"session slot {slot!r} declares key continuity without key_fn")
        value = continuity.key_fn(context)
        if not isinstance(value, str) or not value:
            raise ValueError(f"session slot {slot!r} key continuity must resolve to a non-empty string")
        return SessionKey(slot=slot, domain="explicit_key", value=value)
    if continuity.kind == "work_item":
        if continuity.worklist_name is None:
            raise ValueError(f"session slot {slot!r} work_item continuity is missing a worklist name")
        current = getattr(context, "current", None)
        if not callable(current):
            raise ValueError(
                f"session slot {slot!r} cannot resolve work_item continuity before worklist runtime support exists"
            )
        item = current(continuity.worklist_name)
        if item is None:
            step_name = getattr(context, "_step_name", None)
            step_suffix = f" for step {step_name!r}" if isinstance(step_name, str) and step_name else ""
            raise ValueError(
                f"session {slot!r} uses work-item continuity for worklist {continuity.worklist_name!r}, "
                f"but no current work item is available{step_suffix}."
            )
        item_dir_key = getattr(item, "dir_key", None) or getattr(item, "id", None)
        if not isinstance(item_dir_key, str) or not item_dir_key:
            raise ValueError(
                f"session slot {slot!r} work item continuity requires the current work item to expose id or dir_key"
            )
        return SessionKey(slot=slot, domain="work_item", value=f"{continuity.worklist_name}:{item_dir_key}")
    raise ValueError(f"unsupported continuity kind {continuity.kind!r}")


__all__ = [
    "canonical_session_slot_name",
    "Continuity",
    "ContinuityKind",
    "DEFAULT_SESSION_NAME",
    "LEGACY_DEFAULT_SESSION_NAME",
    "SessionKey",
    "SessionKeyDomain",
    "derive_session_key",
]
