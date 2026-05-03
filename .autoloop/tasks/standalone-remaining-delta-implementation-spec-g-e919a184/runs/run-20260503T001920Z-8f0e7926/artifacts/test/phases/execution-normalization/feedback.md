# Test Author ↔ Test Auditor Feedback

- Task ID: standalone-remaining-delta-implementation-spec-g-e919a184
- Pair: test
- Phase ID: execution-normalization
- Phase Directory Key: execution-normalization
- Phase Title: Execution Normalization
- Scope: phase-local authoritative verifier artifact

## Cycle 1

- Added contract coverage for `before_verifier` returning `RequestInput`, asserting producer-only execution, pending-input checkpoint metadata, and preserved direct-control transition state.
- Added contract coverage for missing undeclared workspace reads staying visible to providers as `readable_artifacts` with `declared_artifact=False` and `exists=False`.
- Validation performed: `python3 -m py_compile tests/contract/test_engine_contracts.py`. Runtime `pytest` execution was not possible in this shell because `pytest` is not installed.

## Cycle 2

- Added `before_verifier` invalid-`Goto` failure coverage, asserting producer-ran/verifier-skipped behavior plus preserved mutated state and `runtime_control_validation` checkpoint metadata sourced from `before_verifier`.
- Validation performed: `python3 -m py_compile tests/contract/test_engine_contracts.py`. Runtime `pytest` execution is still blocked in this shell because `pytest` is not installed.

## Findings

### TST-001 — blocking
Affected behavior/tests: `tests/contract/test_engine_contracts.py`, especially the new `before_verifier` coverage at `test_before_verifier_request_input_short_circuits_verifier_and_checkpoints_pending_input`, plus the phase deliverable requiring contract tests for `before` / `before_producer` / `before_verifier` short-circuit behavior and invalid control failures.

The new tests add the happy-path `before_verifier` direct-control case, but there is still no test for an invalid `before_verifier` control payload or target. That leaves the phase-independent validation guarantee under-covered for the exact lifecycle seam that changed in this phase. A regression where `before_verifier` accidentally skips validation for `RequestInput("")`, `Fail("")`, or `Goto("missing_step")`, or records the wrong failure attribution/checkpoint source after the producer turn, would still pass this suite.

Minimal correction direction: add one focused contract test for an invalid `before_verifier` direct control, preferably an empty-question `RequestInput` or missing-step `Goto`, and assert that producer ran, verifier did not, the run fails clearly, and checkpoint/failure metadata preserve the mutated current state with `source_phase="before_verifier"`.

## Re-review Cycle 2

- Rechecked `TST-001` against `test_before_verifier_invalid_goto_preserves_state_and_failure_context`; the previously missing invalid `before_verifier` direct-control failure path is now covered.
- No active blocking or non-blocking audit findings remain in this review pass.
