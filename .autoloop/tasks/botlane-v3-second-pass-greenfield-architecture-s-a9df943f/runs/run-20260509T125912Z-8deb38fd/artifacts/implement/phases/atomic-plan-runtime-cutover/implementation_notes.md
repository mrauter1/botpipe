# Implementation Notes

- Task ID: `botlane-v3-second-pass-greenfield-architecture-s-a9df943f`
- Pair: `implement`
- Phase ID: `atomic-plan-runtime-cutover`
- Scope: phase-local producer artifact

## Files changed

- Core/compiler/runtime: `botlane/core/{compiler.py,engine.py,engine_collaborators.py,step_plans.py,workflow_plan.py,route_contracts.py,route_required_writes.py,artifacts.py,context.py,workflow_capabilities.py}`, `botlane/core/branch_groups/{__init__.py,models.py,runtime.py}`, `botlane/runtime/{loader.py,runner.py,static_graph.py,tracing.py,provider_policy_resolver.py}`
- SDK/workflows: `botlane/sdk.py`, `botlane/workflows/botlane_v1/parity.py`
- Removed: `botlane/core/plan_adapters.py`, `tests/unit/test_workflow_plan_adapters.py`
- Tests updated: `tests/unit/{test_public_surface.py,test_simple_surface.py,test_step_plans.py,test_artifact_ids.py,test_route_contracts.py}`, `tests/contract/{test_provider_turn_plan_adapter.py,test_single_step_plan_equivalence.py}`, `tests/runtime/{workflow_contract_helpers.py,test_progress_worklists.py}`

## Symbols touched

- Compiler cutover: `compile_workflow`, `_WORKFLOW_PLAN_CACHE`, `WorkflowPlan`, `ArtifactSpec`, `ArtifactId`, `RouteContract`, `StepPlan` variants, `ProviderTurnPlan`
- Runtime cutover: `Engine`, `StepDispatcher`, `RouteFinalizer`, `StepExecutionResult`, branch-group plan imports, workflow capability inspection
- Removed legacy internals: `CompiledArtifact`, compiled branch spec exports, `plan_adapters`

## Checklist mapping

- Plan Phase 2 compiler/runtime cutover: completed for compiler, engine, engine collaborators, SDK, loader/runner/static graph/tracing/provider-policy resolver, workflow capability inspection, and botlane-v1 parity consumer
- Plan Phase 2 branch export cleanup: completed by removing compiled branch exports from `botlane.core.branch_groups.__all__`
- Plan Phase 8 adapter-era cleanup pulled forward where required for Phase 2 correctness: removed `tests/unit/test_workflow_plan_adapters.py`; rewrote adapter-era tests to canonical plan/runtime assertions

## Assumptions

- Private `_route_table` on step plans is acceptable in Phase 2 as an internal runtime/cache detail while public/internal exports remain unchanged
- String-comparison compatibility for `ArtifactId` and `RouteTarget` is acceptable so existing route/artifact surfaces continue to behave while canonical storage remains typed

## Preserved invariants

- `botlane.__all__` and `botlane.core.__all__` were not intentionally changed
- Public route authoring (`FINISH`, `AWAIT_INPUT`, `FAIL`, `SELF`, `Route(...)`) still compiles and executes
- `Botlane.step(...)` still uses `SingleStepPlan` as the one-step path
- `ArtifactHandle.artifact` behavior remains unchanged; runtime artifact resolution now flows through `ArtifactId -> ArtifactSpec -> ArtifactHandle`

## Intended behavior changes

- `compile_workflow(...)` is now the only compiler entrypoint and returns `WorkflowPlan`
- Core/runtime consumers now use `WorkflowPlan`, typed `StepPlan` variants, and `RouteContract` directly
- `botlane.core.branch_groups.__all__` no longer exports compiled branch specs

## Known non-changes

- `ExecutionFrame` authority, typed `BranchResult`/`BranchManifest` runtime internals, and placeholder centralization are still deferred to later phases
- `StepExecutionResult.finalization` still exists as the current transition record surface even though route decisions/actions are now also present

## Expected side effects

- Internal tests and helpers that depended on compiled/adaptor objects now target canonical plan/runtime objects instead
- Workflow capability/CLI payloads now serialize route targets and required writes from typed route contracts rather than compiled-route strings

## Deduplication / centralization decisions

- Route visibility/target compatibility moved onto `RouteContract`/`RouteTarget` helpers instead of keeping adapter conversion layers
- Artifact resolution now centralizes on `WorkflowPlan.artifact_spec(...)` / qualified-name indexes rather than reconstructing compiled artifact metadata

## Validation performed

- `python3 -m compileall -q botlane`
- `./.venv/bin/pytest tests/unit/test_public_surface.py tests/unit/test_simple_surface.py -q`
- `./.venv/bin/pytest tests/unit/test_step_plans.py tests/unit/test_artifact_ids.py tests/unit/test_route_contracts.py tests/contract/test_provider_turn_plan_adapter.py tests/contract/test_single_step_plan_equivalence.py -q`
- `./.venv/bin/pytest tests/unit/test_public_surface.py tests/unit/test_simple_surface.py tests/unit/test_step_plans.py tests/unit/test_artifact_ids.py tests/unit/test_route_contracts.py tests/contract/test_provider_turn_plan_adapter.py tests/contract/test_single_step_plan_equivalence.py tests/runtime/test_progress_worklists.py tests/runtime/test_package_cli.py tests/runtime/test_workspace_and_context.py -q`
  - Result: `204 passed`
- `rg` scan over `botlane/core`, `botlane/runtime`, `botlane/sdk.py`, `botlane/workflows`, `botlane_optimizer`
  - No remaining `Compiled*`, `compile_workflow_plan`, `_COMPILED_WORKFLOW_CACHE`, or `plan_adapters` matches
