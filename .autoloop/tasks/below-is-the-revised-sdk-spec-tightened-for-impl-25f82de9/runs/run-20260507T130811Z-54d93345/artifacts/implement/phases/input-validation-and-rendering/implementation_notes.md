# Implementation Notes

- Task ID: below-is-the-revised-sdk-spec-tightened-for-impl-25f82de9
- Pair: implement
- Phase ID: input-validation-and-rendering
- Phase Directory Key: input-validation-and-rendering
- Phase Title: Align Validation And Rendering
- Scope: phase-local producer artifact

## Files changed
- `autoloop/core/compiler.py`
- `autoloop/core/discovery.py`
- `autoloop/core/artifacts.py`
- `tests/contract/test_engine_contracts.py`
- `tests/unit/test_validation.py`
- `tests/unit/test_simple_surface.py`

## Symbols touched
- `_compile_optional_model`
- `_validate_simple_prompt_reference`
- `_resolve_placeholder`
- `_resolve_input_placeholder`

## Checklist mapping
- Plan milestone 2 / compile validation: reject `Workflow.Input.message` with the spec text.
- Plan milestone 2 / prompt validation: allow bare `{input.message}` alongside existing `ctx.input.message`.
- Plan milestone 2 / runtime rendering: resolve bare `input.message` and typed fields through the composite input view, while surfacing unknown bare `input.*` fields as execution errors.

## Intended behavior changes
- `compile_workflow(...)` now fails when `Workflow.Input` declares a field named `message`.
- Simple-step prompt validation now accepts bare `{input.message}`.
- Runtime template rendering no longer silently empties unknown bare `input.*` placeholders.

## Preserved invariants
- `message` remains separate from persisted `workflow_input`.
- `input.message` continues to resolve from the run request/composite input view.
- `None` values still render as `""` after successful placeholder resolution.
- Child-workflow dict input compatibility was not changed.

## Known non-changes
- No SDK facade or SDK-only typed-input coercion helper was introduced in this phase.
- No broader placeholder syntax redesign was attempted outside `input.message` and bare `input.*` error handling.

## Validation performed
- `python3 -m py_compile autoloop/core/compiler.py autoloop/core/discovery.py autoloop/core/artifacts.py`
- `python3 -m py_compile tests/contract/test_engine_contracts.py tests/unit/test_validation.py tests/unit/test_simple_surface.py`
- Environment limitation: `pytest` and `pydantic` are not installed in the provided interpreter, so runtime/unit execution could not be run in this turn.

## Assumptions
- The phase-local requirement to keep unknown input placeholders as errors applies to bare runtime `input.*` placeholders as well as validated `ctx.input.*` placeholders.
