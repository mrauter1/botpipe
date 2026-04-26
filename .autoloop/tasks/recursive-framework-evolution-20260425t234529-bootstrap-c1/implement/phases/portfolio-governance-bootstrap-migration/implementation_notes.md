# Implementation Notes

- Task ID: recursive-framework-evolution-20260425t234529-bootstrap-c1
- Pair: implement
- Phase ID: portfolio-governance-bootstrap-migration
- Phase Directory Key: portfolio-governance-bootstrap-migration
- Phase Title: Portfolio Family Migration
- Scope: phase-local producer artifact

## Audit

- Cycle mode: `consolidate`
- Three most relevant existing workflows/helpers:
  - `workflows/workflow_run_history_to_failure_modes/workflow.py`
  - `workflows/workflow_portfolio_to_operating_system/workflow.py`
  - `workflows/company_operation_to_recursive_improvement_cycle/workflow.py`
  - adjacent helper/document seams: `stdlib/parameters.py`, `stdlib/lifecycle.py`, `core/context.py`, `.autoloop_recursive/*`
- Repeated pattern identified: the later governance, diagnostic, refinement, and decomposition family still re-read `ctx.workflow_params` in `on_bootstrap(...)` and repeated generic normalization already covered by their shared `Parameters` models.
- Simplification opportunity: make `ctx.params` the default typed bootstrap surface across the remaining family while keeping workflow-specific status ordering, boundary checks, session setup, and invocation-contract shaping local.
- New workflow needed: no.
- Cycle decision: change/consolidate the remaining typed-bootstrap family, focused runtime tests, recursive memory, and this phase note only; no new workflow package and no new helper seam.

## Files Changed

- `workflows/workflow_run_history_to_failure_modes/workflow.py`
- `workflows/workflow_portfolio_to_operating_system/workflow.py`
- `workflows/company_operation_to_recursive_improvement_cycle/workflow.py`
- `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`
- `workflows/workflow_package_to_composable_building_blocks/workflow.py`
- `tests/runtime/test_workflow_run_history_to_failure_modes.py`
- `tests/runtime/test_workflow_portfolio_to_operating_system.py`
- `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
- `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
- `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `.autoloop_recursive/framework_gap_ledger.md`
- `.autoloop_recursive/workflow_candidate_ledger.md`
- `.autoloop_recursive/validation_debt_ledger.md`
- `.autoloop/tasks/recursive-framework-evolution-20260425t234529-bootstrap-c1/decisions.txt`

## Symbols Touched

- `WorkflowRunHistoryToFailureModes.on_bootstrap`
- `WorkflowPortfolioToOperatingSystem.on_bootstrap`
- `CompanyOperationToRecursiveImprovementCycle.on_bootstrap`
- `WorkflowAndEvalToRefinedWorkflowPackage.on_bootstrap`
- `WorkflowPackageToComposableBuildingBlocks.on_bootstrap`

## Checklist Mapping

- Plan milestone 1: confirmed the existing typed-bootstrap doctrine and recorded the phase-local audit plus closeout in recursive memory and this note.
- Plan milestone 2: migrated the remaining scoped bootstraps to `ctx.params` and removed the run-history workflow’s now-obsolete local raw-bootstrap helper tail.
- Plan milestone 3: added focused runtime tests for each migrated workflow and re-ran the scoped proof plus baseline docs coverage.

## Assumptions

- These five workflows continue to declare `Parameters`, so `ctx.params` is available as a typed model during normal runtime-backed bootstrap execution.
- Upstream loader coercion remains the place where raw workflow-parameter normalization happens.

## Preserved Invariants

- No CLI flag, runtime-provider boundary, `workflow.toml`, workspace layout, or `ctx.invoke_workflow(...)` contract changed.
- Session opening and invocation-contract writing remain explicit in workflow code through `stdlib/lifecycle.py`.
- Artifact names, routes, summaries, receipts, and publication-boundary semantics remain unchanged.

## Intended Behavior Changes

- The remaining targeted workflow family now reads typed bootstrap fields from `ctx.params` instead of re-reading `ctx.workflow_params`.
- The run-history workflow no longer keeps a dead raw-bootstrap normalization helper once the typed projection is in place.

## Known Non-Changes

- No new workflow package.
- No runtime or loader automation for bootstrap setup.
- No root `workflow` shim expansion and no new stdlib helper seam.

## Expected Side Effects

- Shorter, more legible bootstrap handlers across the scoped later family.
- Focused runtime suites now pin the typed-bootstrap contract directly for the later workflows instead of relying only on parameter-coercion tests.

## Deduplication / Centralization Decisions

- Reused the existing `Context.params` seam instead of introducing another helper or widening runtime behavior.
- Kept workflow-specific ordering, boundary policy, selected-workflow alignment, and candidate-surface policy local to each workflow.

## Validation Performed

- Added focused bootstrap tests for the five migrated workflows.
- Ran `.venv/bin/pytest -q tests/runtime/test_workflow_run_history_to_failure_modes.py tests/runtime/test_workflow_portfolio_to_operating_system.py tests/runtime/test_company_operation_to_recursive_improvement_cycle.py tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py tests/runtime/test_workflow_package_to_composable_building_blocks.py tests/test_architecture_baseline_docs.py` (`158 passed`).
