# Implement ↔ Code Reviewer Feedback

- Task ID: implementation-goal-add-a-first-class-provider-p-5e755cae
- Pair: implement
- Phase ID: policy-resolution-propagation
- Phase Directory Key: policy-resolution-propagation
- Phase Title: Resolution And Propagation
- Scope: phase-local authoritative verifier artifact

- IMP-001 | blocking | `autoloop/core/engine_collaborators.py:_step_uses_provider_policy`, `OperationRecorder.bind_step`
  `workflow_step(..., policy=...)` never gets its step policy bound, because `_step_uses_provider_policy()` excludes `step.kind == "workflow"`. Inline `llm()/classify()` calls from workflow-step hooks therefore resolve against only the workflow/config defaults, or worse, against a stale prior step policy left on the context, instead of the authored workflow-step override. Verified with a short-circuited `workflow_step` whose `before` hook calls `simple.llm(...)`: the provider call received `full_auto_sandboxed` from the workflow default instead of the step's `ask` override. Minimal fix: centralize step-policy binding in `OperationRecorder.bind_step` for every step kind that can execute provider-backed hooks or inline operations, at minimum including `workflow`, and clear/rebind the context-owned policy per step instead of relying on a narrow whitelist.

- IMP-002 | blocking | `autoloop/core/engine.py`, `autoloop/core/engine_collaborators.py`, `autoloop/runtime/provider_policy_resolver.py`
  Authored workflow/step policies are inert for direct `Engine(...)` callers unless they manually construct and pass a `ProviderPolicyResolver`, which is an internal runtime type not surfaced by the public engine API. Verified with a minimal direct-engine run: `Engine(W, ...)` on a workflow declaring `policy = ProviderPolicy(permissions=PermissionPolicy(mode="ask"))` produced a provider call with `policy is None`. That breaks the "first-class workflow code policy" contract for a major execution entrypoint and silently skips policy propagation, strict validation, and replay fingerprint participation for non-runner callers. Minimal fix: make `Engine` synthesize a default resolver when none is provided, using system defaults plus the compiled workflow policy and a minimal runtime config/workspace root, or factor a shared resolver-construction helper so both `Engine` and the filesystem runner honor authored policies consistently.
