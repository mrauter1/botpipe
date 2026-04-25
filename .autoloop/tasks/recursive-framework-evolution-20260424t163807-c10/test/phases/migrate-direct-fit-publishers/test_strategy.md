# Test Strategy

- Task ID: recursive-framework-evolution-20260424t163807-c10
- Pair: test
- Phase ID: migrate-direct-fit-publishers
- Phase Directory Key: migrate-direct-fit-publishers
- Phase Title: Migrate Direct-Fit Publishers
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- `task_to_candidate_workflow_set` typed summary read at publish time
  - Covered by: `test_task_to_candidate_workflow_set_publish_rejects_summary_missing_typed_required_field`
  - Checks: missing required summary field fails at typed artifact load instead of falling through raw dict parsing
- `task_to_workflow_strategy` typed summary read at publish time
  - Covered by: `test_task_to_workflow_strategy_publish_strategy_rejects_summary_missing_typed_required_field`
  - Checks: missing required strategy summary field raises `ValidationError` before workflow-local policy checks run
- `candidate_workflow_to_adapted_execution_plan` typed summary read at publish time
  - Covered by: `test_candidate_workflow_to_adapted_execution_plan_publish_rejects_summary_missing_typed_required_field`
  - Checks: missing required adapted-execution summary field fails at typed summary read
- `workflow_to_eval_suite` typed summary read at publish time
  - Covered by: `test_workflow_to_eval_suite_publish_rejects_summary_missing_typed_required_field`
  - Checks: missing required eval-suite summary field fails at typed summary read
- `workflow_to_eval_suite` typed validated-manifest read at publish time
  - Covered by: `test_workflow_to_eval_suite_publish_rejects_validated_manifest_missing_typed_required_field`
  - Checks: malformed validated manifest returned from the helper is re-read through the typed manifest seam and rejected with `ValidationError`

## Preserved Invariants Checked

- Publish handlers still own cross-artifact, state, and domain-policy checks; the new tests only force failures at the typed artifact boundary.
- Artifact filenames, route tags, and external JSON keys remain unchanged.
- Proposed pre-validation inputs stay raw where the workflow still owns the validation boundary.

## Edge Cases And Failure Paths

- Missing required summary fields in each scoped publish-summary artifact
- Missing required field in `validated_eval_case_manifest.json` after helper output, proving the direct-fit manifest seam is enforced post-validation

## Validation Run

- `PYTHONPATH=/home/rauter/autoloop_v3_bkp ./.venv/bin/pytest -q tests/runtime/test_task_to_candidate_workflow_set.py tests/runtime/test_task_to_workflow_strategy.py tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py tests/runtime/test_workflow_to_eval_suite.py`
- Result: `88 passed`

## Flake Risk / Stabilization

- Uses only `tmp_path`, local file writes, and `monkeypatch`; no time, network, subprocess, or nondeterministic ordering dependencies were introduced.

## Known Gaps

- The scoped tests target the publish-time typed-read boundary only; broader semantic policy coverage remains in the pre-existing runtime and unit suites.
