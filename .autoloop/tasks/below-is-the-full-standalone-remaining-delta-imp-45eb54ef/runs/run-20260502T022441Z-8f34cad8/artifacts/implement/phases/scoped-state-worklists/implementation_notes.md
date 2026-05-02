# Implementation Notes

- Task ID: below-is-the-full-standalone-remaining-delta-imp-45eb54ef
- Pair: implement
- Phase ID: scoped-state-worklists
- Phase Directory Key: scoped-state-worklists
- Phase Title: Scoped State And Worklists
- Scope: phase-local producer artifact

## Files changed
- `autoloop/core/step_state.py`
- `autoloop/core/worklists.py`
- `autoloop/core/context.py`
- `autoloop/core/engine.py`
- `autoloop/core/engine_collaborators.py`
- `autoloop/core/routes.py`
- `autoloop/core/compiler.py`
- `autoloop/core/lowering.py`
- `autoloop/core/discovery.py`
- `autoloop/core/topology.py`
- `autoloop/core/__init__.py`
- `autoloop/runtime/static_graph.py`
- `tests/unit/test_primitives_and_stores.py`
- `tests/unit/test_simple_surface.py`
- `tests/unit/test_validation.py`
- `tests/contract/test_engine_contracts.py`
- `tests/runtime/test_runtime_static_graph.py`
- Deleted: `autoloop/core/effects.py`

## Symbols touched
- `WorkItemRuntimeState`
- `build_worklist_item_state_model(...)`
- `Worklist.runtime_item_state_model`
- `WorklistRuntimeView`
- `Worklist.reload_items(...)`
- `Worklist._load_items_snapshot(...)`
- `Context.item_state`
- `Context.step_item_state`
- `Context.worklist(...)`
- `Context.worklists`
- `Context.current_worklist`
- `Engine._ensure_item_state_store(...)`
- `Engine._update_item_runtime_state_on_entry(...)`
- `Engine._update_final_item_runtime_state(...)`
- `Engine._sync_context_scoped_state_after_worklist_selection_change(...)`
- `Engine._normalize_direct_runtime_control(...)`
- `HookRunner.run_before(...)`
- `HookRunner.run_after(...)`
- `RouteFinalizer.finalize(...)`

## Checklist mapping
- Plan milestone 3, scoped-state guarantee: completed via built-in `ctx.step_item_state` exposure and built-in/runtime-composed `ctx.item_state`.
- Plan milestone 3, worklist helper surface: completed via `ctx.worklist(name)`, `ctx.worklists.<name>`, `ctx.current_worklist`, and `WorklistRuntimeView`.
- Plan milestone 3, helper tracing/checkpointing: completed via context-bound selection sync, runtime events, and checkpoint-visible helper mutations.
- Plan milestone 3, route-effect removal after parity: completed by deleting `effects=`/compiled effect state/engine execution paths after converting coverage to `on_taken` helper flows.

## Assumptions
- The clarified branch for this phase is the built-in runtime-owned `ctx.item_state` model for active scoped items.
- Existing compiled route summaries remain part of `ctx.route`; this phase does not strip route summary metadata from hook context.

## Preserved invariants
- Built-in scoped runtime fields remain read-only from author code; only declared custom item-state fields remain mutable.
- Worklist helpers do not auto-route on exhaustion or status change.
- Helper mutations remain visible to checkpoint persistence and do not roll back automatically on later failures.
- Worklist cache entries remain full-source snapshots rather than shrinking to the current selected subset.
- Finalized route state continues to update only on successful route-based finalization; direct controls do not fabricate `last_route`.

## Intended behavior changes
- Scoped steps now always expose `ctx.step_item_state`, even without a custom declared step-item model.
- Active scoped items now always expose built-in `ctx.item_state.status`, `ctx.item_state.last_step`, and `ctx.item_state.last_route`.
- Public route-effect authoring is removed; equivalent workflows use `Route.to(..., on_taken=...)` plus worklist helpers.
- Invalid direct controls from hooks are checkpointed as structured `runtime_control_validation` failures with current mutated state preserved.

## Known non-changes
- This phase does not perform the broader structured-exception cleanup that removes dynamic metadata attachment/readback across the engine.
- No implicit helper-driven routing aliases or compatibility shims were added for removed route effects.

## Expected side effects
- Static graph/runtime payloads now expose runtime-composed worklist item-state metadata instead of the pre-helper item-state surface.
- `ctx.current_worklist.refresh()` and `validate()` now force a source reload, so mutable/artifact-backed worklists pick up backing-store changes even after earlier helper mutations populated the cache.
- Repositories that track generated `.pyc` files will show validation-time bytecode churn alongside the source edits.

## Validation performed
- `./.venv/bin/pytest -q tests/unit/test_primitives_and_stores.py tests/unit/test_simple_surface.py tests/unit/test_validation.py tests/contract/test_engine_contracts.py tests/runtime/test_runtime_static_graph.py`
  Result: `302 passed`

## Deduplication / centralization
- Built-in item-state composition is centralized in `step_state.py` and reused by `Worklist`.
- Worklist mutation behavior is centralized in `WorklistRuntimeView` and context sync helpers instead of route-effect execution branches.
- Cached-load versus forced-reload semantics are centralized in `Worklist._load_items_snapshot(...)` so `load_items()`, `refresh()`, validation, and mutable-status updates stay consistent.
- Direct-control validation failure annotation is centralized in `Engine._normalize_direct_runtime_control(...)`.
