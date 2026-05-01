"""Small immutable cursor helpers for ordered workflow state."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Generic, TypeVar


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class SequenceCursor(Generic[T]):
    """Immutable cursor over an ordered sequence."""

    items: tuple[T, ...] = ()
    index: int = -1

    @classmethod
    def from_items(cls, items: Iterable[T]) -> "SequenceCursor[T]":
        return cls(items=tuple(items))

    @property
    def current(self) -> T | None:
        if self.index < 0 or self.index >= len(self.items):
            return None
        return self.items[self.index]

    def peek(self) -> T | None:
        next_index = self.index + 1
        if next_index < 0 or next_index >= len(self.items):
            return None
        return self.items[next_index]

    def has_next(self) -> bool:
        return self.peek() is not None

    def advance(self) -> "SequenceCursor[T]":
        if not self.has_next():
            return self
        return type(self)(items=self.items, index=self.index + 1)

    def reset(self) -> "SequenceCursor[T]":
        return type(self)(items=self.items, index=-1)
