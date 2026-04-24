# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c11
- Pair: test
- Phase ID: workflow-package-to-building-blocks
- Phase Directory Key: workflow-package-to-building-blocks
- Phase Title: Implement Decomposition Workflow
- Scope: phase-local producer artifact

## Behavior To Test Coverage

- AC-1 discovery and invocation:
  - `test_repo_workflows_namespace_discovers_workflow_package_to_composable_building_blocks`
  - `test_workflow_package_to_composable_building_blocks_aliases_resolve_to_same_package`
  - `test_workflow_package_to_composable_building_blocks_compiles_with_explicit_control_contracts`
- AC-2 terminal artifact publication:
  - `test_workflow_package_to_composable_building_blocks_runs_and_publishes_candidate_decomposition_artifacts`
- AC-3 publish-time validation:
  - `test_workflow_package_to_composable_building_blocks_publish_rejects_hidden_execution`
  - `test_workflow_package_to_composable_building_blocks_publish_rejects_identity_drift`
  - `test_workflow_package_to_composable_building_blocks_publish_rejects_candidate_files_outside_allowed_boundary`
  - `test_workflow_package_to_composable_building_blocks_publish_rejects_unlisted_candidate_surface_files`
  - `test_workflow_package_to_composable_building_blocks_publish_rejects_missing_declared_doc_and_runtime_test`
- AC-4 context capture fallback and block behavior:
  - `test_workflow_package_to_composable_building_blocks_records_request_fallback_when_evidence_paths_are_omitted`
  - `test_workflow_package_to_composable_building_blocks_routes_to_blocked_for_unreadable_evidence_paths`

## Preserved Invariants Checked

- The authoritative selected workflow package remains unchanged during a successful candidate publication run.
- The candidate overlay still publishes candidate-only artifacts and receipt without promoting into the repo.
- Prompt/runtime boundary remains explicit through compiled route contracts and prompt marker assertions.

## Edge Cases And Failure Paths

- Parameter normalization and blank required fields:
  - `test_workflow_package_to_composable_building_blocks_rejects_blank_selected_workflow`
  - `test_workflow_package_to_composable_building_blocks_normalizes_repeatable_inputs`
- Prompt/template contract coverage:
  - `test_workflow_package_to_composable_building_blocks_prompt_readme_lists_route_grammar_and_runtime_boundary`
  - `test_workflow_package_to_composable_building_blocks_prompts_keep_step_local_contracts_explicit`
- Publication tampering:
  - hidden execution, identity drift, declared-boundary escape, unlisted post-manifest files, and missing declared doc/test artifacts

## Flake Risks And Stabilization

- Tests run against an isolated temp repo with scripted provider turns, local filesystem copies, and no network calls.
- Workflow module cache is cleared before and after tests to keep alias and discovery assertions deterministic.

## Known Gaps

- No dedicated tampering test targets `candidate_decomposition_manifest.json file_count`; current coverage already locks adjacent manifest/file-set drift and state-consistency failures through the success path plus the unlisted-surface and missing-artifact regressions.
- This phase reruns the workflow-specific runtime suite only, not the full repository test suite.
