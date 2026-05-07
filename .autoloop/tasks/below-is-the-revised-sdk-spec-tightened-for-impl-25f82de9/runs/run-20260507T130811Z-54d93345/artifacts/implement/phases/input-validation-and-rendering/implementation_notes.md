# Implementation Notes

- Task ID: below-is-the-revised-sdk-spec-tightened-for-impl-25f82de9
- Pair: implement
- Phase ID: input-validation-and-rendering
- Phase Directory Key: input-validation-and-rendering
- Phase Title: Align Validation And Rendering
- Scope: phase-local producer artifact

## Files changed
- `autoloop/core/context.py`
- `autoloop/core/compiler.py`
- `autoloop/core/discovery.py`
- `autoloop/core/artifacts.py`
- `tests/contract/test_engine_contracts.py`
- `tests/runtime/test_workspace_and_context.py`
- `tests/unit/test_branch_group_context_sessions.py`
- `tests/unit/test_validation.py`
- `tests/unit/test_simple_surface.py`

## Symbols touched
- `WorkflowInputView`
- `Context.input`
- `_compile_optional_model`
- `_validate_ctx_prompt_reference`
- `_validate_simple_prompt_reference`
- `_resolve_placeholder`
- `_resolve_input_placeholder`
- `_resolve_ctx_placeholder`

## Checklist mapping
- Plan milestone 2 / compile validation: reject `Workflow.Input.message` with the spec text.
- Plan milestone 1 dependency integration: re-land the composite `ctx.input` contract needed by this phase in the current tree so `ctx.input.message` works again for runtime rendering and child/resume contexts.
- Plan milestone 2 / prompt validation: allow both bare `{input.message}` and `{ctx.input.message}` alongside typed input fields.
- Plan milestone 2 / runtime rendering: resolve message through the composite input view, while surfacing unknown bare `input.*` fields as execution errors.

## Intended behavior changes
- `compile_workflow(...)` now fails when `Workflow.Input` declares a field named `message`.
- `WorkflowInputView` now exposes `message` separately from typed fields and includes it in `model_dump()`.
- Simple-step prompt validation now accepts both `{input.message}` and `{ctx.input.message}`.
- Runtime template rendering no longer silently empties unknown bare `input.*` placeholders, and `{ctx.input.message}` now resolves for message-only workflows again.

## Preserved invariants
- `message` remains separate from persisted `workflow_input`.
- `input.message` continues to resolve from the run request/composite input view.
- `None` values still render as `""` after successful placeholder resolution.
- Child-workflow dict input compatibility was not changed.

## Known non-changes
- No SDK facade or SDK-only typed-input coercion helper was introduced in this phase.
- No broader placeholder syntax redesign was attempted outside `input.message` and bare `input.*` error handling.

## Expected side effects
- Tracked runtime and contract tests that previously asserted typed-only `ctx.input` behavior now expect `ctx.input.message` to be available and aligned with `ctx.message`.
- Message-aware context dumps on pause/resume and child-workflow boundaries now record the resolved input message instead of only a boolean presence check.

## Validation performed
- `python3 -m py_compile autoloop/core/context.py autoloop/core/compiler.py autoloop/core/discovery.py autoloop/core/artifacts.py`
- `python3 -m py_compile tests/contract/test_engine_contracts.py tests/runtime/test_workspace_and_context.py tests/unit/test_branch_group_context_sessions.py tests/unit/test_validation.py tests/unit/test_simple_surface.py`
- Environment limitation: `pytest` and `pydantic` are not installed in the provided interpreter, so runtime/unit execution could not be run in this turn.

## Assumptions
- The phase-local requirement to keep unknown input placeholders as errors applies to bare runtime `input.*` placeholders as well as validated `ctx.input.*` placeholders.

## Deduplication / centralization
- Reused the existing `Context.message` / request snapshot fallback instead of duplicating message-loading logic inside prompt rendering; `WorkflowInputView` is again the single composite surface for both `ctx.input.*` and bare `input.*` message access.
