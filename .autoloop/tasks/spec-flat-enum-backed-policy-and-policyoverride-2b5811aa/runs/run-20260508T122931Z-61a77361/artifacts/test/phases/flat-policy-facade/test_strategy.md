# Test Strategy

- Task ID: spec-flat-enum-backed-policy-and-policyoverride-2b5811aa
- Pair: test
- Phase ID: flat-policy-facade
- Phase Directory Key: flat-policy-facade
- Phase Title: Implement Flat Policy Facade
- Scope: phase-local producer artifact

## Behavior-to-test coverage map
- Public surface exports:
  `tests/unit/test_simple_surface.py`, `tests/unit/test_simple_policy.py`
  Covers `autoloop`/`autoloop.simple` exports, `__all__`, and callable helpers/enums.
- Helper coercion and enum strictness:
  `tests/unit/test_simple_policy.py`
  Covers `_policy_tuple`, `_policy_optional_tuple`, `_policy_string_mapping`, bytes rejection, dedupe, and raw-string rejection for enum-backed fields.
- Full policy lowering:
  `tests/unit/test_simple_policy.py`
  Covers default preservation, model/filesystem/network lowering, read-only inference, limited-network inference, and invalid network/read-only combinations.
- Sparse override lowering:
  `tests/unit/test_simple_policy.py`
  Covers sparse model override shape, merge preservation of defaults, write-root replacement, and read-only write-root clearing.
- Dangerous-access behavior:
  `tests/unit/test_simple_policy.py`, `tests/runtime/test_provider_policy_steps.py`
  Covers `FULL_AUTO_UNSANDBOXED` inference, clarified QA-2 rejection of manual `danger_full_access` without explicit `permission_mode`, and the explicit compatible manual path using `PermissionMode.ASK`.
- Compiler/runtime integration:
  `tests/unit/test_simple_policy.py`, `tests/runtime/test_provider_policy_steps.py`
  Covers workflow compilation, step override compilation, and inline operation policy normalization.
- Regression suites:
  `tests/unit/test_provider_policy.py`, `tests/runtime/test_provider_policy_emitters.py`, `tests/runtime/test_provider_policy_config.py`
  Confirms no unintended drift in core merge rules, provider emitters, or config parsing.

## Preserved invariants checked
- Core provider-policy schema and validators remain unchanged and authoritative.
- Engine-facing policy inputs remain canonical `ProviderPolicy` / `ProviderPolicyOverride`.
- Dangerous-access handling does not silently rewrite permission mode after QA-2.

## Edge cases and failure paths
- Empty/bytes/duplicate tuple normalization inputs.
- Raw-string enum inputs rejected at the facade boundary.
- `network_domains=()` and limited/full/none network incompatibilities.
- Read-only plus `allow_write`.
- Manual `danger_full_access` without explicit compatible `permission_mode`.

## Flake risk and stabilization
- Tests are deterministic and in-process only.
- No network, clock, random, or ordering-sensitive assertions were added.

## Known gaps
- No new config-file fixture was added for the clarified manual-danger rejection path because the change is isolated to the flat Python authoring facade, not runtime config parsing.
