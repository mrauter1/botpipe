# Implementation Notes

- Task ID: below-is-the-full-standalone-remaining-delta-imp-45eb54ef
- Pair: implement
- Phase ID: hook-control-unification
- Phase Directory Key: hook-control-unification
- Phase Title: Hook And Control Unification
- Scope: phase-local producer artifact

## Files Changed
- `autoloop/core/compiler.py`
- `autoloop/core/context.py`
- `autoloop/core/engine.py`
- `autoloop/core/engine_collaborators.py`
- `autoloop/core/hook_validation.py`
- `autoloop/core/steps.py`
- `autoloop/runtime/cli.py`
- `tests/contract/test_engine_contracts.py`
- `tests/runtime/test_golden_workflow.py`
- `tests/runtime/test_optional_extensions.py`
- `tests/runtime/test_package_cli.py`
- `tests/runtime/test_runtime_static_graph.py`
- `tests/runtime/test_workflow_builder_package.py`
- `tests/runtime/test_workspace_and_context.py`
- `tests/unit/test_simple_surface.py`
- `tests/unit/test_validation.py`
- repo-owned workflow packages under `workflows/` migrated in the prior pass for this phase

## Symbols Touched
- `HookResult`
- `HookExecutionResult`
- `StepFinalizationRequest`
- `StepFinalizationResult`
- `HookRunner.run_before`
- `HookRunner.run_after`
- `HookRunner.run_route`
- `HookRunner.normalize_result`
- `RouteFinalizer.finalize`
- `StepDispatcher.execute`
- `Engine._execute_pair_step`
- `Engine._execute_llm_step`
- `Engine._execute_workflow_step`
- `_compile_system_handler`
- `validate_step_hooks`

## Checklist Mapping
- Milestone 2 / AC-1: lifecycle hooks and route `on_taken` continue to validate as `hook(ctx)` only.
- Milestone 2 / AC-2: hook short-circuits still finalize before provider execution, and hook-originated pre-provider routes now preserve `candidate_route=None` through explicit finalization request data.
- Milestone 2 / AC-3: remaining repo-owned python-step tests/templates were migrated to `ctx.state` plus direct route/control returns, and explicit rejection coverage was added for tuple and `BaseModel` python-step returns.

## Assumptions
- Pair-step short-circuits from `before_producer`, `after_producer`, and `before_verifier` should finalize immediately without running the pair step’s final `after_verifier` hook.
- Provider/python-selected candidate routes should remain attributable even when later hooks override the final route, while hook-originated pre-provider routes should keep `candidate_route` unset.

## Preserved Invariants
- Direct runtime controls still checkpoint via the existing terminal and goto paths.
- Artifact re-resolution still occurs after hook-driven state mutation before final validation and route `on_taken`.
- Built-in finalized-route state updates still happen only after successful route finalization.

## Intended Behavior Changes
- Hook invocation/normalization ownership now lives in `HookRunner`, route finalization ownership now lives in `RouteFinalizer`, and top-level step-kind dispatch now lives in `StepDispatcher`.
- Finalization now uses explicit request/result structures instead of tuple-heavy argument plumbing, including an explicit `candidate_route_present` distinction for hook-originated pre-provider routes.
- Repo-owned python-step examples now mutate `ctx.state` and return direct route/control values only.

## Known Non-Changes
- This phase still does not complete the broader trace/history schema expansion such as explicit `provider_attempted` / `producer_attempted` / `verifier_attempted` fields.

## Expected Side Effects
- Repo-owned tests and generated workflow snippets now document only the final python-step return contract.
- Explicit rejection tests now fail fast if tuple or `BaseModel` python-step returns are reintroduced.

## Validation Performed
- `python3 -m py_compile autoloop/core/engine.py autoloop/core/engine_collaborators.py autoloop/core/compiler.py autoloop/core/context.py autoloop/core/hook_validation.py autoloop/core/steps.py tests/contract/test_engine_contracts.py tests/runtime/test_workspace_and_context.py tests/runtime/test_package_cli.py tests/runtime/test_workflow_builder_package.py tests/runtime/test_optional_extensions.py tests/unit/test_validation.py`
- `rg -n "return state, Event\\(|return state\\.model_copy\\(update=.*\\), Event\\(" tests workflows autoloop/runtime/cli.py` now leaves only the explicit tuple-return rejection test in `tests/contract/test_engine_contracts.py`
- Runtime test execution remains blocked in this shell because `pytest` and `pydantic` are not installed.

## Deduplication / Centralization
- Hook result handling is centralized in `HookRunner`.
- Route finalization and candidate-route attribution are centralized in `RouteFinalizer`.
- Top-level step dispatch now lives in `StepDispatcher` instead of an engine-owned wrapper path.
