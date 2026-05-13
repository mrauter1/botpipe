"""Compile-time validation helpers for branch groups."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any

from botpipe.core.errors import WorkflowValidationError
from botpipe.core.steps import BranchGroupStep, ChildWorkflowStep, ProduceVerifyStep, PromptStep, Session, Step

from .models import FanInHelperReference


_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def validate_path_safe_name(*, kind: str, value: str, owner: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowValidationError(f"{owner} {kind} must be a non-empty string")
    normalized = value.strip()
    if normalized in {".", ".."} or "/" in normalized or "\\" in normalized or not _SAFE_NAME_RE.fullmatch(normalized):
        raise WorkflowValidationError(f"{owner} {kind} {normalized!r} must be path-safe")


def ensure_json_serializable(value: Any, *, label: str) -> None:
    try:
        json.dumps(value)
    except TypeError as exc:
        raise WorkflowValidationError(f"{label} must be JSON-serializable in v1") from exc


def validate_branch_step_kind(*, group_name: str, step: Step) -> None:
    if step.scope is not None:
        raise WorkflowValidationError(
            f"branch group {group_name!r} includes scoped branch step {step.name!r}, which is unsupported in v1."
        )
    if isinstance(step, ChildWorkflowStep):
        raise WorkflowValidationError(
            f"branch group {group_name!r} includes child workflow branch step {step.name!r}, which is unsupported in v1."
        )
    if _simple_declaration_kind(step) == "operation":
        raise WorkflowValidationError(
            f"branch group {group_name!r} includes operation branch step {step.name!r}, which is unsupported in v1."
        )
    if isinstance(step, BranchGroupStep):
        raise WorkflowValidationError(
            f"branch group {group_name!r} includes unsupported branch step {step.name!r} of kind {step.kind!r}."
        )
    if not isinstance(step, (PromptStep, ProduceVerifyStep)) and not getattr(step, "kind", None) in {"python", "system"}:
        raise WorkflowValidationError(
            f"branch group {group_name!r} includes unsupported branch step {step.name!r} of kind {step.kind!r}."
        )


def validate_fan_in_step_kind(*, group_name: str, step: Step) -> None:
    if step.scope is not None:
        raise WorkflowValidationError(
            f"branch group {group_name!r} includes scoped fan-in step {step.name!r}, which is unsupported in v1."
        )
    if isinstance(step, ChildWorkflowStep):
        raise WorkflowValidationError(
            f"branch group {group_name!r} includes child workflow fan-in step {step.name!r}, which is unsupported in v1."
        )
    if _simple_declaration_kind(step) == "operation":
        raise WorkflowValidationError(
            f"branch group {group_name!r} includes unsupported fan-in step {step.name!r} of kind 'operation'."
        )
    if isinstance(step, BranchGroupStep):
        raise WorkflowValidationError(
            f"branch group {group_name!r} includes unsupported fan-in step {step.name!r} of kind {step.kind!r}."
        )
    if not isinstance(step, (PromptStep, ProduceVerifyStep)) and not getattr(step, "kind", None) in {"python", "system"}:
        raise WorkflowValidationError(
            f"branch group {group_name!r} includes unsupported fan-in step {step.name!r} of kind {step.kind!r}."
        )


def validate_branch_step_session_requirements(*, group_name: str, step: Step) -> None:
    if isinstance(step, PromptStep):
        _require_explicit_fresh_session(group_name=group_name, step=step, session=step.session, label="session")
        return
    if isinstance(step, ProduceVerifyStep):
        _require_explicit_fresh_session(group_name=group_name, step=step, session=step.session, label="session")
        verifier_session = getattr(step, "verifier_session", None)
        if verifier_session is not None:
            _require_explicit_fresh_session(
                group_name=group_name,
                step=step,
                session=verifier_session,
                label="verifier_session",
            )


def _require_explicit_fresh_session(
    *,
    group_name: str,
    step: Step,
    session: Session | None,
    label: str,
) -> None:
    if session is None:
        if label == "verifier_session":
            return
        raise WorkflowValidationError(
            f"branch group {group_name!r} includes provider-backed branch step {step.name!r} without explicit session=Session.fresh()."
        )
    continuity = session.continuity
    if continuity.kind == "fresh":
        return
    if label == "verifier_session":
        raise WorkflowValidationError(
            f"branch group {group_name!r} includes produce/verify branch step {step.name!r} with non-fresh verifier_session continuity {continuity.kind!r}."
        )
    raise WorkflowValidationError(
        f"branch group {group_name!r} includes provider-backed branch step {step.name!r} with non-fresh session continuity {continuity.kind!r}."
    )


def validate_fan_in_helper_placement(
    references: Sequence[object],
    *,
    group_name: str,
    step_name: str,
    allow_helpers: bool,
) -> None:
    for reference in references:
        if isinstance(reference, FanInHelperReference) and not allow_helpers:
            raise WorkflowValidationError(
                f"branch group {group_name!r} includes step {step_name!r} using {reference}, which is only valid inside fan-in."
            )


def _simple_declaration_kind(step: Step) -> str | None:
    declaration = getattr(step, "simple_declaration", None)
    kind = getattr(declaration, "kind", None)
    return kind if isinstance(kind, str) else None
