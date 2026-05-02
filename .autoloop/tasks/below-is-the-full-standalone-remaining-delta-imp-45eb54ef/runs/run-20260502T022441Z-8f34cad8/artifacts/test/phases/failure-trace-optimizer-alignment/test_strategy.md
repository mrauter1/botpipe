# Test Strategy

- Task ID: below-is-the-full-standalone-remaining-delta-imp-45eb54ef
- Pair: test
- Phase ID: failure-trace-optimizer-alignment
- Phase Directory Key: failure-trace-optimizer-alignment
- Phase Title: Failure, Trace, And Optimizer Alignment
- Scope: phase-local producer artifact

## Coverage Map

- Typed failure carriers and no `getattr(exc, ...)` recovery:
  covered by focused engine-contract and provider-retry tests that assert structured `FailureContext`, retry-kind handling, and checkpoint persistence through typed execution errors.
- Trace/history distinction for provider routes vs hook direct controls:
  covered by runtime tracing/history tests plus contract tests for pre-provider `RequestInput`, `Goto`, `Fail`, and producer/verifier short-circuits.
- Optimizer normalization of final control vocabulary:
  covered by direct-runtime-control corpus tests and a provider `question` route case that keeps `route="question"` while still deriving `local_outcome="awaiting_input"` from the `AWAIT_INPUT` terminal.
- Runner/child summary propagation:
  covered by child-workflow workspace tests asserting paused child runs persist `pending_input` metadata and child `finalization` route/attempt fields.

## Preserved Invariants Checked

- Direct runtime controls remain distinct from route tags in optimizer observations.
- Provider `question` routes are not collapsed into `runtime_control:request_input`.
- Child-run metadata keeps stable shape for both `FINISH` and `AWAIT_INPUT` outcomes.

## Edge Cases / Failure Paths

- No-provider hook short-circuits remain covered by existing contract/history tests.
- Retry feedback still reads structured failure context when route/payload details are present.

## Known Gaps

- Child summary `finalization` for provider `question` routes currently omits `pending_input_id` and `terminal`; paused-child coverage asserts the emitted route and attempt fields without normalizing absent fields elsewhere.
- No new full-suite run in this phase; validation stays focused on the changed runtime and consumer surfaces.
