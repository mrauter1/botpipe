# Test Strategy

- Task ID: recursive-framework-evolution-20260424t163807-c4
- Pair: test
- Phase ID: prompt-surface-migration
- Phase Directory Key: prompt-surface-migration
- Phase Title: Migrate Prompt Files
- Scope: phase-local producer artifact

## Behavior Coverage Map

| Behavior | Coverage |
| --- | --- |
| Scoped front-door workflow prompt READMEs keep the shared compact-contract sections and route/payload tables | Added README contract tests in `tests/runtime/test_workflow_builder_package.py`, `tests/runtime/test_task_to_candidate_workflow_set.py`, `tests/runtime/test_task_to_workflow_strategy.py`, and `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py` |
| Migrated prompt bodies in the four previously uncovered families keep the compact section/table surface | Added prompt-body contract tests in those same four runtime suites covering every non-README prompt file |
| The migrated prompt bodies do not regress to the old repeated scaffolding headings | New prompt-body tests assert absence of legacy `Read these artifacts` / `Write these artifacts` markers across all touched prompt files |
| Step-local artifact names and route tags remain explicit after compaction | New prompt-body tests pin suite-local artifact names and application route markers for each touched prompt pair |

## Preserved Invariants Checked

- Prompt file paths, step names, artifact names, and route names remain unchanged.
- The test additions validate prompt markdown only; they do not widen runtime behavior or prompt-rendering machinery.
- Optional evidence wording remains allowed to vary as long as the migrated prompt keeps the common contract markers and explicit step-local route/artifact guidance.

## Edge Cases / Failure Paths

- Regression to the older scaffolding style is now a direct test failure for the four previously uncovered families.
- Loss of README contract sections, reserved-route tables, or verifier payload tables is now a direct test failure for those families.
- Loss of step-local route tags or named artifact references in the migrated prompts is now a direct test failure.

## Validation

- Focused validation: `.venv/bin/pytest -q tests/runtime/test_workflow_builder_package.py tests/runtime/test_task_to_candidate_workflow_set.py tests/runtime/test_task_to_workflow_strategy.py tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py` (`75 passed`)
- Scoped phase validation: `.venv/bin/pytest -q tests/runtime/test_workflow_builder_package.py tests/runtime/test_task_to_candidate_workflow_set.py tests/runtime/test_task_to_workflow_strategy.py tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py tests/runtime/test_workflow_to_eval_suite.py tests/runtime/test_workflow_run_history_to_failure_modes.py tests/runtime/test_workflow_portfolio_to_operating_system.py tests/runtime/test_company_operation_to_recursive_improvement_cycle.py tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py tests/runtime/test_workflow_package_to_composable_building_blocks.py tests/test_architecture_baseline_docs.py` (`238 passed`)

## Known Gaps

- Older domain workflow prompt families remain out of scope for this phase.
