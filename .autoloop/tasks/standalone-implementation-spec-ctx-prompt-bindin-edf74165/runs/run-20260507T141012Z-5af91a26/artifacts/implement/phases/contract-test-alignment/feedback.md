# Implement ↔ Code Reviewer Feedback

- Task ID: standalone-implementation-spec-ctx-prompt-bindin-edf74165
- Pair: implement
- Phase ID: contract-test-alignment
- Phase Directory Key: contract-test-alignment
- Phase Title: Align Remaining ctx.input.message Contract Test
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 `blocking` [autoloop/core/artifacts.py:239](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/artifacts.py:239), [autoloop/core/artifacts.py:590](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/artifacts.py:590): the current resolver still routes `ctx.input.*` through `Context.input` and still exempts `ctx.input.message` from the no-input guard. On the current tree, reviewer rerun of the focused slice fails 4 tests: undeclared `{ctx.input.message}` does not raise, and declared `{ctx.input.message}` still resolves request text instead of the typed `Input.message`. This misses AC-1, AC-2, and the decision ledger entry that `ctx.*` must stop treating `ctx.input.message` as a request-text alias. Minimal fix: make `ctx.*` resolution read `context.input_fields` rather than the compatibility view, and remove the `field_name != "message"` special-case so the no-input guard applies uniformly while bare `{input.message}` remains on `_resolve_input_placeholder`.

## Cycle 2 Review

- No new findings.
- IMP-001 is resolved on the current tree.
- Reviewer reran `.venv/bin/python -m pytest tests/unit/test_primitives_and_stores.py::test_context_request_surface_reads_run_snapshot_and_task_request_file tests/unit/test_primitives_and_stores.py::test_render_runtime_template_rejects_undeclared_ctx_input_message tests/unit/test_primitives_and_stores.py::test_render_runtime_template_resolves_declared_ctx_input_message_separately_from_request tests/contract/test_engine_contracts.py::test_runtime_templates_reject_undeclared_ctx_input_message_without_typed_input tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_declared_ctx_input_message_separately_from_request tests/contract/test_engine_contracts.py::test_engine_context_message_raises_when_run_snapshot_is_removed_after_context_construction tests/contract/test_engine_contracts.py::test_workflow_step_message_can_forward_ctx_message_into_child_request_snapshot` and all 7 tests passed.
