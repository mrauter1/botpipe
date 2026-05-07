# Implementation Notes

- Task ID: standalone-implementation-spec-ctx-prompt-bindin-edf74165
- Pair: implement
- Phase ID: contract-test-alignment
- Phase Directory Key: contract-test-alignment
- Phase Title: Align Remaining ctx.input.message Contract Test
- Scope: phase-local producer artifact

## Files Changed
- `autoloop/core/artifacts.py`
- `tests/unit/test_primitives_and_stores.py`
- `tests/contract/test_engine_contracts.py`
- `.autoloop/tasks/standalone-implementation-spec-ctx-prompt-bindin-edf74165/runs/run-20260507T141012Z-5af91a26/decisions.txt`
- `.autoloop/tasks/standalone-implementation-spec-ctx-prompt-bindin-edf74165/runs/run-20260507T141012Z-5af91a26/artifacts/implement/phases/contract-test-alignment/implementation_notes.md`

## Symbols Touched
- `PromptContextView.input`
- `_resolve_ctx_placeholder`
- `test_render_runtime_template_rejects_undeclared_ctx_input_message`
- `test_render_runtime_template_resolves_declared_ctx_input_message_separately_from_request`
- `test_runtime_templates_reject_undeclared_ctx_input_message_without_typed_input`
- `test_runtime_templates_resolve_declared_ctx_input_message_separately_from_request`

## Checklist Mapping
- Plan item 1: converted the stale undeclared `ctx.input.message` contract into a failure assertion.
- Plan item 2: preserved the declared `Input.message` contract and restored `ctx.input.message` template resolution to the typed-input field path, while leaving request-text access on `ctx.message`.
- Plan item 3: reran the four focused contract tests named in the phase plan.

## Assumptions
- A focused runtime fix was in scope once contract reruns showed declared `ctx.input.message` still aliased request text.

## Preserved Invariants
- Undeclared `{ctx.input.message}` does not alias request text.
- Declared `{ctx.input.message}` remains distinct from `{ctx.message}`.
- Bare `{input.message}` compatibility is unchanged.
- File-backed `ctx.message` snapshot behavior is unchanged.

## Intended Behavior Changes
- `ctx.input.*` template resolution now reads only declared workflow input fields instead of the compatibility view that includes request text as `message`.
- Contract and unit coverage now expect undeclared `{ctx.input.message}` to fail and declared `{ctx.input.message}` to resolve the typed input field.

## Known Non-Changes
- No validation or documentation behavior changed.
- Bare `{input.message}` compatibility and `Context.input.message` behavior were not removed.

## Expected Side Effects
- Prompt/template code using `ctx.input.message` without a declared `Input.message` field now fails consistently instead of falling through to request text.

## Validation Performed
- `.venv/bin/python -m pytest tests/unit/test_primitives_and_stores.py::test_context_request_surface_reads_run_snapshot_and_task_request_file tests/unit/test_primitives_and_stores.py::test_render_runtime_template_rejects_undeclared_ctx_input_message tests/unit/test_primitives_and_stores.py::test_render_runtime_template_resolves_declared_ctx_input_message_separately_from_request tests/contract/test_engine_contracts.py::test_runtime_templates_reject_undeclared_ctx_input_message_without_typed_input tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_declared_ctx_input_message_separately_from_request tests/contract/test_engine_contracts.py::test_engine_context_message_raises_when_run_snapshot_is_removed_after_context_construction tests/contract/test_engine_contracts.py::test_workflow_step_message_can_forward_ctx_message_into_child_request_snapshot`
- Result: `7 passed`.

## Deduplication Or Centralization Decisions
- Kept the request-text compatibility shim centralized on bare `{input.*}` / `Context.input` instead of duplicating alias behavior inside `ctx.*` resolution.
