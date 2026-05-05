# Implementation Notes

- Task ID: autoloop-v3-explicit-branch-groups-full-revised-76d1507c
- Pair: implement
- Phase ID: shared-context-and-session-scaffolding
- Phase Directory Key: shared-context-and-session-scaffolding
- Phase Title: Shared Context And Session Scaffolding
- Scope: phase-local producer artifact

## Files Changed
- `autoloop/core/context.py`
- `autoloop/core/engine.py`
- `autoloop/core/branch_groups/__init__.py`
- `autoloop/core/branch_groups/context.py`
- `autoloop/core/branch_groups/sessions.py`
- `tests/unit/test_branch_group_context_sessions.py`

## Symbols Touched
- `Context`
- `_ContextRuntime`
- `Engine._snapshot_hook_context`
- `Engine._restore_hook_context`
- `Engine._select_session`
- `Engine._persist_session`
- `Engine._resolve_pair_review_session`
- `StateCell`
- `BranchMetadata`
- `FanInMetadata`
- `_create_child_context`
- `_inherit_child_runtime_bookkeeping`
- `_child_worklist_selection_resolver`
- `create_branch_context`
- `create_fan_in_context`
- `BranchSessionStoreView`

## Checklist Mapping
- Plan milestone 2 / shared state cell:
  - Added `StateCell` and wired `Context.state` plus `context_runtime(...).set_state(...)` through the shared cell.
- Plan milestone 2 / branch and fan-in metadata:
  - Added optional `ctx.branch` and `ctx.fan_in` surfaces with runtime-only availability errors outside valid contexts.
- Plan milestone 2 / branch-local session store view:
  - Added `BranchSessionStoreView` overlay with local active-slot tracking and merged snapshots.
- Plan milestone 2 / context-bound session selection and persistence:
  - Rewired nested engine session snapshot/select/persist paths to use `context._session_store`.
- Plan milestone 2 / branch-scoped execution id scaffolding:
  - Added branch execution-id helper plumbing and branch-context factories that set a branch-scoped execution-id prefix.
- Plan milestone 2 / branch-scoped bookkeeping:
  - Child branch/fan-in contexts now clone selection/snapshot/cache bookkeeping by value and resolve worklists through a child-local lazy resolver instead of reusing parent bookkeeping closures.
- Plan milestone 4 / validation coverage for this slice:
  - Added focused unit coverage for shared state/value behavior, fan-in metadata access, branch-local session activation, child-local worklist resolution, and context-bound engine session persistence.

## Assumptions
- Branch runtime will create dedicated child contexts rather than mutating the parent context object in place.
- Branch visit counts will continue to come from the step-state store, so execution-id overrides only need to supply the branch/group prefix.

## Preserved Invariants
- Ordinary non-branch contexts still expose the same public API and continue using their configured session store.
- Parent session-store active-slot state is unchanged by branch-local session activation in the overlay store.
- Existing top-level engine checkpoint/session behavior remains owned by `Engine.session_store`.

## Intended Behavior Changes
- Context state replacement now updates a shared `StateCell`, enabling multiple related contexts to observe the same state object replacement and diagnostic version.
- Branch/fan-in runtime contexts can expose `ctx.branch` / `ctx.fan_in` and emit branch-scoped execution ids without changing ordinary step execution ids.
- Nested engine step execution now honors a context-supplied session-store overlay for snapshot, selection, verifier session resolution, and provider-session persistence.

## Known Non-Changes
- No branch scheduler, manifest generation, fan-in orchestration, or branch result routing was implemented in this phase.
- No shared-values replacement cell or concurrency locking was added yet; branch contexts still share one mutable values mapping by reference.
- No checkpoint schema changes were made for branch-local session overlays in this phase.
- Branch child contexts now resolve and isolate worklist selections locally, but full scoped item-state remapping across branch-specific item stores still belongs to the later branch runtime orchestration phase.

## Expected Side Effects
- Any future branch runtime using `create_branch_context(...)` can share parent state/value references while keeping provider-session activation local to that branch store view.
- Branch/fan-in contexts can now load and advance worklist selections without mutating the parent context’s selection dictionaries or cache.
- Runtime event payloads can now carry a branch-scoped `step_execution_id` when a child context sets an execution-id override.

## Validation Performed
- `.venv/bin/python -m pytest -q tests/unit/test_branch_group_context_sessions.py`
- `.venv/bin/python -m pytest -q tests/unit/test_simple_surface.py -k 'branch_group or fan_in or provider_backed_branch'`
- `.venv/bin/python -m pytest -q tests/contract/test_engine_contracts.py -k 'llm_retry_reuses_pre_step_session_not_failed_attempt_session or pair_retry_reuses_pre_step_session_but_keeps_attempt_local_session_chain or on_start_opens_sessions_before_execution or declared_session_auto_opens_without_on_start or provider_steps_without_explicit_session_use_default_session'`

## Deduplication / Centralization
- Shared state replacement logic stays centralized in `Context` / `context_runtime(...)` via `StateCell` rather than duplicating branch-specific state setters elsewhere.
- Branch session isolation is centralized in `BranchSessionStoreView`, with engine session plumbing changed only at the existing context/session-store seam.
