# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c5
- Pair: test
- Phase ID: front-door-integration-memory-and-proof
- Phase Directory Key: front-door-integration-memory-and-proof
- Phase Title: Front Door Integration Memory And Proof
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- AC-1 front-door composition preserved:
  - Covered by existing `tests/runtime/test_task_to_workflow_strategy.py` compilation, end-to-end run, and publish-time validation tests.
  - Preserved invariants checked: explicit child invocation, adopted child candidate artifacts, parent-local artifact names, `strategy_summary.json` shape, and terminal strategy-only publication.
- AC-2 recursive memory reflects cycle-5 closeout:
  - Covered by `tests/test_architecture_baseline_docs.py::test_recursive_memory_cycle_five_closeout_proof_stays_explicit_without_claiming_recursive_wrapper_parity`.
  - Added in this turn: constrain assertions to the `Cycle 5 Outcome` section, require `103 passed`, and reject stale `102 passed` within that same section.
- AC-3 targeted regression proof stays green:
  - Validate with `.venv/bin/pytest -q tests/runtime/test_task_to_candidate_workflow_set.py tests/runtime/test_task_to_workflow_strategy.py tests/runtime/test_compatibility_runtime.py tests/unit/test_stdlib_and_extensions.py tests/runtime/test_workflow_builder_package.py tests/runtime/test_investigation_request_to_evidence_pack.py tests/runtime/test_security_finding_to_verified_remediation.py tests/test_architecture_baseline_docs.py`.

## Edge cases

- Split-brain roadmap updates where the cycle-5 section contains both the new `103 passed` count and the stale `102 passed` count.
- Future edits that move the closeout command/count outside `Cycle 5 Outcome` while leaving the older value in place.

## Failure paths

- `tests/test_architecture_baseline_docs.py` now fails if the cycle-5 roadmap section omits the accepted targeted command, records the wrong pass count, or retains the stale count in the same outcome section.

## Known gaps

- The test suite intentionally validates the documented closeout command/result, not the dynamic pytest collection count at runtime.
- `recursive_autoloop/` wrapper/template parity remains out of scope for this phase.
