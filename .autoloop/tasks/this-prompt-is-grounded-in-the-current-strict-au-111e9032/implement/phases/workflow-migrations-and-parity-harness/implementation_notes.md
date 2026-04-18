# Implementation Notes

- Task ID: this-prompt-is-grounded-in-the-current-strict-au-111e9032
- Pair: implement
- Phase ID: workflow-migrations-and-parity-harness
- Phase Directory Key: workflow-migrations-and-parity-harness
- Phase Title: Migrate Workflows And Parity Harnesses
- Scope: phase-local producer artifact

## Files Changed
- `autoloop_v1.py`
- `autoloop_v3/runtime/runner.py`
- `autoloop_v3/workflows/autoloop_v1_conventions.py`
- `autoloop_v3/workflows/autoloop_v1_parity.py`
- `autoloop_v3/tests/runtime/test_workflow_integration_parity.py`
- `autoloop_v3/tests/runtime/test_compatibility_runtime.py`
- `.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/decisions.txt`

## Symbols Touched
- `AutoloopV1.extensions`
- `AutoloopV1SessionPathStrategy`
- `run_autoloop_v1`
- `prepare_runtime_services`
- `resolve_max_steps`
- `resolve_session_path_strategy`
- `validate_resume_state`

## Checklist Mapping
- Milestone 5 / AC-1: `autoloop_v1.py` now declares `SessionPaths(...)` explicitly while keeping inline phase parsing and inline artifact templates.
- Milestone 5 / AC-2: `run_autoloop_v1(...)` now composes generic runner services and keeps only workflow-owned parity workspace/logging behavior local.
- Milestone 5 / AC-3: Ralph workflow behavior remains covered by existing parity/runtime tests; no code change was needed in this turn because the current file already satisfies the strict surface and `goal_met` tests.
- Milestone 6: updated workflow/parity tests to lock the explicit session-path contract and the thinner harness composition.

## Assumptions
- The repo-root `autoloop_v1.py` and `Ralph_loop.py` files are intentional workspace inputs even though they are currently untracked in this checkout.
- `autoloop_v1.py` is the authoritative place to declare its exact session filename policy once `SessionPaths(...)` exists.

## Preserved Invariants
- Runtime remains phase-agnostic; exact `plan.json` and `sessions/phases/{phase}.json` naming stays workflow-owned.
- The parity harness still owns raw phase logs, decisions ledger writes, clarification persistence, and legacy status mapping.
- Generic runner prompt resolution remains workflow-module-relative plus explicit workspace-root fallback only.

## Intended Behavior Changes
- Generic `run_workflow(...)` for `autoloop_v1.py` now honors the workflow-declared Autoloop-v1 session filenames instead of the generic scoped-session layout.
- `run_autoloop_v1(...)` now fails clearly if the workflow stops declaring its required `SessionPaths(...)` policy.

## Known Non-Changes
- No legacy `autoloop/` oracle files were edited.
- No new workflow-specific runtime abstraction was added beyond reusing shared runner helpers.
- `Ralph_loop.py` was left structurally unchanged in this turn because its strict imports/signatures and `goal_met` success-path behavior were already correct.

## Expected Side Effects
- Session files for generic runs of `autoloop_v1.py` now appear at `sessions/plan.json` and `sessions/phases/<phase>.json`.
- The parity harness now shares the generic runner’s max-step validation, resume-state validation, and prompt/session/checkpoint/logger service construction.

## Validation Performed
- `pytest autoloop_v3/tests/runtime/test_workflow_integration_parity.py autoloop_v3/tests/runtime/test_compatibility_runtime.py autoloop_v3/tests/runtime/test_optional_extensions.py`
- `pytest autoloop_v3/tests/contract/test_engine_contracts.py autoloop_v3/tests/unit/test_validation.py autoloop_v3/tests/unit/test_stdlib_and_extensions.py`

## Dedup / Centralization Decisions
- Centralized generic runtime service wiring in `prepare_runtime_services(...)` so `run_workflow(...)` and `run_autoloop_v1(...)` share the same session store, checkpoint store, prompt registry, and event logger setup.
- Centralized generic max-step, session-path extraction, and resume validation in `autoloop_v3.runtime.runner` instead of keeping a parallel copy inside the parity harness.
