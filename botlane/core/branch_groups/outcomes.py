"""Mechanical branch-group outcome policies."""

from __future__ import annotations

import inspect
from typing import Any, Mapping

from .manifest import BranchManifest, coerce_branch_manifest
from .results import BranchResult
from ..errors import WorkflowExecutionError
from ..primitives import Event


def branch_is_success(branch: BranchResult | Mapping[str, Any], *, success_routes: tuple[str, ...]) -> bool:
    if isinstance(branch, BranchResult):
        return branch.status == "completed" and branch.route in success_routes
    return branch.get("status") == "completed" and branch.get("route") in success_routes


def select_branch_group_outcome(
    spec: Any,
    manifest: BranchManifest | Mapping[str, Any],
    context: Any,
) -> Event:
    typed_manifest = coerce_branch_manifest(manifest)
    outcome = spec.outcome or "all_done"
    if callable(outcome):
        event = _call_outcome_aggregator(outcome, manifest=typed_manifest.to_dict(), context=context)
        if not isinstance(event, Event):
            raise WorkflowExecutionError(
                f"branch group {spec.name!r} custom outcome must return botlane.core.primitives.Event"
            )
        return event
    if outcome == "all_done":
        return _all_done(spec, typed_manifest)
    if outcome == "all_settled":
        return _all_settled(spec, typed_manifest)
    if outcome == "any_done":
        return _any_done(spec, typed_manifest)
    raise WorkflowExecutionError(f"branch group {spec.name!r} uses unsupported outcome policy {outcome!r}")


def _all_done(spec: Any, manifest: BranchManifest) -> Event:
    branches = list(manifest.branches)
    if all(branch_is_success(branch, success_routes=spec.success_routes) for branch in branches):
        return Event("done")
    if _needs_input(branches):
        return Event("question", question=_question_summary(branches), reason="One or more branches need input.")
    return Event("partial", reason=_partial_reason(branches, success_routes=spec.success_routes))


def _all_settled(spec: Any, manifest: BranchManifest) -> Event:
    branches = list(manifest.branches)
    if _needs_input(branches):
        return Event("question", question=_question_summary(branches), reason="One or more branches need input.")
    if all(branch_is_success(branch, success_routes=spec.success_routes) for branch in branches):
        return Event("done")
    return Event("partial", reason=_partial_reason(branches, success_routes=spec.success_routes))


def _any_done(spec: Any, manifest: BranchManifest) -> Event:
    branches = list(manifest.branches)
    if any(branch_is_success(branch, success_routes=spec.success_routes) for branch in branches):
        return Event("done")
    if _needs_input(branches):
        return Event("question", question=_question_summary(branches), reason="No branch succeeded and input is required.")
    return Event("partial", reason=_partial_reason(branches, success_routes=spec.success_routes))


def _needs_input(branches: list[BranchResult | Mapping[str, Any]]) -> bool:
    for branch in branches:
        if isinstance(branch, BranchResult):
            if branch.status == "needs_input":
                return True
            continue
        if branch.get("status") == "needs_input":
            return True
    return False


def _question_summary(branches: list[BranchResult | Mapping[str, Any]]) -> str:
    questions: list[str] = []
    for branch in branches:
        if isinstance(branch, BranchResult):
            if branch.status == "needs_input":
                questions.append(f"{branch.name}: {branch.question or branch.reason or 'Input required.'}")
            continue
        if branch.get("status") == "needs_input":
            questions.append(f"{branch.get('name')}: {branch.get('question') or branch.get('reason') or 'Input required.'}")
    return "\n".join(questions)


def _partial_reason(
    branches: list[BranchResult | Mapping[str, Any]],
    *,
    success_routes: tuple[str, ...],
) -> str:
    non_success = [
        (
            f"{branch.name}={branch.status}/{branch.route or branch.runtime_control or 'none'}"
            if isinstance(branch, BranchResult)
            else f"{branch.get('name')}={branch.get('status')}/{branch.get('route') or branch.get('runtime_control') or 'none'}"
        )
        for branch in branches
        if not branch_is_success(branch, success_routes=success_routes)
    ]
    return "Branch group settled without full success: " + ", ".join(non_success)


def _call_outcome_aggregator(func: Any, *, manifest: Mapping[str, Any], context: Any) -> Any:
    signature = inspect.signature(func)
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if any(parameter.kind == inspect.Parameter.VAR_POSITIONAL for parameter in signature.parameters.values()):
        return func(manifest, context)
    if len(positional) >= 2:
        return func(manifest, context)
    if len(positional) == 1:
        return func(manifest)
    return func()
