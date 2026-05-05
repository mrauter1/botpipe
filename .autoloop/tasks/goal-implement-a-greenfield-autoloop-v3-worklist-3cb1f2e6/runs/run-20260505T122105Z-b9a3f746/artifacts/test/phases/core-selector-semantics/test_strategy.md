# Test Strategy

- Task ID: goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6
- Pair: test
- Phase ID: core-selector-semantics
- Phase Directory Key: core-selector-semantics
- Phase Title: Extend generic worklist selectors
- Scope: phase-local producer artifact

## Behavior To Coverage Map
- Core selector mode semantics:
  `tests/unit/test_worklist_selectors.py`
  Covers `all`, `single`, `up_to`, `from_to`, inclusive bounds, default implicit selection, explicit-selection tracking, invalid range, unknown ids, and invalid mode/default/allowed-mode declarations.
- Intentional compatibility break for selector params under `mode=all`:
  `tests/unit/test_worklist_selectors.py`
  Asserts item/start/end selector params now fail under `all`.
  `tests/unit/test_primitives_and_stores.py`
  Existing mutable-source cache test was updated to opt into `single` explicitly instead of preserving the old subset-on-all behavior.
- Progress worklist status policy and canonical board shape:
  `tests/unit/test_stdlib_progress_worklists.py`
  Covers default status vocabulary, opt-in extra statuses, skipped policy, alias normalization, canonical `items/id/title/status`, missing collection/item field failures, duplicate ids, fallback writing, and missing-artifact failure.
- Progress worklist persistence invariants:
  `tests/unit/test_stdlib_progress_worklists.py`
  Covers status-only save updates, order preservation, model-backed save preserving sparse non-status payloads, and `dir_key` fallback parity for both safe and unsafe item ids.
- Runtime integration for generated progress worklists:
  `tests/runtime/test_progress_worklists.py`
  Covers default `all`, explicit `single`, `up_to`, `from_to`, invalid range failure, persisted `completed` statuses, and skipped-status rejection/acceptance by policy.

## Preserved Invariants Checked
- Sources still own ordered item materialization and persistence; core owns selection behavior.
- Artifact-backed generated progress worklists expose canonical artifact naming and selector parameter naming.
- Status persistence does not reorder items or mutate unrelated payload fields during save.
- Progress worklist items preserve per-item path semantics through stable `dir_key` fallback behavior.

## Edge Cases And Failure Paths
- Whitespace or absent selector params fall back to implicit selection behavior.
- Unknown selector ids surface known ids in the failure.
- `from_to` start-after-end fails clearly.
- Missing `items`, non-object items, missing `id`/`title`, duplicate ids, and unsupported statuses fail deterministically.
- Unsafe item ids use the same hex-encoded `dir_key` fallback contract as generic artifact-backed worklists.

## Flake Risks / Stabilization
- Tests are filesystem-local, deterministic, and avoid timing/network dependencies.
- Runtime progress tests clear the workflow compiler cache before building same-name local workflow classes to prevent stale compiled handlers from polluting selection/status-policy coverage.

## Known Gaps
- Broader unrelated workspace/catalog loader failures remain outside this phase-local selector/progress test slice.
