"""Internal workflow kernel."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .artifacts import Artifact
from .context import Context
from .effects import Advance, Handoff, Refresh, ResetCompletion, SetStatus
from .providers.retries import ProviderRetryPolicy
from .primitives import AWAIT_INPUT, FAIL, FINISH, GLOBAL, Goto, RequestInput, SELF, Fail
from .prompts import Prompt
from .routes import Route
from .sessions import Continuity
from .steps import Session
from .validation import WorkflowMeta
from .worklists import Selector, WorkItem, Worklist

if TYPE_CHECKING:
    from .extensions import WorkflowExtension


class Workflow(metaclass=WorkflowMeta):
    """Workflow authoring base class."""

    __workflow_abstract__ = True
    __strict_workflow__ = True
    extensions: tuple["WorkflowExtension", ...] = ()
__all__ = [
    "Advance",
    "AWAIT_INPUT",
    "Artifact",
    "Continuity",
    "Context",
    "FAIL",
    "Fail",
    "FINISH",
    "GLOBAL",
    "Goto",
    "Handoff",
    "Prompt",
    "ProviderRetryPolicy",
    "Refresh",
    "RequestInput",
    "ResetCompletion",
    "Route",
    "Selector",
    "SELF",
    "SetStatus",
    "Session",
    "Workflow",
    "WorkItem",
    "Worklist",
]
