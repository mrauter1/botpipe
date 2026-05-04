# Operation Replay Key Stability Fix

## Scope
- Keep all implementation work confined to `autoloop/core/schema_registry.py` and `autoloop/core/operations.py`.
- Remove `callsite` from the operation replay key and from the occurrence counter key.
- Preserve `callsite` in the operation fingerprint and in stored replay records for mismatch detection and diagnostics.
- Treat legacy operation replay records as incompatible cache data: discard `records`, preserve `attempts`, and read/write only `autoloop.operation_replay/v2`.

## Current Code Read
- `autoloop/core/schema_registry.py` already defines `OPERATION_REPLAY_SCHEMA = "autoloop.operation_replay/v2"`.
- `autoloop/core/operations.py` already shows the target helper signatures and a named replay-store migrator.
- The implementation pass should therefore be verification-first: make only residual alignment edits if any requested invariant is still off, and avoid unrelated churn.

## Implementation Milestone
1. Align replay-key behavior and legacy-store handling in `autoloop/core/operations.py`.
   - `_next_occurrence` must be keyed by `(workflow_name, step_name, step_visit, operation_kind)` only.
   - `_operation_replay_key` must hash `(workflow_name, step_name, step_visit, operation_kind, occurrence_index)` only.
   - `_run_operation` must still compute `callsite_id` and pass it to `_operation_fingerprint`, while using the callsite-free occurrence/key helpers.
   - `_migrate_operation_replay_store` must be a named module-level function that discards legacy `records` and preserves list-shaped `attempts`.
   - `_load_replay_store` must use `_migrate_operation_replay_store` as the `validate_persisted_schema(..., legacy_migrator=...)` hook.

## Interfaces And Invariants
- `_next_occurrence(runtime: OperationRuntime, operation_kind: str) -> int`
- `_operation_replay_key(runtime: OperationRuntime, operation_kind: str, occurrence: int) -> str`
- `_operation_fingerprint(...)` remains unchanged with `callsite` included in the payload.
- Public call surfaces remain unchanged: `llm_call`, `classify_call`, and `execute_step_operation`.
- Replay-key uniqueness after this change relies on the shared per-step, per-operation-kind occurrence counter, not on callsite identity.

## Compatibility, Validation, Rollout
- Compatibility break is intentional and required: existing v1 or schemaless `operation_replay.json` records are not reusable under v2 keys.
- No dual-read or legacy compatibility layer should be added; this task explicitly rejects that complexity.
- Validation should cover:
  - helper signatures and `_run_operation` call sites by inspection/grep,
  - `OPERATION_REPLAY_SCHEMA` value,
  - absence of extra `_next_occurrence` or `_operation_replay_key` call sites outside `_run_operation`,
  - focused runtime coverage with `pytest tests/contract/test_engine_contracts.py -k operation_replay`.
- Rollout should land as one atomic change set across the two files.
- Rollback, if ever required, must revert both files together and treat any v2-generated replay stores as disposable cache artifacts.

## Risk Register
- Counter-key regression: if `callsite` survives in the occurrence counter or if the counter is narrowed incorrectly, same-step operations can collide or diverge from the requested behavior.
- Fingerprint regression: if `callsite` is removed from `_operation_fingerprint`, non-deterministic branch changes could replay the wrong value silently.
- Migration regression: if legacy records are retained, v1 payloads may produce invalid hits under v2 expectations.
- Scope creep: adding broader replay-stability mechanisms such as explicit stable IDs, prompt-only addressing, or extra compatibility code would exceed the request and add technical debt.
