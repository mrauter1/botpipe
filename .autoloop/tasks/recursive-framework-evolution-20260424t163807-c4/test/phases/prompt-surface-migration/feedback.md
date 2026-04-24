# Test Author ↔ Test Auditor Feedback

- Task ID: recursive-framework-evolution-20260424t163807-c4
- Pair: test
- Phase ID: prompt-surface-migration
- Phase Directory Key: prompt-surface-migration
- Phase Title: Migrate Prompt Files
- Scope: phase-local authoritative verifier artifact

- Added prompt README and prompt-body contract coverage to the four previously uncovered front-door suites: `test_workflow_builder_package.py`, `test_task_to_candidate_workflow_set.py`, `test_task_to_workflow_strategy.py`, and `test_candidate_workflow_to_adapted_execution_plan.py`.
- New assertions pin the migrated markdown contract surface and explicit suite-local route/artifact markers while rejecting legacy `Read these artifacts` / `Write these artifacts` scaffolding.
- Validation: focused slice `75 passed`; full scoped prompt-surface slice plus baseline docs `238 passed`.
- TST-000 | non-blocking | No additional audit findings. The new tests cover the previously missing front-door prompt families, keep assertions deterministic, and preserve the phase boundary by validating markdown contract markers rather than normalizing runtime or workflow behavior changes.
