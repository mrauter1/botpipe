# Implementation Notes

- Task ID: operation-replay-key-stability-fix-implementatio-543f850c
- Pair: implement
- Phase ID: stabilize-operation-replay-keys
- Phase Directory Key: stabilize-operation-replay-keys
- Phase Title: Stabilize Operation Replay Keys
- Scope: phase-local producer artifact

## Files changed
- `autoloop/core/schema_registry.py`
- `autoloop/core/operations.py`

## Symbols touched
- `OPERATION_REPLAY_SCHEMA`
- `_run_operation`
- `_operation_replay_key`
- `_next_occurrence`
- `_migrate_operation_replay_store`
- `_load_replay_store`

## Checklist mapping
- Plan item 1: completed by bumping `OPERATION_REPLAY_SCHEMA` from `v1` to `v2`.
- Plan item 2: completed by removing `callsite` from occurrence counting and replay-key payloads, while leaving fingerprint generation unchanged.
- Plan item 3: completed by adding `_migrate_operation_replay_store()` and pre-validating any non-`v2` replay payload through that migrator inside `_load_replay_store()`.
- Plan item 4: partially completed with static validation and grep checks; executable contract tests were not runnable in this environment because `pytest` and import-time dependencies were unavailable.

## Assumptions
- The approved clarification remains authoritative: explicit `v1` replay stores must be discarded inside `_load_replay_store()` before schema validation rather than by widening `validate_persisted_schema()`.

## Preserved invariants
- `callsite_id` is still computed in `_run_operation()` and still passed to `_operation_fingerprint()`.
- Stored replay records still include `"callsite"` for human inspection only.
- Replay-key uniqueness remains scoped by workflow, step, visit, operation kind, and monotonically increasing occurrence index.
- Public helper signatures such as `llm_call`, `classify_call`, and `execute_step_operation` remain unchanged.

## Intended behavior changes
- Operation replay keys no longer change when only the callsite string changes, so matching executions now hit the replay record and fall through to fingerprint mismatch handling.
- Existing `operation_replay/v1` records are intentionally discarded on load; list-shaped `attempts` history is preserved and repopulation occurs under `v2`.

## Known non-changes
- `_operation_fingerprint()` still includes `callsite`.
- `_discover_callsite()` is unchanged.
- Structural edits that insert, remove, or reorder same-kind operations earlier in a step still shift occurrence indices and can produce silent misses.

## Expected side effects
- First resume against a persisted `v1` replay store will re-run operations and rewrite the store under `v2`.

## Validation performed
- `python3 -m py_compile autoloop/core/operations.py autoloop/core/schema_registry.py`
- Static AST/text checks confirmed:
  - `_next_occurrence(runtime, operation_kind)`
  - `_operation_replay_key(runtime, operation_kind, occurrence)`
  - `callsite_id` is still computed and passed to `_operation_fingerprint()`
  - `_load_replay_store()` pre-migrates any non-`v2` payload and passes `_migrate_operation_replay_store` to `validate_persisted_schema()`
  - `OPERATION_REPLAY_SCHEMA == "autoloop.operation_replay/v2"`
- `rg -n "_next_occurrence\\(|_operation_replay_key\\(" autoloop tests -g '*.py'` confirmed there are no other Python call sites outside `autoloop/core/operations.py`.
- Attempted but unavailable in this environment:
  - `pytest -q ...` failed because `pytest` is not installed.
  - Import-based `python3` checks failed because `pydantic` is not installed.

## Deduplication / centralization
- Kept explicit v1/non-v2 replay discard logic local to `_load_replay_store()` instead of widening shared schema validation semantics.
