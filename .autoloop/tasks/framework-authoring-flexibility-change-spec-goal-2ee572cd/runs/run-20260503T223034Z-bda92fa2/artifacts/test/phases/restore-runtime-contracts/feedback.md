# Test Author ↔ Test Auditor Feedback

- Task ID: framework-authoring-flexibility-change-spec-goal-2ee572cd
- Pair: test
- Phase ID: restore-runtime-contracts
- Phase Directory Key: restore-runtime-contracts
- Phase Title: Restore Runtime Contracts
- Scope: phase-local authoritative verifier artifact

- Added direct happy-path coverage for `{worklist.<name>.current.payload.<path>}` by extending the scoped prompt rendering contract test.
- Added no-PyYAML fallback regressions for malformed indentation under scalar parents and over-indented sibling mappings.
- Added a valid nested no-PyYAML runtime-config happy-path test; it currently fails and exposes a remaining implementation gap where sibling nested mappings under `runtime` are rejected after a scalar child.

- `TST-001` `blocking` [tests/contract/test_engine_contracts.py::test_prompt_runtime_reports_missing_payload_path_with_placeholder_context]
  The new coverage still does not directly assert the failure-path contract for `{worklist.<name>.current.payload.<path>}` when a current item exists but the nested payload path is missing. The request and phase contract require both `{item.payload.<path>}` and `{worklist.<name>.current.payload.<path>}` to preserve placeholder-specific `WorkflowExecutionError` messages, but the current suite only checks the `item.payload` form and a separate “missing current item” case. A regression in `_resolve_worklist_placeholder(...)` could therefore break or reword the worklist-current payload-path failure while the existing tests still pass. Minimal correction: add a direct current-item-present test that asserts `prompt placeholder {worklist.gate.current.payload.foo} references missing payload path 'foo'`.
