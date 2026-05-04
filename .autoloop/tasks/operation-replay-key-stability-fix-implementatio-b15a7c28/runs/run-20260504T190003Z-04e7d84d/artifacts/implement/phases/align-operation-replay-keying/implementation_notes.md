# Implementation Notes

- Task ID: operation-replay-key-stability-fix-implementatio-b15a7c28
- Pair: implement
- Phase ID: align-operation-replay-keying
- Phase Directory Key: align-operation-replay-keying
- Phase Title: Align Operation Replay Keying
- Scope: phase-local producer artifact

## Files changed
- Repository source:
  - `autoloop/core/operations.py`
- Phase artifacts:
  - `.../decisions.txt`
  - `.../artifacts/implement/phases/align-operation-replay-keying/implementation_notes.md`
- No source edit was required in `autoloop/core/schema_registry.py`.

## Symbols touched
- Edited in repository source:
  - `_load_replay_store`
- Verified by inspection:
  - `OPERATION_REPLAY_SCHEMA`
  - `_run_operation`
  - `_next_occurrence`
  - `_operation_replay_key`
  - `_operation_fingerprint`
  - `_migrate_operation_replay_store`

## Checklist mapping
- Replay schema version: confirmed `autoloop.operation_replay/v2`.
- Occurrence counter contract: confirmed `_next_occurrence(runtime, operation_kind)` excludes `callsite`.
- Replay key contract: confirmed `_operation_replay_key(runtime, operation_kind, occurrence)` excludes `callsite`.
- Fingerprint contract: confirmed `_run_operation` still computes `callsite_id` and passes it to `_operation_fingerprint`.
- Legacy replay migration: narrowed `_load_replay_store` so only schemaless or explicit `v1` payloads are migrated through `_migrate_operation_replay_store`, which drops `records` and preserves list-shaped `attempts`.
- Helper call-site scope: confirmed repo grep finds `_next_occurrence(...)` and `_operation_replay_key(...)` call sites only in `_run_operation`.
- Validation: focused replay contract tests passed.

## Assumptions
- Using the sibling repo virtualenv interpreter was acceptable because this checkout lacks local `pytest` and `python -m pytest`, while the tests executed against the current workspace root.
- The reviewer-owned finding correctly narrowed the remaining in-scope fix to `_load_replay_store` without requiring broader replay semantics changes or test-file edits.

## Preserved invariants
- `callsite` remains part of the operation fingerprint payload.
- `callsite` remains stored in replay records for diagnostics only.
- Public `llm_call`, `classify_call`, and `execute_step_operation` signatures remain unchanged.
- No legacy compatibility layer was added for pre-v2 replay records.

## Intended behavior changes
- Unsupported future replay schemas now remain hard validation failures instead of being silently discarded.

## Known non-changes
- `autoloop/core/schema_registry.py` remained unchanged at `autoloop.operation_replay/v2`.
- No edits outside `autoloop/core/operations.py` and the required phase artifacts.
- No additional replay-stability mechanisms were introduced.

## Expected side effects
- Explicit `v1` and schemaless replay stores continue to reset cached `records` while preserving list-shaped `attempts`.
- Unsupported replay schema versions now raise a `ValueError` during load instead of being converted to empty v2 payloads.

## Validation performed
- Inspected `autoloop/core/schema_registry.py` and `autoloop/core/operations.py` for the approved invariants.
- Ran repo-wide grep to confirm helper usage is limited to `_run_operation` in source code.
- Exercised `_load_replay_store` directly for schemaless, explicit `v1`, and explicit `v3` payloads.
- Ran:
  - `'../autoloop_v3 (Cópia)/.venv/bin/python' -m pytest tests/contract/test_engine_contracts.py -k operation_replay`
- Results:
  - Schemaless payload migrated to empty v2 store with preserved `attempts`.
  - Explicit `v1` payload migrated to empty v2 store with preserved `attempts`.
  - Explicit `v3` payload raised `ValueError` for unsupported schema.
  - Focused pytest slice: `3 passed, 163 deselected`.

## Deduplication or centralization decisions
- Kept the fix local to `_load_replay_store` so schemaless migration remains centralized in `validate_persisted_schema(...)` and explicit `v1` handling stays as a narrow compatibility bridge.
