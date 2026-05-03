# Test Author ↔ Test Auditor Feedback

- Task ID: framework-authoring-flexibility-change-spec-goal-2ee572cd
- Pair: test
- Phase ID: route-interaction-policy
- Phase Directory Key: route-interaction-policy
- Phase Title: Route Policy Rebase
- Scope: phase-local authoritative verifier artifact

- Added `tests/unit/test_validation.py::test_core_control_routes_compile_provider_visibility_and_non_provider_defaults` to lock the core `ControlRoutes` seam, question visibility modes, and the absence of default injected control routes on Python/child steps.
- Added `tests/runtime/test_workspace_and_context.py::test_runner_full_auto_hides_default_question_route_from_provider_contract` to cover the `runtime.full_auto -> RuntimeInteractionPolicy` runner plumbing end-to-end.
- Updated `test_strategy.md` with a phase-specific behavior-to-coverage map, preserved invariants, failure paths, and validation gap notes.

Audit result:

- No blocking or non-blocking findings. The added tests close the runner-plumbing gap, preserve the explicit authored `failed` contract, and keep the new `ControlRoutes` seam covered at both core and simple authoring levels.
