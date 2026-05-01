"""Prompt validation facade."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .validation import _analyze_simple_prompt_references, _simple_prompt_search_roots, _validate_simple_prompt_reference


def analyze_simple_prompt_references(prompt: object, *, workflow_cls: type[Any]) -> tuple[str, ...]:
    return _analyze_simple_prompt_references(prompt, workflow_cls=workflow_cls)


def simple_prompt_search_roots(workflow_cls: type[Any]) -> tuple[Path, ...]:
    return _simple_prompt_search_roots(workflow_cls)


def validate_simple_prompt_reference(
    prompt: object,
    *,
    search_roots: Sequence[Path],
    workflow_cls: type[Any],
    step_name: str,
) -> None:
    _validate_simple_prompt_reference(prompt, search_roots=search_roots, workflow_cls=workflow_cls, step_name=step_name)


__all__ = [
    "analyze_simple_prompt_references",
    "simple_prompt_search_roots",
    "validate_simple_prompt_reference",
]
