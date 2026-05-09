# Implementation Notes

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: implement
- Phase ID: route-authority-cutover
- Phase Directory Key: route-authority-cutover
- Phase Title: Make WorkflowPlan Sole Route Authority
- Scope: phase-local producer artifact

## Files Changed

- `botlane/core/compiler.py`
- `botlane/core/engine.py`
- `botlane/core/engine_collaborators.py`
- `botlane/core/route_contracts.py`
- `botlane/core/route_required_writes.py`
- `botlane/core/step_plans.py`
- `botlane/core/workflow_capabilities.py`
- `botlane/runtime/static_graph.py`
- `tests/contract/test_async_step_dispatcher.py`
- `tests/runtime/test_package_cli.py`
- `tests/strictness/test_no_internal_compat_layers.py`
- `tests/unit/test_simple_surface.py`
- `tests/unit/test_step_plans.py`
- `tests/unit/test_validation.py`

## Symbols Touched

- `_compile_steps`
- `_compile_branch_group_internal_steps`
- `_compile_branch_group_internal_step`
- `_topology_hash_payload`
- `Engine._route_table_for_step`
- `Engine._compiled_route_for_step`
- `Engine._ensure_child_workflow_route_declared`
- `ProviderContractBuilder.available_routes`
- `available_route_tags`
- `available_route_tags_for_table`
- `compiled_route_tags`
- `compiled_route_tags_for_table`
- `suppressed_route_tags`
- `suppressed_route_tags_for_table`
- `runtime_control_route_tags_for_table`
- `provider_visible_route_tags_for_table`
- `effective_route_required_writes_map`
- `PromptStepPlan`
- `ProduceVerifyStepPlan`
- `PythonStepPlan`
- `ChildWorkflowStepPlan`
- `BranchGroupStepPlan`
- `test_maintained_python_sources_do_not_reintroduce_step_owned_route_table_symbols`
- `_step_capability`
- `_internal_step_surface_payload`
- `_step_available_route_tags`
- `_route_table_text`

## Checklist Mapping

- Milestone 1 / route authority: completed.
- AC-1: completed by removing step-owned `_route_table` storage and moving nested branch-group routes into `WorkflowPlan.routes`.
- AC-2: completed by rewiring engine lookup, provider-contract export, static-graph payloads, workflow capability export, and tests to derive route views from `WorkflowPlan.routes` / `WorkflowPlan.global_routes`.
- AC-3: completed by AST-backed strictness coverage for `_route_table` / `_effective_route_table` symbols and by tests asserting route views through plan helpers.
- Milestones 2-4: intentionally deferred; out of active phase scope.

## Assumptions

- Internal branch and fan-in steps are part of the canonical route authority even though they remain absent from `WorkflowPlan.steps`.
- Top-level user-facing route summaries should continue to enumerate only externally addressable workflow steps, not nested branch internals.

## Preserved Invariants

- Public route behavior, route ordering, and route visibility remain unchanged for top-level workflow execution.
- Branch-group composite route ordering is preserved for available-route views.
- Global-route fallback behavior still resolves through the compiled plan rather than step-local copies.
- `botlane.__all__`, `botlane.core.__all__`, `.botlane` identity, and public SDK behavior were not changed.

## Intended Behavior Changes

- Internal-only: branch and fan-in step route tables now live in `WorkflowPlan.routes` so nested runtime and inspection surfaces use the same route authority as top-level steps.

## Known Non-Changes

- No service-boundary cutover work.
- No `Botlane.step(...)` canonicalization work.
- No `StepExecutionResult` transition/finalization removal.

## Expected Side Effects

- Internal contract tests that previously asserted branch substeps were absent from `WorkflowPlan.routes` now expect their route tables there.
- Public top-level capability/static-graph route listings still filter to top-level compiled steps to avoid leaking nested internal step rows.

## Deduplication / Centralization

- Route-tag helpers were centralized in `botlane/core/route_contracts.py` so maintained consumers read plan-backed route data instead of duplicating step-local fallbacks.
- Workflow capability export now reuses the shared route-contract table helpers instead of maintaining a second copy of available/provider-visible/runtime-control derivation.
- Branch-group nested route compilation now registers internal route tables once during compilation and reuses them across runtime and inspection surfaces.

## Validation Performed

- Focused suite:
  `.venv-test/bin/python -m pytest -q tests/unit/test_step_plans.py tests/unit/test_route_contracts.py tests/unit/test_validation.py tests/unit/test_simple_surface.py tests/runtime/test_runtime_static_graph.py tests/runtime/test_package_cli.py tests/strictness/test_no_internal_compat_layers.py tests/contract/engine/test_routes.py`
- Capability/runtime follow-up:
  `.venv-test/bin/python -m pytest -q tests/unit/optimizer/test_portfolio_helpers.py tests/unit/optimizer/test_selected_workflow_helpers.py tests/runtime/test_package_cli.py tests/contract/engine/test_core_contracts.py tests/contract/test_branch_result_runtime.py`
- Full suite:
  `.venv-test/bin/python -m pytest -q`
- Result:
  `1279 passed, 1 warning`
