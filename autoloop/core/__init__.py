"""Internal workflow kernel."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .artifacts import Artifact
from .context import Context
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
    extensions: tuple["WorkflowExtension", ...] = ()
__all__ = [
    "AWAIT_INPUT",
    "Artifact",
    "Continuity",
    "Context",
    "FAIL",
    "Fail",
    "FINISH",
    "GLOBAL",
    "Goto",
    "Prompt",
    "ProviderRetryPolicy",
    "RequestInput",
    "Route",
    "Selector",
    "SELF",
    "Session",
    "Workflow",
    "WorkItem",
    "Worklist",
]
