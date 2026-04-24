# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c11
- Pair: test
- Phase ID: recursive-memory-and-validation
- Phase Directory Key: recursive-memory-and-validation
- Phase Title: Refresh Memory And Prove The Slice
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Behavior covered: cycle-11 recursive-memory baseline records the shipped decomposition seam, the shipped decomposition workflow/building block, and `company_operation_to_recursive_improvement_cycle` as the next deferred follow-on.
  Test coverage: `tests/test_architecture_baseline_docs.py::test_recursive_memory_files_record_cycle_eleven_closeout_baseline`
- Behavior covered: the current global `Deferred Ideas` list treats decomposition as shipped and the company-level learner as deferred.
  Test coverage: `tests/test_architecture_baseline_docs.py::test_recursive_memory_cycle_eleven_statuses_keep_decomposition_out_of_deferred`
- Behavior covered: cycle-11 closeout proof records the planned primary pytest suite, the `104 passed` result, and the explicit reason the conditional refinement regression was unnecessary.
  Test coverage: `tests/test_architecture_baseline_docs.py::test_recursive_memory_cycle_eleven_closeout_proof_stays_explicit_without_claiming_recursive_wrapper_parity`
- Preserved invariant checked: cycle-11 closeout proof must not regress to the earlier runtime-only `20 passed` evidence string.
  Test coverage: same cycle-11 closeout-proof test via a negative assertion
- Preserved invariant checked: the helper seam and decomposition workflow package remain covered by the targeted proof suite instead of broad-suite execution.
  Test coverage: `tests/unit/test_stdlib_and_extensions.py` and `tests/runtime/test_workflow_package_to_composable_building_blocks.py` in the primary suite

## Edge cases

- Current-state versus historical-state semantics for `framework_roadmap.md` `Deferred Ideas`; the tests lock the current global list while still checking the cycle-11 candidate-entry history separately.
- Stale closeout-evidence drift; the tests reject the replaced runtime-only `20 passed` evidence string.

## Failure paths

- Missing cycle-11 memory updates or an incorrect deferred follow-on fail the baseline/status tests.
- Reverting the closeout proof to the narrower runtime-only suite or losing the conditional-regression rationale fails the cycle-11 closeout-proof test.

## Known gaps

- No extra refinement-regression suite was added because shared overlay-validation logic was not extracted in this cycle.
- No broader full-suite execution was added; the phase contract only requires the targeted primary suite.
