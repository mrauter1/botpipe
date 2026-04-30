# Test Strategy

- Task ID: below-is-the-standalone-implementation-spec-for-b066b1fd
- Pair: test
- Phase ID: effective-required-writes
- Phase Directory Key: effective-required-writes
- Phase Title: Normalize Effective Required Writes
- Scope: phase-local producer artifact

## Behavior Coverage Map
- AC-1 / inherited artifact requiredness becomes effective required writes:
  covered by `tests/unit/test_validation.py::test_compilation_keeps_public_empty_required_writes_but_marks_explicit_empty_overrides_privately`
  and `tests/contract/test_canonical_runtime_contracts.py::test_canonical_step_contract_uses_finish_and_required_writes`.
- AC-2 / provider contracts expose explicit plus effective route sets:
  covered by `tests/contract/test_canonical_runtime_contracts.py::test_canonical_step_contract_uses_finish_and_required_writes`,
  `tests/contract/test_canonical_runtime_contracts.py::test_canonical_produce_verify_contract_splits_phase_writes_and_verifier_routes`,
  and `tests/unit/test_provider_boundary_core.py`.
- AC-2 / topology payload and route table preserve `None` versus `[]`:
  covered by `tests/runtime/test_runtime_static_graph.py::test_topology_payload_and_route_table_preserve_explicit_vs_effective_required_writes`.
- AC-2 / inherited `GLOBAL` routes do not fabricate a concrete effective set without step context:
  covered by `tests/runtime/test_runtime_static_graph.py::test_topology_payload_omits_unbound_effective_set_for_inherited_global_routes`.
- Edge case / explicit `GLOBAL` route overrides remain concrete even without step context:
  covered by `tests/runtime/test_runtime_static_graph.py::test_topology_payload_keeps_explicit_global_route_required_writes_concrete`.
- Preserved invariant / explicit empty override still suppresses inherited required artifacts at runtime:
  covered by `tests/contract/test_engine_contracts.py::test_explicit_empty_required_writes_override_skips_artifact_level_required_defaults`.
- Preserved invariant / final routed artifact validation follows the final selected route:
  covered by `tests/contract/test_engine_contracts.py::test_route_redirected_final_route_drives_required_write_validation`.

## Edge Cases
- Inherited route with required artifact and no explicit override.
- Explicit empty route override.
- Inherited top-level `GLOBAL` route with no step context.
- Explicit top-level `GLOBAL` route override with no step context.

## Failure Paths
- Missing required artifact on the final routed path remains covered by existing engine contract tests.
- Incorrect topology serialization for inherited globals is caught by the dedicated `GLOBAL` route regression.

## Flake Risks And Stabilization
- No timing or network behavior is exercised.
- All added assertions use pure compilation or in-memory topology payload generation for deterministic results.

## Known Gaps
- No separate test was added for compiler hash payload shape; topology payload regressions are the authoritative phase-level guard because the hash payload reuses the same helper path.
