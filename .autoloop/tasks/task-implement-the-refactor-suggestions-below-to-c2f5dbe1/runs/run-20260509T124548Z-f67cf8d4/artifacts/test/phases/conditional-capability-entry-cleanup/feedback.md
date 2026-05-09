# Test Author ↔ Test Auditor Feedback

- Task ID: task-implement-the-refactor-suggestions-below-to-c2f5dbe1
- Pair: test
- Phase ID: conditional-capability-entry-cleanup
- Phase Directory Key: conditional-capability-entry-cleanup
- Phase Title: Conditional Workflow Capability Entry Cleanup
- Scope: phase-local authoritative verifier artifact

## Summary

- No repository test files were changed because hotspot 9 remained deferred and the phase contract forbids standalone churn in `botlane/core/workflow_capabilities.py`.
- Updated `test_strategy.md` with the explicit deferment coverage map, preserved invariants, activation criteria for future focused parity tests, and the current validation constraint.
- Validation result: `py_compile` passed for `botlane/core/workflow_capabilities.py` and `tests/runtime/test_workflow_reference_resolution.py`; targeted pytest collection is currently blocked by an unrelated `botlane.sdk` → `botlane.core.context.context_runtime` import error.

## Findings

- TST-001 `non-blocking`: The documented capability-inspection regression path is currently not runnable because `tests/runtime/test_workflow_reference_resolution.py` fails during collection on an unrelated `botlane.sdk` import chain (`context_runtime` missing from `botlane.core.context`). This does not block the deferred hotspot-9 phase because no source behavior changed, but it does reduce the immediacy of revalidation when that slice activates later. Minimal correction: when the broader import drift is addressed, rerun this focused test path or isolate future hotspot-9 tests from the `botlane.sdk` import surface the same way the runtime/discovery phase used a local stub.
