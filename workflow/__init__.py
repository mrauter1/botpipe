"""Strict workflow authoring shim."""

from __future__ import annotations

from typing import TYPE_CHECKING

try:  # pragma: no branch - prefer installed-package imports when available
    from autoloop_v3.core import (
        Artifact,
        Context,
        FAIL,
        GLOBAL,
        LLMStep,
        PAUSE,
        PairStep,
        Prompt,
        Session,
        SUCCESS,
        SystemStep,
        Workflow,
    )
    if TYPE_CHECKING:
        from autoloop_v3.core.extensions import WorkflowExtension
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from core import Artifact, Context, FAIL, GLOBAL, LLMStep, PAUSE, PairStep, Prompt, Session, SUCCESS
    from core import SystemStep, Workflow
    if TYPE_CHECKING:
        from core.extensions import WorkflowExtension


__all__ = [
    "Artifact",
    "Context",
    "FAIL",
    "GLOBAL",
    "LLMStep",
    "PAUSE",
    "PairStep",
    "Prompt",
    "SUCCESS",
    "Session",
    "SystemStep",
    "Workflow",
]
