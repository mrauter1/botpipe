"""Filesystem-backed prompt resolution."""

from __future__ import annotations

from pathlib import Path

from autoloop.core.prompts import Prompt, PromptSpec, ResolvedPrompt, resolve_prompt_reference


class FilesystemPromptRegistry:
    """Resolve prompts from a prioritized list of search roots."""

    def __init__(self, *search_roots: Path) -> None:
        self._search_roots = tuple(root.resolve() for root in search_roots)

    def resolve(self, prompt: PromptSpec) -> ResolvedPrompt:
        if isinstance(prompt, Prompt):
            if prompt.source == "inline":
                return ResolvedPrompt(
                    path=prompt.path,
                    text=prompt.text,
                    source="inline",
                    reference_values={"source": "inline", "inline": True},
                )
            raw_path = prompt.path
            source = prompt.source
        else:
            raw_path = prompt
            source = "registry"
        return resolve_prompt_reference(raw_path, source=source, search_roots=self._search_roots)
