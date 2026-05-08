# Policy Payload Kind Cleanup Plan

## Scope
- Implement the correction spec exactly for public `Policy(...)` payload kinds, compiler/topology fingerprinting, public SDK/simple/core-normalization wording, runtime CLI `--workspace`, and required tests.
- Keep scope local to policy/compiler/SDK/simple/runtime CLI surfaces plus directly affected docs/examples and tests.
- Do not add compatibility aliases for removed public names or flags.

## Milestones
1. Normalize public and core policy payload kinds.
   - Update [autoloop/policy.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/policy.py) so `Policy.to_layer_payload()` emits nested public bases as `{"kind": "policy_layer", "payload": ...}` and concrete `ProviderPolicy` bases as `{"kind": "provider_policy", "payload": ...}`.
   - Preserve deterministic authored-field-only payload generation: enum values as strings, paths as strings, tuples as JSON lists, recursive public `base=` serialization, and stable insertion order.
   - Update [autoloop/core/compiler.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/compiler.py) so `_policy_input_payload(...)` emits `policy_layer`, `provider_policy`, and `provider_policy_override`, and `_policy_input_fingerprint(...)` always hashes that payload for every non-`None` policy input.
   - Leave `policy_fingerprint(...)` available for non-topology internal uses only.

2. Clean public policy surface wording and export guarantees.
   - Update public-facing normalization and validation errors in [autoloop/sdk.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/sdk.py), [autoloop/simple.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/simple.py), [autoloop/core/steps.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/steps.py), [autoloop/core/discovery.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/discovery.py), and any matching public normalization path in [autoloop/policy.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/policy.py) so public errors prefer `Policy`, `core provider policy object`, or `provider policy layer` wording and do not leak `ProviderPolicyOverride` unless the path is explicitly core/internal.
   - Preserve the existing greenfield public API: `Autoloop(workspace=...)`, `client.run(..., input=..., params=..., policy=...)`, `client.step(..., input=..., params=..., policy=...)`, no public `PolicyOverride`, no public `root=`, `typed_input=`, or `parameters=`.
   - Audit `__all__` in [autoloop/policy.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/policy.py), [autoloop/__init__.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/__init__.py), [autoloop/sdk.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/sdk.py), and [autoloop/simple.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/simple.py); current exports already look compliant, so the implementation should preserve them and strengthen tests instead of widening the surface.
   - Confirm public SDK helper examples stay sequence-based for `writes=(Md(...), Json(...))`; mapping-style writes may remain only in lower-level core tests and internals.

3. Rename runtime CLI workspace flag and close regression gaps.
   - Update [autoloop/runtime/cli.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/runtime/cli.py) so covered public parsers require `--workspace` instead of defaulting the workspace selector, remove public `--root`, and keep help text aligned to “workspace”.
   - Internal local variables may remain named `root` after argument resolution.
   - Update directly affected public docs/examples in scope, especially CLI references that still document `--root`.
   - Update runtime CLI tests to assert `--workspace` works, omission of `--workspace` fails as usage error for covered entry points, and `--root` is rejected.

## Interface Contract
- Public `Policy(...)` serialization and fingerprint payloads must use `{"kind": "policy_layer", "payload": ...}` everywhere they appear, including nested `base=` and compiler/topology inputs.
- Concrete `ProviderPolicy` serialization and fingerprint payloads must use `{"kind": "provider_policy", "payload": ...}`.
- Core `ProviderPolicyOverride` serialization and fingerprint payloads must use `{"kind": "provider_policy_override", "payload": ...}`.
- Compiler/topology hashes must change when the serialized kind label changes, but identical authored public `Policy(...)` inputs must still produce stable payloads and fingerprints.
- SDK run policy must remain excluded from workflow topology hashing.
- Runtime CLI public surface must require `--workspace` and must no longer accept `--root` if [autoloop/runtime/cli.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/runtime/cli.py) is touched in this patch.

## Compatibility Notes
- Intentional break: serialized kind labels for policy payloads change to the explicit names above; fingerprint and topology hashes are therefore expected to change when kinds change.
- Intentional break: runtime CLI public `--root` is removed in favor of a required `--workspace`; do not add an alias or keep the current default-to-`cwd` selector behavior under the greenfield directive.
- Intentional non-change: provider emission behavior and runtime YAML/TOML policy syntax stay untouched unless a failing test proves direct dependence on the corrected kind labels.
- Intentional non-change: `policy_fingerprint(...)` may continue to exist for operational/internal paths outside compiler/topology hashing.

## Validation
- Extend [tests/unit/test_policy.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_policy.py) for nested public `Policy` bases, concrete `ProviderPolicy` bases, forbidden legacy kind labels, payload determinism, and fingerprint-kind separation.
- Extend or add compiler-focused assertions in [tests/unit/test_policy.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_policy.py) or another narrow unit suite covering `_policy_input_payload(...)` and `_policy_input_fingerprint(...)` for `Policy`, `ProviderPolicy`, and `ProviderPolicyOverride`.
- Update [tests/unit/test_simple_policy.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_simple_policy.py), [tests/unit/test_simple_surface.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_simple_surface.py), [tests/unit/test_sdk_facade.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_sdk_facade.py), and [tests/runtime/test_sdk_policy.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_sdk_policy.py) for export guarantees, public wording, removed keyword rejection, and sequence-style SDK writes coverage.
- In [tests/unit/test_sdk_facade.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_sdk_facade.py), keep the existing `Autoloop(root=...)` rejection coverage and make `client.step(..., typed_input=...)` plus `client.step(..., parameters=...)` rejection assertions explicit alongside the run-keyword checks.
- Update [tests/runtime/test_runtime_cli_metadata_integration.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_runtime_cli_metadata_integration.py) and [tests/runtime/test_package_cli.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_package_cli.py) for `--workspace` acceptance, omission-of-`--workspace` usage failure, `--root` rejection, and help text wording.

## Regression Controls
- Keep payload-shape logic centralized in `Policy.to_layer_payload()` and `_policy_input_payload(...)` to avoid divergent kind names across workflow, step, SDK, and inline operation paths.
- Avoid broad refactors in provider/runtime code; the only intended behavioral delta is corrected public serialization/fingerprint labels plus the explicit CLI flag rename.
- Prefer message-only test updates where wording changes are public-facing; do not weaken tests that currently protect removed surface area.

## Risk Register
- Risk: compiler fingerprinting could accidentally keep the concrete `ProviderPolicy` shortcut in one call path.
  Mitigation: add explicit tests for `_policy_input_fingerprint(ProviderPolicy(...))` and topology-hash deltas driven by kind labels.
- Risk: public errors could still leak `ProviderPolicyOverride` through simple/core validation helpers.
  Mitigation: update every current public occurrence surfaced by search and lock them with message assertions.
- Risk: CLI rename could miss one parser branch or leave help text inconsistent.
  Mitigation: cover `workflows`, `runs`, `logs`, `run`, `resume`, `answer`, and `init workflow` parser entry points already exercised by runtime tests, including omission-of-`--workspace` failures.
- Risk: public docs/examples drift from the enforced API.
  Mitigation: update touched CLI docs/examples and SDK helper examples in scope during the same patch.
