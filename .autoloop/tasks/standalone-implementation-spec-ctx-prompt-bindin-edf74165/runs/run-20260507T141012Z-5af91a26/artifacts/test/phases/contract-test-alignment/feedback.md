# Test Author ↔ Test Auditor Feedback

- Task ID: standalone-implementation-spec-ctx-prompt-bindin-edf74165
- Pair: test
- Phase ID: contract-test-alignment
- Phase Directory Key: contract-test-alignment
- Phase Title: Align Remaining ctx.input.message Contract Test
- Scope: phase-local authoritative verifier artifact

- Added a mixed runtime-template regression test proving bare `{input.message}` keeps using request/runtime text while `{ctx.input.message}` resolves declared typed input.
- Covered the required undeclared-`ctx.input.message`, declared-`Input.message`, unreadable-snapshot, and `workflow_step(message="{ctx.message}")` contract scenarios in the strategy map.

## Audit Result

- No findings.
- Auditor reran `.venv/bin/python -m pytest tests/unit/test_primitives_and_stores.py::test_context_request_surface_reads_run_snapshot_and_task_request_file tests/unit/test_primitives_and_stores.py::test_render_runtime_template_rejects_undeclared_ctx_input_message tests/unit/test_primitives_and_stores.py::test_render_runtime_template_resolves_declared_ctx_input_message_separately_from_request tests/unit/test_primitives_and_stores.py::test_render_runtime_template_keeps_bare_input_message_separate_from_typed_ctx_input_message tests/contract/test_engine_contracts.py::test_runtime_templates_reject_undeclared_ctx_input_message_without_typed_input tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_declared_ctx_input_message_separately_from_request tests/contract/test_engine_contracts.py::test_engine_context_message_raises_when_run_snapshot_is_removed_after_context_construction tests/contract/test_engine_contracts.py::test_workflow_step_message_can_forward_ctx_message_into_child_request_snapshot` and all 8 tests passed.
