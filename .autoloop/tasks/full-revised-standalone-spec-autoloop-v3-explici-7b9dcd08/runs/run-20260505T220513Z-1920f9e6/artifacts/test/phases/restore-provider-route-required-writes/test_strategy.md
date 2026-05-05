# Test Strategy

- Task ID: full-revised-standalone-spec-autoloop-v3-explici-7b9dcd08
- Pair: test
- Phase ID: restore-provider-route-required-writes
- Phase Directory Key: restore-provider-route-required-writes
- Phase Title: Restore Effective Provider Route Maps
- Scope: phase-local producer artifact

## Behavior-to-test coverage map
- Ordinary `step(...)` provider contracts expose effective `route_required_writes` for inherited visible routes:
  covered by `tests/contract/test_canonical_runtime_contracts.py::test_canonical_step_contract_uses_finish_and_required_writes`
  and `tests/contract/test_engine_contracts.py::test_explicit_empty_required_writes_override_skips_artifact_level_required_defaults`.
- Verifier-side `produce_verify_step(...)` contracts expose effective `route_required_writes` while producer contracts stay empty:
  covered by `tests/contract/test_canonical_runtime_contracts.py::test_canonical_produce_verify_contract_splits_phase_writes_and_verifier_routes`
  and `tests/contract/test_engine_contracts.py::test_produce_verify_step_sends_split_phase_contracts_without_implicitly_requiring_producer_writes`.
- Verifier-side explicit empty overrides do not leak inherited writes onto the authored route, while control routes still inherit required artifacts:
  covered by `tests/contract/test_engine_contracts.py::test_produce_verify_step_verifier_contract_preserves_explicit_empty_route_override`.
- Explicit-vs-effective metadata payload semantics remain stable for topology/global-route surfaces:
  covered by `tests/runtime/test_runtime_static_graph.py::test_topology_payload_keeps_explicit_global_route_required_writes_concrete`.
- Branch-group behavior remains preserved on the shared provider path:
  covered by `tests/contract/test_branch_group_runtime.py`.

## Preserved invariants checked
- `routes[*].required_writes` remains the authored metadata surface.
- `routes[*].explicit_required_writes` remains `None` for inherited routes and `()` for explicit empty overrides.
- Producer-side `route_required_writes` remains `{}` for `produce_verify_step(...)`.

## Edge cases
- Explicit empty authored route override on ordinary step requests.
- Explicit empty authored route override on verifier requests with required producer and verifier artifacts present.
- Explicit global route payload with no step context.

## Failure paths
- Regression target is contract drift, not runtime exceptions; failure is detected through mismatched provider-visible route maps and payload metadata assertions.

## Flake risks / stabilization
- No timing or network risk. All added coverage uses `ScriptedLLMProvider`, in-memory stores, and direct artifact writes for deterministic execution.

## Known gaps
- This turn did not add a separate branch-group-specific assertion for explicit empty verifier overrides because the shared branch-group suite already passed unchanged and the helper fix is pinned directly at the provider-contract layer.

## Validation performed
- `./.venv/bin/python -m pytest -q tests/contract/test_engine_contracts.py::test_produce_verify_step_verifier_contract_preserves_explicit_empty_route_override tests/contract/test_canonical_runtime_contracts.py::test_canonical_produce_verify_contract_splits_phase_writes_and_verifier_routes tests/contract/test_engine_contracts.py::test_explicit_empty_required_writes_override_skips_artifact_level_required_defaults`
- `./.venv/bin/python -m pytest -q tests/contract/test_branch_group_runtime.py tests/runtime/test_runtime_static_graph.py::test_topology_payload_keeps_explicit_global_route_required_writes_concrete`
