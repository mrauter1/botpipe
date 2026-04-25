# Test Strategy

- Task ID: recursive-framework-evolution-20260424t163807-c8
- Pair: test
- Phase ID: proof-docs-memory-sync
- Phase Directory Key: proof-docs-memory-sync
- Phase Title: Proof, Docs, And Memory Sync
- Scope: phase-local producer artifact

## Behavior-to-Test Coverage Map

- Converged selected-workflow helper-family docs boundary
  - Coverage: `tests/test_architecture_baseline_docs.py::test_authoring_doc_describes_shared_validation_helper_boundary`
  - Coverage: `tests/test_architecture_baseline_docs.py::test_authoring_doc_describes_converged_selected_workflow_helper_family_boundary`
  - Checks: explicit validator entrypoints, explicit family boundary, preserved three-artifact contract, and no runtime/root authoring-surface widening.

- Cycle-8 recursive-memory closeout synchronization
  - Coverage: `tests/test_architecture_baseline_docs.py::test_recursive_memory_records_cycle_eight_selected_workflow_closeout_sync`
  - Checks: charter no-doctrine-change note, roadmap closeout note, gap-ledger closeout note, candidate-ledger closeout note, validation-ledger closeout note, and the final focused proof result marker.

- Preserved selected-workflow helper and workflow-family behavior
  - Coverage: `tests/unit/test_validation.py`
  - Coverage: `tests/unit/test_stdlib_and_extensions.py`
  - Coverage: `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
  - Coverage: `tests/runtime/test_workflow_to_eval_suite.py`
  - Coverage: `tests/runtime/test_workflow_run_history_to_failure_modes.py`
  - Coverage: `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
  - Coverage: `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
  - Checks: shared validation helpers, shared selected-workflow helper seams, and no regression in the affected workflow consumers.

## Edge Cases

- Authoring docs name the selected-workflow validation seam conceptually but omit one or more concrete validator entrypoints.
- Recursive-memory closeout updates only some of the standing files, leaving cycle-8 notes inconsistent.
- Closeout docs blur the three distinct selected-workflow artifact contracts into one merged surface.

## Failure Paths

- Missing cycle-8 proof/docs closeout note in any one of the five standing recursive-memory files.
- Missing explicit `257 passed` marker in the synchronized cycle-8 closeout notes.
- Drift between `docs/authoring.md` and the baseline-doc assertions for the selected-workflow helper family.

## Preserved Invariants Checked

- No new workflow package is normalized by the tests.
- No CLI, runtime-owned routing, provider, `workflow.toml`, or `ctx.invoke_workflow(...)` behavior change is encoded into expectations.
- Selected-workflow capability, authoring-surface, and decomposition-surface artifacts remain separate contracts.

## Stabilization

- Tests are deterministic and filesystem-local only.
- Coverage relies on fixed string markers in docs and recursive-memory artifacts rather than timestamps, ordering-sensitive output, or network access.

## Known Gaps

- No new workflow-doc assertions were added because this phase did not change workflow package docs directly.
- The focused proof does not expand into untargeted full-repo coverage; it stays on the selected-workflow helper family plus baseline-doc surfaces per phase scope.
