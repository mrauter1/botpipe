# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260424t163807-c1
- Pair: implement
- Phase ID: workflow-validation-migrations-and-closeout
- Phase Directory Key: workflow-validation-migrations-and-closeout
- Phase Title: Workflow Migrations And Closeout
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking`
  Files: `tests/runtime/test_task_to_candidate_workflow_set.py`, `tests/runtime/test_task_to_workflow_strategy.py`, `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`, `tests/runtime/test_workflow_to_eval_suite.py`, `tests/runtime/test_workflow_run_history_to_failure_modes.py`, `tests/runtime/test_workflow_portfolio_to_operating_system.py`, `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`, `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`, `tests/runtime/test_workflow_package_to_composable_building_blocks.py`, plus the phase notes in `implementation_notes.md`
  Finding: AC-2 is not satisfied. The phase contract required the targeted runtime suites as the regression proof for the migrated workflows, but the implementation notes explicitly say none of those suites were run and no runtime-test changes were made. That leaves publication-behavior and selected-workflow/governance regressions unverified across the exact workflows this phase modified.
  Minimal fix direction: run the targeted runtime suites in an environment with the required dependencies and record the results; if any dependency setup is needed, capture it in the phase notes. If a suite fails, fix the regression before closeout.

- IMP-002 `blocking`
  Files: `workflows/workflow_run_history_to_failure_modes/workflow.py`, `workflows/workflow_portfolio_to_operating_system/workflow.py`, `workflows/company_operation_to_recursive_improvement_cycle/workflow.py`, `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`, `workflows/workflow_package_to_composable_building_blocks/workflow.py`
  Finding: The phase scope said to remove duplicated workflow-local helper tails from the migrated workflows, but these five workflows still end with duplicated generic wrappers such as `_require_text`, `_normalize_optional_text`, `_normalize_unique_strings`, `_require_string_list`, `_require_mapping`, `_require_mapping_list`, and `_read_json`. They now delegate into stdlib, but the duplication and ownership sprawl remain, so the phase only partially delivered the intended authoring-surface simplification.
  Minimal fix direction: finish the migration by inlining the shared stdlib helpers directly at call sites or by centralizing any truly necessary strict variants in one shared stdlib helper rather than keeping per-workflow generic wrapper tails.
