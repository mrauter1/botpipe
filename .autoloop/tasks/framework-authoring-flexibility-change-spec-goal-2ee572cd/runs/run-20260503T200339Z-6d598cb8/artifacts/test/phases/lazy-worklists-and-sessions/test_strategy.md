# Test Strategy

- Task ID: framework-authoring-flexibility-change-spec-goal-2ee572cd
- Pair: test
- Phase ID: lazy-worklists-and-sessions
- Phase Directory Key: lazy-worklists-and-sessions
- Phase Title: Lazy Worklists And Sessions
- Scope: phase-local producer artifact

## Coverage map

- AC-1 `Declared artifact-backed worklists compile/start without backing data`
  - `test_unused_artifact_backed_worklist_does_not_load_on_non_scoped_path`
  - Preserved invariant: fresh runs do not eagerly touch unrelated worklist sources.

- AC-2 `First scoped or explicit use materializes only the referenced worklist and emits a resolution event`
  - Scoped path: `test_artifact_backed_worklist_materializes_after_runtime_creates_source`
  - Explicit context path: `test_context_ensure_selection_lazily_materializes_missing_worklist`
  - Explicit one-of-many path: `test_context_ensure_selection_only_materializes_requested_worklist`
  - Artifact placeholder path: `test_artifact_template_resolution_lazily_materializes_worklist_placeholders`
  - Preserved invariant: existing placeholder rendering still works via `test_artifact_template_resolution_supports_worklist_placeholders`.

- AC-3 `Work-item continuity uses stable worklist:item keys and fails only when no current item exists`
  - Stable/resume path: `test_work_item_session_resume_uses_dir_key_based_key_and_reuses_session`
  - Failure path: `test_non_scoped_work_item_session_fails_when_no_current_item_exists`
  - Adjacent scoped behavior: `test_scoped_step_advances_worklist_items_and_uses_item_placeholders`

## Restore / checkpoint coverage

- Sparse restore plus later lazy materialization:
  - `test_resume_restores_materialized_worklists_and_lazily_materializes_unused_ones`
- Scoped item-state compatibility after lazy selection:
  - `test_scoped_item_state_and_step_item_state_resume_from_checkpoint`

## Failure and edge cases

- Missing artifact-backed source fails at first scoped use:
  - `test_missing_artifact_backed_worklist_fails_at_first_scoped_use`
- Duplicate IDs still fail when a scoped step first materializes the worklist:
  - `test_artifact_backed_worklist_duplicate_ids_fail_before_scoped_execution`

## Stabilization notes

- Added tests are deterministic, in-process, and filesystem-local.
- No timing, network, or ordering assumptions were introduced.
- Worklist materialization assertions use direct call logs or runtime-event capture rather than incidental side effects.

## Known gaps

- `ctx.worklist(...).refresh()` after an initially lazy selection is still covered indirectly by existing refresh tests, not by a new phase-specific contract test.
- This phase does not cover typed effects, validation helpers, or inspection payload behavior by design.
