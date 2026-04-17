"""Prompt references and registries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol


@dataclass(frozen=True, slots=True)
class Prompt:
    """Prompt path reference."""

    path: str


@dataclass(frozen=True, slots=True)
class ResolvedPrompt:
    """Resolved prompt payload."""

    path: str
    text: str | None = None


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
        path = prompt.path if isinstance(prompt, Prompt) else prompt
        return ResolvedPrompt(path=path, text=self._prompts.get(path))

