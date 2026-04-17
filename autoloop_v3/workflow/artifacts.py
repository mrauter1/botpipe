"""Artifact declarations and resolved handles."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Iterator, Mapping

if TYPE_CHECKING:
    from .context import Context
    from .steps import Step


class Artifact:
    """Artifact declaration."""

    __slots__ = ("template", "name", "owner")

    def __init__(self, template: str, name: str | None = None, owner: Step | None = None) -> None:
        self.template = template
        self.name = name
        self.owner = owner

    def bind_name(self, name: str) -> None:
        if self.name is None:
            self.name = name
        elif self.name != name:
            raise ValueError(f"artifact already named {self.name!r}; cannot rename to {name!r}")

    def __repr__(self) -> str:
        return f"Artifact(template={self.template!r}, name={self.name!r})"


@dataclass(frozen=True, slots=True)
class ArtifactHandle:
    """Concrete resolved artifact handle."""

    name: str
    path: Path

    def read_text(self) -> str:
        return self.path.read_text(encoding="utf-8")

    def write_text(self, content: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(content, encoding="utf-8")

    def append(self, content: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(content)

    def exists(self) -> bool:
        return self.path.exists()


class ResolvedArtifacts(Mapping[str, ArtifactHandle]):
    """Read-only mapping with attribute access."""

    def __init__(self, handles: Mapping[str, ArtifactHandle]) -> None:
        self._handles = dict(handles)

    def __getitem__(self, key: str) -> ArtifactHandle:
        return self._handles[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._handles)

    def __len__(self) -> int:
        return len(self._handles)

    def __getattr__(self, item: str) -> ArtifactHandle:
        try:
            return self._handles[item]
        except KeyError as exc:
            raise AttributeError(item) from exc

    def subset(self, names: Iterable[str]) -> "ResolvedArtifacts":
        return ResolvedArtifacts({name: self._handles[name] for name in names})


@dataclass(frozen=True, slots=True)
class CompiledArtifact:
    """Immutable compiled artifact metadata."""

    name: str
    template: str
    workflow_level: bool
    producer_steps: tuple[str, ...]


_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")


def resolve_artifact_template(template: str, context: Context) -> Path:
    """Resolve a template against runtime context."""

    def replace(match: re.Match[str]) -> str:
        value = _resolve_placeholder(match.group(1), context)
        return "" if value is None else str(value)

    rendered = _PLACEHOLDER_RE.sub(replace, template)
    return Path(rendered)


def _resolve_placeholder(expression: str, context: Context) -> Any:
    parts = expression.split(".")
    if not parts:
        return ""
    root_name = parts[0]
    current: Any
    if root_name == "task_id":
        current = context.task_id
    elif root_name == "run_id":
        current = context.run_id
    elif root_name == "task_folder":
        current = context.task_folder
    elif root_name == "run_folder":
        current = context.run_folder
    elif root_name == "state":
        current = context.state
    else:
        return ""
    for part in parts[1:]:
        if current is None:
            return ""
        if isinstance(current, Mapping):
            current = current.get(part, "")
        else:
            current = getattr(current, part, "")
    return "" if current is None else current

