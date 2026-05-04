# Test Author ↔ Test Auditor Feedback

- Task ID: below-is-the-revised-standalone-correction-spec-91e19feb
- Pair: test
- Phase ID: route-and-artifact-contracts
- Phase Directory Key: route-and-artifact-contracts
- Phase Title: Route And Artifact Core
- Scope: phase-local authoritative verifier artifact

## Test additions

- Added `tests/contract/test_engine_contracts.py::test_rendered_provider_invalid_question_retry_exhaustion_marks_failure_context` to pin rendered-provider retry-exhaustion parity with the direct provider path and ensure invalid `question` payloads stay classified as `invalid_payload`.
- Documented the phase coverage map in `test_strategy.md`, including AC-1 through AC-5 coverage, preserved invariants, edge cases, and the scoped verification gap.
- Verified the narrow regression slice with:
  `.venv/bin/python -m pytest tests/contract/test_engine_contracts.py -q -k "provider_invalid_question_retry_exhaustion_marks_failure_context or rendered_provider_invalid_question_retry_exhaustion_marks_failure_context or rendered_provider_invalid_question_retries_and_recovers or provider_invalid_question_retries_and_recovers"`
  and
  `.venv/bin/python -m pytest tests/runtime/test_runtime_providers.py -q -k "parse_outcome_json_rejects_question_without_question_field"`
