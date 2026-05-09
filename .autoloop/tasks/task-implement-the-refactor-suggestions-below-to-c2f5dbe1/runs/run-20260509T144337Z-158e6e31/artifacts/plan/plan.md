# Plan

## Goal

Preserve the runtime/discovery extraction and restore one executable mutator contract by making `Context` the canonical runtime write surface for frame-backed state and worklist selection updates, while keeping `ExecutionFrame` as the storage and child-frame primitive. This is a behavior-preserving consolidation: the cited tests and the full acceptance batch already pass in this workspace, so the implementation must not change runtime semantics.

## Repo Findings

- `Context` no longer owns a separate runtime sidecar; legacy underscore attributes are synthesized from `_execution_frame` via `_legacy_frame_attr(...)`.
- `ExecutionFrame` already holds the authoritative mutable runtime cells plus `child_for_step(...)`, `child_for_branch(...)`, and `child_for_fan_in(...)`.
- The drift is in executable call sites, not in workflow discovery:
  - `Engine._ensure_worklist_selection(...)`
  - `WorklistRuntimeView.refresh(...)`, `set_current_status(...)`, `reset_current_status(...)`, and `advance(...)`
  - `botlane/core/branch_groups/context.py::_child_worklist_selection_resolver(...)`
  - step and branch setup code in `botlane/core/engine.py`, `botlane/core/engine_collaborators.py`, and `botlane/core/branch_groups/runtime.py`
- The duplicated worklist-selection paths all need the same invariants: update the live selection, clear only that worklist's stored snapshot, refresh scoped item stores when the active scoped worklist changes, and preserve existing runtime event behavior.
- Hotspot 9 remains deferred because the current change does not require opening `botlane/core/workflow_capabilities.py`.

## Implementation Plan

### 1. Add a narrow `Context` mutator facade

- In `botlane/core/context.py`, add small private helpers that forward executable runtime writes to `_execution_frame`:
  - direct passthroughs used by executable code such as `_set_state(...)`, `_set_artifacts(...)`, `_set_values(...)`, `_set_route(...)`, `_set_event(...)`, `_set_outcome(...)`, `_set_meta(...)`, `_set_step_state(...)`, `_set_item_state(...)`, `_set_step_item_state(...)`, `_set_active_worklist(...)`, `_set_execution_source(...)`, `_set_selection_snapshots(...)`, `_set_worklist_selection_sync(...)`, and `_set_worklist_selection_resolver(...)`
  - one selection-aware helper, e.g. `_set_worklist_selection(...)`, that owns snapshot invalidation and optional scoped-state sync
- Keep `ExecutionFrame` setters intact for child-frame construction, storage primitives, and existing parity tests. Do not add a new runtime wrapper or registry.

### 2. Route executable writers through `Context`

- Replace direct frame mutation in executable runtime code with the `Context` helpers in:
  - `botlane/core/engine.py`
  - `botlane/core/engine_collaborators.py`
  - `botlane/core/worklists.py`
  - `botlane/core/branch_groups/context.py`
  - `botlane/core/branch_groups/runtime.py`
- Use the same helper in both lazy selection resolvers (`Engine._ensure_worklist_selection(...)` and `_child_worklist_selection_resolver(...)`) so selection writes, snapshot clearing, and scoped-state refresh cannot diverge again.
- Leave `ExecutionFrame.child_for_*()` construction paths unchanged; only normalize the post-construction mutation call sites.

### 3. Preserve behavior and prove parity

- Keep existing runtime-control, route-finalization, worklist-event, and branch/fan-in semantics unchanged.
- If helper extraction requires targeted proof beyond the required acceptance batch, extend the existing parity-focused tests instead of creating a new matrix:
  - `tests/unit/test_execution_frame_context_parity.py`
  - `tests/unit/test_branch_group_context_sessions.py`
- Final sign-off remains the user-supplied acceptance command.

## Interface Contract / Invariants

- After a `Context` exists, executable runtime collaborators should mutate runtime state through `Context`, not by calling `_execution_frame.set_*()` directly.
- `ExecutionFrame` remains the backing store and child-frame factory; it is not removed from constructors or tests.
- Worklist selection mutation must continue to:
  - update `ctx.selection(...)` and `ctx.current_worklist`
  - clear only the mutated worklist's entry from `_selection_snapshots`
  - refresh scoped `item_state` and `step_item_state` only when the mutated worklist is the active scoped worklist
  - emit the existing worklist runtime events with unchanged payload shape and ordering
- Branch and fan-in child contexts must keep shared state-cell behavior, preserved request snapshots, and child-local selection caches.

## Validation

- Optional focused preflight if the helper extraction touches branch/worklist behavior:
  - `tests/unit/test_execution_frame_context_parity.py`
  - `tests/unit/test_branch_group_context_sessions.py`
- Required acceptance command:
  - `.venv/bin/python -m pytest tests/runtime/test_provider_policy_emitters.py tests/unit/test_policy.py tests/unit/test_simple_policy.py tests/runtime/test_provider_policy_config.py tests/unit/test_placeholder_refs.py tests/unit/test_simple_surface.py tests/unit/test_inventory.py tests/unit/test_step_plans.py tests/unit/test_route_contracts.py tests/contract/test_branch_result_serialization.py tests/unit/test_runtime_and_discovery_extraction.py tests/contract/engine/test_runtime_controls.py -q`

## Risks

- A partial rewrite could leave one executable path bypassing snapshot invalidation or scoped-state refresh.
  - Control: migrate the direct `set_*` call sites in the files above as one slice and verify both lazy selection resolvers use the same helper.
- Over-centralizing into a generic runtime wrapper would add indirection and make the extraction harder to trace.
  - Control: keep the facade private on `Context` and keep `ExecutionFrame` simple.
- Branch-group child contexts can regress if parent-shared values/state and child-local selections are not preserved together.
  - Control: keep child-frame construction unchanged and normalize only mutation call sites after child creation.

## Compatibility / Rollback

- No intentional behavior break or migration is allowed for this task.
- Roll back as one slice by reverting the new `Context` mutator helpers and the executable call-site rewrites together; do not keep a mixed direct-frame and context-mediated mutation model.
