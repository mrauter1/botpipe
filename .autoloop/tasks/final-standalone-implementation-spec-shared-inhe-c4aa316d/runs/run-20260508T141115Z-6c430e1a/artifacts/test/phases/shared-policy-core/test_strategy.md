# Test Strategy

- Task ID: final-standalone-implementation-spec-shared-inhe-c4aa316d
- Pair: test
- Phase ID: shared-policy-core
- Phase Directory Key: shared-policy-core
- Phase Title: Shared Policy Core
- Scope: phase-local producer artifact

## Coverage map

- Public policy construction and enum validation:
  - `Policy()` remains sparse and resolves against `SYSTEM_DEFAULT_PROVIDER_POLICY`.
  - Enum-backed public fields reject raw strings and wrong enum types.
- Sparse inheriting resolution:
  - Authored fields lower to concrete provider policy fields only at resolution time.
  - Nested `base=` inheritance preserves unrelated values and supports concrete `ProviderPolicy` bases.
  - Cyclic `Policy(base=...)` references fail deterministically.
- Sandbox/filesystem/network failure paths:
  - `read_only` conflicts with `allow_write`.
  - `network=LIMITED` without domains and `network_domains=()` fail fast.
  - Dangerous access conflicts with incompatible explicit permission/sandbox combinations.
- Dangerous-manual compatibility:
  - `Policy(sandbox_mode=SandboxMode.DANGER_FULL_ACCESS)` resolves over the default `full_auto_sandboxed` base as manual dangerous access (`permissions.mode == "ask"` plus bypass).
  - Dangerous-manual workflow compile/resolve path produces the same effective policy.
  - Non-`full_auto_sandboxed` inherited permission modes are preserved when the public layer only requests dangerous sandbox access.
- Public surface cleanup:
  - `autoloop`, `autoloop.policy`, and `autoloop.simple` share the same `Policy`/enum exports.
  - `PolicyOverride` is absent from public exports.
  - `autoloop.simple.ProviderPolicyOverride` is not publicly importable, while internal override compatibility remains accepted by simple declarations.

## Preserved invariants checked

- Core `ProviderPolicy` and internal `ProviderPolicyOverride` remain accepted where compatibility is required.
- Dangerous access still requires the nested `allow_dangerous_bypass` latch in resolved concrete policies.
- Compiler fingerprint inputs continue using authored-layer payloads rather than eager concrete policy materialization.

## Flake and stability notes

- Coverage is unit-level and deterministic; no timing, network, or filesystem race dependencies are introduced.
- Failure-path assertions use exact local construction/resolution paths instead of provider execution.

## Known gaps

- This phase does not cover later SDK `workspace` / `input` / `params` naming work or SDK default/run-layer merge order, which are out of scope for `shared-policy-core`.
