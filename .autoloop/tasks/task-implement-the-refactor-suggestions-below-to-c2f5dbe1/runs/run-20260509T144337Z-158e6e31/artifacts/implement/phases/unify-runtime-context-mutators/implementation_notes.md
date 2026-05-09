# Implementation Notes

- Task ID: task-implement-the-refactor-suggestions-below-to-c2f5dbe1
- Pair: implement
- Phase ID: unify-runtime-context-mutators
- Phase Directory Key: unify-runtime-context-mutators
- Phase Title: Unify Runtime Context Mutators
- Scope: phase-local producer artifact

## Files changed

- `botlane/core/context.py`
- `botlane/core/engine.py`
- `botlane/core/engine_collaborators.py`
- `botlane/core/worklists.py`
- `botlane/core/branch_groups/context.py`
- `botlane/core/branch_groups/runtime.py`

## Symbols touched

- `Context._set_state`
- `Context._set_artifacts`
- `Context._set_values`
- `Context._set_route`
- `Context._set_event`
- `Context._set_outcome`
- `Context._set_meta`
- `Context._set_step_state`
- `Context._set_item_state`
- `Context._set_step_item_state`
- `Context._set_active_worklist`
- `Context._set_selection_snapshots`
- `Context._set_worklist_selection_sync`
- `Context._set_worklist_selection_resolver`
- `Context._set_execution_source`
- `Context._set_worklist_selection`
- `Engine._configure_context_frame`
- `Engine._prepare_step_frame`
- `Engine._restore_hook_context`
- `Engine._restore_worklist_selections`
- `Engine._ensure_worklist_selection`
- `Engine._sync_context_scoped_state_after_worklist_selection_change`
- `StepDispatcher.execute_async`
- `StepDispatcher._execute_python_step_for_mode`
- `StepDispatcher._run_pair_step_async`
- `RouteFinalizer.capture`
- `RouteFinalizer.finalize_result`
- `HookRunner.run_before`
- `HookRunner.run_after`
- `HookRunner.run_route`
- `WorklistRuntimeView.refresh`
- `WorklistRuntimeView.set_current_status`
- `WorklistRuntimeView.reset_current_status`
- `WorklistRuntimeView.advance`
- `_inherit_child_frame_bookkeeping`
- `_child_worklist_selection_resolver`
- `BranchGroupRuntime.run_async`
- `BranchGroupRuntime._execute_branch`
- `BranchGroupRuntime._run_fan_in`

## Checklist mapping

- Plan item 1: added a private `Context` mutator facade and one shared selection-aware mutator.
- Plan item 2: rewired engine, collaborators, worklist helpers, and branch-group runtime/context helpers to use the facade for executable writes.
- Plan item 3: validated with focused preflight plus the required acceptance batch.

## Assumptions

- `ExecutionFrame` remains the backing store and child-frame factory; tests and construction code may still write to it directly when they are not executable runtime collaborators.

## Preserved invariants

- Worklist selection updates still clear only the touched snapshot entry through `ExecutionFrame.set_selection(...)`.
- Scoped `item_state` and `step_item_state` refresh still happens only through the active scoped worklist callback path.
- Branch and fan-in child contexts still share parent state and request snapshots while keeping child-local selection caches.
- Runtime `values` remain shared by reference across parent/child executable contexts.

## Intended behavior changes

- None. This change is contract consolidation only.

## Known non-changes

- Did not edit workflow discovery/compiler code.
- Did not open `botlane/core/workflow_capabilities.py`.
- Did not change `ExecutionFrame.child_for_*()` construction behavior.

## Expected side effects

- Executable runtime writes now flow through one private `Context` surface, reducing future drift risk between engine selection restore, worklist runtime helpers, and branch child selection restore.

## Validation performed

- Focused preflight:
  - `tests/unit/test_execution_frame_context_parity.py`
  - `tests/unit/test_branch_group_context_sessions.py`
  - `tests/unit/test_runtime_and_discovery_extraction.py`
  - `tests/contract/engine/test_runtime_controls.py`
  - `tests/unit/test_simple_surface.py`
- Preflight note: `tests/unit/test_branch_group_context_sessions.py` has two unrelated local failures from constructor-signature mismatches (`StepExecutionResult(..., finalization=...)` and `replace(..., scope_name=...)`); not in the required acceptance batch and not introduced by this refactor.
- Acceptance:
  - `.venv/bin/python -m pytest tests/runtime/test_provider_policy_emitters.py tests/unit/test_policy.py tests/unit/test_simple_policy.py tests/runtime/test_provider_policy_config.py tests/unit/test_placeholder_refs.py tests/unit/test_simple_surface.py tests/unit/test_inventory.py tests/unit/test_step_plans.py tests/unit/test_route_contracts.py tests/contract/test_branch_result_serialization.py tests/unit/test_runtime_and_discovery_extraction.py tests/contract/engine/test_runtime_controls.py -q`
  - Result: `217 passed`

## Deduplication / centralization decisions

- Centralized executable frame-backed writes behind `Context` instead of introducing a new runtime wrapper.
- Reused `Context._set_worklist_selection(...)` for engine lazy selection restore, worklist runtime mutations, and branch-child lazy selection restore.
