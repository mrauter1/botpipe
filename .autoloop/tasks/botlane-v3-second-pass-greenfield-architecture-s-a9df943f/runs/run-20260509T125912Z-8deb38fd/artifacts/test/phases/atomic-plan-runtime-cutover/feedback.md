# Test Author ↔ Test Auditor Feedback

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: test
- Phase ID: atomic-plan-runtime-cutover
- Phase Directory Key: atomic-plan-runtime-cutover
- Phase Title: Atomic Plan Runtime Cutover
- Scope: phase-local authoritative verifier artifact

- Added regression coverage for the route-action cutover: `tests/unit/test_engine_route_actions.py` verifies the engine follows canonical `RouteAction` instead of legacy `destination` strings and rejects missing actions; `tests/contract/test_provider_turn_plan_adapter.py` now asserts `StepExecutionResult.action` matches `route_decision.action` and that the removed `finalization` field is absent. Focused validation for the new tests passed (`6 passed`), while a broader route/engine subset exposed two existing phase regressions in runtime code: `Engine._run_workflow_step(...)` still expects `ChildWorkflowStepPlan.step`, and `_ensure_named_artifacts_exist(...)` now surfaces `ArtifactId(...)` in the error message where existing tests still expect the artifact name string.
- TST-001 `blocking` — `tests/unit/test_engine_route_actions.py:65-96`, `tests/contract/test_provider_turn_plan_adapter.py:149-210`: the new direct regression guard only proves that `_handle_step_result(...)` follows `Continue.target_step` over a conflicting legacy `destination`. AC-2 requires the engine to consume canonical `RouteAction` for all control-flow branches, but there is still no equally direct mismatch test for terminal actions (`Finish`, `AwaitInput`, `FailAction`). Concrete missed-regression scenario: `_handle_step_result(...)` could regress to trust legacy `destination` for terminal cases while still passing the new provider-turn tests, because those tests only observe matching `route_decision`/`action` payloads and never force `destination` and `action` to disagree. Minimal correction: add narrow unit coverage that injects conflicting terminal `destination` versus `RouteAction` values into `_handle_step_result(...)` for at least one terminal branch, and preferably all three terminal branches, so the engine’s action-first behavior is protected across the full route loop surface.
