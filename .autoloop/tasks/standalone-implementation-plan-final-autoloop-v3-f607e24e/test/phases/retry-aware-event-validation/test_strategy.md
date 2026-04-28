# Test Strategy

- Task ID: standalone-implementation-plan-final-autoloop-v3-f607e24e
- Pair: test
- Phase ID: retry-aware-event-validation
- Phase Directory Key: retry-aware-event-validation
- Phase Title: Retry-Aware Event Validation
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- Provider-attributable invalid question payloads:
  Covered by `test_provider_invalid_question_retries_and_recovers` and `test_provider_invalid_question_retry_exhaustion_marks_failure_context`.
  Checks retry feedback, retry exhaustion metadata, and that invalid pause checkpoints do not persist `pending_question`.
- Provider-attributable invalid blocked/failed payloads:
  Covered by `test_provider_invalid_terminal_route_retries_and_recovers`.
  Checks retry recovery for both reserved terminal routes.
- Deterministic system-step invalid events:
  Covered by `test_system_question_and_failed_events_validate_strictly` and `test_invalid_system_route_still_fails_before_artifact_validation`.
  Checks valid pause/fail behavior plus immediate `WorkflowExecutionError` on malformed payloads and illegal routes.
- Middleware-produced invalid events:
  Covered by `test_invalid_middleware_route_still_fails_before_artifact_validation`.
  Checks provider attribution metadata and ensures route failure happens before artifact validation.
- After-hook attribution split:
  Covered by `test_provider_after_hook_route_string_invalid_event_retries_and_recovers`, `test_provider_after_hook_explicit_invalid_event_hard_fails`, and `test_system_step_hooks_can_override_route_after_candidate_validation`.
  Checks provider-attributable route-string retags, deterministic explicit hook events, and valid explicit reserved-route payload preservation.
- Workflow-step child-result mapping:
  Covered by `test_workflow_step_maps_child_terminals_and_writes_outputs` and `test_workflow_step_rejects_child_question_without_question_payload`.
  Checks valid child terminal mapping and malformed child pause rejection.

## Preserved Invariants Checked

- `_next_retry_feedback(...)` still drives retryable provider failures through the existing retry loop via retry-feedback assertions on illegal-route, invalid-payload, and artifact-validation paths.
- Invalid reserved-route payloads are rejected before PAUSE/FAIL persistence.
- Explicit hook `Event` overrides remain deterministic; route-string retags in provider steps remain provider-attributable.

## Failure Paths And Edge Cases

- Retry exhaustion on invalid `question` payload.
- Illegal-route middleware output in a provider step.
- Illegal-route system output in a deterministic step.
- Explicit invalid final `failed` event from an after hook.
- Child workflow pause with `Event("question")` missing the question text.

## Reliability Notes

- Tests use `ScriptedLLMProvider`, in-memory checkpoint/session stores, and direct child-workflow stubs to avoid timing, network, filesystem ordering, or external provider flake.
- The environment available in this turn does not have `pytest` or importable runtime dependencies, so authoring focused on deterministic assertions and compile-safe edits rather than executed suite validation.

## Known Gaps

- This turn did not add a dedicated pair-step verifier invalid-event test because the changed event-validation paths are already exercised through the shared provider-step finalization code and existing provider retry suites.
