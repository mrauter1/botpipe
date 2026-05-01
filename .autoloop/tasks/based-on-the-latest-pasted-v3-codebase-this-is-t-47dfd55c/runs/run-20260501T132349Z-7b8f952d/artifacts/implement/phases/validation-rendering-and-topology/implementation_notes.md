# Implementation Notes

- Task ID: based-on-the-latest-pasted-v3-codebase-this-is-t-47dfd55c
- Pair: implement
- Phase ID: validation-rendering-and-topology
- Phase Directory Key: validation-rendering-and-topology
- Phase Title: Validation Rendering And Topology
- Scope: phase-local producer artifact

## Files changed
- `core/validation.py`
- `core/providers/models.py`
- `core/providers/rendering.py`
- `core/engine.py`
- `runtime/static_graph.py`
- `tests/unit/test_validation.py`
- `tests/unit/test_provider_boundary_core.py`
- `tests/runtime/test_runtime_static_graph.py`

## Symbols touched
- `_validate_step_hooks`
- `ProviderRoute`
- `_routes_for_step`
- `_visible_routes`
- `workflow_static_step_graph_payload`
- `workflow_topology_payload`
- `write_topology_artifacts`
- `_route_table_text`
- `_compile_report_text`

## Checklist mapping
- Phase 5 / AC-1: removed AST-based hook return inference from validation and kept hook validation at callable/signature level only.
- Phase 5 / AC-2: extended provider/static rendering so provider prompts exclude hidden routes while topology/static artifacts include hidden routes, explicit/effective required writes, state surfaces, and runtime-control hook locations.

## Assumptions
- Internal `on_route` remains an existing runtime hook surface for this phase even though the public authoring surface already removed it.
- Additive artifact payload fields are acceptable under the existing schema ids for this phase because reader/schema hardening was handled in the earlier metadata phase.

## Preserved invariants
- Existing run-start artifact generation path in `runtime.tracing` remains unchanged.
- Hidden routes remain runtime-legal and continue to appear in topology/static artifacts.
- Runtime, not compile-time, remains the authority for validating concrete hook return values.

## Intended behavior changes
- Validation no longer rejects hooks by inspecting source for route/event/handoff returns.
- Provider prompt rendering drops routes marked `provider_visible=False` even if such routes are present in the input contract.
- Static artifacts now expose terminals, worklist item-state surfaces, step-item-state surfaces, route-local hooks, and runtime-control hook locations.

## Known non-changes
- No engine collaborator decomposition or module split was introduced in this phase.
- No prompt-registry or optimizer-boundary work was attempted here.
- No schema id/version bump was added for these artifact payload enrichments.

## Expected side effects
- Topology/route-table/compile-report payloads are richer and include extra rows/columns for global routes and route-local hooks.
- Tests that relied on static hook-source rejection were replaced with compile-success coverage plus existing runtime-validation coverage.

## Validation performed
- `python3 -m compileall core/validation.py core/providers/models.py core/providers/rendering.py core/engine.py runtime/static_graph.py tests/unit/test_validation.py tests/unit/test_provider_boundary_core.py tests/runtime/test_runtime_static_graph.py`
- `./.venv/bin/pytest tests/unit/test_validation.py tests/unit/test_provider_boundary_core.py tests/runtime/test_runtime_static_graph.py -q`

## Deduplication / centralization decisions
- Centralized provider hidden-route filtering in `core.providers.rendering` as a defensive last-mile render guard in addition to the engine contract builder.
- Centralized static artifact enrichment in `runtime/static_graph.py` helper payload builders so topology, static graph, route table, state contracts, and compile report stay derived from the same compiled route/state inventory.
