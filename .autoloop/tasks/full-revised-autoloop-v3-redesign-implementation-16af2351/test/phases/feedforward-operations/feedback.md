# Test Author ↔ Test Auditor Feedback

- Task ID: full-revised-autoloop-v3-redesign-implementation-16af2351
- Pair: test
- Phase ID: feedforward-operations
- Phase Directory Key: feedforward-operations
- Phase Title: Feedforward operations
- Scope: phase-local authoritative verifier artifact

- Added standalone replay coverage in `tests/unit/test_simple_surface.py` to prove a value-returning `llm(...)` call replays from `operation_replay.json` and raises `ProviderExecutionError` on fingerprint drift with the same replay slot.
- Recorded the AC-to-test coverage map, preserved invariants, failure paths, and stabilization notes in `test_strategy.md`.
- `TST-001` `blocking` `tests/unit/test_simple_surface.py::test_standalone_operations_replay_and_fail_loudly_on_fingerprint_mismatch`, `test_strategy.md` AC-1 map: the new standalone replay test only covers `llm(...)`, but AC-1 explicitly requires standalone `classify(...)` fingerprint mismatch protection too. This leaves a material missed-regression path where a stale classification replay could be silently reused after the declared `choices` change if the classify fingerprint stopped incorporating `choices_hash`; the current workflow-node and llm-only mismatch tests would not catch that classify-specific bug. Minimal correction: extend the standalone replay/mismatch coverage to include `classify(...)` with a stable `callsite=` and a changed `choices` set that must raise `ProviderExecutionError`.
- Extended `tests/unit/test_simple_surface.py::test_standalone_operations_replay_and_fail_loudly_on_fingerprint_mismatch` to cover standalone `classify(...)` replay hits and classify-specific fingerprint drift when the declared `choices` set changes.
