# Test Author ↔ Test Auditor Feedback

- Task ID: recursive-framework-evolution-20260427t144615-bootstrap
- Pair: test
- Phase ID: engine-hooks-workflow-step
- Phase Directory Key: engine-hooks-workflow-step
- Phase Title: Engine Hooks And WorkflowStep
- Scope: phase-local authoritative verifier artifact

- Added workflow-step-specific hook regression coverage in `tests/contract/test_engine_contracts.py` for child-workflow `after` route override through the compiled `kind="workflow"` path. The new test currently exposes an implementation gap: when `after` reroutes the workflow step to `question`, the configured `child_result` output artifact is not present at step completion.
- TST-001 `non-blocking` The new red regression in `tests/contract/test_engine_contracts.py::test_workflow_step_after_hook_can_override_route_after_child_completion` is correctly aligned with the phase contract and should remain in place. Evidence: a focused run fails only on the missing `child_result` artifact after a workflow-step `after` override, which is exactly the unintended behavior this phase needs to catch.
