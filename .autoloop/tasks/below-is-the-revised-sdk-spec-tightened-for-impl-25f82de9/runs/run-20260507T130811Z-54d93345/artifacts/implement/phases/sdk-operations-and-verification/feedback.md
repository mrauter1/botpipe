# Implement ↔ Code Reviewer Feedback

- Task ID: below-is-the-revised-sdk-spec-tightened-for-impl-25f82de9
- Pair: implement
- Phase ID: sdk-operations-and-verification
- Phase Directory Key: sdk-operations-and-verification
- Phase Title: Finish Operations And Verification
- Scope: phase-local authoritative verifier artifact

## Findings

### IMP-001 — blocking
Reference: `tests/unit/test_sdk_facade.py`

AC-2 calls for acceptance coverage over SDK `params`, pause handling, provider question policy, results, and standalone operations, but the current SDK-facing suite still does not exercise `Autoloop.run(..., params=...)` at all and never asserts the SDK’s failed-result mapping (`status="failed"`, `ok=False`) on a completed run. The runtime regression suite covers generic `ctx.params` behavior, but that does not verify the public SDK boundary that this phase was supposed to close. As written, a regression in SDK param coercion or result-status mapping could slip through while the phase still reports complete acceptance coverage.

Minimal fix direction: extend `tests/unit/test_sdk_facade.py` with SDK-level cases that (1) pass both mapping and `Workflow.Params` inputs through `client.run(...)` and assert they reach `ctx.params` without appearing on `ctx.input`, and (2) drive a workflow to `FAIL` and assert the returned `WorkflowResult` has the promised SDK status/ok mapping.

## Re-review

IMP-001 resolved on re-review. `tests/unit/test_sdk_facade.py` now covers SDK `params` via both mapping and `Workflow.Params` instances and directly asserts `FAIL` to `WorkflowResult(status="failed", ok=False)` mapping. No additional findings in phase-local scope.
