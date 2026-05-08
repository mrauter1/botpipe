# Original intent considered

- Remove the leaked `PolicyInput` public import path from `autoloop.simple` and keep it public only from `autoloop.policy` and `autoloop.sdk`.
- Remove the duplicate `ProviderPolicyInput` alias from the public `autoloop.simple` namespace.
- Preserve existing simple declaration and runtime acceptance of `Policy`, `ProviderPolicy`, `ProviderPolicyOverride`, and `None`.
- Validate with:
  - `./.venv/bin/pytest tests/unit/test_simple_policy.py`
  - `./.venv/bin/pytest tests/unit/test_simple_surface.py tests/unit/test_policy.py tests/runtime/test_sdk_policy.py tests/unit/test_sdk_facade.py`

# Clarifications / superseding decisions

- No explicit clarification entries in `raw_phase_log.md` supersede the immutable request.
- The recorded decisions are consistent with the original request rather than narrowing it:
  - `decisions.txt:2-3` keeps `autoloop.policy` and `autoloop.sdk` as the canonical `PolicyInput` export sites and preserves accepted simple policy inputs.
  - `decisions.txt:5` documents the chosen implementation detail: a private `_SimplePolicyInput` alias inside `autoloop.simple`.
  - `decisions.txt:7` adds targeted regression coverage for direct `ProviderPolicy` and explicit `None`.

# Implemented behavior

- `autoloop.simple` no longer binds `PolicyInput` or `ProviderPolicyInput` publicly. Instead it defines a private `_SimplePolicyInput` union and uses that for workflow and declaration annotations in `autoloop/simple.py:43-60`.
- `PolicyInput` remains public in `autoloop.policy` via `PolicyInput = Policy | ProviderPolicy | ProviderPolicyOverride | None` and `autoloop.policy.__all__` in `autoloop/policy.py:323` and `autoloop/policy.py:531-538`.
- `PolicyInput` remains public in `autoloop.sdk.__all__` in `autoloop/sdk.py:1834-1842`.
- The export contract and accepted inputs are covered by `tests/unit/test_simple_policy.py:95-145`, including failed import / `AttributeError` checks for the removed `autoloop.simple` names and continued acceptance of `Policy`, `ProviderPolicy`, `ProviderPolicyOverride`, and `None`.
- Direct audit verification in the current workspace confirmed:
  - `"PolicyInput"` is present in `autoloop.policy.__all__` and `autoloop.sdk.__all__`.
  - `"PolicyInput"` is absent from `autoloop.__all__` and `autoloop.simple.__all__`.
  - `"ProviderPolicyInput"` is absent from `autoloop.simple.__all__`.
  - `getattr(autoloop.simple, "PolicyInput")` and `getattr(autoloop.simple, "ProviderPolicyInput")` both raise `AttributeError`.
- Required validation passed during this audit:
  - `./.venv/bin/pytest tests/unit/test_simple_policy.py` -> 8 passed
  - `./.venv/bin/pytest tests/unit/test_simple_surface.py tests/unit/test_policy.py tests/runtime/test_sdk_policy.py tests/unit/test_sdk_facade.py` -> 155 passed

# Unresolved gaps

- None. The final codebase and tests satisfy the requested export contract and validation requirements.

# Differences justified by later clarification or analysis

- The implementation keeps an internal `_SimplePolicyInput` alias in `autoloop.simple` instead of duplicating the union across annotations. This changes only internal structure, not the requested public surface, and is explicitly recorded in `decisions.txt:5`.
- Test coverage was expanded beyond the initial leak-removal checks to lock in direct `ProviderPolicy` and explicit `None` acceptance. This is additive and aligns with the original compatibility requirement.

# Recommended next run

- No follow-up implementation run is required for this request.
