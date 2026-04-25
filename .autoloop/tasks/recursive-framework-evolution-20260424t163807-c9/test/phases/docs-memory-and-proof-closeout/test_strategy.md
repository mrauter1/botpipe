# Test Strategy

- Task ID: recursive-framework-evolution-20260424t163807-c9
- Pair: test
- Phase ID: docs-memory-and-proof-closeout
- Phase Directory Key: docs-memory-and-proof-closeout
- Phase Title: Docs Memory And Proof Closeout
- Scope: phase-local producer artifact

## Coverage Map

- Behavior: shared publication-validation boundary remains documented as one additive governance/diagnostic helper family in `docs/authoring.md`
  - Coverage: `tests/test_architecture_baseline_docs.py`
  - Why this is sufficient: the architecture baseline docs test already pins the validation-helper boundary language and catches drift in the public authoring guidance without adding a second docs-only suite

- Behavior: preserved helper semantics still work for the migrated family
  - Coverage: `tests/unit/test_validation.py`
  - Why this is sufficient: this is the shared helper regression surface for the publication-validation and snapshot-reader seam

- Behavior: preserved publish/runtime behavior for the three migrated workflows
  - Coverage:
    - `tests/runtime/test_workflow_portfolio_to_operating_system.py`
    - `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
    - `tests/runtime/test_workflow_run_history_to_failure_modes.py`
  - Why this is sufficient: the closeout phase changed docs/memory only, so the right regression net is the existing scoped runtime proof rather than new workflow-local assertions

- Behavior: closeout compatibility claims stay true
  - Coverage:
    - runtime suites above
    - `tests/test_architecture_baseline_docs.py`
  - Preserved invariants checked:
    - no new workflow required for the cycle closeout
    - no CLI/runtime/provider/`ctx.invoke_workflow(...)` contract drift was introduced by the docs-memory sync

## Edge Cases / Failure Paths

- Docs wording drift in the authoring guide
  - Covered by `tests/test_architecture_baseline_docs.py`
  - Prior failure observed in implement phase: tightening wording too far removed a required baseline sentence; the docs test correctly caught that regression

- Workflow-family regression despite docs-only closeout
  - Covered by the three scoped runtime suites and `tests/unit/test_validation.py`
  - Stabilization: keep the suite deterministic and limited to the already-migrated family

## Test Changes

- No repository test files were modified in this phase.
- Rationale: the closeout changed documentation, recursive-memory ledgers, and phase-local artifacts only; the existing scoped proof surface already covers the helper seam, the three migrated workflows, and the architecture-baseline docs required by AC-2.

## Validation Run

- Command:
  - `PYTHONPATH=/home/rauter/autoloop_v3_bkp ./.venv/bin/pytest -q tests/unit/test_validation.py tests/runtime/test_workflow_portfolio_to_operating_system.py tests/runtime/test_company_operation_to_recursive_improvement_cycle.py tests/runtime/test_workflow_run_history_to_failure_modes.py tests/test_architecture_baseline_docs.py`
- Expected result:
  - all scoped tests pass deterministically on the final closeout artifact state

## Known Gaps

- No repository test currently asserts the recursive-memory closeout notes directly.
- That gap is acceptable for this phase because the recursive-memory files are phase/cycle bookkeeping artifacts, while the durable regression surface remains the shared helper behavior, migrated workflow runtime behavior, and architecture-baseline docs contract.
