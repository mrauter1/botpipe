"""Shared safe-placeholder contract for ``ctx.*`` runtime bindings."""

from __future__ import annotations

from typing import Final


CTX_SCALAR_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "message",
        "request_file",
        "task_id",
        "run_id",
        "workflow_name",
        "task_folder",
        "workflow_folder",
        "run_folder",
        "package_folder",
        "root",
    }
)

CTX_NESTED_FIELDS: Final[dict[str, frozenset[str]]] = {
    "request": frozenset({"text", "file", "task_file"}),
    "run": frozenset({"id", "folder"}),
    "workflow": frozenset({"name", "folder"}),
}

CTX_MODEL_ROOTS: Final[frozenset[str]] = frozenset({"input", "state", "params"})
_CTX_ALLOWED_ROOTS: Final[frozenset[str]] = CTX_SCALAR_FIELDS | frozenset(CTX_NESTED_FIELDS) | CTX_MODEL_ROOTS
_CTX_FORBIDDEN_CHARS: Final[frozenset[str]] = frozenset({'"', "'", "(", ")", "[", "]"})


def validate_safe_ctx_reference(reference: str) -> tuple[str, ...]:
    """Validate ``ctx.*`` dotted-path syntax without exposing object internals."""

    parts = tuple(reference.split("."))
    if len(parts) < 2 or parts[0] != "ctx":
        raise ValueError("ctx references must start with 'ctx.'")
    if any(not segment for segment in parts):
        raise ValueError("ctx references must not contain empty path segments")
    for segment in parts:
        if segment.startswith("_") or "__" in segment:
            raise ValueError("ctx references must not expose private or dunder segments")
        if any(character.isspace() for character in segment):
            raise ValueError("ctx references must not contain whitespace inside path segments")
        if any(character in _CTX_FORBIDDEN_CHARS for character in segment):
            raise ValueError("ctx references must not contain call, index, or quote syntax")
    if parts[1] not in _CTX_ALLOWED_ROOTS:
        raise ValueError(f"ctx root {parts[1]!r} is not supported")
    return parts


__all__ = [
    "CTX_MODEL_ROOTS",
    "CTX_NESTED_FIELDS",
    "CTX_SCALAR_FIELDS",
    "validate_safe_ctx_reference",
]
