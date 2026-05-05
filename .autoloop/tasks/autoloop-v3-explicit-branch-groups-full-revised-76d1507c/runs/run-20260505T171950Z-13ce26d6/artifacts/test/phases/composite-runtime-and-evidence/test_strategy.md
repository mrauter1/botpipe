# Test Strategy

- Task ID: autoloop-v3-explicit-branch-groups-full-revised-76d1507c
- Pair: test
- Phase ID: composite-runtime-and-evidence
- Phase Directory Key: composite-runtime-and-evidence
- Phase Title: Composite Runtime And Evidence
- Scope: phase-local producer artifact

## Behaviors Covered
- AC-1 composite barrier semantics:
  - `parallel(...)` without fan-in persists `_branch_groups/<group>/results.json` and `context.md`, keeps manifest branch order declaration-stable, and only routes after branch settlement.
  - `parallel(...)` with fan-in routes through the internal fan-in step while exposing `FanIn.results()` / `FanIn.context()` helper reads and `ctx.fan_in` metadata.
  - `parallel(..., settle="fail_fast", concurrency=1)` stops scheduling queued branches after the first hard failure and persists declaration-ordered `failed` / `skipped` branch results at the composite boundary.
- AC-2 branch result capture without parent cursor advancement:
  - branch `RequestInput` becomes branch manifest state and routes the composite to `question` only at the outer boundary.
  - branch `Goto` is recorded in manifest status/runtime-control/destination fields and does not advance the parent workflow to the branch target.
- AC-3 mechanical outcome routing:
  - `all_settled` returns `partial` for completed-but-non-success branch routes.
  - explicit `success_routes=("approved", "done")` upgrades the same settled branch set to `done`.
  - custom aggregator callbacks still receive the manifest/context path and control the composite event.

## Preserved Invariants Checked
- Fresh branch sessions remain branch-local and do not activate the parent session store.
- Branch artifact templates still root under the owning step directory and manifest artifact paths remain declaration-ordered.
- Concurrent branch execution does not guarantee provider callback interleaving order; the contract only asserts persisted branch evidence ordering.

## Edge Cases And Failure Paths
- Mixed successful and needs-input branches without fan-in.
- Completed branch direct control (`Goto`) captured without following the branch destination.
- Mixed settled branch outcomes under `all_settled` with and without explicit `success_routes`.
- Python-step branch hard failure handled through a custom outcome aggregator.
- `fail_fast` settlement with a leading hard failure and queued branches that must remain unscheduled.

## Flake Controls
- Mechanical-outcome provider responses are keyed off prompt text rather than invocation order so concurrent branch scheduling cannot swap expected route tags.
- Fan-out prompt assertions use unordered membership for provider callback observations while manifest assertions continue to enforce declaration order.
- `fail_fast` coverage uses `concurrency=1` so the contract asserts deterministic branch-admission stopping and persisted `skipped` results without depending on best-effort thread cancellation timing.

## Known Gaps
- Manifest/context write failure before fan-in remains covered indirectly by runtime behavior, not by an explicit fault-injection test here.
