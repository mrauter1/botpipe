# Test Strategy

- Task ID: recursive-framework-evolution-20260424t163807-c8
- Pair: test
- Phase ID: extract-selected-workflow-validators
- Phase Directory Key: extract-selected-workflow-validators
- Phase Title: Extract Selected-Workflow Validators
- Scope: phase-local producer artifact

## Behavior Coverage Map

- Shared validator seam
  - `tests/unit/test_stdlib_and_extensions.py`
  - Covers happy-path validation for capability, authoring, decomposition, artifact-alignment, and paired capability/authoring helpers.
  - Covers failure-path validation for artifact selected-workflow drift and paired capability/authoring selected-workflow drift.
- Adaptation workflow publish path
  - `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
  - Covers preserved publish behavior plus failure on `adapted_execution_summary.json` selected-workflow drift through the shared artifact-alignment helper.
- Eval-suite workflow publish path
  - `tests/runtime/test_workflow_to_eval_suite.py`
  - Covers preserved publish behavior plus failure on `workflow_eval_suite_summary.json` selected-workflow drift through the shared artifact-alignment helper.
- Adjacent preserved consumers
  - `tests/runtime/test_workflow_run_history_to_failure_modes.py`
  - `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
  - `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
  - Revalidated the already-covered run-history, refinement, and decomposition selected-workflow/state-drift paths against the shared seam.

## Preserved Invariants Checked

- Separate selected-workflow artifacts remain intact and distinct.
- Workflow-local publication policy stays local:
  - eval-suite case policy
  - run-history evidence/publication policy
  - refinement overlay/evaluation policy
  - decomposition building-block policy
- No CLI/runtime/provider contract drift is encoded in new expectations.

## Edge Cases And Failure Paths

- Artifact payload selected-workflow mismatch against capability snapshot.
- Capability/authoring snapshot mismatch inside the paired refinement helper seam.
- Publish-step summary selected-workflow drift in adaptation and eval-suite consumers.
- Existing refinement workflow-state mismatch remains covered and unchanged.

## Flake Risk And Stabilization

- No network or timing dependencies were added.
- Tests stay deterministic by mutating local JSON fixtures/context artifacts only and by using the existing scripted provider/runtime helpers.

## Known Gaps

- No new tests were added for portfolio/company workflows because they are out of scope for this phase.
- Domain-specific publication policy remains covered by existing workflow-local tests rather than new shared-helper assertions.

## Validation Run

- `PYTHONPATH=/home/rauter/autoloop_v3_bkp ./.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py tests/runtime/test_workflow_to_eval_suite.py tests/runtime/test_workflow_run_history_to_failure_modes.py tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py tests/runtime/test_workflow_package_to_composable_building_blocks.py tests/test_architecture_baseline_docs.py`
- Result: `221 passed`
