# Test Author ↔ Test Auditor Feedback

- Task ID: recursive-framework-evolution-20260427t144615-bootstrap
- Pair: test
- Phase ID: simple-lowering
- Phase Directory Key: simple-lowering
- Phase Title: Simple Workflow Lowering
- Scope: phase-local authoritative verifier artifact

- TEST-001 | Added `tests/unit/test_simple_surface.py` coverage for `workflow_step(...)` edge and failure paths: `message_from` artifact loading, reserved child-question route mapping, and compile-time rejection of unknown `message_from` references. Updated `test_strategy.md` with the behavior-to-test coverage map and remaining intentional gaps.
- TST-001 | blocking | `tests/unit/test_simple_surface.py` still does not prove the generated `workflow_step(...)` handler maps child terminal failures and generic pauses back to the required parent routes. Evidence: the new coverage exercises the success branch and the `question` pause branch, but for failure semantics it only asserts that `compiled.routes["launch"]["failed"].target == "FAIL"` exists; there is no handler-level assertion that a child result with `terminal="FAIL"` yields `Event("failed")`, nor that a paused child without a `question` event yields `Event("blocked")`. Concrete missed-regression scenario: `_map_simple_workflow_child_result(...)` could regress to return `blocked` for every non-success child terminal and the current tests would still pass for the explicit `FAIL` path required by the phase request. Minimal correction: add direct generated-handler tests that inject fake child results for `terminal="FAIL"` and generic `terminal="PAUSE"`/non-question outcomes and assert the returned event tags are `failed` and `blocked` respectively.
