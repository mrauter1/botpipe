"""Compatibility import surface for workspace workflows."""

from __future__ import annotations

from autoloop_v3.workflow import (
    Artifact,
    Context,
    Engine,
    FAIL,
    GLOBAL,
    LLMStep,
    PAUSE,
    PairStep,
    Prompt,
    SUCCESS,
    Session,
    SessionLifecycle,
    SystemStep,
    compile_workflow,
)
from autoloop_v3.workflow.compat import LegacyWorkflow as Workflow

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
    "SessionLifecycle",
    "SystemStep",
    "Workflow",
    "compile_workflow",
]
