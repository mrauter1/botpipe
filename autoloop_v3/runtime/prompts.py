"""Filesystem-backed prompt resolution."""

from __future__ import annotations

from pathlib import Path

from ..workflow.prompts import Prompt, PromptSpec, ResolvedPrompt


class FilesystemPromptRegistry:
    """Resolve prompts from a prioritized list of search roots."""

    def __init__(self, *search_roots: Path) -> None:
        self._search_roots = tuple(root.resolve() for root in search_roots)

    def resolve(self, prompt: PromptSpec) -> ResolvedPrompt:
        raw_path = prompt.path if isinstance(prompt, Prompt) else prompt
        candidate = Path(raw_path)
        if candidate.is_absolute():
            return self._from_candidate(candidate, raw_path)

        for root in self._search_roots:
            resolved = root / raw_path
            if resolved.exists():
                return self._from_candidate(resolved, raw_path)
        return ResolvedPrompt(path=raw_path, text=None)

    def _from_candidate(self, candidate: Path, display_path: str) -> ResolvedPrompt:
        if candidate.exists():
            return ResolvedPrompt(path=str(candidate), text=candidate.read_text(encoding="utf-8"))
        return ResolvedPrompt(path=display_path, text=None)
