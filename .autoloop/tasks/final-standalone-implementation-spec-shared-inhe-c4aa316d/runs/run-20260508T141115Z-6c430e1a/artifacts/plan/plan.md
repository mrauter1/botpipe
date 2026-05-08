# Plan

## Objective

Implement the superseding greenfield public policy surface exactly as specified:

- add `autoloop/policy.py` as the canonical shared module for public policy enums, `Policy`, `PolicyInput`, coercion helpers, and layer resolution
- convert the public facade from eager concrete-policy construction to sparse inheriting policy layers
- align simple and SDK public vocabulary on `workspace`, `input`, `params`, and shared `Policy`
- remove conflicting public compatibility paths: SDK `root=`, SDK `typed_input=`, public `PolicyOverride`, uppercase aliases, and raw strings for enum-backed `Policy(...)` fields

## Concrete Edit Surfaces

- `autoloop/policy.py`
  - New canonical module implementing `_PolicyEnum`, public enums, immutable sparse `Policy`, `PolicyInput`, authored-layer payload/fingerprinting helpers, sparse lowering to `ProviderPolicyOverride`, and `resolve_policy_layer(...)`.
- `autoloop/simple.py`
  - Remove duplicated public policy enums/helpers and import/re-export shared names from `autoloop.policy`.
  - Replace `ProviderPolicyInput` usage with shared `PolicyInput` on workflow, step, and inline operation authoring surfaces.
  - Remove public `PolicyOverride` export and public flat override constructor.
- `autoloop/sdk.py` and `autoloop/__init__.py`
  - Re-export shared policy names from `autoloop.policy`.
  - Rename public SDK constructor/input parameters to `workspace`, `input`, and `params`.
  - Add `default_policy` and run-level / operation-level / step-invocation `policy: PolicyInput`.
  - Preserve step-object immutability by using an invocation-local wrapper/copy when `client.step(..., policy=...)` needs an extra layer.
- `autoloop/core/compiler.py`, `autoloop/core/steps.py`, and workflow validation/discovery surfaces
  - Accept `PolicyInput` anywhere authored workflow/step/operation policies are stored or validated.
  - Switch compile-cache and topology fingerprinting from concrete-policy-only payloads to `Policy.to_layer_payload()` plus existing concrete policy payloads.
- `autoloop/runtime/provider_policy_resolver.py` and `autoloop/runtime/runner.py`
  - Extend resolver ownership to runtime-config default policy, SDK client default policy, workflow policy, SDK run policy, step policy, and inline operation policy.
  - Add runner options for SDK default/run policy layers rather than hand-merging in SDK entrypoints.
- Tests and public surface expectations
  - Update existing policy/simple/SDK/runtime tests and add focused coverage for `autoloop.policy`, SDK naming breaks, resolver merge order, step-local invocation policy layering, and dangerous-access validation.

## Current Codebase Constraints

- `autoloop.simple.Policy(...)` currently returns a fully materialized `ProviderPolicy` seeded from `SYSTEM_DEFAULT_PROVIDER_POLICY`; `simple.PolicyOverride(...)` is a separate public sparse override facade. This is the primary behavior break.
- `autoloop.simple` currently owns duplicated policy enums and flat lowering helpers; `autoloop/__init__.py` re-exports `PolicyOverride`, and existing surface tests assert it.
- `autoloop.sdk.Autoloop` still exposes `root=` and positional `typed_input`, and helper methods still use mapping-style `writes` plus concrete-policy-only typing.
- `ProviderPolicyResolver` currently merges only `SYSTEM_DEFAULT_PROVIDER_POLICY -> runtime config default -> workflow -> step`, and inline operations inherit only the current compiled step policy plus explicit override.
- Compiler fingerprinting currently understands only `ProviderPolicy` and `ProviderPolicyOverride` JSON payloads, so public `Policy` needs deterministic payload support without changing topology semantics for SDK run policy.

## Required Invariants

- Public `Policy(...)` stores only authored fields, treats `read_only=False` as unset, and resolves against an ambient or explicit base without eagerly filling defaults.
- `Policy.resolve(base=None)` resolves against `SYSTEM_DEFAULT_PROVIDER_POLICY`; `Policy(base=<Policy|ProviderPolicy|None>)` recursively resolves explicit bases with cycle protection.
- Raw strings must be rejected for enum-backed public `Policy(...)` fields; internal serialized core policy values remain strings.
- Concrete `ProviderPolicy` remains a complete core policy object, not a public inheriting layer.
- Final provider policy validation remains the hard enforcement boundary and must still catch cross-layer dangerous-access conflicts after merging.
- SDK run policy must affect effective execution policy but must not affect workflow topology hash.
- Inline operations inside workflow execution inherit the current resolved step policy before applying explicit operation policy; direct SDK operations do not inherit workflow-step state.

## Milestones

### 1. Shared policy module and sparse layer semantics

- Create `autoloop/policy.py` with the canonical public enums, `Policy`, `PolicyInput`, coercion helpers, sparse lowering helper, and central `resolve_policy_layer(...)`.
- Encode spec-required lowering rules for model, sandbox, filesystem, network, and permissions, including:
  - `allow_write` implying `workspace_write`
  - `read_only=True` clearing inherited write roots
  - `network_domains` implying limited network
  - dangerous access internally enabling `allow_dangerous_bypass`
  - explicit same-layer incompatibility errors
