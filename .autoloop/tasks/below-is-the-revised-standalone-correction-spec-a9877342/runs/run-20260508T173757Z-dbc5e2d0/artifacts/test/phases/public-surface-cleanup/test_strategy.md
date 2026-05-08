# Test Strategy

- Task ID: below-is-the-revised-standalone-correction-spec-a9877342
- Pair: test
- Phase ID: public-surface-cleanup
- Phase Directory Key: public-surface-cleanup
- Phase Title: Public Surface Cleanup
- Scope: phase-local producer artifact

## Behavior-to-test coverage map
- AC-1 public wording cleanup:
  - `tests/unit/test_sdk_facade.py` asserts invalid `default_policy=` uses `Policy or core provider policy object`.
  - `tests/unit/test_simple_surface.py` asserts invalid workflow `policy` discovery errors use the same public wording.
  - `tests/unit/test_simple_policy.py` asserts simple step policy normalization, core step normalization, and `resolve_policy_layer(...)` all hide `ProviderPolicyOverride`.
- AC-2 public export surface:
  - `tests/unit/test_simple_surface.py` locks the root `autoloop.__all__` contract.
  - `tests/unit/test_simple_policy.py` locks `autoloop.policy.__all__`, verifies the required shared symbols remain exported from `autoloop.sdk` and `autoloop.simple`, and confirms `PolicyOverride` is absent from all public modules.
- AC-3 SDK/public contract preservation:
  - `tests/unit/test_sdk_facade.py` covers `Autoloop(workspace=...)` and rejects `root=`.
  - `tests/unit/test_sdk_facade.py` covers `client.run(..., input=...)` and `client.run(..., params=...)`, including mapping and BaseModel params.
  - `tests/unit/test_sdk_facade.py` covers `client.step(..., input=..., params=...)` for both mapping and BaseModel params and verifies `ctx.params` plus `ctx.workflow_params`.
  - `tests/unit/test_sdk_facade.py` covers removed `typed_input=` and `parameters=` keywords for both `client.run(...)` and `client.step(...)`.
  - `tests/unit/test_sdk_facade.py` keeps public SDK helper coverage sequence-based via `writes=(simple.Md("report"),)`.

## Preserved invariants checked
- Public surfaces continue to expose `Policy` rather than reviving a public `PolicyOverride`.
- Internal compatibility with concrete `ProviderPolicy` / `ProviderPolicyOverride` remains intact while public wording stays collapsed to `core provider policy object`.
- SDK synthetic step execution still supports typed `input` while now preserving typed and mapping `params`.

## Edge cases and failure paths
- Invalid public policy inputs raise cleaned wording instead of leaking internal core type names.
- Removed SDK keywords fail fast with `TypeError` on both run and step entry points.
- Mapping and BaseModel step params both round-trip through synthetic workflow context to catch branch-specific regressions in synthesized `Params` handling.

## Flake / environment risks
- Tests are deterministic and provider-backed by `ScriptedLLMProvider`; no network or timing-sensitive assertions were added.
- Environment gap: local execution here cannot run `pytest` because the interpreter lacks the test dependency set. Compilation is the available validation fallback in this environment.
