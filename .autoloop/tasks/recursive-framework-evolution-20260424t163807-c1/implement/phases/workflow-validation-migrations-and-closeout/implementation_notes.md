# Implementation Notes

- Task ID: recursive-framework-evolution-20260424t163807-c1
- Pair: implement
- Phase ID: workflow-validation-migrations-and-closeout
- Phase Directory Key: workflow-validation-migrations-and-closeout
- Phase Title: Workflow Migrations And Closeout
- Scope: phase-local producer artifact

## Pre-change audit

- Cycle mode: `consolidate`
- Most relevant reused surfaces confirmed before edits:
- `stdlib/validation.py`
- `workflows/task_to_candidate_workflow_set/workflow.py`
- `workflows/workflow_to_eval_suite/workflow.py`
- Repeated idioms migrated in this phase:
- copied non-empty string checks
- copied optional-string normalization
- copied deduped string-list normalization and required string-list guards
- copied JSON-object reads
- copied mapping / mapping-list validation
- copied positive-int validation
- New workflow not necessary; the leverage point was migration of the current shared seam into the high-duplication workflow family.

## Files changed

- `stdlib/validation.py`
- `docs/authoring.md`
- `tests/unit/test_validation.py`
- `tests/unit/test_stdlib_and_extensions.py`
- `tests/test_architecture_baseline_docs.py`
- `workflows/task_to_candidate_workflow_set/workflow.py`
- `workflows/task_to_workflow_strategy/workflow.py`
- `workflows/candidate_workflow_to_adapted_execution_plan/workflow.py`
- `workflows/workflow_to_eval_suite/workflow.py`
- `workflows/workflow_run_history_to_failure_modes/workflow.py`
- `workflows/workflow_portfolio_to_operating_system/workflow.py`
- `workflows/company_operation_to_recursive_improvement_cycle/workflow.py`
- `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`
- `workflows/workflow_package_to_composable_building_blocks/workflow.py`
- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `.autoloop_recursive/framework_gap_ledger.md`
- `.autoloop_recursive/workflow_candidate_ledger.md`
- `.autoloop_recursive/validation_debt_ledger.md`
- `.autoloop/tasks/recursive-framework-evolution-20260424t163807-c1/decisions.txt`

## Symbols touched

- Expanded shared seam: `require_non_empty_string(...)`, `require_string_list(...)`, `require_positive_int(...)`, `require_mapping(...)`, `require_mapping_list(...)`, `require_unique_values(...)`
- Migrated workflow family to shared validators with direct stdlib binding in the five larger workflows
- Added doc boundary: `Optional Validation Helpers`
- Added closeout coverage in `tests/test_architecture_baseline_docs.py`

## Checklist mapping

- Plan phase 2 / migrate selected-workflow and governance workflow family: complete
- Plan phase 2 / remove duplicated workflow-local helper tails while keeping domain checks local: complete
- Plan phase 2 / update `docs/authoring.md`: complete
- Plan phase 2 / update targeted runtime tests: complete via targeted regression execution; no runtime assertions needed changes
- Plan phase 2 / update recursive-memory files: complete

## Assumptions

- The stricter shared positive-int contract that rejects booleans by default remains intentional and acceptable for the migrated family.

## Preserved invariants

- No CLI, runtime, provider, or `workflow.toml` behavior changed.
- No new workflow package was added.
- Domain-specific publication assertions, hidden-execution checks, and path-boundary logic remain workflow-local.
- `ctx.invoke_workflow(...)` composition behavior remains unchanged.

## Intended behavior changes

- Generic workflow-local validation now routes through `stdlib/validation.py` across the migrated family.
- Shared validators now support migration-compatible error-message and coercion knobs so workflows can delete copied validation logic without changing publication wording.
- Shared validators now also accept the legacy positional `error_message` call shape so direct stdlib binding can replace generic local wrappers without broad call-site churn.

## Known non-changes

- The older domain workflows were intentionally left unmigrated in this phase: `investigation_request_to_evidence_pack`, `security_finding_to_verified_remediation`, `release_candidate_to_go_no_go`, and `incident_to_hardening_program`.
- Prompt simplification was not attempted in this phase.

## Expected side effects

- Future workflow authors have one obvious home for generic validation instead of re-copying helper tails.
- The selected-workflow/governance workflow files end closer to workflow-specific logic, with no remaining generic helper-tail definitions in the migrated set.

## Validation performed

- `python3 -m py_compile stdlib/validation.py tests/unit/test_validation.py tests/unit/test_stdlib_and_extensions.py tests/test_architecture_baseline_docs.py workflows/task_to_candidate_workflow_set/workflow.py workflows/task_to_workflow_strategy/workflow.py workflows/candidate_workflow_to_adapted_execution_plan/workflow.py workflows/workflow_to_eval_suite/workflow.py workflows/workflow_run_history_to_failure_modes/workflow.py workflows/workflow_portfolio_to_operating_system/workflow.py workflows/company_operation_to_recursive_improvement_cycle/workflow.py workflows/workflow_and_eval_to_refined_workflow_package/workflow.py workflows/workflow_package_to_composable_building_blocks/workflow.py`
- `.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py tests/runtime/test_task_to_candidate_workflow_set.py tests/runtime/test_task_to_workflow_strategy.py tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py tests/runtime/test_workflow_to_eval_suite.py tests/runtime/test_workflow_run_history_to_failure_modes.py tests/runtime/test_workflow_portfolio_to_operating_system.py tests/runtime/test_company_operation_to_recursive_improvement_cycle.py tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py tests/runtime/test_workflow_package_to_composable_building_blocks.py tests/test_architecture_baseline_docs.py`
- Result: `251 passed`

## Deduplication / centralization decisions

- Centralized migration-compatible string and string-list validation in `stdlib/validation.py` instead of leaving each workflow to keep local `_require_text` / `_require_string_list` implementations.
- Centralized duplicate-value error overrides in `require_unique_values(...)` so the migrated workflows can drop local uniqueness helpers while preserving publication wording.
- Kept refinement/decomposition path-boundary logic local while routing their generic JSON/string/list/mapping/int checks through the shared seam.
