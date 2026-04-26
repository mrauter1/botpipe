# Implementation Notes

- Task ID: recursive-framework-evolution-20260425t234529-bootstrap-c1
- Pair: implement
- Phase ID: typed-bootstrap-contract-and-first-family
- Phase Directory Key: typed-bootstrap-contract-and-first-family
- Phase Title: Typed Bootstrap Contract
- Scope: phase-local producer artifact

## Audit

- Cycle mode: `consolidate`
- Three most relevant existing workflows/helpers:
  - `workflows/task_to_candidate_workflow_set/workflow.py`
  - `workflows/task_to_workflow_strategy/workflow.py`
  - `workflows/candidate_workflow_to_adapted_execution_plan/workflow.py`
  - adjacent helper/document seams: `docs/authoring.md`, `stdlib/parameters.py`, `stdlib/lifecycle.py`, `core/context.py`
- Repeated pattern identified: the scoped workflow family still re-read `ctx.workflow_params` in `on_bootstrap(...)` and repeated generic normalization already covered by shared `Parameters` models.
- Simplification opportunity: make `ctx.params` the default typed bootstrap surface while leaving session opening and invocation-contract writing explicit.
- New workflow needed: no.
- Cycle decision: change/consolidate existing workflows and docs only; no new workflow package.

## Files Changed

- `workflows/task_to_candidate_workflow_set/workflow.py`
- `workflows/task_to_workflow_strategy/workflow.py`
- `workflows/candidate_workflow_to_adapted_execution_plan/workflow.py`
- `workflows/workflow_to_eval_suite/workflow.py`
- `docs/authoring.md`
- `tests/runtime/test_task_to_candidate_workflow_set.py`
- `tests/runtime/test_task_to_workflow_strategy.py`
- `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
- `tests/runtime/test_workflow_to_eval_suite.py`
- `tests/test_architecture_baseline_docs.py`
- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `.autoloop_recursive/framework_gap_ledger.md`
- `.autoloop_recursive/workflow_candidate_ledger.md`
- `.autoloop_recursive/validation_debt_ledger.md`
- `.autoloop/tasks/recursive-framework-evolution-20260425t234529-bootstrap-c1/decisions.txt`

## Symbols Touched

- `TaskToCandidateWorkflowSet.on_bootstrap`
- `TaskToWorkflowStrategy.on_bootstrap`
- `CandidateWorkflowToAdaptedExecutionPlan.on_bootstrap`
- `WorkflowToEvalSuite.on_bootstrap`

## Checklist Mapping

- Plan milestone 1: updated `docs/authoring.md` and recorded the audit/decision in this note plus recursive memory.
- Plan milestone 2: migrated the four scoped bootstraps to `ctx.params` and removed redundant bootstrap normalization from those handlers.
- Plan milestone 3: added focused runtime tests plus doc-baseline coverage for the typed bootstrap rule.

## Assumptions

- These four workflows continue to declare `Parameters`, so `ctx.params` is always available as a typed model during runtime-backed bootstrap execution.
- Upstream loader coercion remains the place where raw workflow-parameter normalization happens.

## Preserved Invariants

- No CLI flag, runtime-provider boundary, `workflow.toml`, or `ctx.invoke_workflow(...)` contract changed.
- Session opening and invocation-contract writing remain explicit in workflow code through `stdlib/lifecycle.py`.
- Artifact names, routes, summaries, and receipts remain unchanged.

## Intended Behavior Changes

- Bootstraps in the scoped first family now read typed bootstrap fields from `ctx.params` instead of re-reading `ctx.workflow_params`.
- `docs/authoring.md` now states this as the default rule when `Parameters` exists.

## Known Non-Changes

- No new workflow package.
- No runtime or loader automation for bootstrap setup.
- No migration yet for `workflow_run_history_to_failure_modes`, `workflow_portfolio_to_operating_system`, `company_operation_to_recursive_improvement_cycle`, `workflow_and_eval_to_refined_workflow_package`, or `workflow_package_to_composable_building_blocks`.

## Expected Side Effects

- Shorter bootstrap handlers in the scoped family.
- Tests now pin the typed-bootstrap contract directly instead of only proving raw compatibility-dict execution paths.

## Deduplication / Centralization Decisions

- Reused the existing `Context.params` seam instead of adding another helper or widening runtime behavior.
- Kept workflow-specific state resets and invocation-contract shaping local to each workflow.

## Validation Performed

- Added focused bootstrap tests for the four migrated workflows.
- Added architecture-doc baseline coverage for the explicit `ctx.params` default-bootstrap rule.
- Ran `.venv/bin/pytest -q tests/runtime/test_task_to_candidate_workflow_set.py tests/runtime/test_task_to_workflow_strategy.py tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py tests/runtime/test_workflow_to_eval_suite.py tests/test_architecture_baseline_docs.py` (`126 passed`).
