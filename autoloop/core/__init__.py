"""Internal workflow kernel."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .artifacts import Artifact
from .context import Context
from .effects import Effects, WorklistEffect
from .providers.retries import ProviderRetryPolicy
from .primitives import AWAIT_INPUT, FAIL, FINISH, GLOBAL, Goto, RequestInput, SELF, Fail
from .prompts import Prompt
from .providers.models import RuntimeInteractionPolicy
from .routes import Route
from .sessions import Continuity
from .steps import ControlRoutes, Session
from .validation_helpers import ValidationResult
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
    "ControlRoutes",
    "FAIL",
    "Effects",
    "Fail",
    "FINISH",
    "GLOBAL",
    "Goto",
    "Prompt",
    "ProviderRetryPolicy",
    "RequestInput",
    "RuntimeInteractionPolicy",
    "Route",
    "Selector",
    "SELF",
    "Session",
    "ValidationResult",
    "Workflow",
    "WorkItem",
    "WorklistEffect",
    "Worklist",
]
