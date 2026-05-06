# Implement ↔ Code Reviewer Feedback

- Task ID: implementation-goal-add-a-first-class-provider-p-5e755cae
- Pair: implement
- Phase ID: policy-config-authoring
- Phase Directory Key: policy-config-authoring
- Phase Title: Config And Authoring
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 `blocking` — [autoloop/runtime/config.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/runtime/config.py): `ProviderPolicyRuntimeConfigOverride` makes both `default` and `validation` optional, so `provider_policy.default: null` and `provider_policy.validation: null` are accepted silently instead of failing fast. That weakens the strict runtime-config validation this phase was supposed to preserve and can cause an operator typo to fall back to system defaults or default validation modes without any error. Minimal fix: keep omission optional for merge-layer purposes, but reject explicit `None` for `default` and `validation` at parse time or with field validators while still allowing `strict: null`.

- IMP-002 `blocking` — [autoloop/simple.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/simple.py), [autoloop/core/__init__.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/__init__.py), [autoloop/core/discovery.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/discovery.py): workflow-level `policy` is only a raw class attribute and is never retained in discovered authoring metadata. A workflow author can declare `policy = ProviderPolicy(...)`, but `get_workflow_definition()` and downstream compile/runtime seams cannot observe it, so the requested workflow-level authoring feature is incomplete in the actual pipeline. Minimal fix: persist workflow policy on `WorkflowDefinition` or another canonical workflow-metadata seam now, and validate the authored type there so later compiler/runtime phases consume one source of truth.

## Follow-up Review

- No new findings in this pass.
- IMP-001 verified fixed: explicit `provider_policy.default: null` and `provider_policy.validation: null` now fail at parse time, while `strict: null` remains allowed.
- IMP-002 verified fixed: workflow-level `policy` is now retained on `WorkflowDefinition.workflow_policy`, validated as a concrete `ProviderPolicy`, and preserved through the internal compiler reconstruction seam.
