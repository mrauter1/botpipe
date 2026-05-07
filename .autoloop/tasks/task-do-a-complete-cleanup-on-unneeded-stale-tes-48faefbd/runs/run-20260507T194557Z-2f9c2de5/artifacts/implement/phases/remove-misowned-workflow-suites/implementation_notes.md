# Implementation Notes

- Task ID: task-do-a-complete-cleanup-on-unneeded-stale-tes-48faefbd
- Pair: implement
- Phase ID: remove-misowned-workflow-suites
- Phase Directory Key: remove-misowned-workflow-suites
- Phase Title: Remove Misowned Workflow Suites
- Scope: phase-local producer artifact

## Files changed
- Deleted `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
- Deleted `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
- Deleted `tests/runtime/test_incident_to_hardening_program.py`
- Deleted `tests/runtime/test_investigation_request_to_evidence_pack.py`
- Deleted `tests/runtime/test_release_candidate_to_go_no_go.py`
- Deleted `tests/runtime/test_security_finding_to_verified_remediation.py`
- Deleted `tests/runtime/test_task_to_candidate_workflow_set.py`
- Deleted `tests/runtime/test_task_to_workflow_strategy.py`
- Deleted `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
- Deleted `tests/runtime/test_workflow_builder_package.py`
- Deleted `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- Deleted `tests/runtime/test_workflow_portfolio_to_operating_system.py`
- Deleted `tests/runtime/test_workflow_run_history_to_failure_modes.py`
- Deleted `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py`
- Deleted `tests/runtime/test_workflow_to_eval_suite.py`
- Updated `tests/strictness/test_no_compat.py`
- Updated `tests/unit/test_stdlib_and_extensions.py`
- Updated `tests/runtime/test_workflow_reference_resolution.py`

## Symbols touched
- `ACTIVE_SCAN_ROOTS`
- `EXCLUDED_SCAN_PREFIXES`
- `OPTIONAL_SCAN_FILES`
- `_iter_active_text_files`
- `_iter_maintained_python_files`
- `test_removed_compatibility_scan_scope_covers_maintained_tree_only`
- `ACTIVE_CONSUMER_RUNTIME_FILES`
- `test_simple_declaration_workflow_is_discoverable_by_path_module_name_and_capability_inspection`

## Checklist mapping
- Milestone 2 / AC-1: removed the 15 repo-owned workflow runtime suites from `tests/runtime`.
- Milestone 2 / AC-1: removed repo-doc assertions and repo-workflow parameter-model coverage from `tests/unit/test_stdlib_and_extensions.py`.
- Milestone 2 / AC-1: narrowed strictness scanning so retained compatibility checks no longer read `docs/`, `recursive_autoloop/`, or `autoloop/workflows/*`.
- Milestone 2 / shared-runtime regression check: updated one retained workflow-reference assertion to match the current simple inspection surface during validation.
- Deferred: Milestone 3 file splitting for `tests/unit/test_stdlib_and_extensions.py` and `tests/contract/test_engine_contracts.py` was not required to satisfy this phase contract and was left unchanged.

## Assumptions
- Synthetic `tmp_path` fixtures that emit canonical repo-relative labels remain in scope because they do not read repo-owned assets.

## Preserved invariants
- Shared workflow discovery, catalog, workspace, CLI, optimizer, and stdlib coverage remains under `tests/`.
- No retained test now reads concrete assets from repo `docs/`, `recursive_autoloop/`, or `autoloop/workflows/*`.

## Intended behavior changes
- `tests/` no longer owns workflow-package regression suites or repo-doc assertions.
- Strictness checks now target shared framework code only and skip repo-owned workflow package files.

## Known non-changes
- No product code, CI config, or non-`tests/` runtime behavior was modified.
- Workflow-owner tests were not re-homed into their owning directories in this phase.

## Expected side effects
- Default test collection is smaller and no longer depends on repo-owned workflow/docs assets.

## Validation performed
- `./.venv/bin/pytest --collect-only tests`
- `./.venv/bin/pytest tests/strictness/test_no_compat.py tests/unit/test_stdlib_and_extensions.py tests/unit/test_optimization_helpers.py tests/runtime/test_package_cli.py tests/runtime/test_wheel_packaging_smoke.py tests/runtime/test_golden_workflow.py tests/runtime/test_workflow_catalog_roots.py tests/runtime/test_workflow_reference_resolution.py tests/runtime/test_workspace_and_context.py -q`

## Deduplication / centralization decisions
- Reused the strictness file’s existing scan helpers and narrowed them in place rather than introducing new filtering helpers elsewhere in `tests/`.
