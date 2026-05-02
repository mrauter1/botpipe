# Implement ↔ Code Reviewer Feedback

- Task ID: below-is-the-full-standalone-remaining-delta-imp-45eb54ef
- Pair: implement
- Phase ID: public-surface-cleanup
- Phase Directory Key: public-surface-cleanup
- Phase Title: Public Surface Cleanup
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 `blocking`
  File/symbol: `autoloop/core/compiler.py:_compile_outcome_handler` (lines 431-439), `autoloop/core/discovery.py:has_start_hook` (lines 288-291), `autoloop/core/lowering.py:outcome_middleware_name` (lines 20-27).
  Problem: the public compiler path still accepts legacy class-level methods on `autoloop.simple.Workflow`, even though this phase is supposed to restrict public authoring to explicit declarations only. Reproduction in the repo venv shows `compile_workflow()` still wires a simple prompt-step `on_<step>` handler (`compiled.steps["ask"].outcome_handler is not None`), still recognizes `on_start` (`compiled.has_start_hook is True`), and still enables `on_outcome` middleware (`compiled.middleware is not None`).
  Risk: the public surface remains a hybrid contract, so removed legacy authoring is still live for simple workflows. That contradicts the phase scope, the remaining-delta spec, and the run decision that only the alias installation was removed in this turn. Future cleanup will be harder because both explicit declarations and legacy class methods still compile on the same path.
  Minimal fix: gate legacy class-level handler discovery off for simple/public workflows in one centralized ownership point, then update the corresponding validation/tests/docs to enforce explicit step hooks and step-local routes only.

- IMP-002 `blocking`
  File/symbol: `tests/contract/test_engine_contracts.py` legacy `on_route` coverage, for example lines 3763-3775 and 4253-4264.
  Problem: the source change intentionally removes `on_route` from core step constructors, but the repo still contains contract tests that construct steps with `on_route=...`. This is an observed regression, not just stale text: `./.venv/bin/python -m pytest tests/contract/test_engine_contracts.py -q -k on_route_hook_invalid_arity_fails_validation` now fails with `TypeError: PromptStep.__init__() got an unexpected keyword argument 'on_route'`.
  Risk: the phase claims removed-surface cleanup and fail-fast validation coverage, but the suite still contains legacy runtime tests for the removed API. That leaves the repo in a knowingly red state and obscures whether the intended replacement behavior is actually covered.
  Minimal fix: replace the remaining `on_route` contract tests with either fail-fast removal assertions or equivalent `Route.to(..., on_taken=...)` coverage, and scrub remaining `on_route` construction sites in the affected contract tests in the same pass.

- IMP-003 `blocking`
  File/symbol: exported public simple workflows under `workflows/*/workflow.py`, including `workflows/company_operation_to_recursive_improvement_cycle/workflow.py`, `workflows/incident_to_hardening_program/workflow.py`, `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`, `workflows/workflow_idea_to_workflow_package/workflow.py`, `workflows/workflow_package_to_composable_building_blocks/workflow.py`, `workflows/workflow_portfolio_to_operating_system/workflow.py`, `workflows/workflow_run_history_to_failure_modes/workflow.py`, `workflows/workflow_run_traces_to_optimization_candidates/workflow.py`, and `workflows/workflow_to_eval_suite/workflow.py`.
  Problem: the central public simple-workflow gate is now enforcing the new contract, but several shipped `autoloop.simple.Workflow` packages in the repo still define removed class-level `on_start`, `on_outcome`, or `on_<step>` handlers and therefore no longer compile. Reproduction: a repo-wide `compile_workflow()` sweep over exported workflow packages still fails with `WorkflowValidationError: simple workflows must declare lifecycle and step behavior on explicit step declarations...` for the files above. The touched targeted tests pass, but the published public workflow surface is still broken end to end.
  Risk: this phase is supposed to restrict the public compiler path to explicit declarations only, without compatibility shims. Leaving repo-shipped public simple workflows on the removed API creates a real regression surface for examples, fixtures, and downstream users, and it leaves the public authoring model half-migrated. That is a material compatibility and maintainability failure even though the central gate itself is correct.
  Minimal fix: migrate the remaining exported simple workflow packages off class-level handlers in the same explicit-hook pattern already applied to the other workflow packages in this cycle, or explicitly isolate those packages from the public simple path if they are not intended to remain public-simple authoring examples.

## Cycle 3 Review

- Reproduced on 2026-05-02: `IMP-001`, `IMP-002`, and `IMP-003` no longer reproduce after the cycle 3 changes.
- Validation rerun:
  `./.venv/bin/python -m pytest tests/unit/test_simple_surface.py tests/contract/test_engine_contracts.py tests/runtime/test_workspace_and_context.py tests/runtime/test_runtime_static_graph.py -q`
  Result: `189 passed`.
- Repo-wide `compile_workflow()` sweeps still fail, but only on separate route-handoff-to-`PythonStep` validation errors that predate this phase and are outside `public-surface-cleanup` scope. No remaining in-scope findings were identified in this review pass.
