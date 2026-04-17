# Implementation Notes

- Task ID: you-are-a-principal-software-architect-and-imple-63e1905d
- Pair: implement
- Phase ID: workflow-migration-parity
- Phase Directory Key: workflow-migration-parity
- Phase Title: Workflow Migration And Autoloop_v1 Parity
- Scope: phase-local producer artifact

## Files Changed

- `autoloop_v1.py`
- `autoloop_v3/workflows/__init__.py`
- `autoloop_v3/workflows/autoloop_v1_support.py`
- `autoloop_v3/tests/runtime/test_workflow_integration_parity.py`
- `autoloop_v3/tests/test_architecture_baseline_docs.py`
- `autoloop_v3/README.md`
- `autoloop_v3/MIGRATION.md`
- `autoloop_v3/docs/architecture.md`
- `autoloop_v3/docs/authoring.md`
- `autoloop_v3/docs/compatibility.md`
- `autoloop_v3/docs/parity-matrix.md`
- `autoloop_v3/docs/risk-register.md`
- `workflow/primitives.py`
- `autoloop/tests/test_installer.py`
- `.autoloop/tasks/you-are-a-principal-software-architect-and-imple-63e1905d/decisions.txt`

## Symbols Touched

- `AutoloopV1`
- `run_autoloop_v1`
- `_AutoloopV1Engine`
- `parse_phase_ids`
- `phase_dir_key`
- `phase_artifact_template`
- `autoloop_v1_session_path`
- `ensure_autoloop_v1_workspace`
- `create_autoloop_v1_run`
- `_AutoloopV1LoggingProvider`
- `_binding_with_step_progress`
- `_session_step_counter`
- `_step_progress_for_state`

## Checklist Mapping

- AC-1 strict workflow migration: completed for `autoloop_v1.py`; `Ralph_loop.py` remained strict and continued to pass without changes.
- AC-2 explicit session-opening and phase-session sharing proof: completed via new parity harness tests plus existing engine contract coverage.
- AC-3 legacy workspace/events/checkpoint/question-blocked-failed/clarification/session parity: completed via `run_autoloop_v1(...)`, event-time phase logging, and expanded runtime parity tests that cover multi-phase event IDs plus cycle-aware blocked/question/clarification logs.
- Required docs and migration notes: completed with new `README.md`, `MIGRATION.md`, and rewritten strict-surface docs/tests.

## Assumptions

- Legacy-equivalent Autoloop-v1 behavior is intentionally provided by the workflow-owned harness, not by the generic runtime entrypoint.
- The generic runtime continues to prove that the strict workflow surface runs without loader injection or compatibility aliases, even though it does not preserve legacy session filenames or raw-log policy.

## Preserved Invariants

- `autoloop_v3.workflow` stays strict; no compat adapter was reintroduced.
- The generic runtime remains phase-agnostic and keeps generic session paths by default.
- Sessions remain explicit-only and are never auto-opened by the engine.

## Intended Behavior Changes

- `autoloop_v1.py` now writes phase artifacts under legacy pair-owned directories: `implement/phases/{phase}` and `test/phases/{phase}`.
- Autoloop-v1 parity runs now create task/run `raw_phase_log.md`, task `decisions.txt`, `sessions/plan.json`, and `sessions/phases/{phase}.json` through workflow-owned code.
- Autoloop-v1 parity runs now record `question`, `blocked`, and `failed` statuses in `events.jsonl` using workflow-owned status mapping.
- Autoloop-v1 parity runs now emit `step_executed`, `phase_started`, and `phase_completed` at step execution time with the active phase id instead of reconstructing them from final state after the run ends.
- Autoloop-v1 terminal notices and resume clarifications now reuse persisted per-step cycle metadata from session files instead of hardcoding `cycle=1`.
- Documentation now freezes the strict public surface and records compatibility removal instead of advertising legacy shims.

## Known Non-Changes

- `Ralph_loop.py` still runs through the generic runtime; it does not need a workflow-specific parity harness.
- The generic runtime still refuses resume attempts that only have session/event state and no `checkpoint.json`.

## Expected Side Effects

- New package `autoloop_v3.workflows` is part of the shipped surface for workflow-owned helpers/harnesses.
- Repo-wide installer tests now use command shims rather than ambient system PATH directories so validation is deterministic across developer machines.

## Validation Performed

- `pytest autoloop_v3/tests/runtime/test_workflow_integration_parity.py -q`
- `pytest autoloop_v3/tests/test_architecture_baseline_docs.py autoloop_v3/tests/runtime/test_workflow_integration_parity.py -q`
- `pytest autoloop_v3/tests -q`
- `pytest autoloop/tests/test_installer.py::test_installer_reports_installed_but_not_ready_for_claude_only_path autoloop/tests/test_installer.py::test_installer_python_version_guard_uses_centralized_error -q`
- `pytest -q`

## Deduplication / Centralization

- Phase-plan parsing, legacy artifact path templates, legacy session filename policy, raw-log writes, clarification persistence, and the Autoloop-v1 parity runner were centralized in `autoloop_v3/workflows/autoloop_v1_support.py` instead of being spread through the runtime core.
- Event-time phase parity and per-step cycle persistence are also centralized in `autoloop_v3/workflows/autoloop_v1_support.py` using a workflow-owned engine subclass plus session `provider_metadata`, rather than adding generic runtime hooks or new checkpoint fields.
- The out-of-phase edit to `autoloop/tests/test_installer.py` was limited to deterministic test PATH setup discovered during repo-wide validation; no production installer behavior was changed.
