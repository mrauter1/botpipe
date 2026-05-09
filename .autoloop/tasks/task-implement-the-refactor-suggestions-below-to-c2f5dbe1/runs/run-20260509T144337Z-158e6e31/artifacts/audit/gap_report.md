# Gap Report

## Original intent considered

- Restore one consistent executable mutator surface after the runtime/discovery extraction without undoing the refactor structure.
- Make executable runtime writes flow coherently across `Context`, `ExecutionFrame`, engine collaborators, worklist helpers, and branch-group context/runtime helpers.
- Clear the named failures in `tests/unit/test_simple_surface.py`, `tests/unit/test_runtime_and_discovery_extraction.py`, and `tests/contract/engine/test_runtime_controls.py`.
- Use the supplied regression batch as the acceptance command.
- Keep hotspot 9 deferred unless adjacent work required opening `botlane/core/workflow_capabilities.py`.

## Clarifications / superseding decisions

- `decisions.txt` block 1 makes `Context` the canonical executable mutator facade and keeps `ExecutionFrame` as the backing store and child-frame construction primitive.
- `decisions.txt` block 1 also locks this into a behavior-preserving consolidation and keeps hotspot 9 deferred.
- `decisions.txt` block 2 preserves shared `values` identity and requires one shared `Context._set_worklist_selection(...)` path for engine lazy restore, worklist runtime mutations, and branch-child lazy restore.
- The plan and implementation artifacts consistently scope the change to executable runtime mutators rather than workflow discovery or broader runtime redesign.

## Implemented behavior

- `botlane/core/context.py` now exposes the private executable mutator facade (`_set_state`, `_set_values`, `_set_route`, `_set_event`, `_set_outcome`, `_set_meta`, `_set_step_state`, `_set_item_state`, `_set_step_item_state`, `_set_active_worklist`, `_set_selection_snapshots`, `_set_worklist_selection_sync`, `_set_worklist_selection_resolver`, `_set_execution_source`, `_set_worklist_selection`).
- `botlane/core/engine.py`, `botlane/core/engine_collaborators.py`, `botlane/core/worklists.py`, `botlane/core/branch_groups/context.py`, and `botlane/core/branch_groups/runtime.py` route executable runtime writes through that facade instead of maintaining separate mutator paths.
- `tests/unit/test_execution_frame_context_parity.py` adds direct regression coverage for the new facade, touched-snapshot-only invalidation plus sync callback behavior, and branch-child lazy selection restore through the same helper path.
- The requested acceptance command passes in the current final workspace: `217 passed in 1.33s`.
- The added parity file also passes in the current final workspace: `9 passed in 0.44s`.

## Unresolved gaps

- No material unresolved gaps remain against the stated request.
- Non-material note: `botlane/core/branch_groups/context.py::_inherit_child_frame_bookkeeping(...)` still copies `child._execution_frame.worklist_items_cache` directly. That is cache bookkeeping rather than the executable state/selection mutator contract the request targeted, and the current tests do not show behavioral drift from it.

## Differences justified by later clarification or analysis

- `botlane/core/workflow_capabilities.py` was not opened or changed. That matches the original deferment instruction and the recorded plan/decision trail.
- The test artifacts documented a transient validation blocker in dirty `botlane/core/branch_groups/outcomes.py`, but the final workspace no longer exhibits that blocker: the full acceptance rerun is green. That earlier note is therefore resolved workspace noise, not an outstanding implementation gap.
- The run added low-level parity coverage in `tests/unit/test_execution_frame_context_parity.py` instead of expanding broader suites. That is consistent with the test decision log and still preserves the required acceptance evidence because the acceptance batch now passes in the final workspace.

## Recommended next run

- No follow-up implementation run is required for this request.
- Optional future cleanup only if this area is reopened: hide the branch-child `worklist_items_cache` copy behind a tiny private `Context` helper for full cosmetic consistency.
