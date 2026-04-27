# Test Strategy

- Task ID: recursive-framework-evolution-20260427t144615-bootstrap
- Pair: test
- Phase ID: engine-hooks-workflow-step
- Phase Directory Key: engine-hooks-workflow-step
- Phase Title: Engine Hooks And WorkflowStep
- Scope: phase-local producer artifact

## Behavior-to-test coverage map
- Provider-step hooks and route override:
  `tests/contract/test_engine_contracts.py::test_llm_step_before_and_after_hooks_run_in_order_and_after_can_override_route`
- System-step hooks and route override:
  `tests/contract/test_engine_contracts.py::test_system_step_hooks_can_override_route_after_candidate_validation`
- Workflow-step hooks, child completion, and route override:
  `tests/contract/test_engine_contracts.py::test_workflow_step_after_hook_can_override_route_after_child_completion`
- Workflow-step verifier rework loops and repeated hook execution per attempt:
  `tests/contract/test_engine_contracts.py::test_workflow_step_honors_hooks_and_can_participate_in_verifier_rework_loops`
- Invalid hook override and final-route required-output recomputation:
  `tests/contract/test_engine_contracts.py::test_after_hook_invalid_route_override_raises_routing_error`
  `tests/contract/test_engine_contracts.py::test_after_hook_route_override_recomputes_required_outputs`
- Workflow-step terminal mapping and lowering invariants:
  `tests/unit/test_simple_surface.py::test_simple_workflow_step_compiles_as_workflow_kind_and_generated_handler_invokes_child_workflow`
  `tests/unit/test_simple_surface.py::test_simple_workflow_step_child_question_maps_to_reserved_question_route`
  `tests/unit/test_simple_surface.py::test_simple_workflow_step_child_failure_maps_to_reserved_failed_route`
  `tests/unit/test_simple_surface.py::test_simple_workflow_step_child_pause_without_question_maps_to_reserved_blocked_route`
- Handoff regression for workflow-step targets:
  `tests/contract/test_engine_contracts.py::test_route_handoff_targeting_workflow_step_is_dropped_before_later_provider_step`
- Trace metadata for hook-driven route changes:
  `tests/runtime/test_runtime_tracing.py::test_runtime_trace_records_hook_route_override_metadata`

## Preserved invariants checked
- `before` runs before provider/system/child-workflow execution and can affect the same step attempt.
- `after` runs after candidate route selection and can change the final route without being treated as provider-attributable.
- Final-route required outputs are validated against the overridden route, not the provider-selected route.
- Lowered simple `workflow_step(...)` nodes still invoke child workflows through `ctx.invoke_workflow(...)` while compiling as `kind="workflow"`.
- Workflow-step configured child-result artifacts still exist by step completion even when the `after` hook changes the final route.
- Workflow-targeted route handoffs are dropped until explicit child-workflow handoff delivery exists.

## Edge cases and failure paths
- Invalid route overrides fail with `RoutingError`.
- Route override to a route with extra required outputs fails artifact validation.
- Child terminal `SUCCESS` / `FAIL` / `PAUSE(question|blocked)` map deterministically.
- Workflow-targeted handoffs do not leak into checkpoints after later step failure.

## Known gaps
- No dedicated test yet exercises explicit queued handoff delivery into child workflow invocations, because that behavior remains intentionally unsupported in this phase.
- Current implementation gap exposed by `tests/contract/test_engine_contracts.py::test_workflow_step_after_hook_can_override_route_after_child_completion`: when a workflow-step `after` hook reroutes to `question`, the configured `out=Json("child_result")` artifact is not written by step completion even though the phase contract requires workflow-step output artifacts when configured.
