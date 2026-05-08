# Test Strategy

- Task ID: below-is-the-revised-standalone-correction-spec-a9877342
- Pair: test
- Phase ID: policy-payload-fingerprints
- Phase Directory Key: policy-payload-fingerprints
- Phase Title: Policy Payload Kinds
- Scope: phase-local producer artifact

## Behavior-to-test coverage map
- Public nested `Policy` base serialization: covered by `test_policy_to_layer_payload_serializes_nested_public_policy_bases_as_policy_layers`.
- Concrete `ProviderPolicy` base serialization: covered by `test_policy_to_layer_payload_serializes_concrete_provider_policy_bases`.
- Compiler payload kind mapping for `Policy`, `ProviderPolicy`, and `ProviderPolicyOverride`: covered by `test_policy_input_payload_and_fingerprint_use_explicit_kind_labels`.
- Unified compiler fingerprinting for every non-`None` policy input, including concrete `ProviderPolicy`: covered by `test_policy_input_payload_and_fingerprint_use_explicit_kind_labels`.
- Payload determinism and identical-authored-layer fingerprint stability: covered by `test_policy_payload_and_fingerprint_are_deterministic_for_identical_authored_layers`.
- Authored-field delta fingerprint changes: covered by `test_policy_payload_and_fingerprint_are_deterministic_for_identical_authored_layers`.
- Kind-label delta fingerprint changes: covered by `test_policy_input_payload_and_fingerprint_use_explicit_kind_labels` and `test_policy_payload_and_fingerprint_are_deterministic_for_identical_authored_layers`.

## Preserved invariants checked
- Public `Policy` payloads do not emit legacy `kind="policy"` or `kind="layer"` labels in the phase-owned serialization paths.
- Concrete provider payloads still serialize through `model_dump(mode="json", warnings=False)`.
- Compiler payload wrapping remains centralized through `_policy_input_payload(...)`.

## Edge cases and failure paths
- Nested public base recursion is exercised with a sparse child and sparse base.
- Concrete provider input is checked against the old `policy_fingerprint(...)` shortcut to catch accidental bypass regressions.
- Distinct wrapper kinds with otherwise similar policy content are asserted to produce distinct compiler fingerprints.

## Flake risk / stabilization
- Tests are pure unit assertions with no network, timing, filesystem race, or nondeterministic ordering dependencies.
- Fingerprint assertions derive from explicit JSON payloads and stable hashing inputs.

## Validation performed
- `python3 -m py_compile tests/unit/test_policy.py autoloop/policy.py autoloop/core/compiler.py`
- Attempted but blocked: `python3 -m pytest tests/unit/test_policy.py` failed because the environment does not have `pytest` installed.

## Known gaps
- No live `pytest` execution was possible in this environment, so runtime confirmation remains pending until the project test environment is available.
