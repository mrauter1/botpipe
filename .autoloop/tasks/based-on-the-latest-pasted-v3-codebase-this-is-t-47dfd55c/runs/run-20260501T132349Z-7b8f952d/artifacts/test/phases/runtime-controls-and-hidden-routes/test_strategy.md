# Test Strategy

- Task ID: based-on-the-latest-pasted-v3-codebase-this-is-t-47dfd55c
- Pair: test
- Phase ID: runtime-controls-and-hidden-routes
- Phase Directory Key: runtime-controls-and-hidden-routes
- Phase Title: Runtime Controls And Hidden Routes
- Scope: phase-local producer artifact

## Behavior-to-test coverage map
- Hook-returned `RequestInput` on plain `after`:
  Covered by `test_after_hook_request_input_checkpoints_pending_input_and_resume_validates_input`.
  Checks `AWAIT_INPUT`, pending-input checkpoint payload, resumed schema validation, and truthful built-in `last_route`.
- Hook-returned `RequestInput` on candidate-free `after_producer`:
  Covered by `test_after_producer_request_input_checkpoints_pending_input_before_verifier`.
  Checks verifier short-circuit on first run, pending-input checkpoint metadata, resumed input injection, and verifier execution only after resume.
- Hook-returned `Goto` on `after_producer`:
  Covered by `test_after_producer_goto_short_circuits_verifier`.
  Checks direct jump semantics and verifies verifier dispatch is skipped.
- Hook-returned `Goto` on `on_taken`:
  Covered by `test_on_taken_goto_skips_declared_route_target_and_emits_runtime_control`.
  Checks no declared-route target execution, runtime-control tracing, and direct jump to the declared step.
- `Goto(..., handoff=...)` propagation and checkpointing:
  Covered by `test_on_taken_goto_handoff_reaches_target_provider_step` and `test_on_taken_goto_checkpoints_target_before_next_step_dispatch`.
  Checks handoff delivery to the next provider step and checkpoint persistence at the destination cursor before target-step dispatch.
- Hook-returned `Fail`:
  Covered by `test_on_taken_fail_preserves_mutated_state_and_emits_runtime_control`.
  Checks `FAIL`, preserved custom-state mutation, and runtime-control tracing.
- Hidden route visibility split:
  Covered by `test_hidden_routes_are_runtime_legal_but_excluded_from_provider_choices` and `test_topology_payload_marks_hidden_routes_and_mermaid_route_table_keep_them`.
  Checks hidden-route runtime legality plus omission from provider choices while remaining present in topology artifacts.
- Runtime-control trace and checkpoint payload surfaces:
  Covered by `test_runtime_trace_records_direct_runtime_control_metadata` and `test_checkpoint_store_round_trip_preserves_pending_input_metadata`.
  Checks emitted trace fields and persisted pending-input round-trip behavior.

## Preserved invariants checked
- Direct runtime controls do not pretend a route finalized and do not update built-in `last_route` on the awaiting-input path.
- Hidden routes remain valid runtime route tags while provider-visible choices stay filtered.
- `Goto` handoff uses the same provider-facing route-handoff channel as route-based dispatch once the target step is provider-mediated.

## Edge cases and failure paths
- Resume with typed input after a runtime-issued pending-input checkpoint.
- Candidate-free direct control before verifier dispatch.
- Checkpoint existence when `Goto` advances to a step whose `before_step` extension fails before dispatch.

## Flake risk and stabilization
- No timing or network dependency; all coverage uses `ScriptedLLMProvider`, in-memory stores, and deterministic extension hooks.
- Assertions use exact provider call sequences and checkpoint payload fields to avoid order ambiguity.

## Known gaps
- This phase-local suite does not try to normalize candidate-free route-tag or `Event(...)` redirects from `after_producer`; coverage stays aligned to the implemented direct-control semantics and accepted reviewer fixes.
- Broader schema-registry and older-reader compatibility remains intentionally out of scope for this phase.
