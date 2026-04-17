# Test Strategy

- Task ID: you-are-implementing-a-new-workflow-runtime-and-c9229fad
- Pair: test
- Phase ID: workflow-integration-and-parity
- Phase Directory Key: workflow-integration-and-parity
- Phase Title: Workflow Integration And Parity
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- `AutoloopV1` explicit multi-phase execution:
  covered by `test_autoloop_v1_explicit_multi_phase_run_preserves_phase_scoping_and_legacy_event_status`
  checks task/run layout, explicit phase activation, phase-local artifacts, phase-scoped sessions, prompt resolution, and legacy `run_finished.status=success`.
- `AutoloopV1` implicit fallback behavior:
  covered by `test_autoloop_v1_invalid_phase_plan_falls_back_to_implicit_phase`
  checks invalid phase-plan parsing falls back to the implicit phase without breaking scoped artifact/session layout.
- Pause/resume clarification parity:
  covered by `test_resume_answer_injection_writes_legacy_compatible_clarification_artifacts`
  checks question/answer pairing in `decisions.txt`, raw-log clarification extraction, and session-note persistence that legacy readers can consume.
- `Ralph_loop` legacy shims:
  covered by `test_ralph_loop_executes_with_legacy_shims_and_persistent_main_session`
  checks `Verdict`/legacy handler compatibility, persisted main-session layout, and deterministic end-to-end execution.
- Legacy helper parity:
  covered by `test_runtime_compatibility_helpers_match_legacy_runtime`, `test_legacy_latest_run_status_reads_v3_success_run`, and `test_runner_emits_fatal_error_status_for_legacy_latest_run_status_compatibility`
  checks config discovery, decisions parsing, resume-root resolution, and event-status compatibility for both success and fatal-error runs.
- Resume rejection safety:
  covered by `test_runner_resume_without_checkpoint_but_with_legacy_state_fails_with_targeted_message` and `test_runner_rejects_legacy_resume_without_scaffolding_workspace_or_run_files`
  checks unsupported legacy resumes fail with the targeted message and do not mutate `events.jsonl` or scaffold task/run files.
- Session persistence metadata preservation:
  covered by `test_filesystem_session_store_sparse_writes_preserve_existing_legacy_metadata`
  checks sparse `restore()` and `upsert()` writes keep legacy `provider_metadata`, clarification notes, and timestamps instead of clobbering them.

## Preserved Invariants Checked

- Legacy workspace readers can consume v3 raw logs, decisions headers, session files, and `run_finished.status` fields in the exercised scenarios.
- Scoped artifacts and sessions remain phase-local for `AutoloopV1`.
- Unsupported resume targets remain rejected rather than being silently migrated or partially resumed.

## Edge Cases And Failure Paths

- Invalid explicit phase plans fall back deterministically to the implicit phase.
- Resume without `checkpoint.json` is asserted on both an existing `.autoloop` run and a pure `.superloop` legacy run.
- Fatal provider exhaustion still emits a legacy-readable `fatal_error` terminal status.
- Session persistence tests use fixed timestamps and payloads to avoid clock-sensitive expectations.

## Known Gaps

- The generic v3 runner still intentionally does not reconstruct legacy event/session-only runs into checkpoints; tests assert rejection rather than migration.
- Legacy `Ralph_loop.py` still emits Pydantic deprecation warnings via `copy()`, but this phase treats them as non-blocking because the source workflow remains intentionally unchanged.
