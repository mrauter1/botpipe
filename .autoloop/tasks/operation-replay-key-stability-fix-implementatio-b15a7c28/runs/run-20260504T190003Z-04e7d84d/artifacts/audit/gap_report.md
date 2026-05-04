# Original intent considered

- Update `autoloop/core/schema_registry.py` so `OPERATION_REPLAY_SCHEMA` is `autoloop.operation_replay/v2` (`autoloop/core/schema_registry.py:13`).
- Update `autoloop/core/operations.py` so replay occurrence counting and replay keys exclude `callsite`, while fingerprinting still includes `callsite` (`autoloop/core/operations.py:217-226`, `630-658`).
- Replace the inline replay-store migrator with a named `_migrate_operation_replay_store(...)` and use it from `_load_replay_store(...)`, discarding legacy cached `records` and preserving list-shaped `attempts` (`autoloop/core/operations.py:728-756`).
- Preserve the stated non-changes: `callsite` remains in `_operation_fingerprint`, remains stored in replay records for diagnostics, and public operation helper signatures stay unchanged.
- Verify the requested grep invariant that `_next_occurrence(...)` and `_operation_replay_key(...)` are only called from `_run_operation`.

# Clarifications / superseding decisions

- No later user clarification changed the requested behavior in the raw phase log.
- The decisions ledger preserves the core intent: pre-v2 replay records are disposable caches, `callsite` must stay in the fingerprint and stored record but not in the occurrence counter or replay key, and only schemaless or explicit `v1` replay payloads may be destructively migrated.
- Later implementation review found one over-broad behavior: `_load_replay_store(...)` initially migrated every non-`v2` schema. That was corrected so unsupported future schemas still fail validation, which is consistent with the request's strict schema/versioning intent.
- The test phase added direct `_load_replay_store(...)` boundary coverage because the pre-existing workflow-level replay tests did not exercise unsupported persisted-schema rejection.

# Implemented behavior

- `OPERATION_REPLAY_SCHEMA` is `autoloop.operation_replay/v2` in `autoloop/core/schema_registry.py:13`.
- `_run_operation(...)` still computes `callsite_id` and still passes it to `_operation_fingerprint(...)`, but now calls `_next_occurrence(runtime, spec.operation_kind)` and `_operation_replay_key(runtime, spec.operation_kind, occurrence)` (`autoloop/core/operations.py:217-226`).
- `_operation_replay_key(...)` excludes `callsite` from its signature and hashed payload (`autoloop/core/operations.py:630-642`).
- `_next_occurrence(...)` excludes `callsite` from its signature and counter key (`autoloop/core/operations.py:645-658`).
- `_migrate_operation_replay_store(...)` is a named module-level function that drops legacy `records` and preserves list-shaped `attempts` (`autoloop/core/operations.py:728-740`).
- `_load_replay_store(...)` uses `validate_persisted_schema(..., legacy_migrator=_migrate_operation_replay_store)` and only pre-migrates explicit `v1` payloads before validation; schemaless payloads still migrate through the validator path, while unsupported schemas raise `ValueError` (`autoloop/core/operations.py:743-756`).
- Repo-wide grep confirms source call sites for `_next_occurrence(...)` and `_operation_replay_key(...)` are only in `_run_operation(...)`.
- Focused replay validation passed on the current tree: `../autoloop_v3 (Cópia)/.venv/bin/python -m pytest tests/contract/test_engine_contracts.py -k operation_replay` reported `6 passed, 163 deselected`.
- Regression coverage now includes persisted-schema boundaries in `tests/contract/test_engine_contracts.py:8204-8249`, alongside the replay mismatch warn/fail coverage already present in `tests/contract/test_engine_contracts.py:8080-8200`.

# Unresolved gaps

- No material unresolved gap remains between the original request and the final codebase.

# Differences justified by later clarification or analysis

- `tests/contract/test_engine_contracts.py` was modified even though the original implementation spec listed only two source files. This is justified by later analysis and review: the added tests directly lock down the replay-store migration boundary and prevent regression in the reviewer-identified future-schema case.
- The final `_load_replay_store(...)` behavior is narrower than the implementation's first pass: unknown future schemas are rejected instead of being silently discarded. That change is justified by the later review finding and is consistent with the request's versioned-schema contract.
- The explicit limitations from the request remain unchanged. Inserting new operations earlier in a step can still shift occurrence numbering and cause silent cache misses; this was documented in the original request as an accepted limitation, not a missed behavior.

# Recommended next run

- No follow-up implementation run is required.
