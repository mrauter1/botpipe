## Follow-up implementation request: remove the last stale undeclared `{ctx.input.message}` contract test

The runtime and validation changes for `ctx.message` versus `ctx.input` are implemented, but the final codebase still contains one stale contract regression that asserts the retired alias behavior.

### Required change

- Update `tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_ctx_input_message_without_typed_input` so it no longer expects undeclared `{ctx.input.message}` to resolve to request text.
- If the test is still meant to cover request text, switch it to `{ctx.message}`.
- If the test is meant to cover undeclared `ctx.input` access, make it assert the current failure behavior instead.

### Required validation

- Rerun focused contract coverage that includes:
  - the updated undeclared-`ctx.input.message` test,
  - the declared-`Input.message` positive case,
  - unreadable run-snapshot failure,
  - `workflow_step(message=...)` forwarding/rendering through `{ctx.message}`.

### Non-goals

- Do not reopen runtime implementation unless new evidence shows a real behavior mismatch.
- Do not remove the intentional bare `{input.message}` compatibility shim.
- Do not change the already-correct file-backed `ctx.message` behavior.
