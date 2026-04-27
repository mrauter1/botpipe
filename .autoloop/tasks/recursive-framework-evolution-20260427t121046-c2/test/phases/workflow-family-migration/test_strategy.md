# Test Strategy

- Task ID: recursive-framework-evolution-20260427t121046-c2
- Pair: test
- Phase ID: workflow-family-migration
- Phase Directory Key: workflow-family-migration
- Phase Title: Workflow Migration
- Scope: phase-local producer artifact

## Coverage Map

- Behavior: selected-workflow capture handlers consume the shared seam output directly for canonical naming.
  Tests:
  `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py::test_candidate_workflow_capture_step_normalizes_alias_without_revalidating_snapshot`
  `tests/runtime/test_workflow_to_eval_suite.py::test_workflow_to_eval_suite_capture_step_normalizes_alias_without_revalidating_snapshot`
  `tests/runtime/test_workflow_run_history_to_failure_modes.py::test_workflow_run_history_capture_step_normalizes_alias_and_preserves_filtered_run_ids`
  `tests/runtime/test_workflow_package_to_composable_building_blocks.py::test_workflow_package_to_composable_building_blocks_capture_step_normalizes_alias_and_writes_baseline_context`

- Behavior: optimizer-family source-manifest generation preserves canonical workflow identity when invoked through an alias.
  Test:
  `tests/unit/test_optimization_helpers.py::test_write_selected_workflow_source_manifest_normalizes_alias_to_canonical_workflow_name`

## Preserved Invariants

- Alias references still resolve to the canonical selected workflow name written into `selected_workflow_capability.json`, `selected_workflow_run_history.json`, `selected_workflow_decomposition_surface.json`, and `selected_workflow_source_manifest.json`.
- Workflow-local capture outputs still materialize the same artifact files and downstream context:
  run-history evidence IDs remain aligned with the captured history snapshot.
  decomposition capture still writes baseline parent context and fallback request evidence when no explicit evidence paths are supplied.

## Edge Cases

- Capture steps are exercised with workflow aliases rather than canonical names to catch regressions in seam-driven normalization.
- The optimizer source manifest is exercised with an alias input to prove canonical identity survives helper reuse.

## Failure Paths / Stabilization

- Candidate, eval-suite, and run-history capture tests monkeypatch the underlying `workflow.py` validator symbol to fail fast if the handler starts revalidating capability snapshots during capture again.
- All added tests are filesystem-local and deterministic; no timing, network, or nondeterministic ordering dependencies were introduced.

## Validation Run

- `pytest -q tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py tests/runtime/test_workflow_to_eval_suite.py tests/runtime/test_workflow_run_history_to_failure_modes.py tests/runtime/test_workflow_package_to_composable_building_blocks.py tests/runtime/test_workflow_run_traces_to_optimization_candidates.py tests/unit/test_optimization_helpers.py tests/test_architecture_baseline_docs.py`
  Result: `214 passed, 588 warnings`

## Known Gaps

- I did not broaden coverage into prompt wording or publication-policy semantics because those were explicitly out of scope for this phase.
- The existing Pydantic `schema` field-name warnings in optimization-candidate contracts remain unchanged and were not normalized by these tests.
