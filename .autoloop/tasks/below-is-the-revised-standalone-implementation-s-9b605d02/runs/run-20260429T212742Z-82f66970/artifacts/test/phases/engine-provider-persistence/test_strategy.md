# Test Strategy

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: test
- Phase ID: engine-provider-persistence
- Phase Directory Key: engine-provider-persistence
- Phase Title: Runtime Contract Cleanup
- Scope: phase-local producer artifact

## Behavior-to-Test Coverage Map

- AC-1 canonical runtime/provider/topology contract
  - `tests/unit/test_provider_boundary_core.py`
  - `tests/runtime/test_runtime_static_graph.py`
  - `tests/runtime/test_runtime_tracing.py`
  - `tests/runtime/test_runtime_git_tracking.py`
  - Covers canonical `FINISH`, canonical provider turn kinds, canonical schema ids, and canonical artifact/write field names in emitted runtime payloads.
- AC-2 legacy persisted terminal/session normalization
  - `tests/runtime/test_compatibility_runtime.py`
  - Covers legacy run-session rebinding from `default`/slot-bound keys to canonical `global` plus active `run_id`.
  - Covers legacy `active_scopes` normalization when no `active_keys_by_slot` exists.
  - Covers preservation of literal `"default"` values for non-run `explicit_key` and `explicit_scope` session identities.
  - Covers filesystem resume loading of legacy global-session bindings and legacy active-scope-only checkpoint payloads.
- AC-3 runtime-owned git tracking and centralized schema ids
  - `tests/runtime/test_runtime_git_tracking.py`
  - `tests/runtime/test_runtime_tracing.py`
  - Covers runtime-config-driven git tracking behavior and schema-registry-backed payload ids.

## Preserved Invariants Checked

- Reader-side migration stays narrow: only persisted legacy run/session payloads are normalized.
- Non-run explicit session identities are not rewritten when their literal value is `"default"`.
- Canonical payload writers continue emitting `writes` / `required_writes` and `FINISH`, not legacy names.

## Edge Cases and Failure Paths

- Legacy checkpoint payloads with `active_scopes` but no `active_keys_by_slot`.
- Legacy default-slot bindings that must rebind to the current `run_id` on resume.
- Compatibility path where a session payload exists but lacks a resumable canonical `session_id`.

## Known Gaps

- No full-repo suite rerun in this phase artifact; coverage remains focused on the changed runtime/provider/persistence surfaces.
- Out-of-phase capability/optimizer consumer migration is intentionally not asserted here.
