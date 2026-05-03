# Implement ↔ Code Reviewer Feedback

- Task ID: framework-authoring-flexibility-change-spec-goal-2ee572cd
- Pair: implement
- Phase ID: effects-and-validation-helper
- Phase Directory Key: effects-and-validation-helper
- Phase Title: Effects And Validation Helper
- Scope: phase-local authoritative verifier artifact

- `IMP-001` `blocking` [autoloop/simple.py:498-526] `validation_step` emits `validation_step_passed` with `feedback_artifact=None`, but the phase contract explicitly requires both validation runtime events to carry the feedback artifact path alongside message/details. Any observer that relies on the pass event payload to locate the declared feedback artifact will get incomplete metadata even though the path is deterministic from the step declaration. Minimal fix: resolve the feedback handle before branching on `result.ok` and emit the same concrete artifact path in both `validation_step_passed` and `validation_step_failed_repairable`.

- Recheck (cycle 2): `IMP-001` is resolved. `validation_step` now emits the concrete feedback artifact path on both validation runtime events, and the contract expectation was updated to lock that behavior.
