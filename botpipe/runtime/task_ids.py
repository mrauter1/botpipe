"""Task id generation helpers."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from uuid import uuid4

from .workspace import resolve_task_workspace


_TASK_ID_TOKEN_RE = re.compile(r"[a-z0-9]+")
_TASK_ID_SAFE_RE = re.compile(r"[^a-z0-9]+")
_TASK_ID_STOPWORDS = {
    "a",
    "add",
    "an",
    "and",
    "build",
    "complete",
    "create",
    "for",
    "from",
    "implement",
    "in",
    "into",
    "make",
    "of",
    "on",
    "or",
    "please",
    "request",
    "requested",
    "should",
    "that",
    "the",
    "these",
    "this",
    "to",
    "update",
    "with",
    "without",
    "write",
}


class TaskIdGenerationError(RuntimeError):
    """Raised when a collision-free generated task id cannot be found."""


def generate_task_id(
    *,
    root: Path,
    message: str | None,
    workflow_name: str | None = None,
    state_dir: Path | None = None,
    prefix: str | None = None,
    max_slug_words: int = 4,
    max_slug_chars: int = 32,
    suffix_chars: int = 6,
    max_attempts: int = 32,
) -> str:
    """Generate a concise, path-safe task id and check for workspace collisions."""

    slug = task_id_slug(message or workflow_name or "task", max_words=max_slug_words, max_chars=max_slug_chars)
    normalized_prefix = _normalize_task_id_part(prefix or "")
    for _ in range(max_attempts):
        suffix = uuid4().hex[:suffix_chars]
        if normalized_prefix:
            candidate = f"{normalized_prefix}-{slug}-{suffix}"
        else:
            candidate = f"{slug}-{suffix}"
        task_workspace = resolve_task_workspace(root, candidate, state_dir=state_dir)
        if not task_workspace.task_dir.exists():
            return candidate
    raise TaskIdGenerationError(f"could not generate a unique task id for {workflow_name or slug!r}")


def task_id_slug(source: str, *, max_words: int = 4, max_chars: int = 32) -> str:
    """Return a short readable slug suitable for use inside a generated task id."""

    normalized = unicodedata.normalize("NFKD", source).encode("ascii", "ignore").decode("ascii").lower()
    tokens = _TASK_ID_TOKEN_RE.findall(normalized)
    meaningful = [token for token in tokens if token not in _TASK_ID_STOPWORDS]
    selected = meaningful[:max_words] or tokens[:max_words] or ["task"]
    slug = "-".join(selected)
    if len(slug) > max_chars:
        slug = slug[:max_chars].rstrip("-")
    return slug or "task"


def _normalize_task_id_part(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    return _TASK_ID_SAFE_RE.sub("-", normalized).strip("-")


__all__ = ["TaskIdGenerationError", "generate_task_id", "task_id_slug"]
