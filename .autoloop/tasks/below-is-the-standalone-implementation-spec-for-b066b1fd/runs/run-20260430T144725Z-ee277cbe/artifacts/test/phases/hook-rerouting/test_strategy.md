# Test Strategy

- Task ID: below-is-the-standalone-implementation-spec-for-b066b1fd
- Pair: test
- Phase ID: hook-rerouting
- Phase Directory Key: hook-rerouting
- Phase Title: Enable Hook Rerouting
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Hook rerouting happy path:
  `tests/contract/test_engine_contracts.py`
  `test_after_hook_returning_route_string_reroutes_execution`
  `test_provider_after_hook_event_override_reroutes_execution`
  `test_route_hooks_can_reroute_across_a_chain_and_emit_redirect_events`
- Final-route enforcement:
  `tests/contract/test_engine_contracts.py`
  `test_route_redirected_final_route_drives_required_write_validation`
- Redirect-cycle failure and redirect-event emission:
  `tests/contract/test_engine_contracts.py`
  `test_route_redirect_cycle_fails_after_max_hook_redirects`
- Rollback safety:
  `tests/contract/test_engine_contracts.py`
  `test_route_hook_failure_rolls_back_chained_state_before_checkpoint`
- Trace visibility:
  `tests/runtime/test_runtime_tracing.py`
  `test_runtime_trace_records_hook_route_override_metadata`
- Producer-phase validation parity:
  `tests/unit/test_validation.py`
  `test_validation_rejects_static_after_do_route_override_before_candidate_event`
  `test_validation_rejects_static_after_do_handoff_override_before_candidate_event`

## Preserved invariants checked

- Redirected tags must already be legal on the current step.
- Final transition and artifact validation follow the final selected route, not the initial candidate route.
- Producer-phase pair hooks remain state-only until a candidate event exists.

## Edge cases and failure paths

- Dynamic invalid hook route still fails as a runtime error after compilation.
- Handoff-only producer-phase overrides are rejected statically, not only route-tag overrides.
- Chained redirects restart hook processing on the redirected route.
- Redirect-limit failure emits redirect events before terminating.
- Route-hook failure restores pre-finalization workflow state into the checkpoint.

## Stabilization / flake control

- All added tests use `ScriptedLLMProvider`, `InMemorySessionStore`, and `InMemoryCheckpointStore`.
- Rollback assertions read deterministic in-memory checkpoint state instead of depending on timing or external files.

## Known gaps

- No direct session-binding rollback assertion was added; rollback coverage is anchored on checkpointed workflow-state restoration because it is stable and phase-relevant.
