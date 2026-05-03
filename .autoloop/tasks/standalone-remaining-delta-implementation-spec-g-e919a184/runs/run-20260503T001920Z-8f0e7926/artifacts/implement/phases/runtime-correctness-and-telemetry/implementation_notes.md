# Implementation Notes

- Task ID: standalone-remaining-delta-implementation-spec-g-e919a184
- Pair: implement
- Phase ID: runtime-correctness-and-telemetry
- Phase Directory Key: runtime-correctness-and-telemetry
- Phase Title: Runtime Correctness And Telemetry
- Scope: phase-local producer artifact

## Files changed

- `autoloop/core/statuses.py`
- `autoloop/core/engine.py`
- `autoloop/core/engine_collaborators.py`
- `autoloop/core/history.py`
- `autoloop/runtime/runner.py`
- `autoloop/runtime/static_graph.py`
- `autoloop/runtime/workspace.py`
- `autoloop_optimizer/optimization.py`
- `tests/contract/test_engine_contracts.py`
- `tests/runtime/test_history.py`
- `tests/runtime/test_runtime_static_graph.py`

## Symbols touched

- `StepFinalizationRequest`, `PairProviderResult`, `RouteFinalizer.finalize`, `StepDispatcher.execute`
- `Engine._run_pair_step`, `Engine._update_final_step_runtime_state`
- `finalization_to_step_status`, `route_to_step_status`, `normalize_run_status`, `terminal_to_run_status`
- `_runtime_control_hook_locations`
- `route_is_input_request`, `route_is_replan`, `route_is_rework`, `runtime_control_to_terminal`

## Checklist mapping

- Milestone 3 / AC-1: added contract coverage that invalid direct controls preserve mutated session bindings in the failure checkpoint; runtime success paths keep using current mutated state/session rather than rollback snapshots.
- Milestone 3 / AC-2: centralized route/status/terminal classification in `autoloop.core.statuses` and routed history, runner, workspace, static-graph, and optimizer telemetry consumers through it.
- Milestone 3 / AC-2: preserved `source_hook` and `source_phase` on successful hook-selected and `python_step`-selected route finalizations so trace/history distinguish pre-provider short-circuits from provider-selected routes.
- Milestone 3 / AC-3: static graph now reports runtime-control-capable `before`, `before_producer`, and `before_verifier` hooks; scoped state surfaces themselves were already present and were left intact.

## Assumptions

- The built-in scoped `ctx.item_state` and `ctx.step_item_state` runtime models were already the baseline from earlier slices, so this phase focused on correctness of telemetry, finalization attribution, and failure preservation rather than redefining those models.
- Workspace-facing legacy `paused` normalization remains a compatibility read concern only; active runtime/history status derivation should use the centralized helpers.

## Preserved invariants

- Direct runtime controls still do not update `last_route`.
- Rework/replan counters still update only after successful route-based finalization.
- No route-effect behavior was reintroduced; runtime-control visibility continues to flow through hooks and `on_taken`.

## Intended behavior changes

- Successful route finalizations triggered by `before`, `before_producer`, `before_verifier`, `after_producer`, or `python_step` now keep hook source attribution in the final transition record.
- Runtime-control-capable pre-provider hooks are now surfaced in topology/static-graph metadata.
- Status, terminal, and route classification now use one shared helper module instead of duplicated per-consumer logic.

## Known non-changes

- Resume/topology mismatch behavior was not changed in this phase.
- No new scoped state models were introduced; this slice relied on the existing built-in item and step-item runtime state surfaces.

## Validation performed

- `python3 -m compileall autoloop autoloop_optimizer tests`
- `./.venv/bin/pytest tests/contract/test_engine_contracts.py -k 'before_hook_route_short_circuits_without_provider_and_preserves_candidate_route_none or before_verifier_route_short_circuits_verifier_and_preserves_candidate_route_none or invalid_goto_after_state_mutation_preserves_state_and_failure_context or invalid_goto_after_session_mutation_preserves_checkpoint_session_bindings'`
- `./.venv/bin/pytest tests/contract/test_engine_contracts.py -k 'before_hook_request_input_short_circuits_without_provider_and_preserves_last_route or before_producer_request_input_short_circuits_without_provider_and_preserves_last_route or before_verifier_request_input_short_circuits_verifier_and_checkpoints_pending_input'`
- `./.venv/bin/pytest tests/runtime/test_history.py -k 'runtime_control_terminal_for_status_and_route_metadata or marks_goto_runtime_control_as_completed or preserves_hook_selected_route_source_for_pre_step_short_circuit'`
- `./.venv/bin/pytest tests/runtime/test_runtime_static_graph.py -k 'topology_artifacts_include_state_surfaces_runtime_control_hook_locations_and_compile_report_details'`
- `./.venv/bin/pytest tests/unit/test_optimization_helpers.py -k 'preserves_direct_runtime_control_metadata or keeps_question_route_distinct_from_awaiting_input_terminal or list_selected_workflow_runs_filters_by_workflow_and_status'`
- `./.venv/bin/pytest tests/runtime/test_workspace_and_context.py -k 'list_run_records_normalizes_legacy_paused_status_for_public_filters'`
