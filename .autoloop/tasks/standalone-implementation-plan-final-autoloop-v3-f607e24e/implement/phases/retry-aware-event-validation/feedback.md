# Implement ↔ Code Reviewer Feedback

- Task ID: standalone-implementation-plan-final-autoloop-v3-f607e24e
- Pair: implement
- Phase ID: retry-aware-event-validation
- Phase Directory Key: retry-aware-event-validation
- Phase Title: Retry-Aware Event Validation
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 `blocking` [tests/contract/test_engine_contracts.py:3574-3612], [core/engine.py:905-936]: `test_system_step_hooks_can_override_route_after_candidate_validation` still expects a deterministic after-hook route-string retag from `Event("done")` to `"question"` to pause successfully, but the new centralized validation correctly rejects that final event because it preserves no non-empty `question`. In the real suite this leaves the touched contract tests self-contradictory and will fail once the environment can actually run `pytest`. Minimal fix: update that test to match the new invariant, either by returning an explicit valid `Event("question", question=...)` from the hook or by asserting `WorkflowExecutionError` for the invalid route-string retag.
