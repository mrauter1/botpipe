# Test Strategy

- Task ID: recursive-framework-evolution-20260427t121046-bootstrap
- Pair: test
- Phase ID: tests-and-verification
- Phase Directory Key: tests-and-verification
- Phase Title: Tests And Verification
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- Failure-seed split:
  `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py::test_failure_scenario_seeds_are_written_separately_from_failure_scenarios`
  validates deterministic `workflow_failure_scenario_seeds.json` publication and preserves a distinct provider-authored final failure artifact.
- Accepted failure artifact ownership:
  `...::test_mine_failures_preserves_provider_authored_failure_scenarios`
  proves accepted provider-authored `workflow_failure_scenarios.json` content is preserved in place.
- No-scenarios fallback:
  `...::test_mine_failures_writes_empty_artifact_only_for_no_failure_scenarios_when_missing`
  proves the minimal empty fallback is only synthesized when the final artifact is absent.
- Invalid accepted artifact path:
  `...::test_mine_failures_malformed_artifact_is_not_replaced`
  proves malformed or workflow-mismatched accepted artifacts fail validation and are not deterministically replaced.
- Soft candidate-budget semantics:
  `...::test_max_candidates_per_pass_is_prompt_guidance_not_schema_limit`
  proves `workflow_optimization_scope.json` publishes `max_candidates_per_pass` and accepted over-budget candidate artifacts survive unchanged.
- Optimization-depth publication semantics:
  `...::test_optimization_depth_standard_is_recorded_and_no_reruns_execute`
  and `...::test_optimization_depth_ablation_records_planning_mode_without_executing_ablation`
  prove depth is recorded in scope, scorecard, packet, and receipt while no reruns or ablation runs are created.
- Deterministic helper payload shape:
  `tests/unit/test_optimization_helpers.py::test_extract_failure_scenario_seeds_limits_to_max_scenarios`
  proves the helper emits the seed schema with bounded `seeds` output and populated `suggested_failure_kind`.

## Preserved Invariants Checked

- Accepted provider-authored optimizer artifacts are not replaced after verifier acceptance.
- `optimization_depth` remains publication/prompt semantics only.
- `ablation_executed` stays false and target workflow reruns remain absent.
- `max_candidates_per_pass` remains published soft guidance, not a schema cap.

## Edge Cases And Failure Paths

- Missing final failure artifact on `no_failure_scenarios`.
- Wrong `selected_workflow` in an accepted failure artifact.
- Accepted candidate artifact intentionally exceeding the soft candidate budget.
- No-op ablation-depth publication path with no eligible Plan-1 observability bundle.

## Flake Risk And Stabilization

- Runtime coverage uses temp roots, seeded fixture runs, and `ScriptedLLMProvider` / direct handler invocation to avoid network, timing, and external-state nondeterminism.
- Depth/no-rerun assertions use run-directory counts rather than timing-sensitive workflow internals.

## Known Gaps

- No additional prompt-render capture assertions were added because the request explicitly allowed the budget test to validate behavior without prompt capture.
- The unrelated recursive-memory charter failures in `tests/test_architecture_baseline_docs.py` remain outside this phase scope.
