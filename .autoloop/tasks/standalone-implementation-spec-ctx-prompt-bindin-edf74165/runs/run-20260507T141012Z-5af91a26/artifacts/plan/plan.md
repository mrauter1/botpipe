# Contract Test Alignment Plan

## Scope
- Update only the stale contract regression in `tests/contract/test_engine_contracts.py` that still treats undeclared `{ctx.input.message}` as request text.
- Keep runtime behavior, the bare `{input.message}` compatibility shim, and file-backed `ctx.message` semantics unchanged unless the focused contract rerun exposes a real mismatch.

## Relevant Findings
- `tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_ctx_input_message_without_typed_input` still expects undeclared `{ctx.input.message}` to resolve `"artifact-request"`.
- `tests/unit/test_primitives_and_stores.py::test_render_runtime_template_rejects_undeclared_ctx_input_message` already asserts the intended runtime failure: undeclared `ctx.input.message` raises `WorkflowExecutionError` for unknown runtime field `message`.
- Adjacent contract coverage already exists for the declared `Input.message` positive case, unreadable `request.md` failure, and `workflow_step(message="{ctx.message}")` child forwarding.

## Implementation Slice
1. Align the stale contract test with the implemented contract.
- Preferred direction: convert `test_runtime_templates_resolve_ctx_input_message_without_typed_input` into a negative contract that asserts undeclared `{ctx.input.message}` fails with the current `WorkflowExecutionError`.
- If the scenario still needs request-text coverage, assert that through `{ctx.message}` instead of reviving the retired alias.
2. Preserve the surrounding request-vs-input split.
- Leave `test_runtime_templates_resolve_declared_ctx_input_message_separately_from_request` as the positive typed-input case.
- Do not touch bare `{input.message}` contract coverage or runtime resolver code unless the focused contract rerun proves a real mismatch.
3. Validate with the focused contract slice named in the request.
- `tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_ctx_input_message_without_typed_input`
- `tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_declared_ctx_input_message_separately_from_request`
- `tests/contract/test_engine_contracts.py::test_engine_context_message_raises_when_run_snapshot_is_removed_after_context_construction`
- `tests/contract/test_engine_contracts.py::test_workflow_step_message_can_forward_ctx_message_into_child_request_snapshot`

## Interface And Compatibility Notes
- `ctx.message` remains the run-local request snapshot text loaded from `request.md`.
- `ctx.input.message` is valid only when `Workflow.Input` declares `message`; otherwise it should fail rather than alias request text.
- Bare `{input.message}` compatibility remains intentional and out of scope for this slice.

## Regression Controls
- Invariants:
  - Undeclared `{ctx.input.message}` must not resolve from request text.
  - Declared `{ctx.input.message}` must remain distinct from `{ctx.message}`.
  - Unreadable run snapshots must keep raising the existing `WorkflowExecutionError`.
  - `workflow_step(message="{ctx.message}")` must keep forwarding the parent request text into the child run snapshot.
- Validation approach:
  - Prefer updating the stale contract into an explicit failure assertion so the undeclared `ctx.input` behavior remains directly covered.
  - Reopen runtime implementation only if the focused contract rerun contradicts the already-passing unit-level behavior.

## Risk Register
- Risk: swapping the stale test to `{ctx.message}` only would drop direct coverage for undeclared `ctx.input.message` failure.
  Mitigation: keep the test focused on the failure path, or add a separate `{ctx.message}` assertion only if needed for request-text coverage.
- Risk: the focused contract rerun reveals a real mismatch between unit and contract behavior.
  Mitigation: treat the rerun as the gate for any runtime changes instead of widening scope preemptively.
- Rollback:
  - Revert only the contract-test expectation change if the focused rerun proves the previous expectation was still intentionally required.
