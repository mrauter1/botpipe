# Implement ↔ Code Reviewer Feedback

- Task ID: autoloop-v3-explicit-branch-groups-full-revised-76d1507c
- Pair: implement
- Phase ID: composite-runtime-and-evidence
- Phase Directory Key: composite-runtime-and-evidence
- Phase Title: Composite Runtime And Evidence
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` [autoloop/core/branch_groups/outcomes.py:47](../../../../../../../../../../autoloop/core/branch_groups/outcomes.py:47), [tests/contract/test_branch_group_runtime.py:233](../../../../../../../../../../tests/contract/test_branch_group_runtime.py:233): `_all_settled()` ignores `success_routes` and returns `done` for any fully completed set of branches whose routes are not `failed`/`blocked`. That violates AC-3 and the spec's non-success handling: a branch group such as `parallel(outcome="all_settled")` with a branch route like `approved` and default `success_routes=("done", "accepted")` currently resolves `done` instead of `partial`. Minimal fix: centralize the non-success predicate around `branch_is_success(..., success_routes=spec.success_routes)` (or an equivalent shared helper) so `all_settled` treats completed-but-non-success routes as partial, then extend the mechanical-outcome contract test to cover a completed non-success route instead of only the existing `blocked` case.
