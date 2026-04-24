# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260424t163807-c4
- Pair: implement
- Phase ID: prompt-surface-migration
- Phase Directory Key: prompt-surface-migration
- Phase Title: Migrate Prompt Files
- Scope: phase-local authoritative verifier artifact

- PSM-001 | non-blocking | `tests/runtime/test_workflow_builder_package.py`, `tests/runtime/test_task_to_candidate_workflow_set.py`, `tests/runtime/test_task_to_workflow_strategy.py`, `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`: These four scoped families were migrated to the new prompt-body contract, but their runtime suites still do not assert the new prompt markers (`## Step Contract`, `## Artifact Contract`, `| Artifact | Direction | Notes |`, `## Output Requirements`). The later six scoped families do pin those markers, so regressions back to the older scaffolding style would now slip through only for the builder and selected-workflow front-door families. Minimal fix direction: add the same prompt-marker assertions used by the later six suites here as well, ideally through one small shared helper so the marker list stays centralized.
