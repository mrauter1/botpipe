# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c7
- Pair: test
- Phase ID: workflow-to-eval-suite-package
- Phase Directory Key: workflow-to-eval-suite-package
- Phase Title: Workflow To Eval Suite
- Scope: phase-local producer artifact

## Behavior To Test Coverage Map

- AC-1 workflow discovery and typed control contracts:
  `tests/runtime/test_workflow_to_eval_suite.py::test_repo_workflows_namespace_discovers_workflow_to_eval_suite_package`
  `tests/runtime/test_workflow_to_eval_suite.py::test_workflow_to_eval_suite_package_compiles_with_explicit_control_contracts`
- AC-2 scripted publish proof without selected-workflow execution:
  `tests/runtime/test_workflow_to_eval_suite.py::test_workflow_to_eval_suite_package_runs_and_publishes_terminal_eval_artifacts`
- AC-3 publish-time validation and failure paths:
  `tests/runtime/test_workflow_to_eval_suite.py::test_workflow_to_eval_suite_publish_rejects_invalid_selected_workflow_reference`
  `tests/runtime/test_workflow_to_eval_suite.py::test_workflow_to_eval_suite_publish_rejects_malformed_case_kind`
  `tests/runtime/test_workflow_to_eval_suite.py::test_workflow_to_eval_suite_publish_rejects_duplicate_case_ids`
  `tests/runtime/test_workflow_to_eval_suite.py::test_workflow_to_eval_suite_publish_rejects_invalid_case_parameters`
  `tests/runtime/test_workflow_to_eval_suite.py::test_workflow_to_eval_suite_publish_rejects_unknown_expected_artifacts`
  `tests/runtime/test_workflow_to_eval_suite.py::test_workflow_to_eval_suite_publish_rejects_summary_drift_from_validated_manifest`
- AC-4 prompt-contract explicitness:
  `tests/runtime/test_workflow_to_eval_suite.py::test_workflow_to_eval_suite_prompt_readme_lists_route_grammar_and_runtime_boundary`
  `tests/runtime/test_workflow_to_eval_suite.py::test_workflow_to_eval_suite_prompts_keep_step_local_contracts_explicit`

## Preserved Invariants Checked

- The package stops at suite publication and does not create a downstream `wf_release_candidate_to_go_no_go` run.
- The validated manifest, summary, next action, and receipt stay aligned on case ids, case kinds, expected-artifact coverage, and authoritative artifacts.
- Runtime control remains narrow: the prompt bundle README still documents route grammar and runtime-injected control surfaces explicitly.

## Edge Cases And Failure Paths

- Blank `selected_workflow` is rejected during parameter coercion.
- Repeatable input normalization trims, de-duplicates, and preserves order for `constraints` and `evidence_expectations`.
- `needs_rework` on the packaging step preserves the same work-item boundary while updating workflow state deterministically.
- Publish-time validation rejects malformed case kinds, duplicate ids, invalid per-case workflow parameters, unknown expected artifacts, and summary drift.

## Known Gaps

- Downstream evaluation execution is intentionally out of scope for this phase.
- No network, timing, or concurrency coverage is needed; tests stay filesystem-local and deterministic.
