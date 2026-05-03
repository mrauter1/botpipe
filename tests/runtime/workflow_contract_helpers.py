from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from autoloop import Event, Outcome
from autoloop.core.compiler import compile_workflow
from autoloop.core.context import Context


def _normalize_control_result(result: Any) -> Any:
    if isinstance(result, str):
        return Event(result)
    return result


def invoke_python_step(workflow_cls: type[Any], step_name: str, ctx: Context) -> Any:
    compiled = compile_workflow(workflow_cls)
    handler = compiled.steps[step_name].python_handler
    assert handler is not None
    result = handler(ctx)
    return _normalize_control_result(result)


def invoke_after_verifier_hook(
    workflow_cls: type[Any],
    step_name: str,
    ctx: Context,
    *,
    outcome: Outcome,
    artifacts: Any | None = None,
    route: Mapping[str, Any] | Any | None = None,
    meta: Mapping[str, Any] | Any | None = None,
) -> Any:
    compiled = compile_workflow(workflow_cls)
    hook = compiled.steps[step_name].after_verifier_hook
    assert hook is not None
    original_artifacts = ctx.artifacts
    original_route = ctx.route
    original_outcome = ctx.outcome
    original_meta = ctx.meta
    if artifacts is not None:
        ctx._runtime.set_artifacts(artifacts)
    ctx._runtime.set_route(route)
    ctx._runtime.set_outcome(outcome)
    ctx._runtime.set_meta(meta)
    try:
        result = hook(ctx)
        return _normalize_control_result(result)
    finally:
        ctx._runtime.set_artifacts(original_artifacts)
        ctx._runtime.set_route(original_route)
        ctx._runtime.set_outcome(original_outcome)
        ctx._runtime.set_meta(original_meta)
