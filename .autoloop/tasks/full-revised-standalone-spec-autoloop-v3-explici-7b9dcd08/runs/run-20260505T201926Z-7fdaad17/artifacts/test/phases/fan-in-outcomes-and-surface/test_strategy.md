# Test Strategy

- Task ID: full-revised-standalone-spec-autoloop-v3-explici-7b9dcd08
- Pair: test
- Phase ID: fan-in-outcomes-and-surface
- Phase Directory Key: fan-in-outcomes-and-surface
- Phase Title: Fan-In, Outcomes, Surface
- Scope: phase-local producer artifact

## Behavior-to-test coverage map
- AC-1 capture-only branch routing:
  - Existing contract coverage keeps branch `Goto` capture-only, skips `on_taken`, and prevents destination following.
- AC-2 fan-in orchestration/finalization:
  - Existing contract/runtime coverage keeps helper reads, fan-in route finalization, and composite-boundary resume behavior pinned.
  - Added tracing assertions to require `fan_in_started` / `fan_in_completed` to carry deterministic fan-in `step_execution_id`.
- AC-3 manifest/context shape and determinism:
  - Added context assertions for needs-input detail sections in question-path evidence.
  - Added fail-fast context assertions for failure/cancellation detail sections and declaration-order branch details.
  - Current targeted red test exposes that the new failure detail line is rendered under the wrong section boundary in `context.md`.
- AC-4 static graph/topology additive branch-group surfaces:
  - Added assertions for additive `outcome_policy`, `has_fan_in`, `default_chain_route`, and `rework_chain_route`.
  - Added mechanical-outcome coverage to ensure the additive fields work both with and without fan-in.
- AC-5 composite-boundary checkpoint/resume:
  - Existing contract coverage already pins fan-in request-input checkpointing and full-group resume semantics.

## Preserved invariants checked
- Branch manifest ordering remains declaration-stable.
- Additive tracing/static-graph assertions avoid snapshotting entire payloads so unrelated additive keys can still evolve.
- No timing-sensitive assertions were added; all new checks use persisted files or emitted trace payload fields.

## Edge cases and failure paths
- Fail-fast provider-backed cancellation path now also validates rendered context summary placement for failed/cancelled/skipped branches.
- Mechanical-outcome branch groups without fan-in now assert outcome-policy metadata explicitly.

## Known gaps
- The new fail-fast context test is intentionally red until implementation moves failure-detail lines under the failure-summary block instead of the cancellation-summary block.
