"""Recorded source identity for honest comparisons between durable workflow runs."""

from __future__ import annotations

import inspect
from hashlib import sha256
from pathlib import Path
from types import CodeType
from typing import Any

from .surface_identity import (
    canonical_workflow_identity,
    derive_workflow_surface_manifest,
)


def _active_module_code(source: Path) -> CodeType | None:
    """Retain only immutable code, never a live frame or its global namespace."""
    frame = inspect.currentframe()
    try:
        while frame is not None:
            code = frame.f_code
            if (
                code.co_name == "<module>"
                and Path(code.co_filename).resolve() == source
            ):
                return code
            frame = frame.f_back
        return None
    finally:
        del frame


def capture_definition_sources(definition: Any) -> dict[str, Any] | None:
    """Remember source bytes at definition time without importing or walking packages."""
    try:
        target = inspect.unwrap(getattr(definition, "fn", definition))
        source = inspect.getsourcefile(target)
        if source is None:
            return None
        path = Path(source).resolve(strict=True)
        return {
            "path": str(path),
            "sha256": sha256(path.read_bytes()).hexdigest(),
            "module_code": _active_module_code(path),
        }
    except (OSError, TypeError, ValueError):
        return None


def _verify_loaded_source(definition: Any) -> None:
    captured = getattr(definition, "_source_identity_at_definition", None)
    current = capture_definition_sources(definition)
    if (
        captured is None
        or current is None
        or any(captured[key] != current[key] for key in ("path", "sha256"))
    ):
        raise ValueError("workflow source changed after its definition was loaded")
    target = inspect.unwrap(definition.fn)
    source = Path(current["path"])
    compiled = compile(source.read_bytes(), str(source), "exec", dont_inherit=True)
    # A valid timestamp-based pyc can contain stale module constants even when
    # this function's bytecode is unchanged. Bind the whole executed module too.
    # Late definitions without an observable module frame stay unverified.
    if captured.get("module_code") != compiled:
        raise ValueError("loaded workflow code does not match current module source")

    def matching_codes(code: CodeType):
        for value in code.co_consts:
            if isinstance(value, CodeType):
                if value.co_qualname == target.__qualname__:
                    yield value
                yield from matching_codes(value)

    matches = list(matching_codes(compiled))
    # Do not execute source to resolve dynamic definitions or decorators. Ambiguous
    # definitions and transformed bytecode cannot support verified source evidence.
    if len(matches) != 1 or matches[0] != target.__code__:
        raise ValueError("loaded workflow code does not match its current source")


def capture_workflow_provenance(
    definition: Any, workspace: str | Path
) -> dict[str, Any]:
    """Observe the current editable surface; unavailable identity stays explicit."""
    try:
        _verify_loaded_source(definition)
        manifest = derive_workflow_surface_manifest(Path(workspace), definition)
        confirmed = derive_workflow_surface_manifest(Path(workspace), definition)
        _verify_loaded_source(definition)
        if confirmed["surface_id"] != manifest["surface_id"]:
            raise ValueError("workflow surface changed during provenance capture")
        return {
            "schema": "botpipe.workflow-provenance.v1",
            "verified": True,
            "workflow_identity": canonical_workflow_identity(manifest["boundary"]),
            "surface_id": manifest["surface_id"],
            "orchestration_id": definition.fingerprint,
            "surface_manifest": manifest,
        }
    except (OSError, SyntaxError, TypeError, ValueError) as exc:
        return {
            "schema": "botpipe.workflow-provenance.v1",
            "verified": False,
            "workflow_identity": None,
            "surface_id": None,
            "orchestration_id": getattr(definition, "fingerprint", None),
            "error": f"{type(exc).__name__}: {exc}",
        }


__all__ = ["capture_definition_sources", "capture_workflow_provenance"]
