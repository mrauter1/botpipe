# Plan

## Goal
Stabilize operation replay keys across incidental source-location changes by removing `callsite` from replay-key generation and occurrence counting, while preserving `callsite` in the fingerprint so warn/fail mismatch behavior still triggers on resume. Because the persisted key shape changes, existing v1 replay records must be discarded when loaded under the new schema.

## Repo Findings
- `_run_operation()` computes `callsite_id` once and currently threads it into `_next_occurrence()`, `_operation_replay_key()`, and `_operation_fingerprint()`.
- `_next_occurrence()` and `_operation_replay_key()` both currently include `callsite`, so line shifts cause key misses instead of fingerprint mismatches.
- `_load_replay_store()` validates immediately after JSON parse, and `validate_persisted_schema()` only invokes `legacy_migrator` when `schema` is missing. Explicit v1 payloads therefore need to be migrated in `_load_replay_store()` before validation.
- Existing replay contract coverage already exercises warn/fail fingerprint mismatch behavior and provider-configuration fingerprinting in `tests/contract/test_engine_contracts.py`.
- No other runtime call sites for `_next_occurrence()` or `_operation_replay_key()` exist outside `_run_operation()`.

## Implementation Plan
### 1. Bump the replay schema
- Change `OPERATION_REPLAY_SCHEMA` in `autoloop/core/schema_registry.py` from `v1` to `v2`.
- Treat this as an intentional persisted-data compatibility break for `operation_replay.json` only; no public API or CLI contract changes are required.

### 2. Remove `callsite` from replay-key allocation only
- Update `_next_occurrence(runtime, operation_kind)` so the counter key is scoped only by workflow, step, visit, and operation kind.
- Update `_operation_replay_key(runtime, operation_kind, occurrence)` so the replay key excludes `callsite`.
- Update `_run_operation()` to call the narrowed helpers while keeping `callsite_id` computation unchanged and still passing `callsite_id` into `_operation_fingerprint()`.
- Keep the persisted replay record’s `"callsite"` field unchanged for human inspection; it is not part of runtime lookup semantics.

### 3. Add explicit v1 replay-store discard migration
- Add a named module-level `_migrate_operation_replay_store()` helper in `autoloop/core/operations.py`.
- The migrator must always emit the current schema, drop all `records`, and preserve `attempts` only when the payload field is list-shaped.
- In `_load_replay_store()`, detect any parsed payload whose schema is absent or not equal to `OPERATION_REPLAY_SCHEMA` and replace it with `_migrate_operation_replay_store(payload)` before calling `validate_persisted_schema()`.
- Still pass `_migrate_operation_replay_store` as the named `legacy_migrator` to `validate_persisted_schema()` so schemaless payloads remain accepted through the same migration rule.
- Preserve the existing non-dict and missing-file fallback behavior.

## Interfaces And Invariants
- `_next_occurrence()` must end with exactly two parameters: `runtime` and `operation_kind`.
- `_operation_replay_key()` must end with exactly three parameters: `runtime`, `operation_kind`, and `occurrence`.
- `callsite` remains part of `_operation_fingerprint()` and must still be computed in `_run_operation()`.
- Within a single step execution, every call of the same `operation_kind` must receive a unique monotonically increasing occurrence index regardless of callsite.
- `operation_replay.json` records written under v1 are intentionally non-reusable under v2; `attempts` remain diagnostic-only and may be retained.
- The known limitation from the request remains unchanged: inserting or reordering same-kind operations earlier in a step still shifts occurrence indices and causes silent misses rather than mismatches.

## Compatibility / Behavior
- Intentional behavior change: line-number shifts, function renames, and file moves for otherwise equivalent operations should now produce replay-key hits followed by fingerprint mismatch handling instead of silent cache misses.
- Intentional compatibility break: existing v1 `operation_replay.json` records are discarded on load and repopulated under v2 keys.
- Unchanged behavior: prompt/configuration changes still mismatch through the fingerprint, and public signatures for `llm_call`, `classify_call`, and `execute_step_operation` do not change.
- Shared schema-validator semantics should not be widened; the v1 fallback stays local to `_load_replay_store()`.

## Validation
- Verify the helper signatures and `_run_operation()` call sites match the requested post-change shapes.
- Run `rg -n "_next_occurrence\\(|_operation_replay_key\\(" .` and confirm the only runtime call sites remain inside `autoloop/core/operations.py::_run_operation()`.
- Run the existing replay contract tests in `tests/contract/test_engine_contracts.py` covering fingerprint mismatch warn/fail behavior and provider-configuration mismatches.
- Seed or simulate a v1 replay-store payload and confirm `_load_replay_store()` discards `records`, preserves list-shaped `attempts`, and returns a v2-shaped store instead of raising on explicit v1 schema.

## Risk Register
- Removing `callsite` from the replay key without also removing it from the occurrence counter would create collisions between multiple callsites of the same operation kind in one step.
  Mitigation: treat helper signature changes and `_run_operation()` call-site updates as one atomic slice.
- Applying migration only through `validate_persisted_schema()` would still reject explicit v1 payloads.
  Mitigation: perform the non-v2 discard migration in `_load_replay_store()` before validation and keep the named migrator for schemaless payloads.
- A partial implementation could accidentally remove `callsite` from the fingerprint, weakening mismatch detection.
  Mitigation: preserve `_operation_fingerprint()` inputs and record this invariant explicitly in validation.

## Rollback
- Revert the schema bump, helper signature changes, and `_load_replay_store()` migration behavior together; do not keep mixed v1/v2 semantics.
- If the v1 discard path behaves unexpectedly, fall back to the previous v1 schema and key structure as a single rollback rather than widening shared schema validation behavior.
