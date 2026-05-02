# Implementation Notes

- Task ID: below-is-the-full-standalone-remaining-delta-imp-45eb54ef
- Pair: implement
- Phase ID: migrate-runtime-test-surfaces
- Phase Directory Key: migrate-runtime-test-surfaces
- Phase Title: Migrate Runtime Test Surfaces
- Scope: phase-local producer artifact

## Files Changed

- Shared test helper:
  `tests/runtime/workflow_contract_helpers.py`
- Runtime suites:
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
  `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py`
  `tests/runtime/test_workflow_to_eval_suite.py`

## Symbols Touched

- `invoke_python_step`
- `invoke_after_verifier_hook`
- `_invoke_optimizer_python_step`
- `_invoke_optimizer_after_verifier_hook`
- `_bootstrap_context`

## Checklist Mapping

- Milestone 2 complete:
  removed the remaining helper-synthesized `(state, result)` test usage from affected runtime suites and asserted behavior through `ctx.state` plus normalized compiled-handler returns.

## Assumptions

- The intended direct-call public surface for these runtime suites is the compiled handler callable plus `ctx.state`, not a tuple-return compatibility helper.

## Preserved Invariants

- Tests still invoke compiled public handlers for bootstrap, capture, route-skip, publish, and after-verifier coverage.
- No workflow package code or core runtime/compiler behavior changed in this phase.

## Intended Behavior Changes

- The shared runtime helper now returns only normalized control values.
- Affected runtime tests treat `ctx.state` as the authoritative mutated state surface after direct handler invocation.

## Known Non-Changes

- Repo-level compile and raw-contract audits from the prior migration phase remain unchanged.
- Existing `schema` shadowing warnings in optimizer contracts remain unchanged.

## Expected Side Effects

- Direct-call behavior tests now fail if a future helper tries to hide state mutation behind a compatibility tuple instead of exposing `ctx.state`.

## Validation Performed

- `./.venv/bin/pytest -q tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py tests/runtime/test_company_operation_to_recursive_improvement_cycle.py tests/runtime/test_incident_to_hardening_program.py tests/runtime/test_investigation_request_to_evidence_pack.py tests/runtime/test_release_candidate_to_go_no_go.py tests/runtime/test_security_finding_to_verified_remediation.py tests/runtime/test_task_to_candidate_workflow_set.py tests/runtime/test_task_to_workflow_strategy.py tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py tests/runtime/test_workflow_builder_package.py tests/runtime/test_workflow_package_to_composable_building_blocks.py tests/runtime/test_workflow_portfolio_to_operating_system.py tests/runtime/test_workflow_run_history_to_failure_modes.py tests/runtime/test_workflow_run_traces_to_optimization_candidates.py tests/runtime/test_workflow_to_eval_suite.py`
  result: `368 passed, 588 warnings`

## Deduplication / Centralization

- Kept the shared compiled-handler helper as the single direct-invocation surface, but removed its tuple-return compatibility behavior so suites consistently assert against `ctx.state`.
