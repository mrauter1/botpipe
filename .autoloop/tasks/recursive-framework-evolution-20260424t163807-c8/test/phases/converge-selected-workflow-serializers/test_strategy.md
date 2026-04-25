# Test Strategy

- Task ID: recursive-framework-evolution-20260424t163807-c8
- Pair: test
- Phase ID: converge-selected-workflow-serializers
- Phase Directory Key: converge-selected-workflow-serializers
- Phase Title: Converge Selected-Workflow Serializers
- Scope: phase-local producer artifact

## Behavior Coverage Map

- Centralized selected-workflow payload builders in `core/workflow_capabilities.py`
  - Covered by direct unit coverage for `selected_workflow_capability_payload(...)`, `selected_workflow_authoring_surface_payload(...)`, and `selected_workflow_decomposition_surface_payload(...)`
  - Checks preserved authoring/decomposition contract shapes, including repo-relative paths and the deliberate omission of `workflow_name` / `package_name` from the nested decomposition authoring surface
- Thin stdlib selected-workflow writers
  - Covered by existing wrapper contract tests for adaptation, refinement, and decomposition snapshot files
  - Checks wrapper output still matches the pre-existing artifact filenames and top-level JSON contracts
- Shared selected-workflow validation seam
  - Covered by direct unit tests for the new validation helpers plus runtime publication-path tests in adaptation, eval-suite, run-history, refinement, and decomposition workflows
  - Checks generic selected-workflow identity alignment moved to shared helpers without changing workflow-local domain validation

## Preserved Invariants Checked

- `selected_workflow_capability.json`, `selected_workflow_authoring_surface.json`, and `selected_workflow_decomposition_surface.json` remain separate artifacts
- Existing top-level JSON contracts remain unchanged
- Runtime test inference and repo-relative path conversion still match prior decomposition/refinement expectations
- Workflow-specific publication semantics remain local to the consuming workflows

## Edge Cases And Failure Paths

- Optional authoring-surface paths remain nullable when absent
- Single-file workflow capability snapshots still work
- Shared selected-workflow validation helpers reject cross-artifact name drift
- Decomposition nested authoring surface does not grow extra identity fields during centralization

## Proof Run

- `PYTHONPATH=/home/rauter/autoloop_v3_bkp ./.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py tests/runtime/test_workflow_to_eval_suite.py tests/runtime/test_workflow_run_history_to_failure_modes.py tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py tests/runtime/test_workflow_package_to_composable_building_blocks.py tests/test_architecture_baseline_docs.py`
- Result: `219 passed`

## Known Gaps

- No new tests were added for workflow-local domain publication policy beyond the existing runtime suites because that behavior was intentionally out of scope for this serializer-convergence phase.
