"""Prompt references and registries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal, Mapping, Protocol


PromptSource = Literal["inline", "file", "registry"]


@dataclass(frozen=True, slots=True)
class Prompt:
    """Prompt reference with optional inline content."""

    path: str | None = None
    text: str | None = None
    source: PromptSource = "registry"

    @classmethod
    def inline(cls, text: str) -> "Prompt":
        return cls(path=None, text=text, source="inline")

    @classmethod
    def file(cls, path: str | Path) -> "Prompt":
        return cls(path=str(path), source="file")

    @classmethod
    def ref(cls, path: str) -> "Prompt":
        return cls(path=path, source="registry")


@dataclass(frozen=True, slots=True)
class ResolvedPrompt:
    """Resolved prompt payload."""

    path: str | None
    text: str | None = None
    source: PromptSource = "registry"


PromptSpec = str | Prompt


class PromptResolver(Protocol):
    """Protocol for prompt lookup backends."""

    def resolve(self, prompt: PromptSpec) -> ResolvedPrompt:
        """Resolve a prompt reference."""


class PromptRegistry:
    """Simple in-memory prompt registry."""

    def __init__(self, prompts: Mapping[str, str] | None = None) -> None:
        self._prompts = dict(prompts or {})

    def resolve(self, prompt: PromptSpec) -> ResolvedPrompt:
        if isinstance(prompt, Prompt):
            if prompt.source == "inline":
                return ResolvedPrompt(path=prompt.path, text=prompt.text, source=prompt.source)
            path = prompt.path
            return resolve_prompt_reference(path, source=prompt.source, prompt_lookup=self._prompts)
        return resolve_prompt_reference(prompt, source="registry", prompt_lookup=self._prompts)


def resolve_prompt_reference(
    raw_path: str | None,
    *,
    source: PromptSource,
    search_roots: Iterable[Path] = (),
    prompt_lookup: Mapping[str, str] | None = None,
) -> ResolvedPrompt:
    """Resolve a prompt path against registry text and optional filesystem roots."""

    if raw_path is None:
        return ResolvedPrompt(path=None, text=None, source=source)
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return _prompt_from_candidate(candidate, display_path=raw_path, source=source, prompt_lookup=prompt_lookup)

    for root in search_roots:
        resolved = root / raw_path
        if resolved.exists():
            return _prompt_from_candidate(
                resolved,
                display_path=raw_path,
                source=source,
                prompt_lookup=prompt_lookup,
            )

    text = prompt_lookup.get(raw_path) if prompt_lookup is not None else None
    return ResolvedPrompt(path=raw_path, text=text, source=source)


def _prompt_from_candidate(
    candidate: Path,
    *,
    display_path: str,
    source: PromptSource,
    prompt_lookup: Mapping[str, str] | None = None,
) -> ResolvedPrompt:
    if candidate.exists():
        return ResolvedPrompt(path=str(candidate), text=candidate.read_text(encoding="utf-8"), source=source)
    text = prompt_lookup.get(display_path) if prompt_lookup is not None else None
    return ResolvedPrompt(path=display_path, text=text, source=source)
