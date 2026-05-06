# Implement ↔ Code Reviewer Feedback

- Task ID: implementation-goal-add-a-first-class-provider-p-5e755cae
- Pair: implement
- Phase ID: policy-codex
- Phase Directory Key: policy-codex
- Phase Title: Codex Emission
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 | blocking | [autoloop/runtime/providers/codex_policy.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/runtime/providers/codex_policy.py:117)
  `CodexPolicyEmitter.emit()` records `effective_enforcement.read_roots=policy.sandbox.workspace.filesystem.allow_read` even when the same emitter classifies narrowed `allow_read` as an `unsafe_expansion` because Codex cannot enforce that restriction. In a run requesting `allow_read=["./src"]`, the generated capability report can simultaneously say the mapping is unsafe and still claim the effective enforced read roots are `["./src"]`. That overstates actual Codex enforcement and makes the target-scoped capability report unsafe to trust for operator review or downstream policy tooling. Minimal fix: have the Codex report expose only roots that Codex really enforces, or leave `read_roots` empty/unknown when narrowing cannot be enforced, while keeping the unsafe/lossy marker for the requested restriction.
