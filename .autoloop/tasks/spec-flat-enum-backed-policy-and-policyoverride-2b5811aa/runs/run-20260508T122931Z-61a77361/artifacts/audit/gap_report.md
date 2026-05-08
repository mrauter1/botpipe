# Original intent considered

- `request.md` requires a flat enum-backed `Policy(...)` / `PolicyOverride(...)` facade in `autoloop/simple.py`, root/simple exports, enum-strict runtime validation for fixed option fields, lowering into unchanged nested core policy objects, and focused unit/runtime coverage.
- The original request also explicitly included a `DangerousManualWorkflow` example using `Policy(sandbox_mode=SandboxMode.DANGER_FULL_ACCESS)` with no explicit `permission_mode`, and required that dangerous sandbox access preserve the default permission mode unless explicitly overridden.

# Clarifications / superseding decisions

- `raw_phase_log.md` clarification QA-1 explicitly rejected a silent fallback that rewrote manual `danger_full_access` to `permissions.mode='ask'`.
- `raw_phase_log.md` clarification QA-2 then explicitly changed intent again: manual `danger_full_access` is invalid unless the author also supplies an explicit compatible `permission_mode`, even though that means the original `DangerousManualWorkflow` example no longer compiles.
- `decisions.txt` block 8 records that narrowed contract as the final implementation direction. Under the authority order for this run, those explicit clarifications supersede the earlier example.

# Implemented behavior

- `autoloop/simple.py` now defines `_PolicyEnum`, the seven requested public enums, the shared lowering helpers, and public `Policy(...) -> ProviderPolicy` / `PolicyOverride(...) -> ProviderPolicyOverride` facades.
- `autoloop/simple.py` lowers flat inputs into nested payloads and validates them through unchanged `ProviderPolicy` / `ProviderPolicyOverride` models from `autoloop.core.provider_policy`.
- `autoloop/__init__.py` and `autoloop.simple.__all__` export `Policy`, `PolicyOverride`, and all new enums.
- `tests/unit/test_simple_policy.py` covers enum rejection, helper coercion, full-policy lowering, sparse override behavior, dangerous-access behavior, merge behavior, workflow compilation, and operation-surface acceptance.
- `tests/unit/test_simple_surface.py` pins the root export surface including all new public names.
- `tests/runtime/test_provider_policy_steps.py` covers inline-operation acceptance for `PolicyOverride(...)`, including the dangerous override path.
- Audit verification:
  - The requested regression slice passed: `./.venv/bin/python -m pytest tests/unit/test_simple_surface.py tests/unit/test_provider_policy.py tests/runtime/test_provider_policy_steps.py tests/runtime/test_provider_policy_emitters.py tests/runtime/test_provider_policy_config.py tests/unit/test_simple_policy.py`
  - Direct audit checks confirmed the main acceptance-shape workflow compiles, `Policy(permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED)` lowers to `danger_full_access`, and manual `Policy(sandbox_mode=SandboxMode.DANGER_FULL_ACCESS)` now raises the clarified `ValueError`.

# Unresolved gaps

- None material after applying the authoritative clarifications in `raw_phase_log.md`.

# Differences justified by later clarification or analysis

- The original request’s dangerous-manual example no longer compiles unchanged. This is justified by explicit clarification QA-2, which superseded that example after the team confirmed the unchanged core `ProviderPolicy` validator makes “preserve the default permission mode” invalid for `sandbox.mode='danger_full_access'`.
- The final facade therefore rejects manual `danger_full_access` unless an explicit compatible `permission_mode` is supplied, instead of silently changing permission mode. That preserves the unchanged core schema and avoids non-sparse override behavior.

# Recommended next run

- No follow-up implementation run is required.
