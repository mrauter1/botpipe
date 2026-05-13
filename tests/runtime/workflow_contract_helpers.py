from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from botpipe import Event, Outcome
from botpipe.core import compiler as workflow_compiler
from botpipe.core.compiler import compile_workflow
from botpipe.core.context import Context


def _normalize_control_result(result: Any) -> Any:
    if isinstance(result, str):
        return Event(result)
    return result


def _compile_fresh_workflow(workflow_cls: type[Any]):
    # Tests in this module monkeypatch workflow module handlers between invocations.
    # Clear the compiler cache so helper-based step calls observe the patched callable.
    workflow_compiler._WORKFLOW_PLAN_CACHE.clear()
    return compile_workflow(workflow_cls)


def invoke_python_step(workflow_cls: type[Any], step_name: str, ctx: Context) -> Any:
    compiled = _compile_fresh_workflow(workflow_cls)
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
    compiled = _compile_fresh_workflow(workflow_cls)
    hook = compiled.steps[step_name].after_verifier_hook
    assert hook is not None
    original_artifacts = ctx.artifacts
    original_route = ctx.route
    original_outcome = ctx.outcome
    original_meta = ctx.meta
    if artifacts is not None:
        ctx._execution_frame.set_artifacts(artifacts)
    ctx._execution_frame.set_route(route)
    ctx._execution_frame.set_outcome(outcome)
    ctx._execution_frame.set_meta(meta)
    try:
        result = hook(ctx)
        return _normalize_control_result(result)
    finally:
        ctx._execution_frame.set_artifacts(original_artifacts)
        ctx._execution_frame.set_route(original_route)
        ctx._execution_frame.set_outcome(original_outcome)
        ctx._execution_frame.set_meta(original_meta)
