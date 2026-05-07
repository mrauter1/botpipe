# Test Strategy

- Task ID: standalone-implementation-spec-ctx-prompt-bindin-edf74165
- Pair: test
- Phase ID: contract-test-alignment
- Phase Directory Key: contract-test-alignment
- Phase Title: Align Remaining ctx.input.message Contract Test
- Scope: phase-local producer artifact

## Behavior To Coverage Map
- Undeclared `ctx.input.message` fails instead of aliasing request text:
  `tests/contract/test_engine_contracts.py::test_runtime_templates_reject_undeclared_ctx_input_message_without_typed_input`
  `tests/unit/test_primitives_and_stores.py::test_render_runtime_template_rejects_undeclared_ctx_input_message`
- Declared `Input.message` stays separate from `ctx.message` request text:
  `tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_declared_ctx_input_message_separately_from_request`
  `tests/unit/test_primitives_and_stores.py::test_render_runtime_template_resolves_declared_ctx_input_message_separately_from_request`
- Bare `{input.message}` compatibility stays on runtime/request text:
  `tests/unit/test_primitives_and_stores.py::test_render_runtime_template_bare_input_message_uses_runtime_message`
  `tests/unit/test_primitives_and_stores.py::test_render_runtime_template_keeps_bare_input_message_separate_from_typed_ctx_input_message`
  `tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_bare_input_message_and_fields`
- File-backed `ctx.message` failure and forwarding invariants remain intact:
  `tests/contract/test_engine_contracts.py::test_engine_context_message_raises_when_run_snapshot_is_removed_after_context_construction`
  `tests/contract/test_engine_contracts.py::test_workflow_step_message_can_forward_ctx_message_into_child_request_snapshot`

## Preserved Invariants Checked
- `ctx.input.message` never falls back to request text unless `Workflow.Input` explicitly declares `message`.
- Bare `{input.message}` still resolves the runtime/request message, even when a typed `Input.message` also exists.
- `ctx.message` continues to read the run-local request snapshot and powers child `workflow_step(message="{ctx.message}")` forwarding.

## Edge Cases And Failure Paths
- No typed input present at all for `ctx.input.message`.
- Typed input present but `message` absent from the declared schema.
- Typed `Input.message` present alongside the bare compatibility shim.
- Run snapshot removed after context construction.

## Known Gaps
- No additional compile-time validation coverage was added in this phase; this slice stays focused on runtime/template behavior and the required contract reruns.
