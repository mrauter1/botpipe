# Implement ↔ Code Reviewer Feedback

- Task ID: spec-flat-enum-backed-policy-and-policyoverride-2b5811aa
- Pair: implement
- Phase ID: flat-policy-facade
- Phase Directory Key: flat-policy-facade
- Phase Title: Implement Flat Policy Facade
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` [autoloop/simple.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/simple.py:264), [tests/unit/test_simple_policy.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_simple_policy.py:201): the facade silently rewrites `sandbox_mode=SandboxMode.DANGER_FULL_ACCESS` with no explicit `permission_mode` to `permissions.mode='ask'`. That contradicts the requested contract that dangerous sandbox access should preserve the existing/default permission mode unless the caller explicitly overrides it, and it makes `PolicyOverride(sandbox_mode=SandboxMode.DANGER_FULL_ACCESS)` non-sparse by stomping any outer permission mode to `ask` during merge. Concrete failure: a workflow or step override that only asks for dangerous sandbox mode will now unexpectedly downgrade an outer `auto_edit` or other permission mode to `ask`, even though the author never requested a permission-mode change. Minimal fix direction: remove the implicit `PermissionMode.ASK` rewrite from the shared lowering helper and either (a) implement a lowering strategy that preserves the existing permission mode while still satisfying the unchanged core validator, or (b) stop and request clarification instead of silently inventing a new permission mode. The tests should also assert the requested dangerous-manual-access semantics once the behavior is corrected.
