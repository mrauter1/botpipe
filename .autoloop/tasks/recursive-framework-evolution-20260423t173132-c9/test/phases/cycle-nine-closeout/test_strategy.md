# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c9
- Pair: test
- Phase ID: cycle-nine-closeout
- Phase Directory Key: cycle-nine-closeout
- Phase Title: Cycle Nine Closeout
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Cycle-9 recursive-memory baseline is recorded in all four standing memory files.
  - Covered by `tests/test_architecture_baseline_docs.py::test_recursive_memory_files_record_cycle_nine_closeout_baseline`.
- Current deferred-idea posture moves from `workflow_run_history_to_failure_modes` to `workflow_portfolio_to_operating_system`.
  - Covered by the updated deferred-status assertions plus `tests/test_architecture_baseline_docs.py::test_recursive_memory_cycle_nine_statuses_keep_diagnostics_out_of_deferred`.
- Cycle-9 closeout proof wording stays exact for command, pass count, and no-wrapper-parity posture.
  - Covered by `tests/test_architecture_baseline_docs.py::test_recursive_memory_cycle_nine_closeout_proof_stays_explicit_without_claiming_recursive_wrapper_parity`.

## Preserved invariants checked

- No runtime/provider contract widening or public CLI/runtime drift is normalized by the closeout tests.
- Earlier shipped workflows and building blocks remain out of the roadmap deferred list where prior closeouts marked them shipped.
- The closeout continues to treat recursive wrapper/template cleanup as out of scope.

## Edge cases and failure paths

- Fails if the roadmap keeps `workflow_run_history_to_failure_modes` in `Deferred Ideas`.
- Fails if the cycle-9 proof string drifts to the earlier provisional `126 passed` count or another exact-string mismatch.
- Fails if cycle-9 recursive-memory sections omit the chosen seam, shipped workflow, or next deferred candidate.

## Validation executed

- `.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py tests/runtime/test_workspace_and_context.py tests/runtime/test_workflow_builder_package.py tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py tests/runtime/test_workflow_run_history_to_failure_modes.py tests/test_architecture_baseline_docs.py`
- Result: `122 passed`

## Flake risk / stabilization

- No timing, network, or nondeterministic ordering dependence was added.
- Coverage relies on exact-string file reads plus deterministic pytest subsets only.

## Known gaps

- This phase does not add coverage for `recursive_autoloop/` wrapper cleanup because that scope remains explicitly deferred.
