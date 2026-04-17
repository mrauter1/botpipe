# Test Strategy

- Task ID: you-are-a-principal-software-architect-and-imple-63e1905d
- Pair: test
- Phase ID: workflow-migration-parity
- Phase Directory Key: workflow-migration-parity
- Phase Title: Workflow Migration And Autoloop_v1 Parity
- Scope: phase-local producer artifact

## Behavior Coverage Map

- Strict workflow execution without compat or loader injection:
  `test_autoloop_v1_runs_with_generic_runtime_and_explicit_prompt_paths`
  `test_ralph_loop_executes_with_generic_runtime_and_persistent_main_session`
- Explicit session opening and phase-session sharing:
  `test_autoloop_v1_parity_harness_preserves_legacy_workspace_logs_and_sessions`
- Legacy event-log parity for Autoloop-v1:
  `test_autoloop_v1_parity_harness_preserves_legacy_workspace_logs_and_sessions`
  Coverage includes phase-aware `step_executed`, `phase_started`, `phase_completed`, and lifecycle ordering.
- Clarification persistence and resume parity:
  `test_autoloop_v1_parity_harness_persists_clarifications_and_resumes`
  Coverage includes second-cycle question logging and clarification-cycle reuse on resume.
- Blocked and failed terminal mapping:
  `test_autoloop_v1_parity_harness_maps_blocked_pause_to_legacy_status`
  `test_autoloop_v1_parity_harness_maps_failed_terminal_to_legacy_status`
- Legacy status-reader compatibility for generic runtime:
  `test_runner_emits_fatal_error_status_for_legacy_status_reader_compatibility`
  `test_legacy_latest_run_status_reads_generic_runtime_success_run`

## Preserved Invariants Checked

- `Ralph_loop.py` continues to run on the generic runtime with generic session paths.
- Autoloop-v1 parity remains workflow-owned rather than reintroducing runtime-core hooks.
- Implement/test keep sharing the current phase session while plan uses the global plan session.

## Edge Cases Covered

- Two-phase success path with exact phase lifecycle ordering.
- Second plan cycle pausing for clarification before resume.
- Second implement cycle blocking after `needs_rework`.
- Final `activate_next_phase` completion path without extra `phase_started` emissions.

## Failure Paths Covered

- Generic-runtime fatal error status emission for legacy readers.
- Autoloop-v1 blocked terminal parity.
- Autoloop-v1 failed terminal parity.

## Stabilization Notes

- All coverage uses `ScriptedLLMProvider`, temporary directories, and explicit JSON/raw-log assertions.
- No network, clock-sensitive ordering, or ambient environment dependencies are used.

## Known Gaps

- In-repo providers do not rotate session IDs between turns, so there is no dedicated regression test for cycle tracking across provider-issued session replacement.
