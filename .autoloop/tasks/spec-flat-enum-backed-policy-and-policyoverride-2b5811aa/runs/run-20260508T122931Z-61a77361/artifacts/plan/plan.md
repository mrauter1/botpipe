# Flat Policy Facade Plan

## Scope
- Implement the flat public policy authoring facade in `autoloop/simple.py` only.
- Add `Policy(...) -> ProviderPolicy` and `PolicyOverride(...) -> ProviderPolicyOverride`.
- Add public enums `ProviderName`, `ModelEffort`, `ModelVerbosity`, `ReasoningSummary`, `SandboxMode`, `NetworkMode`, and `PermissionMode`.
- Export the new helpers and enums from `autoloop/simple.py`, `autoloop/__init__.py`, and `autoloop.__all__`.
- Add targeted tests for exports, enum strictness, lowering, dangerous-access inference, override sparsity, workflow compilation, and operation normalization.

## Out Of Scope
- No changes to `autoloop/core/provider_policy.py` schema definitions, validators, or accepted nested payload shape.
- No provider emitter changes, runtime config parsing changes, merge-order changes, or strict-policy semantic changes.
- No alternate constructors, namespaced kwargs, uppercase aliases, or raw-string acceptance for enum-backed flat fields.

## Required Public Contract
### Imports to add in `autoloop/simple.py`
```python
from collections.abc import Mapping, Sequence
from enum import Enum
from pathlib import Path

from autoloop.core.provider_policy import (
    ModelPolicy,
    PermissionPolicy,
    ProviderPolicy,
    ProviderPolicyOverride,
    SandboxPolicy,
    SYSTEM_DEFAULT_PROVIDER_POLICY,
    WorkspaceFilesystemPolicy,
    WorkspaceNetworkPolicy,
    WorkspacePolicy,
)
```

### Enum base and public enums
```python
class _PolicyEnum(str, Enum):
    def __str__(self) -> str:
        return self.value
```

- Implement the seven public enums exactly as specified in the request.
- Enum-backed flat fields are: `provider`, `effort`, `verbosity`, `reasoning_summary`, `sandbox_mode`, `network`, and `permission_mode`.
- Open-ended string fields remain only: `model`, `base_url`, filesystem paths, network domains, permission rule patterns, and `model_overrides` keys/values.

### Exact public signatures
```python
def Policy(
    *,
    model: str | None = None,
    provider: ProviderName | None = None,
    base_url: str | None = None,
    effort: ModelEffort | None = None,
    verbosity: ModelVerbosity | None = None,
    reasoning_summary: ReasoningSummary | None = None,
    model_overrides: Mapping[str, str] | None = None,
    sandbox_mode: SandboxMode | None = None,
    read_only: bool = False,
    allow_read: str | Path | Sequence[str | Path] | None = None,
    deny_read: str | Path | Sequence[str | Path] | None = None,
    allow_write: str | Path | Sequence[str | Path] | None = None,
    deny_write: str | Path | Sequence[str | Path] | None = None,
    network: NetworkMode | None = None,
    network_domains: str | Sequence[str] | None = None,
    deny_network_domains: str | Sequence[str] | None = None,
    allow_local_binding: bool | None = None,
    permission_mode: PermissionMode | None = None,
    allow_permissions: str | Sequence[str] | None = None,
    ask_permissions: str | Sequence[str] | None = None,
    deny_permissions: str | Sequence[str] | None = None,
) -> ProviderPolicy:
    ...


def PolicyOverride(
    *,
    model: str | None = None,
    provider: ProviderName | None = None,
    base_url: str | None = None,
    effort: ModelEffort | None = None,
    verbosity: ModelVerbosity | None = None,
    reasoning_summary: ReasoningSummary | None = None,
    model_overrides: Mapping[str, str] | None = None,
    sandbox_mode: SandboxMode | None = None,
    read_only: bool = False,
    allow_read: str | Path | Sequence[str | Path] | None = None,
    deny_read: str | Path | Sequence[str | Path] | None = None,
    allow_write: str | Path | Sequence[str | Path] | None = None,
    deny_write: str | Path | Sequence[str | Path] | None = None,
    network: NetworkMode | None = None,
    network_domains: str | Sequence[str] | None = None,
    deny_network_domains: str | Sequence[str] | None = None,
    allow_local_binding: bool | None = None,
    permission_mode: PermissionMode | None = None,
    allow_permissions: str | Sequence[str] | None = None,
    ask_permissions: str | Sequence[str] | None = None,
    deny_permissions: str | Sequence[str] | None = None,
) -> ProviderPolicyOverride:
    ...
```

- Do not add public `allow_dangerous_bypass` or `disable_dangerous_bypass` kwargs.
- Unknown kwargs should continue to fail with normal Python `TypeError`.

