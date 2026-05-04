# Implementation Notes

- Task ID: operation-replay-key-stability-fix-implementatio-b15a7c28
- Pair: implement
- Phase ID: align-operation-replay-keying
- Phase Directory Key: align-operation-replay-keying
- Phase Title: Align Operation Replay Keying
- Scope: phase-local producer artifact

## Files changed
- Phase artifacts only:
  - `.../decisions.txt`
  - `.../artifacts/implement/phases/align-operation-replay-keying/implementation_notes.md`
- No source-file edits were required in `autoloop/core/schema_registry.py` or `autoloop/core/operations.py`.

## Symbols touched
- None in repository source.
- Verified by inspection:
  - `OPERATION_REPLAY_SCHEMA`
  - `_run_operation`
  - `_next_occurrence`
  - `_operation_replay_key`
  - `_operation_fingerprint`
  - `_migrate_operation_replay_store`
  - `_load_replay_store`

## Checklist mapping
- Replay schema version: confirmed `autoloop.operation_replay/v2`.
- Occurrence counter contract: confirmed `_next_occurrence(runtime, operation_kind)` excludes `callsite`.
- Replay key contract: confirmed `_operation_replay_key(runtime, operation_kind, occurrence)` excludes `callsite`.
- Fingerprint contract: confirmed `_run_operation` still computes `callsite_id` and passes it to `_operation_fingerprint`.
- Legacy replay migration: confirmed named `_migrate_operation_replay_store` drops `records` and preserves list-shaped `attempts`.
- Helper call-site scope: confirmed repo grep finds `_next_occurrence(...)` and `_operation_replay_key(...)` call sites only in `_run_operation`.
- Validation: focused replay contract tests passed.

## Assumptions
- The accepted plan's verification-first note is authoritative: source was allowed to remain unchanged when already aligned with the requested behavior.
- Using the sibling repo virtualenv interpreter was acceptable because this checkout lacks local `pytest` and `python -m pytest`, while the tests executed against the current workspace root.

## Preserved invariants
- `callsite` remains part of the operation fingerprint payload.
- `callsite` remains stored in replay records for diagnostics only.
- Public `llm_call`, `classify_call`, and `execute_step_operation` signatures remain unchanged.
- No legacy compatibility layer was added for pre-v2 replay records.

## Intended behavior changes
- None introduced in this turn; requested replay-key behavior was already present in source on entry.

## Known non-changes
- No edits outside phase artifacts.
- No additional replay-stability mechanisms were introduced.

## Expected side effects
- None beyond artifact updates documenting verification results.

## Validation performed
- Inspected `autoloop/core/schema_registry.py` and `autoloop/core/operations.py` for the approved invariants.
- Ran repo-wide grep to confirm helper usage is limited to `_run_operation` in source code.
- Ran:
  - `'../autoloop_v3 (Cópia)/.venv/bin/python' -m pytest tests/contract/test_engine_contracts.py -k operation_replay`
- Result: `3 passed, 163 deselected`.

## Deduplication or centralization decisions
- None; no source changes were necessary.
