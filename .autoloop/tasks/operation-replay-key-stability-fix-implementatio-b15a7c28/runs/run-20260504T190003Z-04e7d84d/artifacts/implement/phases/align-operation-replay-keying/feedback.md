# Implement ↔ Code Reviewer Feedback

- Task ID: operation-replay-key-stability-fix-implementatio-b15a7c28
- Pair: implement
- Phase ID: align-operation-replay-keying
- Phase Directory Key: align-operation-replay-keying
- Phase Title: Align Operation Replay Keying
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 `blocking` — [autoloop/core/operations.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/operations.py:743): `_load_replay_store()` currently migrates every non-`autoloop.operation_replay/v2` payload by running `_migrate_operation_replay_store()` before schema validation. That is broader than the accepted contract, which only authorizes destructive migration for schemaless or `v1` replay stores. Concrete failure: a future writer emitting `autoloop.operation_replay/v3` is silently downgraded to an empty v2 store, discarding all cached records and diagnostic attempts instead of surfacing an unsupported-schema error. Minimal fix: narrow the pre-validation migration gate to schemaless or explicit `v1` payloads only, then let `validate_persisted_schema()` reject any other schema string.
- IMP-002 `non-blocking` — Re-review outcome: `IMP-001` is resolved in the current source. [autoloop/core/operations.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/operations.py:749) now migrates only explicit `autoloop.operation_replay/v1` payloads before validation; direct checks confirm schemaless and `v1` payloads migrate to empty `v2` stores with preserved `attempts`, while `v3` raises `ValueError`, and the focused replay contract slice still passes.
