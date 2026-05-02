# Implementation Notes

- Task ID: below-is-the-full-standalone-remaining-delta-imp-45eb54ef
- Pair: implement
- Phase ID: hook-control-unification
- Phase Directory Key: hook-control-unification
- Phase Title: Hook And Control Unification
- Scope: phase-local producer artifact

## Files Changed
- `autoloop/core/engine.py`
- `autoloop/core/compiler.py`
- `autoloop/core/context.py`
- `autoloop/core/hook_validation.py`
- `autoloop/core/steps.py`
- `autoloop/runtime/cli.py`
- `tests/runtime/test_golden_workflow.py`
- `tests/runtime/test_runtime_static_graph.py`
- `tests/unit/test_simple_surface.py`
- `workflows/autoloop_v1/workflow.py`
- `workflows/candidate_workflow_to_adapted_execution_plan/workflow.py`
- `workflows/company_operation_to_recursive_improvement_cycle/workflow.py`
- `workflows/incident_to_hardening_program/workflow.py`
- `workflows/investigation_request_to_evidence_pack/workflow.py`
- `workflows/release_candidate_to_go_no_go/workflow.py`
- `workflows/security_finding_to_verified_remediation/workflow.py`
- `workflows/task_to_candidate_workflow_set/workflow.py`
- `workflows/task_to_workflow_strategy/workflow.py`
- `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`
- `workflows/workflow_idea_to_workflow_package/workflow.py`
- `workflows/workflow_package_to_composable_building_blocks/workflow.py`
- `workflows/workflow_portfolio_to_operating_system/workflow.py`
- `workflows/workflow_run_history_to_failure_modes/workflow.py`
- `workflows/workflow_run_traces_to_optimization_candidates/workflow.py`
- `workflows/workflow_to_eval_suite/workflow.py`

## Symbols Touched
- `HookResult`
- `_HookExecutionResult`
- `Engine._run_before_hook`
- `Engine._run_after_hook`
- `Engine._run_route_hook`
- `Engine._normalize_hook_result`
- `Engine._finalize_step_result`
- `Engine._execute_step`
- `Engine._execute_pair_step`
- `Engine._run_pair_step`
- `Context.state`
- `Context.outcome`
- `_compile_system_handler`
- `validate_step_hooks`

## Checklist Mapping
- Milestone 2 / AC-1: step hooks now validate as single-argument `hook(ctx)` only.
- Milestone 2 / AC-2: `before`, `before_producer`, and `before_verifier` can now short-circuit into route finalization or direct runtime control before provider execution.
- Milestone 2 / AC-3: repo-owned `python_step` surfaces were migrated to mutate `ctx.state` and return route/control values instead of returning replacement state from handlers.

## Assumptions
- Pair-step short-circuits from `before_producer`, `after_producer`, and `before_verifier` should finalize immediately without running the pair step’s final `after_verifier` hook.
- Hook-originated pre-provider routes should surface as final routes while leaving `candidate_route` unset to avoid misattributing a provider-selected route that never happened.

## Preserved Invariants
- Direct runtime controls still checkpoint via the existing terminal and goto paths.
- Artifact re-resolution still occurs after hook-driven state mutation before final validation and route `on_taken`.
- Built-in finalized-route state updates still happen only after successful route finalization.

## Intended Behavior Changes
- Public lifecycle hooks and route `on_taken` are now `hook(ctx)` only; multi-arity hook execution branches were removed.
- `AfterStepResult` was removed from the core runtime path.
- Hook result normalization now accepts route tags, `Event`, `RequestInput`, `Goto`, and `Fail` even before a provider candidate route exists.

## Known Non-Changes
- This turn did not refactor the collaborator classes into full standalone owners; the behavior change is concentrated in engine/runtime semantics first.
- This turn did not complete broader history/tracing schema expansion such as explicit `provider_attempted` / `producer_attempted` / `verifier_attempted` fields.

## Expected Side Effects
- Repo-owned workflow packages and CLI scaffolds now use `ctx.state = ...` plus direct route/control returns in `python_step` handlers.
- Hook-focused contract tests and topology fixtures now declare hooks with the final single-argument form.

## Validation Performed
- `python3 -m py_compile` on the touched core modules, touched tests, and migrated workflow packages.
- Runtime smoke execution was attempted but blocked because the shell environment does not currently provide `pydantic` or `pytest`.

## Deduplication / Centralization
- Hook result handling is now centralized through a single normalized `HookResult` path shared by `before`, `after`, `before_producer`, `after_producer`, `before_verifier`, `after_verifier`, route `on_taken`, and python-step result handling in the engine.
