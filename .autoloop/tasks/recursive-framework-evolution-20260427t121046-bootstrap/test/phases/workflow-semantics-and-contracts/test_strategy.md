# Test Strategy

- Task ID: recursive-framework-evolution-20260427t121046-bootstrap
- Pair: test
- Phase ID: workflow-semantics-and-contracts
- Phase Directory Key: workflow-semantics-and-contracts
- Phase Title: Workflow Semantics And Contracts
- Scope: phase-local producer artifact

## Behavior-To-Test Map

- AC-1 deterministic failure seeds vs provider-authored final scenarios:
  Covered by `test_failure_scenario_seeds_are_written_separately_from_failure_scenarios`, `test_mine_failures_preserves_provider_authored_failure_scenarios`, `test_mine_failures_writes_empty_artifact_only_for_no_failure_scenarios_when_missing`, and `test_mine_failures_malformed_artifact_is_not_replaced`.
- AC-2 accepted/not-applicable artifact preservation:
  Covered by `test_max_candidates_per_pass_is_prompt_guidance_not_schema_limit` for accepted candidate preservation, `test_optional_skip_routes_preserve_existing_artifacts_when_present` for deterministic skip-route preservation, `test_not_applicable_candidate_handlers_preserve_existing_artifacts` for provider-emitted `*_not_applicable` preservation, and `test_not_applicable_candidate_handlers_write_empty_artifacts_when_missing` for minimal empty synthesis only when the not-applicable artifact is absent.
- AC-3 scope/publication metadata and ablation summary:
  Covered by `test_package_writes_scorecard_refinement_evidence_packet_and_receipt`, `test_package_rejects_candidate_count_mismatch`, `test_optimization_depth_standard_is_recorded_and_no_reruns_execute`, and `test_optimization_depth_ablation_records_planning_mode_without_executing_ablation`.

## Preserved Invariants Checked

- No target-workflow reruns are created during optimizer publication.
- No ablation workflow is executed; `ablation_executed` remains `false`.
- No source mutation of the selected workflow is allowed during publication.
- Candidate over-budget output is not rejected solely for exceeding `max_candidates_per_pass`.

## Edge Cases And Failure Paths

- Missing final failure artifact on `no_failure_scenarios` writes only the minimal empty fallback.
- Malformed or selected-workflow-mismatched final failure artifacts fail validation instead of being silently replaced.
- Existing provider-authored optional-pass artifacts survive skip/not-applicable routing unchanged.
- Provider-emitted `*_not_applicable` outcomes preserve existing artifacts and synthesize minimal empty artifacts only when missing.
- Package publication rejects scorecard count drift and malformed candidate artifacts.

## Stabilization Notes

- Coverage uses local fake-provider/runtime helpers and repository-installed workflow fixtures only; there is no network or timing dependency.
- Artifact assertions compare exact JSON payloads written to the workflow folder so regressions in rewrite behavior fail deterministically.

## Known Gaps

- Prompt text itself is not snapshot-tested here; coverage stays on artifact semantics and publication/runtime behavior.
