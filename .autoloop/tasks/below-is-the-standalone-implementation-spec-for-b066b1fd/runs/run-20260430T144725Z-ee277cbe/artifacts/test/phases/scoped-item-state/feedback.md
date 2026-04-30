# Test Author ↔ Test Auditor Feedback

- Task ID: below-is-the-standalone-implementation-spec-for-b066b1fd
- Pair: test
- Phase ID: scoped-item-state
- Phase Directory Key: scoped-item-state
- Phase Title: Implement Scoped Item State
- Scope: phase-local authoritative verifier artifact

- Added `tests/unit/test_simple_surface.py::test_simple_scoped_item_state_and_step_item_state_restore_on_resume` to exercise the repaired simple `step(..., item_state=...)` path through a real pause/resume cycle, including restored `item_state`, `step_item_state.visits`, `last_route`, and custom per-item fields.

- TST-001 | blocking | `tests/unit/test_simple_surface.py:560-633`
  The suite still has no negative prompt-validation test for an unknown `{step_name.item_state.*}` field. It covers `{item.state.missing}` and unscoped `item_state=...` rejection, but the validation branch for step-item-state field lookup only has happy-path assertions. A regression that stopped rejecting a typo such as `{review.item_state.attemps}` would now pass unnoticed even though AC-2 explicitly requires field validation for both `item.state.*` and `step.item_state.*`. Minimal correction: add a compile-time failure test mirroring the existing worklist item-state negative case, asserting that an unknown scoped `step.item_state` field raises `WorkflowValidationError`.
