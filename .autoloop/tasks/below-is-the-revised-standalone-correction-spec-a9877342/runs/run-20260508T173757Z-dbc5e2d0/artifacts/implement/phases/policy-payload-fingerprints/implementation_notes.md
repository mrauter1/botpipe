# Implementation Notes

- Task ID: below-is-the-revised-standalone-correction-spec-a9877342
- Pair: implement
- Phase ID: policy-payload-fingerprints
- Phase Directory Key: policy-payload-fingerprints
- Phase Title: Policy Payload Kinds
- Scope: phase-local producer artifact

## Files changed
- `autoloop/policy.py`
- `autoloop/core/compiler.py`
- `tests/unit/test_policy.py`

## Symbols touched
- `Policy.to_layer_payload`
- `_policy_input_payload`
- `_policy_input_fingerprint`
- `test_policy_to_layer_payload_serializes_nested_public_policy_bases_as_policy_layers`
- `test_policy_to_layer_payload_serializes_concrete_provider_policy_bases`
- `test_policy_input_payload_and_fingerprint_use_explicit_kind_labels`
- `test_policy_payload_and_fingerprint_are_deterministic_for_identical_authored_layers`

## Checklist mapping
- Plan milestone 1: completed for `Policy.to_layer_payload()` and compiler payload/fingerprint helpers.
- Plan validation bullets for `tests/unit/test_policy.py`: completed for nested public `Policy`, concrete `ProviderPolicy`, `ProviderPolicyOverride`, deterministic payloads, and kind-driven fingerprint changes.
- Plan milestones 2 and 3: intentionally deferred to later phases by active phase scope.

## Assumptions
- Active phase scope owns serialization/fingerprint normalization only; broader public-surface cleanup is tracked elsewhere in the run plan.

## Preserved invariants
- `Policy.to_layer_payload()` still emits authored fields only.
- Authored tuple values still serialize as JSON lists.
- Concrete provider policy payloads still use `model_dump(mode="json", warnings=False)`.
- Compiler payload hashing still uses the same stable JSON encoding path for non-`None` policy inputs.

## Intended behavior changes
- Public `Policy(...)` payloads now use `kind="policy_layer"` everywhere touched in this phase.
- Compiler payloads now use `provider_policy` and `provider_policy_override` for concrete core policy objects.
- Compiler fingerprints for concrete `ProviderPolicy` now hash the unified serialized payload, so kind-label changes affect fingerprints.

## Known non-changes
- No public SDK/simple normalization wording changes in this phase.
- No runtime CLI `--workspace` migration in this phase.
- No provider emitter redesign or runtime config syntax changes.

## Expected side effects
- Workflow topology hashes can change when policy kind labels change, as intended by the spec.

## Validation performed
- `python3 -m py_compile autoloop/policy.py autoloop/core/compiler.py tests/unit/test_policy.py`
- Attempted but blocked: `python3 -m pytest tests/unit/test_policy.py tests/runtime/test_sdk_policy.py` failed because the environment lacks `pytest` and project dependencies such as `pydantic`.

## Deduplication / centralization
- Kept payload-kind normalization centralized in the existing `Policy.to_layer_payload()` and `_policy_input_payload()` helpers rather than introducing new serialization branches.
