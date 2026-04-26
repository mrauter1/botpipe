# Test Strategy

- Task ID: recursive-framework-evolution-20260425t234529-bootstrap-c1
- Pair: test
- Phase ID: proof-docs-and-memory-closeout
- Phase Directory Key: proof-docs-and-memory-closeout
- Phase Title: Proof And Closeout
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- Typed bootstrap projection stays on `ctx.params` across the full migrated workflow family:
  - `tests/runtime/test_task_to_candidate_workflow_set.py`
  - `tests/runtime/test_task_to_workflow_strategy.py`
  - `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
  - `tests/runtime/test_workflow_to_eval_suite.py`
  - `tests/runtime/test_workflow_run_history_to_failure_modes.py`
  - `tests/runtime/test_workflow_portfolio_to_operating_system.py`
  - `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
  - `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
  - `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- Shared validation and helper seams used by the migrated family remain stable:
  - `tests/unit/test_stdlib_and_extensions.py`
  - `tests/unit/test_validation.py`
- Docs and recursive-memory closeout stays synchronized with the authoring contract:
  - `tests/test_architecture_baseline_docs.py`

## Preserved Invariants Checked

- Bootstrap coverage continues to call migrated `on_bootstrap(...)` handlers with populated `ctx.params` and empty `workflow_params`, proving the typed surface is the behavior under test rather than the compatibility dict.
- Runtime tests continue to assert unchanged invocation-contract payloads after the migration, so closeout does not silently normalize a compatibility break.
- Existing bootstrap tests also prove declared session opening remains explicit, preserving the `stdlib/lifecycle.py` contract.
- Architecture-baseline coverage continues to assert the typed-bootstrap doctrine and charter/memory references remain present.

## Edge Cases And Failure Paths

- Optional values still serialize as `None` where expected in invocation contracts.
- Workflow-specific list and integer behavior stays covered where the migration could have drifted normalization:
  - evidence expectations and constraints
  - decision-driver bundles
  - run-history `statuses` ordering
  - max-run / max-task / max-message integers
- Failure path for this closeout is documentation or memory drift; `tests/test_architecture_baseline_docs.py` is the guardrail for missing charter or authoring-rule updates.

## Reliability / Flake Controls

- Proof uses deterministic local pytest suites only; no network, timing, or randomized ordering dependencies are introduced in this phase.
- Closeout intentionally reuses existing regression suites instead of adding redundant tests for documentation-only sync, which keeps the phase stable and avoids test churn.

## Validation Run

- Ran `.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py tests/unit/test_validation.py tests/runtime/test_task_to_candidate_workflow_set.py tests/runtime/test_task_to_workflow_strategy.py tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py tests/runtime/test_workflow_to_eval_suite.py tests/runtime/test_workflow_run_history_to_failure_modes.py tests/runtime/test_workflow_portfolio_to_operating_system.py tests/runtime/test_company_operation_to_recursive_improvement_cycle.py tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py tests/runtime/test_workflow_package_to_composable_building_blocks.py tests/test_architecture_baseline_docs.py` (`396 passed in 34.64s`).

## Known Gaps

- No new repository test files were added in this closeout slice because the implementation phase already landed the typed-bootstrap regression tests and the remaining work here was proof plus documentation synchronization.
