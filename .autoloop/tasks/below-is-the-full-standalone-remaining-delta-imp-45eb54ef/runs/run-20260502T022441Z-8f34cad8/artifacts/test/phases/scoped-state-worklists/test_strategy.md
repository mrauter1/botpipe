# Test Strategy

- Task ID: below-is-the-full-standalone-remaining-delta-imp-45eb54ef
- Pair: test
- Phase ID: scoped-state-worklists
- Phase Directory Key: scoped-state-worklists
- Phase Title: Scoped State And Worklists
- Scope: phase-local producer artifact

## Behavior-to-test coverage map
- AC-1 scoped `ctx.step_item_state` availability:
  covered by `tests/unit/test_simple_surface.py` and `tests/contract/test_engine_contracts.py` resume/runtime assertions that access built-in step-item fields without requiring a custom declared model.
- AC-2 built-in `ctx.item_state` surface and read-only runtime fields:
  covered by `tests/unit/test_simple_surface.py` read-only/runtime-field tests and scoped resume tests asserting built-in `status`, `last_step`, and `last_route` alongside mutable custom fields.
- AC-3 worklist helper mutation semantics:
  covered by `tests/unit/test_primitives_and_stores.py` for `advance`, `advance_or`, runtime event emission, mutable-source status updates, forced refresh reloads, validation reloads, and refresh failure when a selected item disappears.
- AC-4 route-effect removal after helper parity:
  covered by `tests/unit/test_validation.py` fail-fast route-effect rejection and `tests/contract/test_engine_contracts.py` helper-driven `on_taken` parity flows.

## Preserved invariants checked
- Helpers mutate selection/status only and do not auto-route.
- Built-in item/step-item runtime fields remain read-only while custom fields stay mutable.
- Mutable-source helper updates do not collapse the cache to the selected subset.
- Refresh and helper validation bypass stale cache entries and observe backing-source changes.

## Edge cases
- Mutable source changes the selected item payload/title before `refresh()`.
- Mutable source removes the selected item before `validation_error()` or `refresh()`.
- Explicit single-item selection updates status while preserving the cached full-source snapshot.

## Failure paths
- `refresh()` raises when a previously selected item no longer exists in the reloaded source.
- `validation_error()` reports missing selected ids after a forced reload.
- Route effects remain rejected on the public authoring path.

## Flake risks and stabilization
- No timing/network coverage was added.
- New worklist-helper tests use in-memory sources and direct source mutation to keep ordering and reload behavior deterministic.

## Known gaps
- This phase does not broaden into optimizer/history assertions beyond the existing scoped-state and helper regression surfaces.
