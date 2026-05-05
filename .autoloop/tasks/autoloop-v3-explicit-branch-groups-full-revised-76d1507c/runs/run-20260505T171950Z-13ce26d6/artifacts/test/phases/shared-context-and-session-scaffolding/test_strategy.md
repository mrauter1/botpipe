# Test Strategy

- Task ID: autoloop-v3-explicit-branch-groups-full-revised-76d1507c
- Pair: test
- Phase ID: shared-context-and-session-scaffolding
- Phase Directory Key: shared-context-and-session-scaffolding
- Phase Title: Shared Context And Session Scaffolding
- Scope: phase-local producer artifact

## Behavior To Coverage Map
- AC-1 shared state/value cell:
  - `test_branch_context_shares_state_cell_values_and_branch_metadata`
  - Covers shared `StateCell`, shared values mapping, `Context.state` assignment, and `context_runtime(...).set_state(...)`.
- Branch/fan-in metadata surfaces and branch-scoped execution ids:
  - `test_fan_in_context_exposes_metadata_and_branch_execution_ids`
  - Covers `ctx.branch`, `ctx.fan_in`, invalid parent access, and event payload execution-id prefixing.
- AC-2 branch-local session persistence and parent-session determinism:
  - `test_branch_session_store_view_keeps_activation_local_to_branch`
  - `test_engine_session_selection_and_persistence_follow_context_store`
  - `test_engine_hook_snapshot_and_restore_follow_branch_context_store`
  - Covers fresh branch session activation, nested engine selection/persistence via `context._session_store`, and hook snapshot/restore rollback against the branch overlay instead of the parent store.
- Branch-scoped bookkeeping isolation:
  - `test_branch_context_resolves_worklists_locally_without_mutating_parent`
  - Covers child-local worklist resolution, local selection/cache mutation, and parent bookkeeping non-mutation.

## Preserved Invariants Checked
- Parent contexts still reject `ctx.branch` / `ctx.fan_in`.
- Parent active session slots do not change when branch-local fresh sessions are opened, persisted, or hook-restored.
- Branch worklist operations do not mutate parent selection or cache dictionaries.

## Edge Cases / Failure Paths
- Invalid metadata access outside branch/fan-in contexts raises `WorkflowExecutionError`.
- Hook restore returns the branch overlay to its pre-hook active session even after an in-hook session replacement.

## Known Gaps
- No test yet for full branch runtime orchestration, branch result manifests, or fan-in execution because they are out of phase scope.
- No concurrency/locking coverage yet; this phase only establishes deterministic shared references and branch-local session overlays.
