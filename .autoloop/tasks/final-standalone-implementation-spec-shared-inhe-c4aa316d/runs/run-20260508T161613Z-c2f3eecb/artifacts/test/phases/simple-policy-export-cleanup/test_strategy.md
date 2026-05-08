# Test Strategy

- Task ID: final-standalone-implementation-spec-shared-inhe-c4aa316d
- Pair: test
- Phase ID: simple-policy-export-cleanup
- Phase Directory Key: simple-policy-export-cleanup
- Phase Title: Clean Up Simple Policy Exports
- Scope: phase-local producer artifact

## Behavior-to-Test Coverage Map

- AC-1 public import removal:
  `tests/unit/test_simple_policy.py::test_policy_input_export_matrix_matches_phase_contract`
  covers failed import and `AttributeError` for `autoloop.simple.PolicyInput`, and also confirms `autoloop.policy` / `autoloop.sdk` keep the canonical export.
- AC-2 duplicate alias removal:
  `tests/unit/test_simple_policy.py::test_policy_input_export_matrix_matches_phase_contract`
  covers failed import and `AttributeError` for `autoloop.simple.ProviderPolicyInput`, plus absence from `simple.__all__`.
- AC-3 preserved accepted policy inputs:
  `tests/unit/test_simple_policy.py::test_simple_declarations_accept_public_policy_layers`
  covers `Policy`.
  `tests/unit/test_simple_policy.py::test_simple_declarations_accept_provider_policy_and_none`
  covers direct `ProviderPolicy` and explicit `None`.
  `tests/unit/test_simple_policy.py::test_simple_declarations_keep_internal_override_compatibility`
  covers `ProviderPolicyOverride`.
- AC-4 required regression surface:
  `./.venv/bin/pytest tests/unit/test_simple_policy.py`
  `./.venv/bin/pytest tests/unit/test_simple_surface.py tests/unit/test_policy.py tests/runtime/test_sdk_policy.py tests/unit/test_sdk_facade.py`

## Preserved Invariants Checked

- `PolicyInput` remains public only from `autoloop.policy` and `autoloop.sdk`.
- `autoloop` root still does not export `PolicyInput`.
- Simple declarations keep storing accepted policy-layer objects without coercion or behavior drift.

## Edge Cases

- Explicit `policy=None` on simple declarations remains accepted.
- Direct concrete `ProviderPolicy` remains accepted in addition to layered `Policy` and override objects.

## Failure Paths

- Unsupported simple-surface imports fail deterministically with `ImportError`.
- Direct attribute lookup for removed simple-surface symbols raises `AttributeError`.

## Flake Risks / Stabilization

- No timing, network, or ordering risk introduced.
- Coverage uses unit-level import and declaration checks plus deterministic pytest targets already in the phase contract.

## Known Gaps

- No new fixture coverage was needed; the changed behavior is fully exercised by existing unit/runtime suites with one added simple-policy regression test.
