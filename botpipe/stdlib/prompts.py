"""Pure helpers for grouping prompt references."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from botpipe.core.prompts import Prompt


PromptInput = str | Prompt


@dataclass(frozen=True, slots=True)
class PromptPair:
    """Producer/verifier prompt references kept together explicitly."""

    producer: PromptInput
    verifier: PromptInput


@dataclass(frozen=True, slots=True)
class PromptBundle:
    """Prefix prompt paths without introducing a registry or DSL."""

    root: str = ""

    def prompt(self, prompt: PromptInput) -> Prompt:
        path = prompt.path if isinstance(prompt, Prompt) else prompt
        return Prompt(_join_prompt_path(self.root, path))

    def pair(self, producer: PromptInput, verifier: PromptInput) -> PromptPair:
        return PromptPair(
            producer=self.prompt(producer),
            verifier=self.prompt(verifier),
        )


def _join_prompt_path(root: str, path: str) -> str:
    if not root or path.startswith("/"):
        return path
    return str(PurePosixPath(root) / path)
