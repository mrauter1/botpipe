# Test Strategy

- Task ID: final-standalone-implementation-spec-shared-inhe-c4aa316d
- Pair: test
- Phase ID: compiler-simple-integration
- Phase Directory Key: compiler-simple-integration
- Phase Title: Compiler And Simple Integration
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- AC-1 simple/public policy acceptance:
  - `tests/unit/test_simple_policy.py`
    - `test_simple_declarations_accept_public_policy_layers`
    - `test_policy_input_export_matrix_matches_phase_contract`
  - `tests/runtime/test_provider_policy_steps.py`
    - `test_inline_operations_accept_public_policy_layers`
- AC-2 compiler/topology fingerprinting for public `Policy` layers:
  - `tests/unit/test_policy.py`
    - `test_policy_layer_payload_and_compiler_fingerprint_support_public_policy`
    - `test_public_policy_changes_participate_in_topology_hash_for_workflow_and_step_layers`
- AC-3 exact export matrix and removed public compatibility:
  - `tests/unit/test_policy.py`
    - `test_public_policy_imports_and_all`
  - `tests/unit/test_simple_policy.py`
    - `test_policy_surface_exports_shared_policy_symbols`
    - `test_policy_rejects_removed_public_policy_override_symbol`
    - `test_policy_input_export_matrix_matches_phase_contract`

## Preserved invariants checked

- `PolicyOverride` remains absent from public root/simple surfaces.
- Authored public `Policy` layers remain accepted alongside internal `ProviderPolicyOverride`.
- Public `Policy` payloads influence topology hashing for authored workflow and step policy differences.

## Edge cases and failure paths

- Failure path captured: `autoloop.simple` must not publicly expose `PolicyInput`; the new export-matrix assertion currently fails because the symbol is still importable from `autoloop.simple`.
- Inline operation coverage uses deterministic scripted provider turns to avoid timing or nondeterministic output risk.

## Validation run

- Failed as intended for uncovered phase bug:
  - `./.venv/bin/python -m pytest tests/unit/test_simple_policy.py tests/unit/test_policy.py`
- Passed:
  - `./.venv/bin/python -m pytest tests/runtime/test_provider_policy_steps.py`

## Known gaps

- I did not broaden into SDK constructor naming or run-policy hash isolation because those are outside this phase contract.