### Exact helper signatures
```python
def _policy_enum_value(value: object, *, enum_cls: type[_PolicyEnum], field_name: str) -> str | None:
    ...


def _policy_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    ...


def _policy_optional_tuple(value: object, *, field_name: str) -> tuple[str, ...] | None:
    ...


def _policy_string_mapping(value: object, *, field_name: str) -> dict[str, str] | None:
    ...
```

### Exact docstrings to require
```python
"""Flat workflow-level authoring facade for ProviderPolicy.

Omitted fields preserve SYSTEM_DEFAULT_PROVIDER_POLICY. Fixed option fields use
Autoloop policy enums rather than raw strings. network_domains implies limited
network mode. allow_write implies workspace_write mode unless read_only or
sandbox_mode=SandboxMode.READ_ONLY is set, which is invalid with allow_write.
sandbox_mode=SandboxMode.DANGER_FULL_ACCESS and
permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED use the same flat API and
internally enable the dangerous-bypass latch required by the nested policy
schema.
"""
```

```python
"""Flat step/operation-level authoring facade for ProviderPolicyOverride.

Only supplied fields are included in the override payload. Fixed option fields
use Autoloop policy enums rather than raw strings. read_only=True also sets
allow_write=() so merged policy cannot inherit write roots. network_domains
implies limited network mode. sandbox_mode=SandboxMode.DANGER_FULL_ACCESS and
permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED use the same flat API and
internally enable the dangerous-bypass latch required by the nested policy
schema.
"""
```

## Implementation Approach
### 1. Add flat facade types and helpers in `autoloop/simple.py`
- Keep `ProviderPolicyInput = ProviderPolicy | ProviderPolicyOverride | None` unchanged; the new helpers must return those canonical objects rather than widening accepted input types elsewhere.
- Implement `_policy_enum_value(...)` so:
  - `None` returns `None`,
  - enum members lower to `.value`,
  - raw strings and wrong types raise `TypeError` instructing authors to use the correct enum class.
- Implement `_policy_tuple(...)`, `_policy_optional_tuple(...)`, and `_policy_string_mapping(...)` with the exact coercion behavior from the request:
  - scalar `str` becomes a one-element tuple,
  - scalar `Path` becomes a one-element tuple of `str(path)`,
  - `Sequence[str | Path]` normalizes to ordered deduped tuples,
  - `str` is not treated as a sequence,
  - `bytes` is rejected,
  - whitespace is stripped,
  - empty string entries are rejected,
  - mapping keys/values are stringified and empty keys are rejected.

### 2. Centralize lowering in one private helper
- Implement one shared helper for full and sparse construction with the request’s suggested shape or an equivalent local name:
```python
def _flat_policy_payload(
    *,
    full_policy: bool,
    model: str | None,
    provider: ProviderName | None,
    base_url: str | None,
    effort: ModelEffort | None,
    verbosity: ModelVerbosity | None,
    reasoning_summary: ReasoningSummary | None,
    model_overrides: Mapping[str, str] | None,
    sandbox_mode: SandboxMode | None,
    read_only: bool,
    allow_read: object,
    deny_read: object,
    allow_write: object,
    deny_write: object,
    network: NetworkMode | None,
    network_domains: object,
    deny_network_domains: object,
    allow_local_binding: bool | None,
    permission_mode: PermissionMode | None,
    allow_permissions: object,
    ask_permissions: object,
    deny_permissions: object,
) -> dict[str, object]:
    ...
```
- Centralize in that helper:
  - enum normalization,
  - read-only handling,
  - workspace-write inference,
  - network-domain inference,
  - dangerous-access inference,
  - tuple/mapping coercion,
  - incompatible-input validation,
  - sparse section inclusion rules.

### 3. Lower into existing nested payloads only
- `Policy(...)`:
  - start from `SYSTEM_DEFAULT_PROVIDER_POLICY.model_dump(mode="python", warnings=False)`,
  - apply only fields changed by explicit or implied flat inputs,
  - return `ProviderPolicy.model_validate(updated_payload)`.
- `PolicyOverride(...)`:
  - build payload from scratch,
  - include `model`, `permissions`, `sandbox`, `workspace.filesystem`, and `workspace.network` only when the request’s sparse rules require them,
  - return `ProviderPolicyOverride.model_validate(payload)`.
- Keep `_normalize_provider_policy(policy)` behavior unchanged so the new helpers work naturally because they already return accepted policy types.

