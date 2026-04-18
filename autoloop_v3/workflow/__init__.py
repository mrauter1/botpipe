"""Strict workflow authoring surface."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .artifacts import Artifact
from .context import Context
from .primitives import FAIL, GLOBAL, PAUSE, SUCCESS
from .prompts import Prompt
from .steps import LLMStep, PairStep, Session, SystemStep
from .validation import WorkflowMeta

if TYPE_CHECKING:
    from .extensions import WorkflowExtension


class Workflow(metaclass=WorkflowMeta):
    """Workflow authoring base class."""

    __workflow_abstract__ = True
    __strict_workflow__ = True
    extensions: tuple["WorkflowExtension", ...] = ()


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
