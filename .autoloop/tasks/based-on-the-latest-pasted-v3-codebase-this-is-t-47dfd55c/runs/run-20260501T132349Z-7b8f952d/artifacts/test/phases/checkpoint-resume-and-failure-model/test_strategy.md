# Test Strategy

- Task ID: based-on-the-latest-pasted-v3-codebase-this-is-t-47dfd55c
- Pair: test
- Phase ID: checkpoint-resume-and-failure-model
- Phase Directory Key: checkpoint-resume-and-failure-model
- Phase Title: Checkpoint Resume And Failure Model
- Scope: phase-local producer artifact

## Behavior-to-Test Coverage Map

- AC-1 pending-input persistence:
  - `tests/contract/test_engine_contracts.py::test_after_hook_request_input_checkpoints_pending_input_and_resume_validates_input`
  - `tests/contract/test_engine_contracts.py::test_after_producer_request_input_checkpoints_pending_input_before_verifier`
  - `tests/unit/test_primitives_and_stores.py::test_checkpoint_store_round_trip_preserves_pending_input_metadata`
  - `tests/runtime/test_package_cli.py::test_runs_show_and_logs_surface_awaiting_input_metadata`
- AC-1 resumed-input validation failure preserves pending input:
  - `tests/contract/test_engine_contracts.py::test_resume_invalid_pending_input_preserves_checkpoint_and_failure_context`
- AC-1 consumed input is cleared before later dispatch:
  - `tests/contract/test_engine_contracts.py::test_resumed_request_input_is_consumed_before_later_steps`
- AC-1 writer compatibility boundary:
  - `tests/runtime/test_compatibility_runtime.py::test_filesystem_checkpoint_store_roundtrips_failure_context`
  - Preserved invariant: new filesystem checkpoint writes omit legacy top-level `pending_question`.
- AC-2 structured failure persistence keeps mutated authored state:
  - `tests/contract/test_engine_contracts.py::test_invalid_goto_after_state_mutation_preserves_state_and_failure_context`
- AC-2 runtime-owned state fields remain read-only while custom fields stay mutable:
  - `tests/unit/test_simple_surface.py::test_simple_context_step_state_runtime_fields_are_read_only`
  - `tests/unit/test_simple_surface.py::test_simple_context_step_item_state_runtime_fields_are_read_only`
- AC-2 structured failure metadata remains readable through retry/checkpoint surfaces:
  - `tests/unit/test_provider_retries.py`
  - `tests/runtime/test_compatibility_runtime.py::test_filesystem_checkpoint_store_roundtrips_failure_context`

## Edge Cases And Failure Paths

- Resume with schema-invalid input keeps `pending_input` and records `failure_context.kind == "resume_input_validation"`.
- Direct-control validation failure after authored mutation keeps the mutated custom state in the checkpoint.
- A consumed `ctx.input_response` must not leak into downstream steps during the same resumed run.

## Preserved Invariants

- Successful route finalization updates built-in route state only on finalized route-based transitions.
- Direct runtime controls do not set built-in `last_route`.
- Legacy persisted compatibility stays read-tolerant where explicitly retained, without restoring duplicate `pending_question` writes.

## Known Gaps

- This phase does not extend provider prompt rendering assertions; that behavior is owned by later rendering/topology work.
