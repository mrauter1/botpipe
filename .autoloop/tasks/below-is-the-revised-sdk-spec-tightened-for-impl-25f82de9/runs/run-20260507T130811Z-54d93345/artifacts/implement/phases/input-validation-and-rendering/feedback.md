# Implement ↔ Code Reviewer Feedback

- Task ID: below-is-the-revised-sdk-spec-tightened-for-impl-25f82de9
- Pair: implement
- Phase ID: input-validation-and-rendering
- Phase Directory Key: input-validation-and-rendering
- Phase Title: Align Validation And Rendering
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` — `autoloop/core/context.py:89`, `autoloop/core/artifacts.py:_resolve_ctx_placeholder`: the current tree still exposes `WorkflowInputView` as typed-fields-only, so `ctx.input.message` is not actually part of the runtime input view. In a message-only workflow, any prompt or runtime template that resolves `{ctx.input.message}` will still fail once `context.input_fields is None` because `_resolve_ctx_placeholder(...)` raises `ctx.input.message requires workflow input, but no input was provided`. That violates the runtime-input-contract dependency and AC-2, and the new tests miss it because they only exercise bare `{input.message}` with a typed input instance. Minimal fix: land the composite `WorkflowInputView(message=..., fields=...)` / `Context.input` contract together with this phase and restore the `ctx.input.message` no-typed-input path in `_resolve_ctx_placeholder(...)`; add a tracked regression test that renders `{ctx.input.message}` when `workflow_input is None`.
- IMP-002 `non-blocking` — phase scope / `autoloop/runtime/runner.py:_coerce_workflow_input_payload`: the active phase contract explicitly included “Implement SDK-targeted typed input coercion rules around compiled.input_model”, but this turn leaves that work entirely deferred and documents the omission in `implementation_notes.md`. That does not break the current runtime rendering changes immediately, but it leaves later SDK work without the requested central helper for the exact-instance / no-dict validation rules, increasing the risk of duplicated or inconsistent coercion logic. Minimal fix: add the SDK-specific coercion helper near the existing runner input-coercion path, or move this item out of the authoritative phase scope before later turns assume it is complete.