- Keep `ProviderPolicyOverride` accepted only as an internal/core compatibility type; do not expose a new public constructor or public export.

### 2. Compiler and simple-surface integration

- Replace simple-surface duplicated policy definitions with imports/re-exports from `autoloop.policy`.
- Update workflow/step/operation normalization to accept `Policy`, `ProviderPolicy`, `ProviderPolicyOverride`, or `None`.
- Update workflow validation, compiled step/workflow typing, and topology fingerprinting so public `Policy` payloads are JSON-serializable, deterministic, and participate in compile caching where authored workflow/step policy changes topology.
- Keep dependency direction one-way: `autoloop.policy` may depend on core policy types, but must not import `simple` or `sdk`.

### 3. SDK and runtime merge-order alignment

- Update `Autoloop.__init__` to use `workspace=` and accept `default_policy: PolicyInput = None`; remove public `root=` compatibility.
- Update `Autoloop.run(...)` and `Autoloop.step(...)` to use `input=` and `params=` with `policy: PolicyInput = None`; remove public `typed_input=` and `parameters=` compatibility.
- Re-export shared policy names from `autoloop.sdk` and root package, and remove public `PolicyOverride` from exported surfaces and examples.
- Extend `RunnerOptions` and `ProviderPolicyResolver` so resolver-owned merge order is:
  - `SYSTEM_DEFAULT_PROVIDER_POLICY`
  - runtime config default policy
  - SDK client default policy
  - workflow policy
  - SDK run policy
  - step policy
  - inline explicit operation policy
- Update direct SDK operations (`llm`, `classify`) and SDK step helpers to accept `PolicyInput`, use the same shared lowering/resolution path, and support simple-style `writes=(Md(...), Json(...), Text(...), Raw(...))` as the canonical helper shape.
- Ensure `client.step(..., policy=...)` applies invocation policy after the authored step policy without mutating the caller-provided step object.

### 4. Surface cleanup, regression coverage, and validation

- Rewrite public-surface tests that currently assert `PolicyOverride`, `root=`, or `typed_input=` compatibility so they instead assert the intentional breakage from this spec.
- Add focused tests for:
  - imports/re-exports from `autoloop`, `autoloop.policy`, `autoloop.simple`, and `autoloop.sdk`
  - enum rejection for raw strings
  - sparse inheritance and explicit-base resolution
  - SDK client default policy, run policy, and `client.step(..., policy=...)` precedence
  - topology fingerprint changes for authored workflow/step `Policy` layers only
- Run the required targeted suites from the spec, plus `tests/unit/test_policy.py` and `tests/runtime/test_sdk_policy.py` if created.

## Validation Plan

- Policy unit coverage:
  - `pytest tests/unit/test_provider_policy.py`
  - `pytest tests/unit/test_policy.py`
- Runtime policy execution coverage:
  - `pytest tests/runtime/test_provider_policy_steps.py`
  - `pytest tests/runtime/test_provider_policy_emitters.py`
  - `pytest tests/runtime/test_provider_policy_config.py`
  - `pytest tests/runtime/test_sdk_policy.py`
- Public surface and SDK coverage:
  - `pytest tests/unit/test_simple_surface.py`
  - `pytest tests/unit/test_sdk_facade.py`
- If merge-order or fingerprint changes fan out beyond the targeted suites, run the broader affected buckets before closing because compiler cache, runtime resolver behavior, and root exports are cross-cutting.

## Compatibility / Intentional Behavior Break

- Intentional public API removals required by the spec:
  - `autoloop.PolicyOverride`, `autoloop.simple.PolicyOverride`, and public examples using it
  - SDK constructor `root=`
  - SDK `typed_input=` compatibility
  - public `parameters=` workflow-parameter alias
  - raw strings for enum-backed public `Policy(...)` fields
- Compatibility retained only for internal/core policy objects where the spec allows it:
  - existing concrete `ProviderPolicy`
  - existing core `ProviderPolicyOverride`
- Do not change runtime config policy syntax, strict-policy semantics, or provider emitters in this patch.

## Risk Register

- Risk: implementing `Policy` as a full concrete policy again would silently preserve the old semantics and break inheritance-sensitive tests.
  - Control: keep one central sparse-lowering path in `autoloop.policy` and forbid duplicate flattening helpers elsewhere.
- Risk: resolver merge order could diverge between workflow execution, inline operations, and direct SDK operations.
  - Control: make `ProviderPolicyResolver` and shared policy helpers the only merge owners; SDK should pass layers, not merged policies.
- Risk: removing `PolicyOverride` and renaming SDK arguments will break a large number of existing tests and exports in ways that obscure real regressions.
  - Control: update public-surface tests first in the implementation sequence and keep compatibility removals explicit in failure triage.
- Risk: topology hashing could become unstable if `Policy.to_layer_payload()` includes non-deterministic or non-JSON-safe values.
  - Control: normalize enums to strings, paths to strings, tuples/lists to deterministic order, and serialize explicit bases recursively.
- Risk: dangerous-access interactions can regress if same-layer and cross-layer validation are split inconsistently.
  - Control: enforce same-layer invariants in public lowering and rely on final post-merge strict validation for cross-layer contradictions.

## Out Of Scope

- Provider emitter behavior changes for Codex or Claude.
- CLI policy flags, SDK `strict_policy`, or config-file syntax changes.
- Schema changes to core nested provider-policy models beyond accepting shared public policy layers around them.
