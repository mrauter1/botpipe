# Test Strategy

- Task ID: recursive-framework-evolution-20260424t163807-c1
- Pair: test
- Phase ID: workflow-validation-migrations-and-closeout
- Phase Directory Key: workflow-validation-migrations-and-closeout
- Phase Title: Workflow Migrations And Closeout
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Shared validation seam migration compatibility
  Files: `tests/unit/test_validation.py`, `tests/unit/test_stdlib_and_extensions.py`
  Covered behaviors:
  - keyword and legacy positional `error_message` handling for shared string/list/mapping/int validators
  - duplicate-value custom message override via `require_unique_values(...)`
  - preserved strictness for bool rejection, mapping-list shape checks, and custom-message propagation

- Migrated selected-workflow family publication contracts
  Files: `tests/runtime/test_task_to_candidate_workflow_set.py`, `tests/runtime/test_task_to_workflow_strategy.py`, `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`, `tests/runtime/test_workflow_to_eval_suite.py`, `tests/runtime/test_workflow_run_history_to_failure_modes.py`
  Covered behaviors:
  - happy-path package publication
  - selected-workflow identity matching
  - artifact receipt / manifest consistency
  - failure paths for mismatched summaries, invalid references, and incomplete required artifacts

- Migrated governance / recursive / refinement / decomposition family
  Files: `tests/runtime/test_workflow_portfolio_to_operating_system.py`, `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`, `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`, `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
  Covered behaviors:
  - happy-path publication and candidate-package generation
  - hidden downstream execution rejection
  - path-boundary and manifest drift rejection
  - selected-workflow / scoped-task / scoped-workflow boundary preservation

- Recursive-memory and docs closeout
  File: `tests/test_architecture_baseline_docs.py`
  Covered behaviors:
  - cycle 13 consolidation wording is recorded in charter/roadmap/ledgers
  - migrated workflow family is no longer left in deferred-ideas status

## Preserved invariants checked

- No runtime-owned hidden publication/routing abstraction was normalized into expectations.
- Domain-specific publication and path-boundary checks remain local while generic validation moved to stdlib.
- The targeted runtime regression command stays deterministic and filesystem-local.

## Edge cases and failure paths

- Legacy positional `error_message` usage continues to raise the caller-supplied message.
- Duplicate ID / duplicate value paths still preserve workflow-specific wording.
- Hidden execution language and boundary drift still fail publication in governance and recursive workflows.

## Stabilization notes

- Tests are deterministic and repo-local; no network, timing, or nondeterministic ordering dependencies were introduced.
- Coverage relies on direct pytest execution against the scoped unit/runtime/doc suites only.

## Known gaps

- The deferred older domain workflows remain intentionally out of scope for this phase and were not expanded here.
