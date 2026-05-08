# Implementation Notes

- Task ID: spec-flat-enum-backed-policy-and-policyoverride-2b5811aa
- Pair: implement
- Phase ID: flat-policy-facade
- Phase Directory Key: flat-policy-facade
- Phase Title: Implement Flat Policy Facade
- Scope: phase-local producer artifact

## Files changed
- `autoloop/simple.py`
- `autoloop/__init__.py`
- `tests/unit/test_simple_surface.py`
- `tests/unit/test_simple_policy.py`
- `tests/runtime/test_provider_policy_steps.py`

## Symbols touched
- Public: `Policy`, `PolicyOverride`, `ProviderName`, `ModelEffort`, `ModelVerbosity`, `ReasoningSummary`, `SandboxMode`, `NetworkMode`, `PermissionMode`
- Private helpers: `_PolicyEnum`, `_policy_enum_value`, `_policy_tuple`, `_policy_optional_tuple`, `_policy_string_mapping`, `_flat_policy_payload`
- Export surfaces: `autoloop.simple.__all__`, `autoloop.__all__`

## Checklist mapping
- Flat facade and enums in `autoloop/simple.py`: complete
- Shared lowering / inference / incompatibility validation helper: complete
- Root/simple exports: complete
- Unit and runtime coverage for lowering, sparsity, dangerous access, imports, and operation/workflow integration: complete

## Assumptions
- The existing core `ProviderPolicy` validator remains authoritative and unchanged, even where it constrains the facade shape.

## Preserved invariants
- No changes to `autoloop/core/provider_policy.py`
- No new accepted policy input types outside canonical `ProviderPolicy` / `ProviderPolicyOverride`
- No emitter, runtime config parsing, merge-order, or strict-policy semantic changes
- Enum-backed flat fields reject raw strings at the facade boundary

## Intended behavior changes
- Added flat enum-backed workflow/step policy authoring helpers that lower into nested provider policy payloads.
- Added runtime inference for read-only, workspace-write, limited-network, and dangerous-access cases.

## Known non-changes
- No uppercase aliases, namespaced kwargs, or alternate dangerous-access constructors
- No public `allow_dangerous_bypass` / `disable_dangerous_bypass` kwargs

## Expected side effects
- `Policy()` now reproduces `SYSTEM_DEFAULT_PROVIDER_POLICY` through the flat surface.
- `PolicyOverride(...)` now produces sparse override payloads suitable for merge-based resolution.
- Explicit `sandbox_mode=SandboxMode.DANGER_FULL_ACCESS` without an explicit `permission_mode` lowers to manual `permissions.mode='ask'` plus dangerous bypass, because the unchanged core validator rejects the current default `full_auto_sandboxed` mode with danger-full-access.

## Deduplication / centralization
- Centralized enum normalization, tuple/mapping coercion, inference, and compatibility checks in `_flat_policy_payload` to keep `Policy` and `PolicyOverride` aligned.

## Validation performed
- `./.venv/bin/python -m pytest tests/unit/test_simple_surface.py tests/unit/test_provider_policy.py tests/runtime/test_provider_policy_steps.py tests/runtime/test_provider_policy_emitters.py tests/runtime/test_provider_policy_config.py tests/unit/test_simple_policy.py`
