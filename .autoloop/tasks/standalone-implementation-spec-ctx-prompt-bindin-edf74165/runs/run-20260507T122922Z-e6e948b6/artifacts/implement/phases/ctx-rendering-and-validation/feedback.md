# Implement ↔ Code Reviewer Feedback

- Task ID: standalone-implementation-spec-ctx-prompt-bindin-edf74165
- Pair: implement
- Phase ID: ctx-rendering-and-validation
- Phase Directory Key: ctx-rendering-and-validation
- Phase Title: Integrate Safe ctx Prompt Rendering
- Scope: phase-local authoritative verifier artifact

## Findings

- `IMP-001` `blocking` `autoloop/core/artifacts.py::_resolve_ctx_placeholder`, `autoloop/core/engine.py::_resolve_workflow_step_message`
  Invalid `ctx` model-field references can still escape as raw `AttributeError` on runtime-only message paths. `workflow_step(message=...)` is now rendered through `render_runtime_template(...)`, but that path does not go through `_validate_simple_prompt_reference(...)`. A workflow such as `workflow_step(Child, message="{ctx.input.missing}")` reaches `_resolve_ctx_placeholder(...)`, `validate_safe_ctx_reference(...)` accepts the shape, and `_lookup_runtime_value(...)` raises `AttributeError` directly because missing model fields are not converted into `WorkflowExecutionError`. This violates the safe explicit runtime failure contract for unsupported `ctx.*` access and creates an unhandled exception path precisely on one of the newly enabled surfaces. Minimal fix: make `_resolve_ctx_placeholder(...)` convert missing `ctx.input/state/params` fields into `WorkflowExecutionError` consistently, ideally by centralizing runtime model-root field validation alongside the shared `ctx` contract, and add coverage for an invalid `workflow_step(message=...)` placeholder case.

## Re-review notes

- `IMP-001` resolved on re-review: `autoloop/core/artifacts.py::_resolve_ctx_placeholder` now converts missing `ctx` model-root fields into `WorkflowExecutionError`, and `tests/contract/test_engine_contracts.py::test_workflow_step_message_invalid_ctx_field_raises_workflow_execution_error` covers the runtime-only `workflow_step(message=...)` path that previously leaked `AttributeError`.
- No new findings in cycle 2 review.
