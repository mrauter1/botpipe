# Test Author ↔ Test Auditor Feedback

- Task ID: autoloop-v3-explicit-branch-groups-full-revised-76d1507c
- Pair: test
- Phase ID: composite-runtime-and-evidence
- Phase Directory Key: composite-runtime-and-evidence
- Phase Title: Composite Runtime And Evidence
- Scope: phase-local authoritative verifier artifact

- Added/confirmed branch-group contract coverage for no-fan-in question routing, fan-in helper exposure, fan-out branch-input/artifact/session behavior, branch `Goto` capture, `all_settled` success-route semantics, and custom outcome aggregation. Stabilized the concurrent cases by keying expected provider outcomes to prompt text and by asserting persisted evidence order rather than provider callback interleaving order.
- TST-001 `blocking` [tests/contract/test_branch_group_runtime.py]: The phase scope and AC-1 require declared settlement-policy coverage, but the contract file still has no explicit `settle=\"fail_fast\"` case and the active [test_strategy.md](./test_strategy.md) lists that gap openly. A regression in branch admission/cancellation/skip recording could ship unnoticed while this suite still passes because it only exercises the default settlement path. Add a deterministic `fail_fast` contract test that proves new branches stop being scheduled after the first hard failure and that cancelled/skipped branch results are persisted at the composite boundary.
