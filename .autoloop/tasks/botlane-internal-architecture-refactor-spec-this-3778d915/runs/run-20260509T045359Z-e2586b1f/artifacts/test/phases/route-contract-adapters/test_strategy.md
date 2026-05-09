# Test Strategy

- Task ID: botlane-internal-architecture-refactor-spec-this-3778d915
- Pair: test
- Phase ID: route-contract-adapters
- Phase Directory Key: route-contract-adapters
- Phase Title: Route Contract Adapters
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- Internal route target/action mapping:
  - `tests/unit/test_route_contracts.py::test_route_contract_targets_map_to_internal_route_actions`
  - Covers `finish`, `await_input`, `fail`, `step`, and disabled-route failure path for `route_action_for_contract(...)`.
- Compiled-route metadata round-trip with inventory-backed required writes:
  - `tests/unit/test_route_contracts.py::test_route_contract_round_trip_preserves_metadata_and_inventory_backed_required_writes`
  - Covers summary, handoff, provider visibility, payload schema, route-fields schema, validators, explicit required writes, and dotted artifact identities.
- Explicit empty override preservation:
  - `tests/unit/test_route_contracts.py::test_route_contract_preserves_explicit_empty_required_writes_without_inventory`
  - Covers the empty-but-explicit edge case without requiring inventory.
- Missing-inventory failure contract:
  - `tests/unit/test_route_contracts.py::test_route_contract_requires_inventory_for_non_empty_required_writes`
  - Covers the required `ValueError` path for non-empty `required_writes`.
- Derived route-view helpers:
  - `tests/unit/test_route_contracts.py::test_route_view_helpers_derive_tags_from_plan_route_tables`
  - Covers disabled-route suppression, runtime-control tag derivation, and interactive vs full-auto visibility.
- Compiler-produced route-table parity:
  - `tests/unit/test_route_contracts.py::test_compiled_route_adapter_round_trip_matches_compiler_normalized_routes`
  - Covers adapter parity against real `compile_workflow(...)` output for step targets, inherited `question`, disabled routes, payload schema normalization, and inventory-resolved required writes.

## Preserved Invariants Checked

- No public route authoring changes are required to exercise the new internals.
- `CompiledRoute` remains the compatibility boundary; tests round-trip back to the compiled shape.
- Required-write resolution continues to rely on inventory ownership instead of string splitting.

## Edge Cases And Failure Paths

- Explicit empty required-write overrides remain distinguishable from implicit empty defaults.
- Disabled routes do not produce runtime actions.
- Missing artifact inventory fails only when non-empty required writes must be resolved.
- Compiler-backed parity test avoids optional `jsonschema` dependence by using built-in helper route fields instead of raw custom mappings.

## Flake Risk / Stabilization

- No network, time, subprocess, or ordering sensitivity introduced.
- All added coverage is unit-level and uses local compiler/value-object paths only.

## Known Gaps

- Engine-loop consumption of `RouteAction` remains intentionally out of scope for this phase.
- Workflow-plan-backed route-view helpers cannot be exercised until `WorkflowPlan` exists in a later phase.
