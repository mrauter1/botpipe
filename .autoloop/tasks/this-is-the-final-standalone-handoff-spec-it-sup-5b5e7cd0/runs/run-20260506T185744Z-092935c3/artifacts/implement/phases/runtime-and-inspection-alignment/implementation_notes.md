# Implementation Notes

- Task ID: this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0
- Pair: implement
- Phase ID: runtime-and-inspection-alignment
- Phase Directory Key: runtime-and-inspection-alignment
- Phase Title: Align Runtime And Reporting
- Scope: phase-local producer artifact

## Files changed
- `autoloop/core/engine.py`
- `autoloop/core/compiler.py`
- `autoloop/core/workflow_capabilities.py`
- `autoloop/runtime/static_graph.py`
- `autoloop/core/route_reporting.py`
- `tests/contract/test_engine_contracts.py`
- `tests/runtime/test_runtime_static_graph.py`
- `.../decisions.txt`

## Symbols touched
- `Engine._map_workflow_step_result`
- `_topology_hash_payload`, `_topology_hash_step_payload`, `_topology_hash_route_payload`
- `WorkflowRouteCapability`, `WorkflowStepCapability`, `WorkflowCapabilityEntry`
- `workflow_capability_payload`, `selected_workflow_decomposition_surface_payload`
- `_compiled_routes`, `_compiled_step_capability`, `_route_capability_payload`
- `workflow_static_step_graph_payload`, `workflow_topology_payload`
- `_internal_route_payload`, `_topology_route_payload`
- `_route_table_text`, `_compile_report_text`, `_route_view_payload`, `_step_route_view_line`
- new helper module `autoloop/core/route_reporting.py`

## Checklist mapping
- Runtime projection updates for `Outcome.route_fields`: completed via child-workflow await-input projection update and preserved `Outcome`/`Event` compatibility fields.
- Inspection / compile-report / route-table alignment: completed via compiled-route metadata, schema contracts, suppressed-route exposure, and hook-location reporting.
- Topology-hash/reporting alignment: completed via explicit payload/route-fields schema fingerprint fields in topology payload hashing.
- Persisted-reader compatibility: preserved additively by keeping existing filenames plus legacy `runtime_control_routes` and `runtime_control_hook_locations` fields.

## Assumptions
- Persisted JSON readers may still depend on existing top-level keys, so new inspection data was added instead of replacing legacy compatibility views.
- Question-style child workflow pauses should project through `Event.question` even when the child route tag is not literally `question`.

## Preserved invariants
- Route finalization, after hooks, on_taken hooks, handoffs, redirects, and required-write enforcement were not redesigned.
- `ctx.outcome.payload` remains intact; new reporting metadata is additive.
- Legacy `runtime_control_routes` and `runtime_control_hook_locations` remain derived compatibility fields, not an independent legality mechanism.

## Intended behavior changes
- Child workflow `AWAIT_INPUT` results now map to parent `question` routing based on projected `Event.question`, not only on the literal child tag name.
- Static graph, topology payloads, compile report, route table, and workflow capability payloads now expose compiled-route schema contracts, fingerprints, inheritance source, provider visibility mode, and suppressed-route state.
- Step inspection surfaces now report provider-response schema fallback status for interactive and full-auto route sets.

## Known non-changes
- Provider prompt rendering and provider-side validation logic were not modified in this phase.
- Legacy checkpoint `pending_question` compatibility remains unchanged.
- Existing `routes` and `global_routes` target maps remain present for compatibility; richer compiled metadata was added alongside them.

## Expected side effects
- Human-readable `route_table.md`, `compile_report.md`, and `topology.mmd` outputs now use compiled-route metadata terminology instead of authored/runtime-control as the primary view.
- Capability snapshots gain `compiled_routes`, `compiled_global_routes`, `provider_response_contracts`, and schema contract metadata.

## Validation performed
- `python3 -m py_compile autoloop/core/route_reporting.py autoloop/core/engine.py autoloop/runtime/static_graph.py autoloop/core/workflow_capabilities.py autoloop/core/compiler.py tests/runtime/test_runtime_static_graph.py tests/contract/test_engine_contracts.py`
- Attempted `python -m pytest` / `python3 -m pytest` for focused suites, but `pytest` is not installed in this environment.

## Deduplication / centralization
- Centralized schema-name/fingerprint/fallback reporting logic in `autoloop/core/route_reporting.py` so runtime artifacts, workflow capability inspection, and topology hashing share one contract view.
