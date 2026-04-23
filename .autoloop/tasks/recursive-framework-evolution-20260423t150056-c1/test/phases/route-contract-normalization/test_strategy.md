# Test Strategy

- Task ID: recursive-framework-evolution-20260423t150056-c1
- Pair: test
- Phase ID: route-contract-normalization
- Phase Directory Key: route-contract-normalization
- Phase Title: Normalize Route Contracts
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Typed route-contract declarations normalize to canonical runtime shape:
  - `tests/unit/test_validation.py::test_compilation_normalizes_typed_route_contracts`
  - `tests/contract/test_engine_contracts.py::test_pair_requests_include_step_control_contracts`
- Mapping-style declarations remain backward compatible and normalize to `summary`, `required_artifacts`, and `work_item_effect`:
  - `tests/unit/test_validation.py::test_validation_accepts_legacy_state_effect_and_normalizes_work_item_effect`
  - `tests/unit/test_validation.py::test_validation_accepts_legacy_evidence_and_normalizes_summary`
  - `tests/runtime/test_workflow_builder_package.py::test_workflow_builder_package_compiles_with_explicit_control_contracts`
  - `tests/contract/test_engine_contracts.py::test_pair_requests_normalize_legacy_evidence_route_contracts`
- Validation rejects illegal route-contract declarations:
  - `tests/unit/test_validation.py::test_validation_rejects_unknown_route_contracts`
  - `tests/unit/test_validation.py::test_validation_requires_application_route_contracts_when_declared`
  - `tests/unit/test_validation.py::test_validation_rejects_route_contract_unknown_artifacts`
- Repo-local strict import surface remains authoritative after the reviewer-driven path-order fix:
  - `tests/strictness/test_no_compat.py::test_workflow_shim_exports_only_the_strict_authoring_surface`

## Preserved invariants checked

- Runtime control data remains limited to `expected_output_schema`, `available_routes`, and normalized `route_contracts`.
- Existing repo-owned workflow packages using mapping-style route contracts still compile unchanged.
- `workflow` resolves to the repo-local shim under the repo test harness.

## Edge cases

- Route contracts without explicit `required_artifacts` normalize to an empty list.
- Route contracts without explicit `work_item_effect` infer the default route-based effect.
- Legacy alias normalization is exercised for both `state_effect` and `evidence`.

## Failure paths

- Unknown route tags are rejected.
- Missing application-route contracts are rejected once route contracts are declared for a step.
- Unknown artifact references in route contracts are rejected.

## Flake / stabilization notes

- All added coverage is deterministic and filesystem-local.
- Tests use scripted providers and fixed temporary directories; there is no timing, network, or nondeterministic ordering dependency.

## Known gaps

- Full `tests/strictness/test_no_compat.py` and the recursive-memory baseline doc check still have unrelated existing failures outside this phase scope.
