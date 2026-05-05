# Test Author ↔ Test Auditor Feedback

- Task ID: autoloop-v3-explicit-branch-groups-full-revised-76d1507c
- Pair: test
- Phase ID: composite-runtime-and-evidence
- Phase Directory Key: composite-runtime-and-evidence
- Phase Title: Composite Runtime And Evidence
- Scope: phase-local authoritative verifier artifact

- Added/confirmed branch-group contract coverage for no-fan-in question routing, fan-in helper exposure, fan-out branch-input/artifact/session behavior, branch `Goto` capture, `all_settled` success-route semantics, and custom outcome aggregation. Stabilized the concurrent cases by keying expected provider outcomes to prompt text and by asserting persisted evidence order rather than provider callback interleaving order.
- TST-001 `blocking` [tests/contract/test_branch_group_runtime.py]: The phase scope and AC-1 require declared settlement-policy coverage, but the contract file still has no explicit `settle=\"fail_fast\"` case and the active [test_strategy.md](./test_strategy.md) lists that gap openly. A regression in branch admission/cancellation/skip recording could ship unnoticed while this suite still passes because it only exercises the default settlement path. Add a deterministic `fail_fast` contract test that proves new branches stop being scheduled after the first hard failure and that cancelled/skipped branch results are persisted at the composite boundary.
- Added deterministic `fail_fast` contract coverage with `concurrency=1`: the leading hard-failure branch runs, queued branches remain unscheduled, and `_branch_groups/<group>/results.json` persists declaration-ordered `failed` / `skipped` results plus the `fail_fast` settlement tag. The test intentionally asserts `skipped` persistence rather than thread-cancellation timing.
- TST-002 `blocking` [tests/contract/test_branch_group_runtime.py, autoloop/core/branch_groups/runtime.py]: The phase contract still has no explicit fault-injection coverage for branch-group evidence write failure before fan-in or mechanical outcome routing, and [test_strategy.md](./test_strategy.md) still lists that gap. A regression where `write_branch_group_evidence(...)` partially fails but fan-in still runs, or where the composite routes onward after a failed `results.json` / `context.md` write, would silently violate AC-1 and the requested “fail before fan-in/outcome routing” behavior while this suite still passes. Add a deterministic test that forces evidence writing to fail and asserts the composite fails immediately without `fan_in_started` / downstream routing.
