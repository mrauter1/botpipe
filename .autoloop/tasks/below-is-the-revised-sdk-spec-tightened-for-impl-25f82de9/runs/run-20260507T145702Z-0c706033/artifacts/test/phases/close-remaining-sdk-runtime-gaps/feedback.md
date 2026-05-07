# Test Author ↔ Test Auditor Feedback

- Task ID: below-is-the-revised-sdk-spec-tightened-for-impl-25f82de9
- Pair: test
- Phase ID: close-remaining-sdk-runtime-gaps
- Phase Directory Key: close-remaining-sdk-runtime-gaps
- Phase Title: Close Remaining SDK/Runtime Contract Gaps
- Scope: phase-local authoritative verifier artifact

- Added focused regression coverage for `ctx.input.message` without typed input, with typed input present, through workflow-step child message rendering, and through strict `ChildWorkflowStep` SDK dispatch plus unresolved-reference failure. Reran `.venv/bin/python -m pytest -q tests/unit/test_primitives_and_stores.py tests/contract/test_engine_contracts.py tests/unit/test_sdk_facade.py` with `277 passed`.
- TST-001 | blocking | `tests/unit/test_sdk_facade.py:412-445` adds the new strict `ChildWorkflowStep` success and unresolved-reference failure checks, but the same changed preflight path still has an explicit preserved rejection for worklist-scoped declarations and there is no SDK regression asserting that behavior. Because AC-3 and the phase scope explicitly keep scoped child-workflow declarations rejected, a regression that accidentally permits `client.step(ChildWorkflowStep(..., scope=\"items\"))` would now pass this focused slice. Add a focused SDK facade test that constructs a scoped strict `ChildWorkflowStep` (or another scoped step declaration on the same path) and asserts `SDKExecutionError` with the existing `worklist-scoped` rejection message.
