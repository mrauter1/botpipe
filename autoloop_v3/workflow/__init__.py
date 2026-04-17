"""Strict workflow authoring surface."""

from __future__ import annotations

from .artifacts import Artifact
from .compiler import compile_workflow
from .context import Context
from .engine import Engine
from .primitives import FAIL, GLOBAL, PAUSE, SUCCESS
from .prompts import Prompt
from .steps import LLMStep, PairStep, Session, SystemStep
from .validation import WorkflowMeta


class Workflow(metaclass=WorkflowMeta):
    """Workflow authoring base class."""

    __workflow_abstract__ = True
    __strict_workflow__ = True


__all__ = [
    "Artifact",
    "Context",
    "Engine",
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
    "compile_workflow",
]
