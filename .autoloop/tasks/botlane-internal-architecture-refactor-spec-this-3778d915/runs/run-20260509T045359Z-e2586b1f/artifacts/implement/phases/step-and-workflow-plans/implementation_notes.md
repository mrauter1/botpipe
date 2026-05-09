# Implementation Notes

- Task ID: botlane-internal-architecture-refactor-spec-this-3778d915
- Pair: implement
- Phase ID: step-and-workflow-plans
- Phase Directory Key: step-and-workflow-plans
- Phase Title: Step And Workflow Plans
- Scope: phase-local producer artifact

## Files Changed

- `botlane/core/plan_adapters.py`
- `botlane/core/step_plans.py`
- `tests/unit/test_step_plans.py`

## Symbols Touched

- Updated `StepHeader.original_step` parity behavior
- Added private step-plan `_compiled_step` parity carriers
- Updated `step_plan_from_compiled_step`, `compiled_step_from_step_plan`, `_compiled_branch_group_from_plan`

## Checklist Mapping

- Phase `step-and-workflow-plans` AC-1: complete
- Typed step/workflow plan modules remain in place: complete
- Lazy `compile_workflow_plan(...)` entrypoint remains in place: complete
- Compiled step/workflow round-trip adapters and topology/route parity tests remain passing after reviewer fix: complete
- Engine migration to consume `WorkflowPlan` directly: deferred by phase scope

## Assumptions

- `WorkflowPlan` remains an adapter layer in this phase; engine/runtime consumers stay on `CompiledWorkflow`
- Branch-group exact round-trip parity may rely on adapter-owned private compiled parity records, but not on `StepHeader`

## Preserved Invariants

- No public exports changed
- No `botlane.core` runtime imports from `botlane.runtime` were introduced
- `CompiledWorkflow`, `CompiledStep`, and `CompiledRoute` remain the compatibility/runtime shapes
- Route-contract ownership stays in workflow-level route tables, not on `StepHeader`
- `StepHeader.original_step` stays the authored step object instead of carrying a legacy compiled-step bag

## Intended Behavior Changes

- None on public SDK/simple/runtime surfaces
- No new public behavior; internal typed plans now keep compiled parity in private variant fields rather than on `StepHeader`

## Known Non-Changes

- Engine still executes `CompiledWorkflow`
- Provider request artifact names remain string-compatible
- No `SingleStepPlan`, `ExecutionFrame`, `ExecutionServices`, or placeholder migration in this phase

## Expected Side Effects

- Internal tests can now inspect typed plan objects without changing compiled/runtime consumers
- Branch-group plan round-trips remain exact even when top-level parity is rebuilt from nested explicit parity carriers

## Deduplication / Centralization

- Kept all compiled <-> plan conversion logic in `botlane/core/plan_adapters.py`
- Centralized adapter-only exact round-trip state in private `_compiled_step` fields on step-plan variants instead of duplicating compiled route metadata through `StepHeader`

## Validation Performed

- `.venv/bin/python -m pytest tests/unit/test_step_plans.py tests/unit/test_workflow_plan_adapters.py tests/unit/test_simple_surface.py tests/unit/test_sdk_facade.py tests/strictness/test_no_compat.py`
