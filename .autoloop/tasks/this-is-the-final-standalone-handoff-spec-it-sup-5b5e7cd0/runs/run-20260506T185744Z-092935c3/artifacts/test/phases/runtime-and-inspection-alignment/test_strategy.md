# Test Strategy

- Task ID: this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0
- Pair: test
- Phase ID: runtime-and-inspection-alignment
- Phase Directory Key: runtime-and-inspection-alignment
- Phase Title: Align Runtime And Reporting
- Scope: phase-local producer artifact

## Coverage Map

- AC-1 runtime projection compatibility:
  - Preserved existing child-workflow question projection coverage in `tests/contract/test_engine_contracts.py`.
  - Added no duplicate runtime-path test here because that behavior is already locked in the contract suite.

- AC-2 compiled metadata in reporting and topology hash:
  - `tests/runtime/test_runtime_static_graph.py::test_route_visibility_and_route_schema_changes_change_topology_hash`
    - Confirms topology hash changes when provider visibility changes.
    - Confirms topology hash changes when route schema metadata changes.
  - `tests/unit/test_stdlib_and_extensions.py::test_core_selected_workflow_payload_builders_preserve_authoring_and_decomposition_contract_shapes`
    - Confirms workflow capability and decomposition payloads expose `compiled_global_routes`, `compiled_route_tags`, `provider_response_contracts`, and compiled question-route schema/inheritance metadata.

- AC-3 provider-schema fallback reporting and additive inspection compatibility:
  - `tests/runtime/test_runtime_static_graph.py::test_static_graph_and_compile_report_surface_simplified_provider_schema_fallback`
    - Forces simplified provider-schema fallback deterministically.
    - Confirms `provider_response_contracts` surfaces `schema_simplified`.
    - Confirms `compile_report.md` renders the fallback state.
  - Extended selected-workflow payload assertions to keep additive snapshot compatibility under the existing artifact shapes.

## Edge Cases And Failure Paths

- Fallback reporting is forced with a monkeypatched schema builder rather than a giant schema fixture, avoiding brittle threshold-dependent expectations.
- Topology-hash coverage checks route visibility and route-fields-schema changes independently from runtime execution.

## Preserved Invariants Checked

- Existing filenames and snapshot roots remain unchanged.
- Legacy compatibility payloads remain additive while compiled-route metadata is now asserted as authoritative.

## Validation Performed

- `python3 -m py_compile tests/runtime/test_runtime_static_graph.py tests/unit/test_stdlib_and_extensions.py`

## Known Gaps

- `pytest` is unavailable in this environment, so runtime execution of the focused suites is deferred.
