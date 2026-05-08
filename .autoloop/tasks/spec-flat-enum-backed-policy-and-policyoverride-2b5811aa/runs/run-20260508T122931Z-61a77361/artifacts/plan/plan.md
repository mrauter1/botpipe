# Flat Policy Facade Plan

## Scope
- Implement `Policy(...) -> ProviderPolicy` and `PolicyOverride(...) -> ProviderPolicyOverride` in `autoloop/simple.py` only as flat public authoring helpers.
- Add enum-backed public fixed-option types in `autoloop/simple.py`: `ProviderName`, `ModelEffort`, `ModelVerbosity`, `ReasoningSummary`, `SandboxMode`, `NetworkMode`, `PermissionMode`.
- Export the new helpers and enums from `autoloop/simple.py`, `autoloop/__init__.py`, and `autoloop.__all__`.
- Add focused unit/runtime coverage for exports, enum strictness, lowering, override sparsity, merge behavior, workflow compilation, and operation normalization.

## Out Of Scope
- No schema changes in `autoloop/core/provider_policy.py`.
- No provider emitter changes, runtime config parsing changes, merge-order changes, or strict-policy semantic changes.
- No compatibility aliases, helper constructors, namespaced kwargs, or raw-string acceptance for enum-backed flat fields.

## Existing Constraints To Preserve
- `ProviderPolicy` and `ProviderPolicyOverride` remain the only engine-facing authored policy types accepted by workflow declarations and inline operations.
- Internal serialized values must stay as strings because fingerprints, runtime config, and emitters already depend on the nested schema payload shape.
- `_normalize_provider_policy(policy)` in `autoloop/simple.py` should remain behaviorally unchanged apart from import/export adjacency if needed.
- `Policy()` must produce a full `ProviderPolicy` based on `SYSTEM_DEFAULT_PROVIDER_POLICY`; `PolicyOverride()` must produce a sparse `ProviderPolicyOverride`.

## Planned Interface
- `autoloop.simple` adds `_PolicyEnum(str, Enum)` plus the seven public enums defined by the spec.
- `autoloop.simple` adds:
  - `Policy(...) -> ProviderPolicy`
  - `PolicyOverride(...) -> ProviderPolicyOverride`
  - `_policy_enum_value(...)`
  - `_policy_tuple(...)`
  - `_policy_optional_tuple(...)`
  - `_policy_string_mapping(...)`
  - one shared private flat-policy payload builder for both full and sparse lowering.
- `ProviderPolicyInput` remains `ProviderPolicy | ProviderPolicyOverride | None`; the new helpers return those canonical types instead of widening accepted input types.

## Implementation Approach
### 1. Flat facade and enum normalization in `autoloop/simple.py`
- Add the enum classes and helper coercions near other public simple-surface declarations.
- Enforce runtime enum strictness centrally with `_policy_enum_value(...)`; raw strings and other wrong types must raise `TypeError` with guidance to use the matching enum class.
- Normalize tuple-like open-ended inputs for filesystem paths, domains, and permission rules with shared helpers that:
  - accept scalar `str` and `Path`,
  - accept ordered sequences without treating `str`/`bytes` as sequences,
  - trim whitespace,
  - reject empty entries,
  - convert `Path` to `str`,
  - dedupe while preserving first occurrence.
- Normalize `model_overrides` through `_policy_string_mapping(...)`, keeping keys/values stringified and rejecting empty keys.

### 2. Shared lowering helper
- Implement one private helper that computes effective flat inputs and returns the nested payload for either full or sparse construction.
- Centralize all non-trivial behavior there:
  - enum `.value` lowering,
  - read-only alias handling,
  - implicit `workspace_write` when `allow_write` is supplied,
  - implicit `limited` network when `network_domains` is supplied,
  - dangerous-access inference for `sandbox_mode=SandboxMode.DANGER_FULL_ACCESS` and `permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED`,
  - incompatibility checks required by the spec,
  - sparse inclusion rules for override payloads.
- For `Policy(...)`, start from `SYSTEM_DEFAULT_PROVIDER_POLICY.model_dump(mode="python", warnings=False)` and only overwrite fields whose effective value changed.
- For `PolicyOverride(...)`, build a payload from scratch and include only touched sections (`model`, `permissions`, `sandbox`, `workspace.filesystem`, `workspace.network`) per the spec.

### 3. Dangerous-access and mode rules
- Encode the required coupling without touching nested validators:
  - `PermissionMode.FULL_AUTO_UNSANDBOXED` implies `allow_dangerous_bypass=True` and, unless already explicit, `SandboxMode.DANGER_FULL_ACCESS`.
  - `SandboxMode.DANGER_FULL_ACCESS` implies `allow_dangerous_bypass=True` while preserving default permission mode unless explicitly changed.
