# Implement ↔ Code Reviewer Feedback

- Task ID: below-is-the-revised-standalone-correction-spec-91e19feb
- Pair: implement
- Phase ID: route-and-artifact-contracts
- Phase Directory Key: route-and-artifact-contracts
- Phase Title: Route And Artifact Core
- Scope: phase-local authoritative verifier artifact

## Findings

### IMP-001 — blocking
- File/symbol: `autoloop/core/providers/parsing.py`, `parse_outcome_json`; downstream `autoloop/core/engine.py::_provider_retry_kind`
- Problem: rendered-provider `question` payload validation now happens in the JSON parser, but the parser raises a bare `ProviderExecutionError` with no `failure_context` or `retry_kind`. When the provider returns `{"tag":"question"}` or `{"tag":"question","question":""}`, the engine falls back to classifying the error as `malformed_provider_output` because the message contains `"outcome JSON"`. The direct `Outcome(...)` path still classifies the same defect as `invalid_payload`.
- Failure scenario: a rendered provider emits `{"tag":"question"}` under a retryable step. The direct fake-provider path retries with invalid-payload feedback (`question route requires a non-empty question field`), but the rendered path is treated as malformed provider output and follows the wrong retry bucket and feedback path. This violates AC-2’s direct/rendered parity requirement.
- Minimal fix direction: centralize `question` payload validation in the shared outcome-validation path, or have `parse_outcome_json(...)` attach `FailureContext(kind="invalid_payload", ...)` plus `retry_kind="invalid_payload"` for question-specific payload defects while leaving malformed JSON/shape errors in the malformed-provider-output bucket.
