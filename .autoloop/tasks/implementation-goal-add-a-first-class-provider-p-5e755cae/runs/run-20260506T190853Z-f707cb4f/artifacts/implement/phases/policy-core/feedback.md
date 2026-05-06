# Implement ↔ Code Reviewer Feedback

- Task ID: implementation-goal-add-a-first-class-provider-p-5e755cae
- Pair: implement
- Phase ID: policy-core
- Phase Directory Key: policy-core
- Phase Title: Core Policy Domain
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 `blocking` — [autoloop/core/provider_policy.py:300] `ProviderPolicy.with_model_effort()` uses `model_copy(update=...)`, which bypasses Pydantic validation and can return an invalid `ProviderPolicy` instance. Concrete failure: `.venv/bin/python - <<'PY'` with `ProviderPolicy().with_model_effort('bogus')` succeeds and stores `model.effort='bogus'`, so later phases can fingerprint, merge, and emit malformed policy objects without any immediate error. Minimal fix: route convenience helpers back through `ModelPolicy.model_validate(...)` / `ProviderPolicy.model_validate(...)` or centralize them through `merge_provider_policies()` so every public helper returns a validated policy object.

- IMP-002 `blocking` — [autoloop/core/provider_policy.py:164-184, 637-734] the requested `WorkspaceNetworkPolicy(mode='limited')` invariant is not enforced. Concrete failure: `WorkspaceNetworkPolicy(mode='limited')` and a full `ProviderPolicy(...network=WorkspaceNetworkPolicy(mode='limited'))` both validate with an empty `allow_domains`, and `validate_against_strict_policy(...)` still accepts that policy, even though the request explicitly requires limited mode to have at least one allowed domain unless an explicit strict-policy escape hatch exists. Minimal fix: centralize this check either in `WorkspaceNetworkPolicy` validation or in `validate_against_strict_policy()`, and add focused unit coverage for the empty-limited-mode reject path.

## Re-review

Cycle 2 re-review: `IMP-001` and `IMP-002` are resolved in the current implementation. No additional blocking or non-blocking findings were identified within the `policy-core` phase scope.
