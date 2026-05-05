# Implement ↔ Code Reviewer Feedback

- Task ID: full-revised-standalone-spec-autoloop-v3-explici-7b9dcd08
- Pair: implement
- Phase ID: strictness-and-cleanup
- Phase Directory Key: strictness-and-cleanup
- Phase Title: Strictness and Cleanup
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 `blocking` — [tests/strictness/test_no_compat.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/strictness/test_no_compat.py:138): `test_branch_group_subsystem_does_not_reintroduce_forbidden_thread_backed_primitives()` only searches for exact string tokens like `threading.RLock` and `asyncio.to_thread`. A future regression such as `from threading import RLock; lock = RLock()` or `from asyncio import to_thread; await to_thread(...)` in `autoloop/core/branch_groups/**` or `autoloop/core/engine_collaborators.py` would bypass this guard while still violating AC-1. Minimal fix: strengthen the scan to match import forms as well as dotted references, preferably in one centralized helper for forbidden import/use patterns.

- IMP-002 `blocking` — [tests/contract/test_branch_group_runtime.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/contract/test_branch_group_runtime.py:1062) and [autoloop/core/branch_groups/manifest.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/branch_groups/manifest.py:15): the phase still does not cover the two distinct evidence-write failure cases required by the spec. Both current tests monkeypatch `write_branch_group_evidence()` to fail before either file is written, so there is no regression test for `results.json` failing independently from `context.md`, nor for `context.md` failing after `results.json` succeeds. That leaves AC-2 incomplete and risks silent drift in the fan-in/outcome short-circuit behavior around partial evidence writes. Minimal fix: add targeted tests that fail the first and second file write separately, ideally by intercepting the individual `Path.write_text()` calls inside `write_branch_group_evidence()`.

## Re-review

- Cycle 2 re-review: IMP-001 and IMP-002 are resolved. The strictness guard now catches imported and dotted forbidden forms in the branch-group execution path, the evidence-write matrix now distinguishes `results.json` failure from `context.md` failure, and the focused phase validation command passed with `250 passed`.
