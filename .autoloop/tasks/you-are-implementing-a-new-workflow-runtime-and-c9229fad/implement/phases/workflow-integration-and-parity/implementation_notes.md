# Implementation Notes

- Task ID: you-are-implementing-a-new-workflow-runtime-and-c9229fad
- Pair: implement
- Phase ID: workflow-integration-and-parity
- Phase Directory Key: workflow-integration-and-parity
- Phase Title: Workflow Integration And Parity
- Scope: phase-local producer artifact

## Files Changed

- `autoloop_v3/runtime/events.py`
- `autoloop_v3/runtime/runner.py`
- `autoloop_v3/runtime/stores/filesystem.py`
- `autoloop_v3/tests/runtime/test_compatibility_runtime.py`
- `autoloop_v3/tests/runtime/test_workflow_integration_parity.py`
- `.autoloop/tasks/you-are-implementing-a-new-workflow-runtime-and-c9229fad/decisions.txt`

## Symbols Touched

- `append_clarification`
- `append_resume_clarification`
- `run_workflow`
- `_paused_session_file`
- `_legacy_status`
- `FilesystemSessionStore._write_binding`

## Checklist Mapping

- Plan milestone 4: added end-to-end `AutoloopV1` and `Ralph_loop` parity coverage, including explicit multi-phase execution, implicit fallback, scoped artifacts, scoped sessions, and pause/resume answer injection.
- Plan milestone 4: added legacy comparison assertions for `latest_run_status`, `discover_config_file`, `resolve_resume_state_root`, `parse_decisions_headers`, `extract_clarifications`, and session-file compatibility fields.
- Plan milestone 4: added negative resume-path regression coverage proving unsupported legacy session/event-only resumes do not mutate `events.jsonl` or scaffold task/run files before the compatibility gate rejects them.
- Plan milestone 5 hardening subset: tightened runner/event/session persistence behavior to satisfy the new parity tests without widening the core engine boundary.

## Assumptions

- The generic v3 runner may express pause/resume differently from the legacy loop harness, but legacy readers still need compatible persisted artifacts and event fields.
- For the required target workflows, paused steps have stable session slots, so resume-time clarification notes should bind to the paused step’s declared session file.

## Preserved Invariants

- Strict core execution and compatibility normalization boundaries remain unchanged; all new behavior stays in `autoloop_v3.runtime` and filesystem persistence.
- Resume without a v3 checkpoint is still rejected; this phase only improves persisted-artifact parity for valid v3 runs and makes the rejection path non-mutating.
- Legacy workflow source files were not edited.

## Intended Behavior Changes

- Resume-time answers now write a legacy-compatible clarification record to raw logs, reuse the original decisions turn/qa sequence, and persist the full `Question/Answer` note to the active session file.
- Session restore and provider binding writes now preserve existing session metadata instead of overwriting it with sparse checkpoint/provider payloads.
- `run_finished` events now include legacy-compatible `status` values and are emitted on fatal exceptions as well as normal completion.
- Unsupported resume targets are now compatibility-gated before `ensure_workspace()`, `open_existing_run()`, or any event emission, so rejected legacy runs remain byte-for-byte unchanged on disk.

## Known Non-Changes

- The generic runner still does not reconstruct legacy event/session-only runs into v3 checkpoints.
- This turn did not refactor generic step raw logging into the full legacy pair/phase raw-log format; coverage focused on clarification/raw-log parity that affects resume and operator context.

## Expected Side Effects

- Existing tests that read `pending_clarification_note` must now expect the full `Question/Answer` note rather than only the answer text.
- Legacy helper functions can now consume v3 `run_finished` events directly in the tested scenarios.

## Validation Performed

- `pytest -q autoloop_v3/tests/runtime/test_compatibility_runtime.py autoloop_v3/tests/runtime/test_workflow_integration_parity.py`
- `pytest -q autoloop_v3/tests`
- Manual repro of `.superloop/tasks/.../runs/...` unsupported resume confirms `events.jsonl` and missing task/run scaffolding files remain unchanged after the targeted compatibility error.

## Deduplication / Centralization

- Centralized resume-answer parity handling in `runtime.events.append_resume_clarification` instead of scattering answer-ledger/raw-log/session updates across the runner.
- Centralized session metadata preservation in `FilesystemSessionStore._write_binding` so restore/open/upsert paths share the same merge behavior.
