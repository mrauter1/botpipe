# Test Strategy

- Task ID: recursive-framework-evolution-20260424t163807-c9
- Pair: test
- Phase ID: migrate-governance-and-diagnostic-publishers
- Phase Directory Key: migrate-governance-and-diagnostic-publishers
- Phase Title: Migrate Governance And Diagnostic Publishers
- Scope: phase-local producer artifact

## Behavior-To-Test Coverage Map

- Shared helper happy path
  - `tests/unit/test_validation.py`
  - Covers normalized workflow-name extraction from capability snapshots and portfolio-health payloads.
- Shared helper failure paths
  - `tests/unit/test_validation.py`
  - Covers empty capability snapshots, duplicate scoped workflow names, and malformed snapshot shapes for both helper entrypoints.
- Preserved governance publish behavior
  - `tests/runtime/test_workflow_portfolio_to_operating_system.py`
  - Confirms publish-time artifact contracts and scoped portfolio validation still pass after helper extraction.
- Preserved company-operation publish behavior
  - `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
  - Confirms publish-time artifact contracts and scoped company/portfolio validation still pass after helper extraction.
- Preserved diagnostic publish behavior
  - `tests/runtime/test_workflow_run_history_to_failure_modes.py`
  - Confirms the existing shared publish-validation seam still holds and the diagnostic contract is unchanged.
- Documentation / boundary guardrail
  - `tests/test_architecture_baseline_docs.py`
  - Confirms the docs surface remains aligned with the shared validation seam.

## Preserved Invariants Checked

- No workflow artifact names, receipt filenames, route tags, or prompt paths changed.
- Unknown-reference checks and domain publication semantics remain workflow-local.
- `workflow_run_history_to_failure_modes` keeps its narrower diagnostic contract.

## Edge Cases And Failure Paths

- Capability snapshot with no usable workflow names.
- Capability snapshot with a non-list `workflows` payload or non-object entries.
- Portfolio-health payload with duplicate scoped workflow names.
- Portfolio-health payload with a non-list `workflows` payload.

## Known Gaps

- No new workflow-specific negative tests were added for unknown-reference branches because those semantics were unchanged and are already covered by the scoped runtime suites.
- Adjacent workflows that still keep local snapshot readers remain out of phase scope.
