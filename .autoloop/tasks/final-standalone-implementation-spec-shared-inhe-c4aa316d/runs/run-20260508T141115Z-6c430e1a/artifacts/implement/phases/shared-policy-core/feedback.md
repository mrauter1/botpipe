# Implement ↔ Code Reviewer Feedback

- Task ID: final-standalone-implementation-spec-shared-inhe-c4aa316d
- Pair: implement
- Phase ID: shared-policy-core
- Phase Directory Key: shared-policy-core
- Phase Title: Shared Policy Core
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` — [autoloop/policy.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/policy.py): `Policy(sandbox_mode=SandboxMode.DANGER_FULL_ACCESS).resolve()` still fails against the default base policy with `permissions.mode='full_auto_sandboxed' is incompatible with sandbox.mode='danger_full_access'`. This breaks the spec’s dangerous-manual workflow example and the explicit dangerous-access acceptance for `Policy(sandbox_mode=SandboxMode.DANGER_FULL_ACCESS)`. Minimal fix: centralize the dangerous-manual resolution rule in `autoloop.policy` so a public dangerous sandbox layer resolves to a compatible non-full-auto permission state when no explicit `permission_mode` is supplied, then add direct coverage for `Policy(sandbox_mode=SandboxMode.DANGER_FULL_ACCESS).resolve()` and the dangerous manual workflow compile/resolve path.

- IMP-002 `blocking` — [autoloop/simple.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/simple.py): the internal core compatibility type is still publicly importable as `autoloop.simple.ProviderPolicyOverride` because it remains bound in the module globals. That contradicts the phase requirement that `ProviderPolicyOverride` remain internal/core compatibility only and leaves a public authoring-module escape hatch to the old override surface. Minimal fix: stop exporting the core override type through `autoloop.simple` by renaming the import to a private alias (or localizing the runtime type checks), and add an explicit regression test that `from autoloop.simple import ProviderPolicyOverride` fails.

- Review pass `cycle-2`: no remaining blocking or non-blocking findings in phase-local scope. Verified that `Policy(sandbox_mode=SandboxMode.DANGER_FULL_ACCESS).resolve()` now produces a valid dangerous-manual policy (`permissions.mode == "ask"`, `allow_dangerous_bypass is True`, `sandbox.mode == "danger_full_access"`), and verified that `from autoloop.simple import ProviderPolicyOverride` now fails while internal `ProviderPolicyOverride` compatibility remains covered by tests.
