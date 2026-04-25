"""Strict workflow authoring shim."""

from __future__ import annotations

from typing import TYPE_CHECKING

try:  # pragma: no branch - prefer installed-package imports when available
    from autoloop_v3.core import (
        Advance,
        Artifact,
        BoardMutation,
        Continuity,
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
        Selector,
        SetStatus,
        Session,
        SUCCESS,
        SystemStep,
        Workflow,
        WorkItem,
        Worklist,
    )
    if TYPE_CHECKING:
        from autoloop_v3.core.extensions import WorkflowExtension
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from core import Advance, Artifact, BoardMutation, Continuity, Context, FAIL, GLOBAL, LLMStep, PAUSE
    from core import PairStep, Prompt, Refresh, ResetCompletion, Route, RouteContract, Selector, SetStatus
    from core import Session, SUCCESS, SystemStep, Workflow, WorkItem, Worklist
    if TYPE_CHECKING:
        from core.extensions import WorkflowExtension


__all__ = [
    "Advance",
    "Artifact",
    "BoardMutation",
    "Continuity",
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
    "Selector",
    "SetStatus",
    "SUCCESS",
    "Session",
    "SystemStep",
    "Workflow",
    "WorkItem",
    "Worklist",
]
