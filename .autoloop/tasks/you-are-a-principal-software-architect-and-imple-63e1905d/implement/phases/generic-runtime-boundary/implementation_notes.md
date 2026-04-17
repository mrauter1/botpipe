# Implementation Notes

- Task ID: you-are-a-principal-software-architect-and-imple-63e1905d
- Pair: implement
- Phase ID: generic-runtime-boundary
- Phase Directory Key: generic-runtime-boundary
- Phase Title: Generic Runtime Boundary
- Scope: phase-local producer artifact

## Files changed

- `autoloop_v3/runtime/__init__.py`
- `autoloop_v3/runtime/cli.py`
- `autoloop_v3/runtime/config.py`
- `autoloop_v3/runtime/events.py`
- `autoloop_v3/runtime/runner.py`
- `autoloop_v3/runtime/stores/__init__.py`
- `autoloop_v3/runtime/stores/filesystem.py`
- `autoloop_v3/runtime/workspace.py`
- `autoloop_v3/tests/runtime/test_compatibility_runtime.py`
- `autoloop_v3/tests/runtime/test_workflow_integration_parity.py`
- `autoloop_v3/tests/fixtures/toy_runtime_workflow.py`
- `autoloop_v1.py`
- `.autoloop/tasks/you-are-a-principal-software-architect-and-imple-63e1905d/decisions.txt`

## Symbols touched

- `RuntimeConfig`, `RuntimeConfigOverride`, `resolve_runtime_config`
- `TaskWorkspace`, `RunWorkspace`, `ensure_workspace`, `create_run`, `open_existing_run`
- `RunnerOptions`, `run_workflow`
- `EventLogger`
- `FilesystemSessionStore`, `FilesystemCheckpointStore`, `scope_key`
- `ToyRuntimeWorkflow`
- `AutoloopV1.plan`, `AutoloopV1.implement`, `AutoloopV1.test`

## Checklist mapping

- Phase 2 / Milestone 1: removed phase-plan scaffolding and phase-selection ownership from `runtime.workspace`.
- Phase 2 / Milestone 2: removed pair/phase/git compatibility flags from `runtime.cli`, `runtime.config`, and `runtime.runner`.
- Phase 2 / Milestone 3: removed `plan_session` / `phase_session` path special cases from `runtime.stores.filesystem`.
- Phase 2 / Milestone 4: added a toy workflow fixture plus runner and CLI tests proving unrelated step names execute end to end.

## Assumptions

- Detailed Autoloop-v1 clarification / decisions / raw-log parity is deferred to the workflow-owned parity-harness phase, not the generic runtime core.

## Preserved invariants

- `.autoloop/tasks/{task_id}/runs/{run_id}` root layout remains the generic on-disk contract.
- Task-level and run-level request snapshots still exist and are written through the runtime workspace helpers.
- Checkpoint persistence, resume-root discovery, and legacy `thread_id` -> `session_id` session payload loading still work.
- Event log status values remain compatible with `legacy_autoloop.latest_run_status(...)`.

## Intended behavior changes

- Generic runtime no longer creates `plan/`, `implement/`, `test/`, `raw_phase_log.md`, `decisions.txt`, or `phase_selection.json`.
- Generic session persistence now uses slot/scope paths instead of hardcoded `plan.json` and `phases/{phase}.json`.
- Prompt resolution is now generic; `autoloop_v1.py` carries explicit prompt paths instead of depending on a runtime-specific Autoloop template root.

## Known non-changes

- Legacy `.superloop` resume-root discovery remains in place.
- Workflow engine contracts, explicit session opening semantics, and root `workflow` strict re-export behavior were not changed in this phase.

## Expected side effects

- Tests that previously asserted runtime-owned phase scaffolding or legacy session filenames were rewritten to assert the new generic runtime boundary.
- `autoloop_v1.py` still runs, but its phase/workspace artifacts now arise from workflow-owned artifact templates rather than runtime-created directories.

## Validation performed

- `pytest autoloop_v3/tests`

## Deduplication / centralization decisions

- Removed phase/pair policy from `runtime.workspace`, `runtime.runner`, and `runtime.events`, leaving only generic workspace setup, session/checkpoint persistence, prompt resolution, and event logging in the runtime.
