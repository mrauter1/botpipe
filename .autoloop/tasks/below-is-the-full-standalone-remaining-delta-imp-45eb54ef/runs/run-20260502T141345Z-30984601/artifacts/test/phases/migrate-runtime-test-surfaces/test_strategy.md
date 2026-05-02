# Test Strategy

- Task ID: below-is-the-full-standalone-remaining-delta-imp-45eb54ef
- Pair: test
- Phase ID: migrate-runtime-test-surfaces
- Phase Directory Key: migrate-runtime-test-surfaces
- Phase Title: Migrate Runtime Test Surfaces
- Scope: phase-local producer artifact

## Behavior Coverage Map

- Bootstrap direct-call behavior:
  `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
  `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
  `tests/runtime/test_incident_to_hardening_program.py`
  `tests/runtime/test_investigation_request_to_evidence_pack.py`
  `tests/runtime/test_release_candidate_to_go_no_go.py`
  `tests/runtime/test_security_finding_to_verified_remediation.py`
  `tests/runtime/test_task_to_candidate_workflow_set.py`
  `tests/runtime/test_task_to_workflow_strategy.py`
  `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
  `tests/runtime/test_workflow_builder_package.py`
  `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
  `tests/runtime/test_workflow_portfolio_to_operating_system.py`
  `tests/runtime/test_workflow_run_history_to_failure_modes.py`
  `tests/runtime/test_workflow_to_eval_suite.py`
  Coverage: compiled bootstrap invocation returns normalized control output; state assertions read from `ctx.state`.

- Representative capture / route-skip / publish direct behavior:
  `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py`
  Coverage: bootstrap, capture-frame context, route skip branches, not-applicable after-verifier hooks, publish success, and publish failure paths all assert through `ctx.state` plus normalized control values.

- After-verifier direct hook behavior:
  `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
  `tests/runtime/test_workflow_to_eval_suite.py`
  `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py`
  Coverage: hook invocation uses compiled surfaces, mutates `ctx.state`, and preserves artifact behavior for needs-rework and not-applicable outcomes.

## Preserved Invariants Checked

- Affected suites do not treat `WorkflowClass.on_*` helper entry points as supported API.
- Shared direct-invocation helpers expose normalized control returns, while state is read from `ctx.state`.
- Representative publish-path tests continue to validate artifact writes and failure guards without reintroducing tuple-return compatibility assumptions.

## Edge Cases / Failure Paths

- Optional route-skipping paths preserve or initialize artifacts deterministically when optimization passes are disabled.
- After-verifier not-applicable outcomes preserve provider-authored artifacts when present and materialize empty artifacts only when absent.
- Publish failure tests still reject drift, malformed artifacts, and selected-workflow mismatches under the migrated invocation surface.

## Flake Risk / Stabilization

- Tests remain deterministic by using local temp directories, scripted providers, and direct compiled-handler invocation with no network or wall-clock dependencies.
- Existing contract-warning noise from optimizer `schema` fields is tolerated but not asserted on.

## Known Gaps

- Repo-level raw declaration/source audits live in the prior migration phase’s strictness coverage and are not duplicated here.
- No new compatibility shim tests were added, by design.
