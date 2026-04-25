# Test Strategy

- Task ID: recursive-framework-evolution-20260425t013735-bootstrap
- Pair: test
- Phase ID: session-continuity
- Phase Directory Key: session-continuity
- Phase Title: Session Continuity Model
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- AC-07 default-session invariant
  Covered by `tests/contract/test_engine_contracts.py` for fresh engine startup on system-only workflows and provider-owned steps without explicit sessions.
  Covered by `tests/runtime/test_compatibility_runtime.py` for filesystem-backed package execution persisting `sessions/default.json`.

- AC-08 continuity/override stability
  Covered by `tests/unit/test_primitives_and_stores.py` for backward-compatible `ctx.open_session(..., scope=...)`, positional scope, explicit key, and legacy direct-restore reopening.
  Covered by `tests/contract/test_engine_contracts.py` for explicit scope switching and legacy global checkpoint resume through the engine.
  Covered by `tests/runtime/test_compatibility_runtime.py` for filesystem checkpoint loading of legacy `active_scopes` and filesystem-backed resume normalization of legacy global bindings.

## Preserved Invariants Checked

- `ctx.open_session(session)`, `ctx.open_session(session, scope="x")`, and positional scope remain valid.
- Provider-owned steps without explicit sessions reuse the implicit `default` slot.
- Declared task continuity still resolves to task-scoped keys.
- Legacy session payloads that only expose the removed continuation field remain non-resumable rather than being silently aliased.

## Edge Cases And Failure Paths

- Fresh system-only runs still create a default session despite never hitting a provider step.
- Legacy `scope=None` snapshots reopen the same provider conversation instead of rebinding to a fresh run-global key.
- Filesystem checkpoint payloads with legacy `active_scopes` but no `active_keys_by_slot` still load deterministically.

## Stabilization Notes

- All added coverage is deterministic and uses `ScriptedLLMProvider`, temporary filesystem workspaces, and direct JSON checkpoint fixtures.
- No network, wall-clock timing, or ordering-sensitive assertions were introduced.

## Known Gaps

- Work-item continuity remains intentionally uncovered here because worklist runtime behavior is out of phase.
- Full end-to-end runner resume coverage for every continuity domain is deferred; this phase covers run-global/task/default semantics and legacy-snapshot compatibility only.
