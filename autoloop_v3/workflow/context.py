"""Stable runtime context surface."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from .steps import Session

if TYPE_CHECKING:
    from .stores.protocols import SessionBinding, SessionStore


class Context:
    """Runtime context exposed to workflow hooks and system handlers."""

    def __init__(
        self,
        *,
        task_id: str,
        run_id: str,
        task_folder: Path,
        run_folder: Path,
        state: BaseModel,
        session_store: SessionStore,
        answer: str | None = None,
    ) -> None:
        self.task_id = task_id
        self.run_id = run_id
        self.task_folder = task_folder
        self.run_folder = run_folder
        self._state = state
        self._session_store = session_store
        self._answer = answer

    @property
    def state(self) -> BaseModel:
        return self._state

    @property
    def answer(self) -> str | None:
        return self._answer

    def open_session(self, ref: Session | str, scope: str | None = None) -> SessionBinding:
        return self._session_store.open(_session_name(ref), scope=scope)

    def get_session(self, ref: Session | str, scope: str | None = None) -> SessionBinding | None:
        return self._session_store.get(_session_name(ref), scope=scope)

    def _set_state(self, state: BaseModel) -> None:
        self._state = state

    def _set_answer(self, answer: str | None) -> None:
        self._answer = answer


def _session_name(ref: Session | str) -> str:
    if isinstance(ref, Session):
        if ref.name is None:
            raise ValueError("session slot is not bound to a workflow attribute name")
        return ref.name
    return ref

