"""Strict workflow authoring shim."""

from __future__ import annotations

from typing import TYPE_CHECKING

try:  # pragma: no branch - prefer installed-package imports when available
    from autoloop_v3.core import (
        Advance,
        Artifact,
        BoardMutation,
        Context,
        FAIL,
        GLOBAL,
        LLMStep,
        PAUSE,
        PairStep,
        Prompt,
        Refresh,
        ResetCompletion,
        Route,
        RouteContract,
        SetStatus,
        Session,
        SUCCESS,
        SystemStep,
        Workflow,
    )
    if TYPE_CHECKING:
        from autoloop_v3.core.extensions import WorkflowExtension
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from core import Advance, Artifact, BoardMutation, Context, FAIL, GLOBAL, LLMStep, PAUSE, PairStep, Prompt
    from core import Refresh, ResetCompletion, Route, RouteContract, Session, SetStatus, SUCCESS
    from core import SystemStep, Workflow
    if TYPE_CHECKING:
        from core.extensions import WorkflowExtension


__all__ = [
    "Advance",
    "Artifact",
    "BoardMutation",
    "Context",
    "FAIL",
    "GLOBAL",
    "LLMStep",
    "PAUSE",
    "PairStep",
    "Prompt",
    "Refresh",
    "ResetCompletion",
    "Route",
    "RouteContract",
    "SetStatus",
    "SUCCESS",
    "Session",
    "SystemStep",
    "Workflow",
]
