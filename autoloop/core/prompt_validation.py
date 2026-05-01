"""Prompt validation facade."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .discovery import _simple_prompt_search_roots, _simple_prompt_text
from .errors import WorkflowValidationError


_PROMPT_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")


def analyze_simple_prompt_references(prompt: object, *, workflow_cls: type[Any]) -> tuple[str, ...]:
    text = _simple_prompt_text(prompt, search_roots=_simple_prompt_search_roots(workflow_cls))
    if not text:
        return ()
    return tuple(
        dict.fromkeys(reference.strip() for reference in _PROMPT_PLACEHOLDER_RE.findall(text) if reference.strip())
    )


def simple_prompt_search_roots(workflow_cls: type[Any]) -> tuple[Path, ...]:
    return _simple_prompt_search_roots(workflow_cls)


def validate_simple_prompt_reference(
    prompt: object,
    *,
    search_roots: Sequence[Path],
    workflow_cls: type[Any],
    step_name: str,
) -> None:
    if prompt is None:
        return
    prompt_path = getattr(prompt, "path", None)
    prompt_source = getattr(prompt, "source", None)
    if prompt_source == "registry" or not isinstance(prompt_path, str) or not prompt_path:
        return
    if _simple_prompt_text(prompt, search_roots=search_roots or _simple_prompt_search_roots(workflow_cls)) is None:
        raise WorkflowValidationError(
            f"simple step {step_name!r} prompt reference {prompt_path!r} did not resolve to text"
        )


__all__ = [
    "analyze_simple_prompt_references",
    "simple_prompt_search_roots",
    "validate_simple_prompt_reference",
]
