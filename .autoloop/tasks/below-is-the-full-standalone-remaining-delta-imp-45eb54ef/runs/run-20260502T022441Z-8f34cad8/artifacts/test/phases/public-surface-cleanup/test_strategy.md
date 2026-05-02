# Test Strategy

- Task ID: below-is-the-full-standalone-remaining-delta-imp-45eb54ef
- Pair: test
- Phase ID: public-surface-cleanup
- Phase Directory Key: public-surface-cleanup
- Phase Title: Public Surface Cleanup
- Scope: phase-local producer artifact

## Behavior Coverage Map

- Removed declaration/runtime surfaces:
  `tests/unit/test_simple_surface.py`
  Covers fail-fast rejection of removed `on_route`, `outputs`, `review_writes`, and core-step `on_route` keywords.

- Public simple compiler gate:
  `tests/unit/test_simple_surface.py`
  Covers rejection of legacy class-level `on_start`, `on_outcome`, and `on_<step>` handlers on `autoloop.simple.Workflow`.

- Exported public simple workflow regression guard:
  `tests/unit/test_simple_surface.py`
  Covers the nine migrated public simple workflow packages and asserts they no longer fail compilation because of removed legacy class-handler surfaces, while tolerating unrelated out-of-scope validation failures.

- Canonical payload vocabulary and topology surface:
  `tests/unit/test_simple_surface.py`
  `tests/runtime/test_runtime_static_graph.py`
  Covers canonical `writes` / `producer_writes` / `verifier_writes`, absence of compiled `on_route_hook`, and absence of `on_route` in topology payload hooks.

## Preserved Invariants Checked

- Route-local `on_taken` remains the only route-finalization hook surface.
- Public simple `python_step` declarations still require explicit handlers and do not auto-install `on_<step>` aliases.
- Public simple workflows still compile through explicit declarations even after class-level handler removal.

## Edge Cases And Failure Paths

- Removed keyword arguments raise immediately at declaration/construction time.
- Legacy class-level handler workflows fail with the explicit public-simple validation error.
- Migrated exported workflows may still fail for unrelated route-handoff validation; the new regression test asserts only that the removed class-handler failure mode does not return.

## Flake Risk / Stabilization

- Tests are deterministic and import/compile local workflow classes only.
- The exported-workflow regression test avoids asserting full compile success because repo-known out-of-scope route-handoff validation errors remain; it narrows the assertion to the removed-surface failure mode to stay stable and phase-accurate.

## Known Gaps

- No new coverage was added for the out-of-scope route-handoff-to-`PythonStep` validation failures.
- No new runtime history or optimizer tests were added because this phase did not change those behaviors.
