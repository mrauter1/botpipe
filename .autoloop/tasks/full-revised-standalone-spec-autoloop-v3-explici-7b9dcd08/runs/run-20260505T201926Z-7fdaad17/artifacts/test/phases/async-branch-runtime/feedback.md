# Test Author ↔ Test Auditor Feedback

- Task ID: full-revised-standalone-spec-autoloop-v3-explici-7b9dcd08
- Pair: test
- Phase ID: async-branch-runtime
- Phase Directory Key: async-branch-runtime
- Phase Title: Async Branch Runtime
- Scope: phase-local authoritative verifier artifact

- Added branch-runtime regression coverage for workflow-folder evidence reads in ordinary downstream steps, not just fan-in helpers.
- Recorded the phase coverage map in `test_strategy.md`, including concurrency, fail-fast cancellation, trace events, evidence-path assertions, flake controls, and deferred gaps.
- TST-001 `blocking` — `tests/contract/test_branch_group_runtime.py:606` and `tests/contract/test_branch_group_runtime.py:711` are the only `concurrency=1` branch-group cases in the suite, and both are Python-branch scenarios rather than provider-backed async execution. The original request explicitly requires runtime coverage that `parallel(..., concurrency=1)` works for an async provider, and `test_strategy.md` currently claims that edge case is covered even though no such test exists. Concrete missed-regression scenario: the branch-group scheduler could regress to rejecting or mishandling provider-backed `concurrency=1` runs while all current tests still pass, because the existing async-provider cases only exercise `concurrency > 1`. Minimal correction: add a provider-backed `parallel(..., concurrency=1)` regression test that asserts normal completion through the async provider path and preserves branch-group semantics without falling back to sync execution.
