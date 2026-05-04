# Test Strategy

- Task ID: operation-replay-key-stability-fix-implementatio-b15a7c28
- Pair: test
- Phase ID: align-operation-replay-keying
- Phase Directory Key: align-operation-replay-keying
- Phase Title: Align Operation Replay Keying
- Scope: phase-local producer artifact

## Behavior-to-test coverage
- Replay fingerprint mismatch, warn path:
  - Covered by `test_operation_replay_fingerprint_mismatch_warns_and_reuses_cached_value_by_default`
  - Checks replay-key hit plus default `warn` behavior reuse
- Replay fingerprint mismatch, fail path:
  - Covered by `test_operation_replay_fingerprint_mismatch_fails_in_strict_mode`
  - Checks strict-mode exception on fingerprint mismatch
- Fingerprint preserved invariants:
  - Covered by `test_operation_replay_fingerprint_includes_provider_configuration`
  - Checks provider configuration remains part of fingerprint
- Legacy replay-store migration, happy path:
  - Covered by `test_operation_replay_store_migrates_only_schemaless_and_v1_payloads`
  - Checks schemaless and explicit `v1` payloads are migrated to empty `v2` stores with list-shaped `attempts` preserved
- Unsupported replay-store schema, failure path:
  - Covered by `test_operation_replay_store_rejects_unsupported_schema_versions`
  - Checks explicit `v3` payloads raise `ValueError` instead of being silently discarded

## Preserved invariants checked
- `OPERATION_REPLAY_SCHEMA` remains `autoloop.operation_replay/v2` via migrated store expectations.
- Replay keys and occurrence counters remain callsite-free through the existing workflow-level replay contract tests.
- `callsite` stays in fingerprint behavior through the existing warn/fail mismatch tests.

## Edge cases and failure paths
- Schemaless replay payloads still migrate through the legacy migrator path.
- Explicit `v1` replay payloads still migrate destructively.
- Unknown future schemas fail validation instead of downgrading to empty `v2` payloads.

## Flake risk and stabilization
- No timing, network, or nondeterministic ordering dependencies.
- New coverage uses temp-path local files and direct helper invocation for deterministic persisted-schema assertions.

## Known gaps
- The focused slice does not add a workflow-level scenario that resumes from an on-disk `v1` replay store, because the key risk here is the loader boundary and the helper-level assertions already isolate it deterministically.