### 4. Required behavior to encode explicitly
- `read_only=True` aliases `sandbox_mode=SandboxMode.READ_ONLY`.
- `allow_write` implies `SandboxMode.WORKSPACE_WRITE` only when not read-only and no explicit sandbox mode overrides it.
- `network_domains=<non-empty>` implies `NetworkMode.LIMITED` when `network is None`.
- `PermissionMode.FULL_AUTO_UNSANDBOXED` implies `allow_dangerous_bypass=True` and, unless explicitly set, `SandboxMode.DANGER_FULL_ACCESS`.
- `SandboxMode.DANGER_FULL_ACCESS` implies `allow_dangerous_bypass=True` while preserving default permission mode unless the caller explicitly changes it.
- The facade must reject incompatible combinations required by the spec, including:
  - raw strings for enum-backed fields,
  - read-only with `allow_write`,
  - `NetworkMode.LIMITED` without `network_domains`,
  - `NetworkMode.FULL` or `NetworkMode.NONE` with non-empty `network_domains`,
  - `network_domains=()` when it would be used for inference,
  - `PermissionMode.FULL_AUTO_UNSANDBOXED` with `SandboxMode.READ_ONLY` or `SandboxMode.WORKSPACE_WRITE`,
  - `SandboxMode.DANGER_FULL_ACCESS` with `PermissionMode.FULL_AUTO_SANDBOXED`.
- Lower filesystem and network subpayloads even for danger-full-access mode; enforcement remains with existing strict validation and emitters.

### 5. Exports and tests
- Export all new helpers and enums from `autoloop/simple.py`, `autoloop/__init__.py`, and `autoloop.__all__`.
- Add or extend tests to cover:
  - root/simple imports and `__all__` membership for every new public name,
  - callable status for `Policy` and `PolicyOverride`,
  - exact enum strictness failures for both helpers,
  - full-policy default preservation,
  - sparse override behavior,
  - merge behavior against `SYSTEM_DEFAULT_PROVIDER_POLICY`,
  - dangerous-access inference and invalid combinations,
  - workflow compilation and operation normalization using the new helpers,
  - the exact examples and acceptance workflows called out in the request.
- Keep existing provider-emitter, provider-policy, runtime-config, and runtime-step suites in the validation list to guard regressions outside the new facade.

## Milestone
### M1. Ship the flat enum-backed facade without schema changes
- Implement the exact public signatures, exact helper signatures, exact docstrings, enums, and shared lowering helper in `autoloop/simple.py`.
- Export every new public symbol from `autoloop/simple.py`, `autoloop/__init__.py`, and `autoloop.__all__`.
- Add focused tests proving exact lowering, sparsity, dangerous-access behavior, compiler integration, and operation normalization.
- Run the required targeted pytest commands from the request.

## Regression Prevention
- Do not widen accepted policy surface types outside the helper return values.
- Keep nested payload keys and serialized values string-based so fingerprints, config parsing, resolver merging, and emitters remain unchanged.
- Use one shared lowering helper so `Policy(...)` and `PolicyOverride(...)` cannot drift on enum coercion, inference, or incompatibility checks.
- Preserve `Policy()` defaults by layering over `SYSTEM_DEFAULT_PROVIDER_POLICY`; preserve `PolicyOverride()` sparsity by omitting untouched sections.
- Preserve current strict-policy validation ownership for danger-full-access enforcement and reporting.

## Validation Plan
- Run:
  - `pytest tests/unit/test_simple_surface.py`
  - `pytest tests/unit/test_provider_policy.py`
  - `pytest tests/runtime/test_provider_policy_steps.py`
  - `pytest tests/runtime/test_provider_policy_emitters.py`
  - `pytest tests/runtime/test_provider_policy_config.py`
  - `pytest tests/unit/test_simple_policy.py` if a new focused file is added
- Verify the exact workflow-level, step-level, dangerous-access, and operation examples from the request compile or normalize successfully.
- Verify the new facade does not require any special handling in workflow discovery, compiler validation, resolver merge paths, or operation normalization.

## Compatibility Notes
- This is an additive authoring API, but it intentionally rejects raw strings for enum-backed flat fields.
- Existing direct nested `ProviderPolicy(...)` and `ProviderPolicyOverride(...)` authoring remains supported and unchanged.
- Config-file and JSON-facing policy serialization remain string-based and unchanged because the nested schema is intentionally untouched.
- No migration is required for existing nested policy authors; the new facade is optional.

## Risk Register
- Risk: omission of exact signature or docstring requirements reopens public-surface drift.
  - Control: keep the exact signature and docstring blocks above as implementation requirements and mirror them in phase acceptance criteria.
- Risk: sparse override construction accidentally materializes default sandbox or permissions blocks and changes merge behavior.
  - Control: gate inclusion strictly on the request’s sparse rules and add merge assertions against `SYSTEM_DEFAULT_PROVIDER_POLICY`.
- Risk: facade-side inference diverges between `Policy(...)` and `PolicyOverride(...)`.
  - Control: keep one shared lowering helper and add paired tests for both helpers.
- Risk: export-order changes break canonical-surface tests.
  - Control: update `tests/unit/test_simple_surface.py` in lockstep with `autoloop.__all__`.

## Rollback
- Remove the new flat-facade helpers, enums, exports, and tests.
- Because the nested schema and runtime layers stay unchanged, rollback remains local to `autoloop/simple.py`, `autoloop/__init__.py`, and the added/updated tests.
