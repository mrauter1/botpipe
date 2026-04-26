# Implementation Notes

- Task ID: recursive-framework-evolution-20260426t124100-bootstrap
- Pair: implement
- Phase ID: regression-coverage-and-docs
- Phase Directory Key: regression-coverage-and-docs
- Phase Title: Regression Coverage And Docs
- Scope: phase-local producer artifact

## Files changed

- `runtime/runner.py`
- `docs/architecture.md`
- `docs/authoring.md`
- `tests/test_architecture_baseline_docs.py`
- `tests/runtime/test_optional_extensions.py`
- `tests/runtime/test_workflow_reference_resolution.py`
- `tests/runtime/test_compatibility_runtime.py`
- `tests/runtime/test_workflow_integration_parity.py`
- `tests/runtime/test_task_to_workflow_strategy.py`
- `tests/runtime/test_task_to_candidate_workflow_set.py`
- `tests/runtime/test_incident_to_hardening_program.py`
- `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
- `tests/runtime/test_release_candidate_to_go_no_go.py`
- `tests/runtime/test_workflow_builder_package.py`
- `tests/runtime/test_workflow_run_history_to_failure_modes.py`
- `tests/runtime/test_investigation_request_to_evidence_pack.py`
- `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
- `tests/runtime/test_security_finding_to_verified_remediation.py`
- `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
- `tests/runtime/test_workflow_portfolio_to_operating_system.py`
- `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- `tests/runtime/test_workflow_to_eval_suite.py`

## Symbols touched

- `runtime.runner._execute_compiled_workflow`
- `test_normal_run_writes_runtime_observability_artifacts_without_workflow_declarations`
- architecture/authoring doc baseline assertions in `tests/test_architecture_baseline_docs.py`

## Checklist mapping

- Regression coverage: added end-to-end runtime observability artifact coverage and fixed the tracked-to-disabled resume warning regression.
- Existing test updates: explicit git opt-out added to non-git runtime package tests instead of weakening defaults.
- Documentation: architecture/authoring now state runtime-owned git tracking/tracing defaults, clean-start rules, GitTracking deprecation behavior, replay boundary, and future optimization artifacts.

## Assumptions

- Temp-directory runtime package tests are intentionally not git-backed unless they explicitly initialize a repo.

## Preserved invariants

- Runtime git tracking remains enabled by default outside tests that explicitly opt out.
- Resume warnings remain append-only `run.json` metadata; no backfill or history mutation was introduced.
- Workflow-declared `Tracing` behavior was not filtered or changed.

## Intended behavior changes

- Resuming a run with git tracking disabled after an earlier tracked segment now reliably persists `runtime_git_tracking_disabled_on_resume` before current-run metadata rebinding.

## Known non-changes

- No new observability flags were added.
- No runtime/workflow production semantics were widened beyond the warning-order bug fix.

## Expected side effects

- Additional runtime package tests now exercise the new default contract explicitly, so future regressions in git preflight behavior should fail closer to the affected call sites.

## Validation performed

- `.venv/bin/python -m pytest tests/runtime/test_runtime_git_tracking.py tests/runtime/test_runtime_tracing.py tests/runtime/test_runtime_static_graph.py tests/runtime/test_optional_extensions.py tests/runtime/test_provider_backends.py tests/runtime/test_workflow_reference_resolution.py tests/runtime/test_compatibility_runtime.py tests/runtime/test_workflow_integration_parity.py tests/runtime/test_task_to_workflow_strategy.py tests/runtime/test_task_to_candidate_workflow_set.py tests/runtime/test_incident_to_hardening_program.py tests/runtime/test_company_operation_to_recursive_improvement_cycle.py tests/runtime/test_release_candidate_to_go_no_go.py tests/runtime/test_workflow_builder_package.py tests/runtime/test_workflow_run_history_to_failure_modes.py tests/runtime/test_investigation_request_to_evidence_pack.py tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py tests/runtime/test_security_finding_to_verified_remediation.py tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py tests/runtime/test_workflow_portfolio_to_operating_system.py tests/runtime/test_workflow_package_to_composable_building_blocks.py tests/runtime/test_workflow_to_eval_suite.py tests/test_architecture_baseline_docs.py`
- Result: `468 passed`

## Deduplication / centralization

- Kept the production fix local to runner ordering; test updates stayed at explicit `RunnerOptions(...)` call sites to preserve visibility of git opt-outs.
