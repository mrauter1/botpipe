# Implementation Notes

- Task ID: full-revised-standalone-spec-autoloop-v3-explici-7b9dcd08
- Pair: implement
- Phase ID: restore-provider-route-required-writes
- Phase Directory Key: restore-provider-route-required-writes
- Phase Title: Restore Effective Provider Route Maps
- Scope: phase-local producer artifact

## Files changed
- `autoloop/core/engine_collaborators.py`
- `autoloop/core/route_required_writes.py`
- `tests/contract/test_engine_contracts.py`

## Symbols touched
- `ProviderContractBuilder.route_required_writes`
- `effective_route_required_writes`
- `effective_route_required_writes_for_step`
- `route_required_write_payload`
- `test_explicit_empty_required_writes_override_skips_artifact_level_required_defaults`

## Checklist mapping
- `M1 shared provider-contract builder`: completed via `ProviderContractBuilder.route_required_writes` using the shared effective-write helper.
- `Keep producer requests unchanged`: preserved; producer `available_routes`, `routes`, and `route_required_writes` remain empty.
- `Preserve route metadata surface`: preserved; `ProviderContractBuilder.routes` still exposes authored `required_writes` and `explicit_required_writes`.
- `Validation plan`: completed for canonical contracts, metadata invariants, branch-group coverage, explicit-global topology payloads, and the full suite.

## Assumptions
- The accepted branch-group behavior should remain unchanged unless the shared helper can restore effective route maps without altering runtime control flow or compiled metadata.

## Preserved invariants
- Per-route authored metadata remains unchanged, including explicit empty overrides.
- Producer-side `produce_verify_step` contracts still expose no routes and no `route_required_writes`.
- Runtime/static-graph explicit-vs-effective semantics remain intact for step routes and global routes.

## Intended behavior changes
- Ordinary `step(...)` and verifier-side `produce_verify_step(...)` provider requests now expose effective `route_required_writes` for every provider-visible route, including inherited required artifacts when the route has no explicit override.
- Explicit global route payloads now keep their own required writes as effective writes when rendered without step context.

## Known non-changes
- No changes to compiled route normalization, route metadata storage, branch-group scheduling, or artifact/session semantics.
- No changes to producer-side writable surfaces or verifier route tables beyond the effective request map restoration.

## Expected side effects
- Provider prompt rendering and any backend consuming `route_required_writes` now see inherited required artifacts on visible default/control routes.
- Topology/global-route payloads keep explicit global required writes concrete instead of collapsing them to an empty effective list.

## Deduplication / centralization
- Centralized effective-write resolution in `autoloop.core.route_required_writes` and reused it from provider-contract assembly instead of duplicating fallback logic in the builder.

## Validation performed
- `./.venv/bin/python -m pytest -q tests/contract/test_canonical_runtime_contracts.py::test_canonical_step_contract_uses_finish_and_required_writes tests/contract/test_canonical_runtime_contracts.py::test_canonical_produce_verify_contract_splits_phase_writes_and_verifier_routes tests/unit/test_validation.py::test_compilation_keeps_public_empty_required_writes_but_marks_explicit_empty_overrides_privately tests/runtime/test_runtime_static_graph.py::test_topology_payload_and_route_table_preserve_explicit_vs_effective_required_writes tests/contract/test_branch_group_runtime.py tests/contract/test_engine_contracts.py::test_explicit_empty_required_writes_override_skips_artifact_level_required_defaults`
- `./.venv/bin/python -m pytest -q tests/runtime/test_runtime_static_graph.py::test_topology_payload_keeps_explicit_global_route_required_writes_concrete tests/contract/test_canonical_runtime_contracts.py::test_canonical_step_contract_uses_finish_and_required_writes tests/contract/test_canonical_runtime_contracts.py::test_canonical_produce_verify_contract_splits_phase_writes_and_verifier_routes`
- `./.venv/bin/python -m pytest -q`
