# Implementation Notes

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: implement
- Phase ID: strictness-cleanup
- Phase Directory Key: strictness-cleanup
- Phase Title: Strictness And Cleanup
- Scope: phase-local producer artifact

## Files changed

- Added `tests/strictness/test_no_internal_compat_layers.py`
- Deleted `tests/strictness/test_no_compat.py`
- Updated `tests/strictness/test_botlane_identity.py`
- Updated `tests/contract/test_single_step_plan_equivalence.py`
- Updated `tests/contract/engine/test_hooks.py`
- Updated `tests/contract/engine/test_worklists.py`
- Updated `tests/unit/test_execution_frame_context_parity.py`
- Updated `tests/unit/test_validation.py`
- Updated `botlane/core/context.py`
- Updated `botlane/core/engine.py`
- Updated `botlane/core/engine_collaborators.py`
- Updated `botlane/core/branch_groups/runtime.py`
- Updated `botlane/core/route_required_writes.py`
- Updated `botlane/core/workflow_plan.py`
- Updated `botlane/core/workflow_capabilities.py`
- Updated `botlane/runtime/static_graph.py`

## Symbols touched

- Strictness: `test_no_internal_compat_layers`, identity token scan, stale single-step test variable rename
- Context/frame facade: `_sync_state`, `_sync_artifacts`, `_sync_values`, `_sync_route`, `_sync_event`, `_sync_outcome`, `_sync_meta`, `_sync_step_state`, `_sync_item_state`, `_sync_step_item_state`, `_sync_active_worklist`, `_sync_selection_snapshots`, `_sync_worklist_selection`
- Route/runtime serialization: `WorkflowPlan.route`, `Engine._ensure_named_artifacts_exist`, `Engine._artifact_reference_display_name`, `route_required_write_payload`
- Inspection/static graph: `_step_route_table`, `_step_available_route_tags`, `_step_runtime_control_route_tags`, `_step_provider_visible_route_tags`, `_surface_ref_payload`

## Checklist mapping

- Strictness tests added: `tests/strictness/test_no_internal_compat_layers.py`, `tests/strictness/test_core_runtime_boundary.py`, `tests/strictness/test_botlane_identity.py`
- Adapter-era cleanup: removed `tests/strictness/test_no_compat.py`; updated stale compiled-shape assertions in validation, engine, optimizer, and single-step tests
- Final full suite: `.venv/bin/python -m pytest -q`

## Assumptions

- Phase 8 can include adjacent regression fixes when they are required to keep preserved public/runtime behavior green under the final suite.
- JSON-facing capability/selected-workflow payloads must keep string artifact references even though internal plans now store typed `ArtifactId` / `ExternalRead` values.

## Preserved invariants

- Public Botlane exports and SDK behavior unchanged
- Strictness scans target maintained Python sources only; deleted internals are not reintroduced
- Global/step route reporting remains JSON-safe and user-facing
- Runtime/context state still flows through `ExecutionFrame`; public `Context` no longer exposes the tested `_set_*` mutator names

## Intended behavior changes

- None at the public API level
- Internal `WorkflowPlan.route(...)` now correctly treats disabled step-local routes as suppressing same-tag global fallthrough

## Known non-changes

- `tests/strictness/test_core_runtime_boundary.py` logic remained structurally the same because it already enforced the required AST boundary
- No new architecture changes beyond phase-local cleanup and regression fixes

## Expected side effects

- Capability and selected-workflow snapshot artifacts serialize typed plan references back to their public string forms
- Missing-artifact runtime errors now mention the user-facing artifact name instead of raw `ArtifactId(...)` reprs

## Validation performed

- `.venv/bin/python -m pytest -q tests/strictness/test_no_internal_compat_layers.py tests/strictness/test_core_runtime_boundary.py tests/strictness/test_botlane_identity.py`
- `.venv/bin/python -m pytest -q tests/unit/test_primitives_and_stores.py::test_public_context_hides_runtime_mutators tests/contract/engine/test_routes.py::test_produce_verify_step_verifier_requires_fail_before_verifier_when_declared tests/runtime/test_runtime_static_graph.py::test_branch_group_payloads_are_additive_in_static_graph_and_topology tests/runtime/test_runtime_static_graph.py::test_topology_payload_keeps_explicit_global_route_required_writes_concrete tests/contract/engine/test_worklists.py::test_prompt_runtime_reports_missing_item_state_field_with_placeholder_context tests/contract/engine/test_hooks.py::test_workflow_step_honors_hooks_and_can_participate_in_verifier_rework_loops`
- `.venv/bin/python -m pytest -q tests/contract/engine/test_hooks.py::test_workflow_step_honors_hooks_and_can_participate_in_verifier_rework_loops tests/contract/engine/test_worklists.py::test_prompt_runtime_reports_missing_item_state_field_with_placeholder_context tests/unit/test_validation.py tests/runtime/test_runtime_static_graph.py tests/unit/optimizer/test_portfolio_helpers.py::test_portfolio_helpers_keep_catalog_snapshot_lightweight_and_capability_snapshot_rich tests/unit/optimizer/test_selected_workflow_helpers.py`
- `.venv/bin/python -m pytest -q tests/unit/test_validation.py::test_route_helper_defaults_and_global_suppression_compile_from_route_metadata tests/unit/optimizer/test_portfolio_helpers.py::test_portfolio_helpers_keep_catalog_snapshot_lightweight_and_capability_snapshot_rich tests/unit/optimizer/test_selected_workflow_helpers.py`
- `.venv/bin/python -m pytest -q`

## Deduplication / centralization

- Reused one `_surface_ref_payload` serializer for capability and selected-workflow inspection payloads instead of allowing multiple JSON writers to learn typed artifact refs independently
- Reused step-route fallback helpers in `runtime/static_graph.py` so nested branch/fan-in steps report routes without reopening compiled compatibility layers
