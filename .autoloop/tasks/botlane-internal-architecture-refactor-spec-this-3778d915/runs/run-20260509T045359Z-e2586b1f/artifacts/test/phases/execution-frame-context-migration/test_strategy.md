# Test Strategy

- Task ID: botlane-internal-architecture-refactor-spec-this-3778d915
- Pair: test
- Phase ID: execution-frame-context-migration
- Phase Directory Key: execution-frame-context-migration
- Phase Title: ExecutionFrame Behind Context
- Scope: phase-local producer artifact

## Behavior-To-Test Coverage Map

- `Context` synthesizes an internal `ExecutionFrame` from the existing constructor args.
  Covered by `test_context_synthesizes_execution_frame_and_preserves_default_message_sentinel`.
- Default message sentinel behavior remains distinct from explicit `message=None`.
  Covered by `test_context_synthesizes_execution_frame_and_preserves_default_message_sentinel`.
- `context_runtime(...)` mutators update both frame-backed state and legacy `Context`-visible fields.
  Covered by `test_context_runtime_mutators_update_execution_frame_and_legacy_fields`.
- Frame-backed worklist mutation paths preserve public selection behavior and clear stale selection snapshots.
  Covered by `test_worklist_runtime_mutators_keep_frame_and_public_selection_in_sync`.
- Branch child contexts preserve shared state cell/value semantics while using child frame copies for branch metadata and selection snapshots.
  Covered by `test_branch_child_context_uses_child_frame_and_preserves_shared_state`.
- Fan-in child contexts expose fan-in metadata through the public facade while retaining frame-backed storage.
  Covered by `test_fan_in_child_context_exposes_fan_in_frame_metadata`.

## Preserved Invariants Checked

- `_DEFAULT_MESSAGE` identity remains compatible with engine/runner default-message semantics.
- `Context.state` and `context_runtime(...).set_state(...)` still update the shared `StateCell`.
- Worklist selection reads continue to work through `ctx.selection(...)` and `ctx.current_worklist`.
- Branch child selection snapshot changes remain child-local.

## Edge Cases

- Explicit `message=None` versus sentinel-driven request-file fallback.
- Empty selection-snapshot state after `set_selection(...)`.
- Branch child frame copies share mutable state/value references where prior behavior depended on sharing.

## Failure Paths / Regression Risks Addressed

- Prevent silent divergence between `Context._execution_frame` and legacy private attrs after runtime mutations.
- Prevent regressions where frame-backed worklist updates stop reflecting through the public `Context` worklist facade.
- Prevent regressions where child branch/fan-in contexts lose metadata or stop sharing the parent state cell.

## Stabilization / Flake Notes

- Tests are deterministic and filesystem-local under `tmp_path`.
- No timing, network, subprocess, or ordering-sensitive assertions were added.

## Known Gaps

- This phase-local file does not duplicate broader unchanged contract coverage for worklist operations, branch sessions, or workspace layout; those remain covered by existing suites rerun for regression validation.
