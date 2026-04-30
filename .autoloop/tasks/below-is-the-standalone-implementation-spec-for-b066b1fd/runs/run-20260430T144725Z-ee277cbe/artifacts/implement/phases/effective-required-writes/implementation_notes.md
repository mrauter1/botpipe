# Implementation Notes

- Task ID: below-is-the-standalone-implementation-spec-for-b066b1fd
- Pair: implement
- Phase ID: effective-required-writes
- Phase Directory Key: effective-required-writes
- Phase Title: Normalize Effective Required Writes
- Scope: phase-local producer artifact

## Files Changed
- `core/route_required_writes.py`
- `core/compiler.py`
- `core/engine.py`
- `core/providers/models.py`
- `core/providers/rendering.py`
- `runtime/static_graph.py`
- `tests/contract/test_canonical_runtime_contracts.py`
- `tests/runtime/test_runtime_static_graph.py`
- `tests/unit/test_provider_boundary_core.py`
- `tests/unit/test_validation.py`

## Symbols Touched
- `explicit_route_required_writes`
- `effective_route_required_writes`
- `effective_route_required_writes_map`
- `route_required_write_payload`
- `Engine._required_output_artifacts`
- `Engine._route_required_writes_for_step`
- `Engine._routes_for_step`
- `ProviderRoute.explicit_required_writes`
- `workflow_topology_payload`
- `workflow_static_step_graph_payload`
- `_topology_route_payload`
- `_route_table_text`

## Checklist Mapping
- Phase 5 / preserve `None` vs `[]`: implemented via shared helper plus `explicit_required_writes` payloads.
- Phase 5 / render explicit and effective writes in provider and topology outputs: implemented in provider rendering, topology payloads, static graph payloads, and `route_table.md`.
- Phase 5 / validate final route using effective writes: runtime now calls the shared helper from artifact validation.

## Assumptions
- Global fallback routes without an explicit override continue to inherit artifact-level required writes for the current step, matching the runtime formula in the phase spec.

## Preserved Invariants
- `CompiledRoute.required_writes` remains the normalized explicit route-level tuple surface.
- `required_writes=[]` still overrides artifact-level required defaults to “no required writes”.
- Producer turns still expose no route contract.

## Intended Behavior Changes
- Provider contracts now expose effective required writes through `route_required_writes` and retain explicit route overrides separately.
- `topology.json`, static graph route payloads, and `route_table.md` now distinguish inherited required writes from explicit empty overrides.

## Known Non-Changes
- No hook-routing behavior changed.
- No history/telemetry behavior changed.
- No workflow-capability payload changes were made outside the scoped runtime/topology surfaces.

## Expected Side Effects
- `topology_hash` changes for workflows because route payloads now include explicit and effective required-write metadata.
- Rendered provider route tables now have explicit/effective required-write columns.

## Validation Performed
- `.venv/bin/python -m pytest tests/unit/test_validation.py tests/unit/test_provider_boundary_core.py tests/contract/test_canonical_runtime_contracts.py tests/runtime/test_runtime_static_graph.py`
- `.venv/bin/python -m pytest tests/contract/test_engine_contracts.py::test_llm_requests_include_step_control_contracts tests/contract/test_engine_contracts.py::test_pair_requests_include_step_control_contracts tests/contract/test_engine_contracts.py::test_route_redirected_final_route_drives_required_write_validation tests/contract/test_engine_contracts.py::test_explicit_empty_required_writes_override_skips_artifact_level_required_defaults`

## Deduplication / Centralization
- Centralized explicit/effective required-write computation in `core/route_required_writes.py` instead of keeping separate fallback logic in engine and topology serializers.
