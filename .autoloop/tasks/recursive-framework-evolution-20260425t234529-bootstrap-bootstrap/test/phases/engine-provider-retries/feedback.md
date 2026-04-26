# Test Author ↔ Test Auditor Feedback

- Task ID: recursive-framework-evolution-20260425t234529-bootstrap-bootstrap
- Pair: test
- Phase ID: engine-provider-retries
- Phase Directory Key: engine-provider-retries
- Phase Title: Engine Retry Semantics
- Scope: phase-local authoritative verifier artifact

- Added engine regression coverage for retry-policy gating via `test_retry_policy_can_disable_illegal_route_retries` in `tests/contract/test_engine_contracts.py`.
- Added direct unit coverage for `build_retry_feedback(...)` in `tests/unit/test_provider_retries.py`, including specialized messages for illegal route, invalid payload, missing/invalid output artifacts, transport failure, malformed provider output, and fallback messaging.
- Validation run: `.venv/bin/pytest -q tests/unit/test_provider_retries.py` and `.venv/bin/pytest -q tests/contract/test_engine_contracts.py` both passed.
- TST-001 `blocking` [tests/contract/test_engine_contracts.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/contract/test_engine_contracts.py), [tests/unit/test_provider_retries.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_provider_retries.py): the added tests still do not exercise the engine’s retry loop for two explicit AC-2 failure classes: provider-attributable malformed output and provider transport failure. The helper unit test only proves message rendering for `build_retry_feedback(...)`; it would still pass if `core/engine.py` stopped retrying when a provider returned a non-`Outcome` value or raised a transport exception. Concrete missed-regression scenario: `_validate_outcome(...)` could regress to raising a non-retryable error for malformed outputs, or transport exceptions could stop being classified as `provider_transport_failure`, and this phase’s tests would not detect the loss of retry semantics required by AC-2. Minimal fix: add engine-level contract tests that force (1) a malformed provider output on early attempts and (2) a provider transport failure on early attempts, then assert retry counts, retry feedback on subsequent attempts, and success or exhausted-checkpoint behavior at the engine boundary.