- Reject incompatible combinations in the facade before model validation:
  - read-only with `allow_write`,
  - explicit read-only alias conflicting with non-read-only sandbox mode,
  - limited network without domains,
  - full/none network with non-empty `network_domains`,
  - empty `network_domains` when used for inference,
  - unsandboxed full-auto with read-only/workspace-write sandbox mode,
  - danger-full-access sandbox with `PermissionMode.FULL_AUTO_SANDBOXED`.
- Preserve lowering of filesystem and network subpayloads even for danger-full-access mode; enforcement remains with existing strict validation and emitters.

### 4. Public exports
- Re-export the helpers and enums from `autoloop/simple.py` and `autoloop/__init__.py`.
- Expand `autoloop.__all__` in a stable order that keeps the existing canonical surface intact while adding the new symbols explicitly.
- Update export tests in `tests/unit/test_simple_surface.py` to assert root/simple imports, `__all__` membership, and callable status for `Policy` / `PolicyOverride`.

### 5. Test coverage
- Prefer a new focused file `tests/unit/test_simple_policy.py` for flat facade behavior so export tests in `test_simple_surface.py` stay readable.
- Add unit coverage for:
  - `Policy()` / `PolicyOverride()` return types,
  - enum strictness `TypeError` cases for both helpers,
  - tuple/mapping normalization outcomes,
  - default-preserving full policy behavior,
  - sparse override behavior,
  - dangerous-access inference and invalid combinations,
  - merge behavior with `merge_provider_policies(...)`.
- Extend runtime-facing coverage in existing files only where it proves integration:
  - workflow compilation with workflow-level `Policy(...)`,
  - step compilation with `PolicyOverride(...)`,
  - dangerous workflow compilation,
  - operation normalization path using `llm(..., policy=PolicyOverride(...))`.

## Milestone
### M1. Ship the flat enum-backed policy facade
- Add the enums, coercion helpers, lowering helper, `Policy`, and `PolicyOverride` in `autoloop/simple.py`.
- Export new public names from `autoloop/simple.py` and `autoloop/__init__.py`.
- Add/extend unit and runtime tests listed in the spec.
- Run the required targeted pytest commands.

## Regression Prevention
- Do not widen accepted policy input types anywhere outside the new helper return values; declarations and operations should keep consuming only `ProviderPolicy`, `ProviderPolicyOverride`, or `None`.
- Keep all nested payload keys and value formats aligned with current schema field names so fingerprints, compiler serialization, resolver merging, and emitters remain unchanged.
- Prefer facade-side validation for flat incompatibilities so failures are deterministic and do not depend on downstream emitter/runtime paths.
- Preserve default sections in `Policy()` by layering over `SYSTEM_DEFAULT_PROVIDER_POLICY`; preserve override sparsity in `PolicyOverride()` by omitting untouched sections.

## Validation Plan
- Run:
  - `pytest tests/unit/test_simple_surface.py`
  - `pytest tests/unit/test_provider_policy.py`
  - `pytest tests/runtime/test_provider_policy_steps.py`
  - `pytest tests/runtime/test_provider_policy_emitters.py`
  - `pytest tests/runtime/test_provider_policy_config.py`
  - `pytest tests/unit/test_simple_policy.py` if the new focused file is added
- Spot-check that compiled workflow policies are still JSON-serializable through existing compiler paths and that operation policy normalization still accepts the new override-returning helpers without special cases.

## Compatibility Notes
- This is an additive public API expansion, but it intentionally rejects raw strings for new enum-backed flat fields in the facade at runtime.
- Existing direct nested `ProviderPolicy(...)` / `ProviderPolicyOverride(...)` authoring remains valid and unchanged.
- Existing config-file policy parsing remains string-based and unchanged because the nested schema is intentionally untouched.

## Risk Register
- Risk: sparse override construction accidentally materializes default sandbox or permissions blocks and changes merge behavior.
  - Control: explicitly gate section inclusion on supplied/effective flat fields and add merge assertions against `SYSTEM_DEFAULT_PROVIDER_POLICY`.
- Risk: facade-side inference diverges from current nested validation rules and creates incoherent dangerous-access payloads.
  - Control: encode the spec’s compatibility matrix in the shared helper and verify with both direct construction and merge tests.
- Risk: export-order changes break canonical-surface tests.
  - Control: update `tests/unit/test_simple_surface.py` in lockstep with `autoloop.__all__`.
- Risk: normalization helpers over-accept sequence-like inputs such as `bytes` or under-handle `Path`.
  - Control: add negative tests for `bytes` and positive tests for scalar and sequence `Path` inputs.

## Rollback
- Remove the new public helpers/enums and corresponding exports.
- Remove the new flat-facade tests.
- Because the core schema and runtime config layers stay unchanged, rollback is isolated to `autoloop/simple.py`, `autoloop/__init__.py`, and test files.
