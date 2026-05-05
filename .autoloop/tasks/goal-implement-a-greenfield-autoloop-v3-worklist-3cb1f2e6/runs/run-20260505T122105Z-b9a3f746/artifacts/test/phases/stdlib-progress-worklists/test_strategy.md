# Test Strategy

- Task ID: goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6
- Pair: test
- Phase ID: stdlib-progress-worklists
- Phase Directory Key: stdlib-progress-worklists
- Phase Title: Add canonical progress JSON worklists
- Scope: phase-local producer artifact

## Behavior-to-test coverage map
- AC-1 default factory conventions:
  `test_progress_artifact_worklist_uses_default_artifact_path`
  `test_progress_artifact_worklist_uses_default_selector_names`
- AC-2 default status vocabulary and opt-in extras:
  `test_work_status_policy_default_statuses_are_minimal`
  `test_work_status_policy_supports_extra_statuses`
  `test_work_status_policy_can_enable_skipped`
  `test_work_status_policy_normalizes_aliases`
  `test_work_status_policy_rejects_unknown_status`
- AC-3 canonical load/save/fallback persistence:
  `test_progress_source_loads_canonical_items_collection`
  `test_progress_source_validates_with_pydantic_model`
  `test_progress_source_writes_fallback_when_missing`
  `test_progress_source_save_updates_status_only`
  `test_progress_source_save_with_model_preserves_non_status_fields`
  `test_progress_source_save_preserves_order`

## Preserved invariants checked
- Canonical shape remains fixed to top-level `items` with `id` / `title` / `status`.
- Selector naming and mode behavior remain aligned with the core-selector phase via `tests/unit/test_worklist_selectors.py`.
- Runtime persistence still completes selected items and writes normalized statuses back to the artifact in `tests/runtime/test_progress_worklists.py`.

## Edge cases covered
- Missing status defaults to `planned`.
- Unsafe item ids still derive safe `dir_key` values.
- `skipped` is rejected by default and accepted only under `SKIPPABLE_WORK_STATUS_POLICY`.
- Duplicate fallback ids now fail before any artifact write in both:
  `test_progress_source_rejects_duplicate_ids_in_fallback_before_write`
  `test_progress_source_load_rejects_duplicate_ids_in_fallback_before_write`

## Failure paths covered
- Missing `items`, non-object items, missing `id`, missing `title`, duplicate ids, unsupported statuses, and missing artifact without fallback.
- Invalid selector params and invalid ordered ranges remain covered in `tests/unit/test_worklist_selectors.py`.
- Runtime invalid range failure remains covered in `test_progress_worklist_invalid_range_fails_clearly`.

## Stabilization approach
- All tests use temporary filesystem state, in-memory stores, and deterministic scripted provider outputs.
- No network, wall-clock timing, or nondeterministic ordering dependencies were introduced.

## Known gaps
- Broader stdlib/workspace suites remain out of phase scope; this phase validates only the focused selector/progress/runtime surfaces relevant to canonical progress worklists.
