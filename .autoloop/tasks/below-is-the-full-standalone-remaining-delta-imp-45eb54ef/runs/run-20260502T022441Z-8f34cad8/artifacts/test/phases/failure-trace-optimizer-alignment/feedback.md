# Test Author ↔ Test Auditor Feedback

- Task ID: below-is-the-full-standalone-remaining-delta-imp-45eb54ef
- Pair: test
- Phase ID: failure-trace-optimizer-alignment
- Phase Directory Key: failure-trace-optimizer-alignment
- Phase Title: Failure, Trace, And Optimizer Alignment
- Scope: phase-local authoritative verifier artifact

- Added targeted regression coverage for optimizer normalization of provider `question` routes versus `AWAIT_INPUT` terminals, and for child-run finalization metadata when a child workflow pauses for input.
- `TST-001` `blocking`: [tests/runtime/test_workspace_and_context.py] now hard-codes paused child-run `finalization["pending_input_id"]` and `finalization["terminal"]` as `None` for a provider `question` route. That bakes the current omission into expected behavior instead of treating it as a gap, so the test will both miss regressions on those fields and actively fail if the runtime consumer is later corrected to carry the pending-input id / `AWAIT_INPUT` terminal consistently. Minimal correction: stop asserting those fields as `None`; either leave them unspecified in this test, or coordinate with implementation to expose them and then assert the concrete values.
- Follow-up: narrowed the paused-child `finalization` assertion to stable route and attempt-attribution fields only, so the test no longer encodes missing `pending_input_id` / `terminal` fields as intended behavior.
- `TST-002` `non-blocking`: Re-audit after the follow-up found no remaining blocking issues. The optimizer `question`-route coverage and the paused-child finalization assertions now protect the scoped behavior without freezing the current implementation gap into the expected contract.
