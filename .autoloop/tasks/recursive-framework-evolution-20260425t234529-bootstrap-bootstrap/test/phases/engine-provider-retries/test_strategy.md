# Test Strategy

- Task ID: recursive-framework-evolution-20260425t234529-bootstrap-bootstrap
- Pair: test
- Phase ID: engine-provider-retries
- Phase Directory Key: engine-provider-retries
- Phase Title: Engine Retry Semantics
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- AC-1 default retry budget and single-attempt override:
  - Covered by `tests/unit/test_validation.py` (`test_compiled_step_defaults_provider_retry_policy`, `test_provider_retry_policy_validates_max_attempts`, `test_validation_rejects_provider_retry_policy_on_system_step`).
  - Covered by `tests/contract/test_engine_contracts.py` existing `max_attempts=1` checkpoint/failure cases.
- AC-2 provider-only retry scope:
  - Covered by `tests/contract/test_engine_contracts.py` existing illegal-route, invalid-payload, missing-output-artifact, middleware bogus-route, system-step bogus-route, and checkpoint exhaustion tests.
  - Added `test_retry_policy_can_disable_illegal_route_retries` to prove retry-policy flags prevent a provider retry class even when retry budget remains.
- AC-3 pair retry restart and no prior transcript/raw-output reuse:
  - Covered by existing pair retry test asserting producer→verifier→producer→verifier order and no raw-output leakage in retry feedback.
  - Covered by existing session-bound llm/pair retry tests asserting retries reuse the pre-step baseline session while keeping same-attempt producer→verifier session chaining.
- AC-4 retry exhaustion failure context:
  - Covered by existing checkpoint assertions for `retry_attempts_consumed`, `retry_max_attempts`, and `retry_exhausted`.

## Added in this test turn

- `tests/contract/test_engine_contracts.py`
  - `test_retry_policy_can_disable_illegal_route_retries`
- `tests/unit/test_provider_retries.py`
  - Direct `build_retry_feedback(...)` coverage for illegal route, invalid payload, missing required output artifact, invalid output artifact, provider transport failure, malformed provider output, and fallback messaging.

## Preserved invariants checked

- Retry-policy opt-out does not silently consume extra attempts.
- Retry-feedback markdown stays deterministic and human-readable.
- Helper messaging does not depend on provider transcripts, timing, or filesystem state.

## Edge cases and failure paths

- Policy flag disables retries before budget exhaustion.
- Artifact-name-aware retry feedback uses failure context when present.
- Blank exception messages fall back to a step-scoped default problem line.

## Flake risk and stabilization

- No timing, network, subprocess, or nondeterministic ordering dependencies were added.
- All new tests use scripted providers or direct helper calls with fixed in-memory state.

## Known gaps

- Provider transport and malformed-output retry execution paths remain primarily covered indirectly through engine/provider integration tests from implement; this test turn focused on policy gating and helper rendering because those phase surfaces lacked direct assertions.
