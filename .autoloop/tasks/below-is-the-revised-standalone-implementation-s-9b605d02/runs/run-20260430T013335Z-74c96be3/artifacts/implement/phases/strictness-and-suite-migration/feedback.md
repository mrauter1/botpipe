# Implement ↔ Code Reviewer Feedback

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: implement
- Phase ID: strictness-and-suite-migration
- Phase Directory Key: strictness-and-suite-migration
- Phase Title: Migrate Active Suites And Tighten Strictness
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 `blocking` — [tests/strictness/test_no_compat.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/strictness/test_no_compat.py:50) and [tests/unit/test_simple_surface.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_simple_surface.py:169) still exclude `tests/fixtures/toy_runtime_workflow.py` from the maintained strictness surface even though the fixture was migrated off the banned names and is no longer clearly quarantined as compatibility-only coverage. That leaves AC-1 unmet because the active scan is still excluding more than the explicit compatibility/migration boundary. Minimal fix: either remove `tests/fixtures/toy_runtime_workflow.py` from the exclusion/allow lists so it is scanned with the maintained tree, or move/rename it under an explicit compatibility or migration fixture path before keeping it excluded.

- IMP-002 `blocking` — The phase contract requires canonical verification plus targeted compatibility regressions, but [implementation_notes.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/below-is-the-revised-standalone-implementation-s-9b605d02/runs/run-20260430T013335Z-74c96be3/artifacts/implement/phases/strictness-and-suite-migration/implementation_notes.md:63) records only `py_compile` because `pydantic` and `pytest` are unavailable. That means AC-3 is still unproven and runtime/validation regressions from the internal rename remain unverified. Minimal fix: provision the test dependencies, run the canonical verification suite and the targeted compatibility/runtime suites required by the phase contract, and record the actual pass/fail results in the phase artifacts.
