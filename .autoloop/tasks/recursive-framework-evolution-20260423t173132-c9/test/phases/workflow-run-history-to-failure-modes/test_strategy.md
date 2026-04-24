# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c9
- Pair: test
- Phase ID: workflow-run-history-to-failure-modes
- Phase Directory Key: workflow-run-history-to-failure-modes
- Phase Title: Workflow Run History To Failure Modes
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- AC-1 workflow discovery and compilation:
  `test_repo_workflows_namespace_discovers_workflow_run_history_to_failure_modes_package`
  `test_workflow_run_history_to_failure_modes_package_compiles_with_explicit_control_contracts`
- AC-2 runtime publication proof:
  `test_workflow_run_history_to_failure_modes_package_runs_and_publishes_terminal_diagnostic_artifacts`
- AC-3 publish-time rejection paths:
  `test_workflow_run_history_to_failure_modes_publish_rejects_empty_filtered_history`
  `test_workflow_run_history_to_failure_modes_publish_rejects_selected_workflow_mismatch`
  `test_workflow_run_history_to_failure_modes_publish_rejects_missing_diagnostic_artifact`
  `test_workflow_run_history_to_failure_modes_publish_rejects_hidden_downstream_execution_boundary`
  `test_workflow_run_history_to_failure_modes_publish_rejects_incomplete_authoritative_artifacts`
  `test_workflow_run_history_to_failure_modes_publish_rejects_hidden_downstream_execution_text`
- AC-4 prompt-local contract coverage:
  `test_workflow_run_history_to_failure_modes_prompt_readme_lists_route_grammar_and_runtime_boundary`
  `test_workflow_run_history_to_failure_modes_prompts_keep_step_local_contracts_explicit`

## Preserved invariants checked

- `improvement_opportunities.json` remains the authoritative terminal JSON package.
- The workflow stops at `diagnostic_publication_only` and does not auto-run downstream workflows.
- Publish validation remains deterministic and artifact-first.

## Edge cases and failure paths

- Empty filtered history remains valid at the helper seam but is rejected at workflow publication.
- Selected-workflow snapshot drift is rejected.
- Missing workflow-local publication artifacts are rejected.
- Hidden downstream execution is rejected both by explicit boundary drift and by textual auto-execution phrasing.
- Missing required authoritative terminal artifacts are rejected.

## Flake-risk assessment

- Tests are deterministic: they use tmp-path fixtures, scripted providers, local file writes, and no network or timing assumptions.
- Ordering-sensitive expectations are stabilized by explicit sorted inputs and exact fixture payloads.
