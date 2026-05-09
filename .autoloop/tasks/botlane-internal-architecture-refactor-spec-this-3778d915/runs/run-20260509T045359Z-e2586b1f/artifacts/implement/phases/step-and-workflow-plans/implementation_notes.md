# Implementation Notes

- Task ID: botlane-internal-architecture-refactor-spec-this-3778d915
- Pair: implement
- Phase ID: step-and-workflow-plans
- Phase Directory Key: step-and-workflow-plans
- Phase Title: Step And Workflow Plans
- Scope: phase-local producer artifact

## Files Changed

- `botlane/core/compiler.py`
- `botlane/core/plan_adapters.py`
- `botlane/core/step_plans.py`
- `botlane/core/workflow_plan.py`
- `tests/unit/test_step_plans.py`
- `tests/unit/test_workflow_plan_adapters.py`
- `tests/strictness/test_no_compat.py`

## Symbols Touched

- Added `compile_workflow_plan`
- Added `StepIO`, `StepHeader`, `StepStateSpec`, `StepHookSpec`, `ProviderTurnPlan`
- Added `PromptStepPlan`, `ProduceVerifyStepPlan`, `PythonStepPlan`, `ChildWorkflowStepPlan`, `BranchPlan`, `BranchGroupPlan`, `BranchGroupStepPlan`
- Added `WorkflowPlan`
- Implemented `step_plan_from_compiled_step`, `compiled_step_from_step_plan`, `workflow_plan_from_compiled`, `compiled_workflow_from_plan`

## Checklist Mapping

- Phase `step-and-workflow-plans` AC-1: complete
- Added typed step/workflow plan modules: complete
- Added lazy `compile_workflow_plan(...)` entrypoint: complete
- Added compiled step/workflow round-trip adapters and topology/route parity tests: complete
- Engine migration to consume `WorkflowPlan` directly: deferred by phase scope

## Assumptions

- `WorkflowPlan` remains an adapter layer in this phase; engine/runtime consumers stay on `CompiledWorkflow`
- Branch-group internal compiled-route metadata must stay exact even though canonical route tables only live at top-level `WorkflowPlan.routes`

## Preserved Invariants

- No public exports changed
- No `botlane.core` runtime imports from `botlane.runtime` were introduced
- `CompiledWorkflow`, `CompiledStep`, and `CompiledRoute` remain the compatibility/runtime shapes
- Route-contract ownership stays in workflow-level route tables, not on `StepHeader`

## Intended Behavior Changes

- None on public SDK/simple/runtime surfaces
- New internal adapter entrypoint and typed plan objects only

## Known Non-Changes

- Engine still executes `CompiledWorkflow`
- Provider request artifact names remain string-compatible
- No `SingleStepPlan`, `ExecutionFrame`, `ExecutionServices`, or placeholder migration in this phase

## Expected Side Effects

- Internal tests can now inspect typed plan objects without changing compiled/runtime consumers
- Strictness allowlists were extended narrowly for `WorkflowPlan`/adapter-test `RouteContract` references

## Deduplication / Centralization

- Kept all compiled <-> plan conversion logic in `botlane/core/plan_adapters.py`
- Reused the original compiled step object inside `StepHeader.original_step` to preserve exact round-trip parity for branch-group internals and mixed raw/compiled provider-turn tuples

## Validation Performed

- `.venv/bin/python -m pytest tests/unit/test_route_contracts.py`
- `.venv/bin/python -m pytest tests/unit/test_step_plans.py tests/unit/test_workflow_plan_adapters.py`
- `.venv/bin/python -m pytest tests/unit/test_simple_surface.py`
- `.venv/bin/python -m pytest tests/unit/test_sdk_facade.py`
- `.venv/bin/python -m pytest tests/strictness/test_no_compat.py`
