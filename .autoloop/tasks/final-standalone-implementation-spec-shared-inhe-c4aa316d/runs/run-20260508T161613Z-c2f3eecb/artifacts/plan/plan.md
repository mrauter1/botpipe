# Shared-Policy Export Cleanup Plan

## Objective
Remove leaked policy-type aliases from the public `autoloop.simple` namespace while preserving the canonical shared-policy exports from `autoloop.policy` and `autoloop.sdk`, plus existing simple declaration/runtime acceptance of `Policy`, `ProviderPolicy`, `ProviderPolicyOverride`, and `None`.

## Current state
- `autoloop.simple` imports `PolicyInput` into module scope and re-exports it implicitly via normal module attribute lookup.
- `autoloop.simple` also defines `ProviderPolicyInput = PolicyInput`, creating a second public alias that is not part of the intended surface.
- `autoloop.__init__` already omits `PolicyInput` from `__all__`; the remaining leak is the simple module namespace.
- Existing tests already require `PolicyInput` to stay public only in `autoloop.policy` and `autoloop.sdk`, and require simple declarations to keep accepting internal `ProviderPolicyOverride` instances.

## Scope
- In scope:
  - `autoloop/simple.py` public namespace cleanup and internal type-alias usage update.
  - Unit/runtime surface tests that assert the export matrix and accepted policy inputs.
- Out of scope:
  - Any change to `autoloop.policy.PolicyInput` or `autoloop.sdk.PolicyInput`.
  - Any widening/narrowing of supported policy-layer runtime values.
  - Broader public-surface cleanup unrelated to policy aliases.

## Milestone
### 1. Remove simple-module leaked aliases without changing behavior
- Stop binding public `PolicyInput` and `ProviderPolicyInput` names in `autoloop.simple`.
- Replace internal annotations in `autoloop.simple` with a private alias or equivalent private union so:
  - `from autoloop.simple import PolicyInput` fails.
  - `getattr(autoloop.simple, "PolicyInput")` raises `AttributeError`.
  - `from autoloop.simple import ProviderPolicyInput` fails or the name is otherwise absent from the module namespace.
  - Internal annotation resolution and runtime normalization still accept `None`, `Policy`, `_CoreProviderPolicy`, and `_CoreProviderPolicyOverride`.
- Keep `autoloop.simple.__all__` unchanged except for continuing to exclude these names.

## Interface and compatibility notes
- Intentional public-surface break: only the leaked `autoloop.simple.PolicyInput` and duplicate `autoloop.simple.ProviderPolicyInput` aliases are removed.
- Required compatibility preservation:
  - `autoloop.policy.PolicyInput` remains public and unchanged.
  - `autoloop.sdk.PolicyInput` remains public and identical to `autoloop.policy.PolicyInput`.
  - Simple workflow/step declarations continue to accept `Policy`, `ProviderPolicy`, `ProviderPolicyOverride`, and `None`.
- No migration is required for supported public imports; unsupported imports from `autoloop.simple` become hard failures by design.

## Regression risks and controls
- Risk: converting annotations carelessly could break runtime/type-hint resolution inside `autoloop.simple`.
  - Control: keep a private in-module alias or private union available to annotation resolution while removing only the public names.
- Risk: cleanup could accidentally narrow accepted policy values for workflow or step declarations.
  - Control: preserve `_normalize_provider_policy()` behavior and cover both public `Policy` and internal `ProviderPolicyOverride` acceptance in tests.
- Risk: top-level package or SDK surface could drift during cleanup.
  - Control: retain export-matrix assertions covering `autoloop`, `autoloop.simple`, `autoloop.policy`, and `autoloop.sdk`.

## Validation
- `./.venv/bin/pytest tests/unit/test_simple_policy.py`
- `./.venv/bin/pytest tests/unit/test_simple_surface.py tests/unit/test_policy.py tests/runtime/test_sdk_policy.py tests/unit/test_sdk_facade.py`

## Rollback
- Revert the `autoloop.simple` alias cleanup if it unexpectedly breaks internal annotation resolution or declaration validation.
- If rollback is needed, keep the stronger tests and use them to isolate a private-alias implementation that removes the public leak without restoring the public symbols.
