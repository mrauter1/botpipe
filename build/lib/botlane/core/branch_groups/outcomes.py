"""Mechanical branch-group outcome policies."""

from __future__ import annotations

import inspect
from typing import Any, Mapping

from ..errors import WorkflowExecutionError
from ..primitives import Event


def branch_is_success(branch: Mapping[str, Any], *, success_routes: tuple[str, ...]) -> bool:
    return branch.get("status") == "completed" and branch.get("route") in success_routes


def select_branch_group_outcome(
    spec: Any,
    manifest: Mapping[str, Any],
    context: Any,
) -> Event:
    outcome = spec.outcome or "all_done"
    if callable(outcome):
        event = _call_outcome_aggregator(outcome, manifest=manifest, context=context)
        if not isinstance(event, Event):
            raise WorkflowExecutionError(
                f"branch group {spec.name!r} custom outcome must return botlane.core.primitives.Event"
            )
        return event
    if outcome == "all_done":
        return _all_done(spec, manifest)
    if outcome == "all_settled":
        return _all_settled(spec, manifest)
    if outcome == "any_done":
        return _any_done(spec, manifest)
    raise WorkflowExecutionError(f"branch group {spec.name!r} uses unsupported outcome policy {outcome!r}")


def _all_done(spec: Any, manifest: Mapping[str, Any]) -> Event:
    branches = list(manifest.get("branches", ()))
    if all(branch_is_success(branch, success_routes=spec.success_routes) for branch in branches):
        return Event("done")
    if _needs_input(branches):
        return Event("question", question=_question_summary(branches), reason="One or more branches need input.")
    return Event("partial", reason=_partial_reason(branches, success_routes=spec.success_routes))


def _all_settled(spec: Any, manifest: Mapping[str, Any]) -> Event:
    branches = list(manifest.get("branches", ()))
    if _needs_input(branches):
        return Event("question", question=_question_summary(branches), reason="One or more branches need input.")
    if all(branch_is_success(branch, success_routes=spec.success_routes) for branch in branches):
        return Event("done")
    return Event("partial", reason=_partial_reason(branches, success_routes=spec.success_routes))


def _any_done(spec: Any, manifest: Mapping[str, Any]) -> Event:
    branches = list(manifest.get("branches", ()))
    if any(branch_is_success(branch, success_routes=spec.success_routes) for branch in branches):
        return Event("done")
    if _needs_input(branches):
        return Event("question", question=_question_summary(branches), reason="No branch succeeded and input is required.")
    return Event("partial", reason=_partial_reason(branches, success_routes=spec.success_routes))


def _needs_input(branches: list[Mapping[str, Any]]) -> bool:
    return any(branch.get("status") == "needs_input" for branch in branches)


def _question_summary(branches: list[Mapping[str, Any]]) -> str:
    questions = [
        f"{branch.get('name')}: {branch.get('question') or branch.get('reason') or 'Input required.'}"
        for branch in branches
        if branch.get("status") == "needs_input"
    ]
    return "\n".join(questions)


def _partial_reason(
    branches: list[Mapping[str, Any]],
    *,
    success_routes: tuple[str, ...],
) -> str:
    non_success = [
        f"{branch.get('name')}={branch.get('status')}/{branch.get('route') or branch.get('runtime_control') or 'none'}"
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
