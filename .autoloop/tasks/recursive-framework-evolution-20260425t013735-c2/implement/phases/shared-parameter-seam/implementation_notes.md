# Implementation Notes

- Task ID: recursive-framework-evolution-20260425t013735-c2
- Pair: implement
- Phase ID: shared-parameter-seam
- Phase Directory Key: shared-parameter-seam
- Phase Title: Shared Parameter Seam
- Scope: phase-local producer artifact

## Files changed

- `stdlib/parameters.py`
- `stdlib/__init__.py`
- `workflows/task_to_candidate_workflow_set/params.py`
- `workflows/task_to_workflow_strategy/params.py`
- `workflows/candidate_workflow_to_adapted_execution_plan/params.py`
- `workflows/workflow_to_eval_suite/params.py`
- `workflows/workflow_and_eval_to_refined_workflow_package/params.py`
- `workflows/workflow_package_to_composable_building_blocks/params.py`
- `workflows/workflow_portfolio_to_operating_system/params.py`
- `workflows/company_operation_to_recursive_improvement_cycle/params.py`
- `workflows/workflow_run_history_to_failure_modes/params.py`
- `tests/unit/test_stdlib_and_extensions.py`
- `docs/authoring.md`
- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `.autoloop_recursive/framework_gap_ledger.md`
- `.autoloop_recursive/workflow_candidate_ledger.md`
- `.autoloop_recursive/validation_debt_ledger.md`

## Symbols touched

- `stdlib.parameters.TaskContextParameters`
- `stdlib.parameters.TaskFramingParameters`
- `stdlib.parameters.TaskFramingWithEvidenceParameters`
- `stdlib.parameters.SelectedWorkflowTaskFramingParameters`
- `stdlib.parameters.SelectedWorkflowTaskFramingWithEvidenceParameters`
- `stdlib.parameters.PortfolioReviewParameters`
- workflow-local `Parameters` classes in the migrated workflow family

## Checklist mapping

- Shared stdlib-owned parameter-model seam: complete
- Updated stdlib exports: complete
- Focused unit proof for shared parameter behavior: complete
- Docs and recursive-memory sync for the seam boundary: complete

## Assumptions

- Runtime parameter resolution order and local `Parameters` exports must remain unchanged.
- The current run allows authoring-surface consolidation but not a new workflow package.

## Preserved invariants

- CLI `-wf` behavior is unchanged.
- Runtime loader resolution order is unchanged.
- `ctx.params`, `ctx.workflow_params`, artifact contracts, and `ctx.invoke_workflow(...)` behavior are unchanged.
- Workflow-specific identifier/literal normalization remains local.

## Intended behavior changes

- Repeated task-framing, selected-workflow-framing, evidence-expectation, and decision-driver bundles now come from `stdlib/parameters.py` instead of being recopied across workflow-local `params.py`.

## Known non-changes

- No runtime-owned parameter seam was added.
- No root `workflow` shim change was made.
- No prompt families were rewritten.
- `workflow_run_history_to_failure_modes.statuses` still normalizes locally and sorts output.

## Expected side effects

- Touched `params.py` modules are shorter and surface only workflow-specific deltas.
- Future workflow parameter models have one obvious stdlib seam for shared framing bundles.

## Validation performed

- `PYTHONPATH=/home/rauter/autoloop_v3_bkp .venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py tests/runtime/test_task_to_candidate_workflow_set.py tests/runtime/test_task_to_workflow_strategy.py tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py tests/runtime/test_workflow_to_eval_suite.py tests/runtime/test_workflow_run_history_to_failure_modes.py tests/runtime/test_workflow_portfolio_to_operating_system.py tests/runtime/test_company_operation_to_recursive_improvement_cycle.py tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py tests/runtime/test_workflow_package_to_composable_building_blocks.py tests/test_architecture_baseline_docs.py`
- Result: `320 passed in 33.32s`

## Deduplication decisions

- Shared field bundles moved into `stdlib/parameters.py`.
- Positive-int validator factories stayed in `stdlib/validation.py`; local message wording remains local when workflows differ.
- Workflow-specific fields such as `target_test_command`, `evaluation_*_path`, `evidence_paths`, and sorted `statuses` remain in workflow-local models.
